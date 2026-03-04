"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1

DependencyGuardian - AI-powered dependency conflict prediction engine for CX Linux.
Part of the Enterprise System Health suite.
"""

import os
import subprocess
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("cx.dependency_guardian")

@dataclass
class ConflictReport:
    """Represents the result of a dependency conflict analysis."""
    target: str
    predicted_conflicts: List[Dict[str, Any]]
    status: str
    timestamp: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())

class DependencyGuardian:
    """
    Predicts package conflicts before installation.
    SECURITY: Operates in READ-ONLY mode on system status files.
    """
    def __init__(self, status_path: str = "/var/lib/dpkg/status"):
        self.status_path = status_path
        self.installed_packages: Dict[str, Any] = {}
        self.virtual_providers: Dict[str, List[str]] = {}
        self._load_system_state()

    def _load_system_state(self) -> None:
        """Parses the local dpkg status file. Uses secure read-only access."""
        if not os.path.exists(self.status_path):
            logger.error(f"System status file not found: {self.status_path}")
            return

        current_package = None
        try:
            # SECURITY: Explicitly opening in read-only mode
            with open(self.status_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Package: "):
                        current_package = line.split(": ")[1]
                        self.installed_packages[current_package] = {"Depends": [], "Conflicts": [], "Provides": []}
                    elif current_package:
                        if line.startswith("Depends: "):
                            self.installed_packages[current_package]["Depends"] = [d.strip().split(' ')[0] for d in line.split(": ")[1].split(",")]
                        elif line.startswith("Conflicts: "):
                            self.installed_packages[current_package]["Conflicts"] = [c.strip().split(' ')[0] for c in line.split(": ")[1].split(",")]
                        elif line.startswith("Provides: "):
                            v_pkgs = [p.strip().split(' ')[0] for p in line.split(": ")[1].split(",")]
                            self.installed_packages[current_package]["Provides"] = v_pkgs
                            for vp in v_pkgs:
                                if vp not in self.virtual_providers:
                                    self.virtual_providers[vp] = []
                                self.virtual_providers[vp].append(current_package)
        except Exception as e:
            logger.error(f"Failed to parse system state: {e}")

    async def simulate_install_async(self, target_package: str) -> Optional[ConflictReport]:
        """
        Asynchronous wrapper for simulation to prevent EventLoopErrors.
        """
        return await asyncio.to_thread(self.simulate_install, target_package)

    def simulate_install(self, target_package: str) -> Optional[ConflictReport]:
        """Simulates installation using apt-cache."""
        try:
            result = subprocess.run(["apt-cache", "depends", target_package], capture_output=True, text=True, check=True)
            output = result.stdout.split('\n')
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(f"Package '{target_package}' analysis failed.")
            return None

        incoming_deps = []
        incoming_conflicts = []

        for line in output:
            if line.startswith("  Depends:"):
                pkg = line.split("Depends:")[1].strip()
                incoming_deps.append(pkg.split(' ')[0].replace('<', '').replace('>', ''))
            elif line.startswith("  Conflicts:"):
                pkg = line.split("Conflicts:")[1].strip()
                incoming_conflicts.append(pkg.split(' ')[0].replace('<', '').replace('>', ''))

        return self._analyze_conflicts(target_package, incoming_deps, incoming_conflicts)

    def _analyze_conflicts(self, target: str, incoming_deps: List[str], incoming_conflicts: List[str]) -> ConflictReport:
        conflicts = []
        for conflict in incoming_conflicts:
            if conflict in self.installed_packages:
                conflicts.append({"type": "DIRECT_CONFLICT", "reason": f"Target '{target}' conflicts with installed '{conflict}'"})
            elif conflict in self.virtual_providers:
                for provider in self.virtual_providers[conflict]:
                    conflicts.append({"type": "VIRTUAL_CONFLICT", "provider": provider, "virtual": conflict, "reason": f"Target '{target}' conflicts with virtual '{conflict}' provided by '{provider}'"})
        
        status = "CONFLICT_DETECTED" if conflicts else "SAFE"
        return ConflictReport(target=target, predicted_conflicts=conflicts, status=status)
