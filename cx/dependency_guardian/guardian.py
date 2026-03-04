"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1

DependencyGuardian - AI-powered dependency conflict prediction engine for CX Linux.
Part of the Enterprise System Health suite.
"""

import os
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger("cx.dependency_guardian")

class ConflictReport(BaseModel):
    """
    Pydantic V2 Model for dependency conflict reports.
    Provides automated validation and serialization for enterprise audit trails.
    """
    target: str
    predicted_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    status: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DependencyGuardian:
    """
    Predicts package conflicts before installation by analyzing the system state
    and dependency graphs. Supports direct and virtual package conflicts.
    
    SECURITY: Hardened for enterprise environments with strict input validation.
    """
    # Regex allow-list for package names to prevent injection attacks (e.g., $(), ``, ;)
    _PKG_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?$", re.IGNORECASE)
    _APT_CACHE_BIN = "/usr/bin/apt-cache"

    def __init__(self, status_path: str = "/var/lib/dpkg/status"):
        self.status_path = status_path
        self.installed_packages: Dict[str, Any] = {}
        self.virtual_providers: Dict[str, List[str]] = {}

    async def initialize(self) -> None:
        """
        Asynchronously initializes the system state.
        This must be called before simulation to avoid false negatives.
        """
        logger.info("AUDIT: Starting system state initialization from %s", self.status_path)
        await self._load_system_state_async()
        logger.info("AUDIT: System state initialized (Packages: %d, Providers: %d)", 
                    len(self.installed_packages), len(self.virtual_providers))

    async def _load_system_state_async(self) -> None:
        """
        Parses the local dpkg status file using non-blocking I/O.
        Handles multi-line continuation fields correctly for high-fidelity parsing.
        """
        if not os.path.exists(self.status_path):
            logger.error("AUDIT: System status file missing at %s. Simulation impossible.", self.status_path)
            # Surfacing as an error state is critical to prevent false 'SAFE' reports
            return

        current_package = None
        last_field = None
        
        try:
            async with aiofiles.open(self.status_path, mode='r', encoding='utf-8') as f:
                async for raw_line in f:
                    line = raw_line.rstrip('\n')

                    # Blank line indicates end of current package stanza
                    if line.strip() == "":
                        current_package = None
                        last_field = None
                        continue

                    # New package stanza
                    if line.startswith("Package: "):
                        current_package = line.split(": ", 1)[1]
                        self.installed_packages[current_package] = {"Depends": [], "Conflicts": [], "Provides": []}
                        last_field = None
                        continue

                    if not current_package:
                        continue

                    # Parse direct fields
                    if line.startswith("Depends: "):
                        deps_part = line.split(": ", 1)[1]
                        deps = [d.strip().split(' ')[0] for d in deps_part.split(",") if d.strip()]
                        self.installed_packages[current_package]["Depends"] = deps
                        last_field = "Depends"
                    elif line.startswith("Conflicts: "):
                        conflicts_part = line.split(": ", 1)[1]
                        conflicts = [c.strip().split(' ')[0] for c in conflicts_part.split(",") if c.strip()]
                        self.installed_packages[current_package]["Conflicts"] = conflicts
                        last_field = "Conflicts"
                    elif line.startswith("Provides: "):
                        provides_part = line.split(": ", 1)[1]
                        v_pkgs = [p.strip().split(' ')[0] for p in provides_part.split(",") if p.strip()]
                        self.installed_packages[current_package]["Provides"] = v_pkgs
                        last_field = "Provides"
                        for vp in v_pkgs:
                            if vp not in self.virtual_providers:
                                self.virtual_providers[vp] = []
                            self.virtual_providers[vp].append(current_package)
                    
                    # Handle continuation lines for multi-line fields (Debian standard)
                    elif line and line[0].isspace() and last_field in ("Depends", "Conflicts", "Provides"):
                        cont_part = line.lstrip()
                        items = [x.strip().split(' ')[0] for x in cont_part.split(",") if x.strip()]
                        if items:
                            if last_field == "Depends":
                                self.installed_packages[current_package]["Depends"].extend(items)
                            elif last_field == "Conflicts":
                                self.installed_packages[current_package]["Conflicts"].extend(items)
                            elif last_field == "Provides":
                                self.installed_packages[current_package]["Provides"].extend(items)
                                for vp in items:
                                    if vp not in self.virtual_providers:
                                        self.virtual_providers[vp] = []
                                    self.virtual_providers[vp].append(current_package)
                                    
        except (OSError, UnicodeDecodeError, IndexError, ValueError):
            logger.exception("AUDIT: Fatal parsing error for system state at %s", self.status_path)

    async def simulate_install(self, target_package: str) -> Optional[ConflictReport]:
        """
        Asynchronously simulates package installation by querying apt-cache.
        SECURITY: Validates package name and uses argument boundary protection.
        """
        # Validate user-supplied package name (Anti-Injection)
        if not self._PKG_NAME_RE.fullmatch(target_package):
            logger.warning("AUDIT: Rejected invalid package identifier for simulation: %s", target_package)
            return None

        logger.info("AUDIT: Simulating installation for '%s'", target_package)

        try:
            # SECURITY: Use absolute path, argument separator (--), and timeout
            proc = await asyncio.create_subprocess_exec(
                self._APT_CACHE_BIN, "depends", "--", target_package,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            except asyncio.TimeoutExpired:
                proc.kill()
                logger.error("AUDIT: Simulation for '%s' timed out after 15s.", target_package)
                return None

            if proc.returncode != 0:
                logger.warning("AUDIT: apt-cache failed for '%s' (Exit: %d, Stderr: %s)", 
                               target_package, proc.returncode, stderr.decode().strip())
                return None

            output = stdout.decode().split('\n')
        except FileNotFoundError:
            logger.error("AUDIT: Crucial binary %s missing. Simulation aborted.", self._APT_CACHE_BIN)
            return None
        except Exception:
            logger.exception("AUDIT: Unexpected failure during simulation for '%s'", target_package)
            return None

        incoming_deps = []
        incoming_conflicts = []

        # High-fidelity parsing for apt-cache output (handles alternates and virtuals)
        for line in output:
            stripped = line.strip()
            if stripped.startswith("Depends:") or stripped.startswith("|Depends:"):
                dep_part = stripped.split("Depends:", 1)[1].strip()
                for alt in dep_part.split("|"):
                    alt = alt.strip()
                    if alt:
                        pkg = alt.split(" ")[0].replace("<", "").replace(">", "")
                        incoming_deps.append(pkg)
            elif stripped.startswith("Conflicts:") or stripped.startswith("|Conflicts:"):
                conf_part = stripped.split("Conflicts:", 1)[1].strip()
                for alt in conf_part.split("|"):
                    alt = alt.strip()
                    if alt:
                        pkg = alt.split(" ")[0].replace("<", "").replace(">", "")
                        incoming_conflicts.append(pkg)

        report = self._analyze_conflicts(target_package, incoming_deps, incoming_conflicts)
        logger.info("AUDIT: Simulation result for '%s': %s (Conflicts: %d)", 
                    target_package, report.status, len(report.predicted_conflicts))
        return report

    def _analyze_conflicts(self, target: str, incoming_deps: List[str], incoming_conflicts: List[str]) -> ConflictReport:
        """Performs graph analysis against the pre-loaded system state."""
        conflicts = []

        # 1. Direct and Virtual conflict checks
        for conflict in incoming_conflicts:
            if conflict in self.installed_packages:
                conflicts.append({
                    "type": "DIRECT_CONFLICT",
                    "reason": f"Target '{target}' explicitly conflicts with installed '{conflict}'"
                })
            elif conflict in self.virtual_providers:
                for provider in self.virtual_providers[conflict]:
                    conflicts.append({
                        "type": "VIRTUAL_CONFLICT",
                        "provider": provider,
                        "virtual": conflict,
                        "reason": f"Target '{target}' conflicts with virtual capability '{conflict}' provided by '{provider}'"
                    })

        # 2. Reverse dependency conflict checks
        for dep in incoming_deps:
            for inst_pkg, info in self.installed_packages.items():
                if dep in info["Conflicts"]:
                    conflicts.append({
                        "type": "REVERSE_CONFLICT",
                        "aggressor": inst_pkg,
                        "dependency": dep,
                        "reason": f"Installed package '{inst_pkg}' is configured to conflict with required dependency '{dep}'"
                    })

        status = "CONFLICT_DETECTED" if conflicts else "SAFE"
        # If no system state was loaded (e.g., missing file), we should be UNKNOWN rather than SAFE
        if not self.installed_packages:
            status = "UNKNOWN_STATE"

        return ConflictReport(target=target, predicted_conflicts=conflicts, status=status)
