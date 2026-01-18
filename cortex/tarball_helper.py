"""
tarball_helper.py - Tarball/Manual Build Helper for Cortex Linux

Features:
1. Analyze build files (configure, CMakeLists.txt, meson.build, etc.) for requirements
2. Install missing -dev packages automatically
3. Track manual installations for cleanup
4. Suggest package alternatives when available

Usage:
  cortex tarball-helper analyze <path>
  cortex tarball-helper install-deps <path>
  cortex tarball-helper track <package>
  cortex tarball-helper cleanup
"""

import json
import os
import re
from pathlib import Path

from rich.console import Console
from rich.table import Table

MANUAL_TRACK_FILE = Path.home() / ".cortex" / "manual_builds.json"
console = Console()


class TarballHelper:
    def __init__(self):
        self.tracked_packages = self._load_tracked_packages()

    def suggest_apt_packages(self, deps: list[str]) -> dict[str, str]:
        """Map dependency names to apt packages (simple heuristic)."""
        mapping = {}
        for dep in deps:
            dep_lower = dep.lower()
            if dep_lower.startswith("lib"):
                pkg = f"{dep_lower}-dev"
            else:
                pkg = f"lib{dep_lower}-dev"
            mapping[dep] = pkg
        return mapping

    def install_deps(self, pkgs: list[str]) -> None:
        """Install missing -dev packages via apt. Only track successful installs."""
        import subprocess
        for pkg in pkgs:
            console.print(f"[cyan]Installing:[/cyan] {pkg}")
            result = subprocess.run(["sudo", "apt-get", "install", "-y", pkg], check=False)
            if result.returncode == 0:
                self.track(pkg)
            else:
                console.print(f"[red]Failed to install:[/red] {pkg} (exit code {result.returncode}). Package will not be tracked for cleanup.")

    def track(self, pkg: str) -> None:
        """Track a package for later cleanup."""
        if pkg not in self.tracked_packages:
            self.tracked_packages.append(pkg)
            self._save_tracked_packages()
            console.print(f"[green]Tracked:[/green] {pkg}")

    def _load_tracked_packages(self) -> list[str]:
        """Load tracked packages from file, handling corrupt JSON."""
        if MANUAL_TRACK_FILE.exists():
            try:
                with open(MANUAL_TRACK_FILE) as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                console.print(
                    f"[yellow]Warning:[/yellow] Failed to parse {MANUAL_TRACK_FILE}. Ignoring corrupt tracking data."
                )
                return []
            packages = data.get("packages", [])
            if not isinstance(packages, list):
                return []
            return packages
        return []

    def _save_tracked_packages(self):
        MANUAL_TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MANUAL_TRACK_FILE, "w") as f:
            json.dump({"packages": self.tracked_packages}, f, indent=2)

    def analyze(self, path: str) -> list[str]:
        """Analyze build files for dependencies."""
        deps = set()
        for root, _, files in os.walk(path):
            for fname in files:
                if fname in (
                    "CMakeLists.txt",
                    "configure.ac",
                    "meson.build",
                    "Makefile",
                    "setup.py",
                ):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, errors="ignore") as f:
                            content = f.read()
                    except Exception:
                        continue
                    if fname == "setup.py":
                        deps.update(self._parse_setup_py_dependencies(content))
                    else:
                        deps.update(self._parse_dependencies(fname, content))
        return list(deps)
    def _parse_dependencies(self, fname: str, content: str) -> list[str]:
        """Extract dependencies from build files using regex or delegate to setup.py parser."""
        if fname == "setup.py":
            return self._parse_setup_py_dependencies(content)
        patterns = {
            "CMakeLists.txt": r"find_package\(([-\w]+)",
            "meson.build": r"dependency\(['\"]([\w-]+)",
            "configure.ac": r"AC_CHECK_LIB\(\[?([\w-]+)",
            "Makefile": r"-l([\w-]+)",
        }
        deps = set()
        if fname in patterns:
            matches = re.findall(patterns[fname], content, re.DOTALL)
            deps.update(matches)
        return list(deps)

    def _parse_setup_py_dependencies(self, content: str) -> list[str]:
        """Robustly parse install_requires from setup.py using ast and regex fallback."""
        import ast
        deps = set()
        try:
            tree = ast.parse(content)
            # Look for install_requires in assignments and in setup() call
            for node in ast.walk(tree):
                # Top-level assignment
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "install_requires":
                            if isinstance(node.value, (ast.List, ast.Tuple)):
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Str):
                                        deps.add(elt.s)
                                    elif hasattr(ast, "Constant") and isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                        deps.add(elt.value)
                # install_requires in setup() call
                if isinstance(node, ast.Call) and hasattr(node.func, "id") and node.func.id == "setup":
                    for kw in node.keywords:
                        if kw.arg == "install_requires" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Str):
                                    deps.add(elt.s)
                                elif hasattr(ast, "Constant") and isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    deps.add(elt.value)
            if deps:
                return list(deps)
        except Exception:
            pass
        # fallback: try regex for install_requires in assignment or setup()
        # Robust regex: match install_requires in assignment or setup(), with arbitrary whitespace/newlines
        # Match install_requires assignments with any whitespace/newlines
        pattern = r"install_requires\s*=\s*\[(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)
        for m in matches:
            # Extract all quoted package names from the captured group
            deps.update(re.findall(r"['\"]([^'\"]+)['\"]", m, re.DOTALL))
        return list(deps)
    def cleanup(self) -> None:
        """Remove tracked packages using apt-get purge."""
        import subprocess
        if not self.tracked_packages:
            console.print("[yellow]No tracked packages to remove.[/yellow]")
            return
        for pkg in self.tracked_packages:
            console.print(f"[yellow]Purging:[/yellow] {pkg}")
            subprocess.run(["sudo", "apt-get", "purge", "-y", pkg], check=False)
        self.tracked_packages = []
        self._save_tracked_packages()
        console.print("[green]Cleanup complete.[/green]")
