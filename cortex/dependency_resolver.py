#!/usr/bin/env python3
"""
Dependency Resolution System
Detects and resolves package dependencies using AI assistance
"""

import subprocess
import json
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Dependency:
    """Represents a package dependency"""
    name: str
    version: Optional[str] = None
    reason: str = ""  # Why this dependency is needed
    is_satisfied: bool = False
    installed_version: Optional[str] = None


@dataclass
class DependencyGraph:
    """Complete dependency graph for a package"""
    package_name: str
    direct_dependencies: List[Dependency]
    all_dependencies: List[Dependency]
    conflicts: List[Tuple[str, str]]  # (package1, package2)
    installation_order: List[str]


class DependencyResolver:
    """Resolves package dependencies intelligently"""
    
    # Common dependency patterns
    DEPENDENCY_PATTERNS = {
        'docker': {
            'direct': ['containerd', 'docker-ce-cli', 'docker-buildx-plugin'],
            'system': ['iptables', 'ca-certificates', 'curl', 'gnupg']
        },
        'postgresql': {
            'direct': ['postgresql-common', 'postgresql-client'],
            'optional': ['postgresql-contrib']
        },
        'nginx': {
            'direct': [],
            'runtime': ['libc6', 'libpcre3', 'zlib1g']
        },
        'mysql-server': {
            'direct': ['mysql-client', 'mysql-common'],
            'system': ['libaio1', 'libmecab2']
        },
        'python3-pip': {
            'direct': ['python3', 'python3-setuptools'],
            'system': ['python3-wheel']
        },
        'nodejs': {
            'direct': [],
            'optional': ['npm']
        },
        'redis-server': {
            'direct': [],
            'runtime': ['libc6', 'libjemalloc2']
        },
        'apache2': {
            'direct': ['apache2-bin', 'apache2-data', 'apache2-utils'],
            'runtime': ['libapr1', 'libaprutil1']
        }
    }
    
    def __init__(self):
        self.dependency_cache: Dict[str, DependencyGraph] = {}
        self.installed_packages: Set[str] = set()
        self._refresh_installed_packages()
    
    def _run_command(self, cmd: List[str]) -> Tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))
    
    def _refresh_installed_packages(self) -> None:
        """Refresh cache of installed packages"""
        logger.info("Refreshing installed packages cache...")
        success, stdout, _ = self._run_command(['dpkg', '-l'])
        
        if success:
            for line in stdout.split('\n'):
                if line.startswith('ii'):
                    parts = line.split()
                    if len(parts) >= 2:
                        self.installed_packages.add(parts[1])
        
        logger.info(f"Found {len(self.installed_packages)} installed packages")
    
    def is_package_installed(self, package_name: str) -> bool:
        """Check if package is installed"""
        return package_name in self.installed_packages
    
    def get_installed_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package"""
        if not self.is_package_installed(package_name):
            return None
        
        success, stdout, _ = self._run_command([
            'dpkg-query', '-W', '-f=${Version}', package_name
        ])
        
        return stdout.strip() if success else None
    
    def get_apt_dependencies(self, package_name: str) -> List[Dependency]:
        """Get dependencies from apt-cache"""
        dependencies = []
        
        success, stdout, stderr = self._run_command([
            'apt-cache', 'depends', package_name
        ])
        
        if not success:
            logger.warning(f"Could not get dependencies for {package_name}: {stderr}")
            return dependencies
        
        current_dep_name = None
        for line in stdout.split('\n'):
            line = line.strip()
            
            # Parse dependency lines
            if line.startswith('Depends:'):
                current_dep_name = line.split(':', 1)[1].strip()
                # Handle alternatives (package1 | package2)
                if '|' in current_dep_name:
                    current_dep_name = current_dep_name.split('|')[0].strip()
                
                # Remove version constraints
                current_dep_name = re.sub(r'\s*\(.*?\)', '', current_dep_name)
                
                is_installed = self.is_package_installed(current_dep_name)
                installed_ver = self.get_installed_version(current_dep_name) if is_installed else None
                
                dependencies.append(Dependency(
                    name=current_dep_name,
                    reason="Required dependency",
                    is_satisfied=is_installed,
                    installed_version=installed_ver
                ))
            
            elif line.startswith('Recommends:'):
                dep_name = line.split(':', 1)[1].strip()
                dep_name = re.sub(r'\s*\(.*?\)', '', dep_name)
                
                dependencies.append(Dependency(
                    name=dep_name,
                    reason="Recommended package",
                    is_satisfied=self.is_package_installed(dep_name)
                ))
        
        return dependencies
    
    def get_predefined_dependencies(self, package_name: str) -> List[Dependency]:
        """Get dependencies from predefined patterns"""
        dependencies = []
        
        if package_name not in self.DEPENDENCY_PATTERNS:
            return dependencies
        
        pattern = self.DEPENDENCY_PATTERNS[package_name]
        
        # Direct dependencies
        for dep in pattern.get('direct', []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(Dependency(
                name=dep,
                reason="Required dependency",
                is_satisfied=is_installed,
                installed_version=self.get_installed_version(dep) if is_installed else None
            ))
        
        # System dependencies
        for dep in pattern.get('system', []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(Dependency(
                name=dep,
                reason="System dependency",
                is_satisfied=is_installed,
                installed_version=self.get_installed_version(dep) if is_installed else None
            ))
        
        # Optional dependencies
        for dep in pattern.get('optional', []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(Dependency(
                name=dep,
                reason="Optional enhancement",
                is_satisfied=is_installed
            ))
        
        return dependencies
    
    def resolve_dependencies(
        self,
        package_name: str,
        recursive: bool = True
    ) -> DependencyGraph:
        """
        Resolve all dependencies for a package
        
        Args:
            package_name: Package to resolve dependencies for
            recursive: Whether to resolve transitive dependencies
        """
        logger.info(f"Resolving dependencies for {package_name}...")
        
        # Check cache
        if package_name in self.dependency_cache:
            logger.info(f"Using cached dependencies for {package_name}")
            return self.dependency_cache[package_name]
        
        # Get dependencies from multiple sources
        apt_deps = self.get_apt_dependencies(package_name)
        predefined_deps = self.get_predefined_dependencies(package_name)
        
        # Merge dependencies (prefer predefined for known packages)
        all_deps: Dict[str, Dependency] = {}
        
        for dep in predefined_deps + apt_deps:
            if dep.name not in all_deps:
                all_deps[dep.name] = dep
        
        direct_dependencies = list(all_deps.values())
        
        # Resolve transitive dependencies if recursive
        transitive_deps: Dict[str, Dependency] = {}
        if recursive:
            for dep in direct_dependencies:
                if not dep.is_satisfied:
                    # Get dependencies of this dependency
                    sub_deps = self.get_apt_dependencies(dep.name)
                    for sub_dep in sub_deps:
                        if sub_dep.name not in all_deps and sub_dep.name not in transitive_deps:
                            transitive_deps[sub_dep.name] = sub_dep
        
        all_dependencies = list(all_deps.values()) + list(transitive_deps.values())
        
        # Detect conflicts
        conflicts = self._detect_conflicts(all_dependencies)
        
        # Calculate installation order
        installation_order = self._calculate_installation_order(
            package_name,
            all_dependencies
        )
        
        graph = DependencyGraph(
            package_name=package_name,
            direct_dependencies=direct_dependencies,
            all_dependencies=all_dependencies,
            conflicts=conflicts,
            installation_order=installation_order
        )
        
        # Cache result
        self.dependency_cache[package_name] = graph
        
        return graph
    
    def _detect_conflicts(self, dependencies: List[Dependency]) -> List[Tuple[str, str]]:
        """Detect conflicting packages"""
        conflicts = []
        
        # Check for known conflicts
        conflict_patterns = {
            'mysql-server': ['mariadb-server'],
            'mariadb-server': ['mysql-server'],
            'apache2': ['nginx'],  # Can coexist but conflict on port 80
            'nginx': ['apache2']
        }
        
        dep_names = {dep.name for dep in dependencies}
        
        for dep_name in dep_names:
            if dep_name in conflict_patterns:
                for conflicting in conflict_patterns[dep_name]:
                    if conflicting in dep_names or self.is_package_installed(conflicting):
                        conflicts.append((dep_name, conflicting))
        
        return conflicts
    
    def _calculate_installation_order(
        self,
        package_name: str,
        dependencies: List[Dependency]
    ) -> List[str]:
        """Calculate optimal installation order"""
        # Simple topological sort based on dependency levels
        
        # Packages with no dependencies first
        no_deps = []
        has_deps = []
        
        for dep in dependencies:
            if not dep.is_satisfied:
                # Simple heuristic: system packages first, then others
                if 'lib' in dep.name or dep.name in ['ca-certificates', 'curl', 'gnupg']:
                    no_deps.append(dep.name)
                else:
                    has_deps.append(dep.name)
        
        # Build installation order
        order = no_deps + has_deps
        
        # Add main package last
        if package_name not in order:
            order.append(package_name)
        
        return order
    
    def get_missing_dependencies(self, package_name: str) -> List[Dependency]:
        """Get list of dependencies that need to be installed"""
        graph = self.resolve_dependencies(package_name)
        return [dep for dep in graph.all_dependencies if not dep.is_satisfied]
    
    def generate_install_plan(self, package_name: str) -> Dict:
        """Generate complete installation plan"""
        graph = self.resolve_dependencies(package_name)
        missing = self.get_missing_dependencies(package_name)
        
        plan = {
            'package': package_name,
            'total_dependencies': len(graph.all_dependencies),
            'missing_dependencies': len(missing),
            'satisfied_dependencies': len(graph.all_dependencies) - len(missing),
            'conflicts': graph.conflicts,
            'installation_order': graph.installation_order,
            'install_commands': self._generate_install_commands(graph.installation_order),
            'estimated_time_minutes': len(missing) * 0.5  # Rough estimate
        }
        
        return plan
    
    def _generate_install_commands(self, packages: List[str]) -> List[str]:
        """Generate apt install commands"""
        commands = []
        
        # Update package list first
        commands.append("sudo apt-get update")
        
        # Install in order
        for package in packages:
            if not self.is_package_installed(package):
                commands.append(f"sudo apt-get install -y {package}")
        
        return commands
    
    def print_dependency_tree(self, package_name: str, indent: int = 0) -> None:
        """Print dependency tree"""
        graph = self.resolve_dependencies(package_name, recursive=False)
        
        prefix = "  " * indent
        status = "✅" if self.is_package_installed(package_name) else "❌"
        print(f"{prefix}{status} {package_name}")
        
        for dep in graph.direct_dependencies:
            dep_prefix = "  " * (indent + 1)
            dep_status = "✅" if dep.is_satisfied else "❌"
            version_str = f" ({dep.installed_version})" if dep.installed_version else ""
            print(f"{dep_prefix}{dep_status} {dep.name}{version_str} - {dep.reason}")
    
    def export_graph_json(self, package_name: str, filepath: str) -> None:
        """Export dependency graph to JSON"""
        graph = self.resolve_dependencies(package_name)
        
        graph_dict = {
            'package_name': graph.package_name,
            'direct_dependencies': [asdict(dep) for dep in graph.direct_dependencies],
            'all_dependencies': [asdict(dep) for dep in graph.all_dependencies],
            'conflicts': graph.conflicts,
            'installation_order': graph.installation_order
        }
        
        with open(filepath, 'w') as f:
            json.dump(graph_dict, f, indent=2)
        
        logger.info(f"Dependency graph exported to {filepath}")


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Resolve package dependencies"
    )
    parser.add_argument(
        'package',
        help='Package name to analyze'
    )
    parser.add_argument(
        '--tree',
        action='store_true',
        help='Show dependency tree'
    )
    parser.add_argument(
        '--plan',
        action='store_true',
        help='Generate installation plan'
    )
    parser.add_argument(
        '--export',
        help='Export dependency graph to JSON file'
    )
    parser.add_argument(
        '--missing',
        action='store_true',
        help='Show only missing dependencies'
    )
    
    args = parser.parse_args()
    
    resolver = DependencyResolver()
    
    if args.tree:
        print(f"\n📦 Dependency tree for {args.package}:")
        print("=" * 60)
        resolver.print_dependency_tree(args.package)
    
    if args.plan:
        print(f"\n📋 Installation plan for {args.package}:")
        print("=" * 60)
        plan = resolver.generate_install_plan(args.package)
        
        print(f"\nPackage: {plan['package']}")
        print(f"Total dependencies: {plan['total_dependencies']}")
        print(f"✅ Already satisfied: {plan['satisfied_dependencies']}")
        print(f"❌ Need to install: {plan['missing_dependencies']}")
        
        if plan['conflicts']:
            print(f"\n⚠️  Conflicts detected:")
            for pkg1, pkg2 in plan['conflicts']:
                print(f"   - {pkg1} conflicts with {pkg2}")
        
        print(f"\n📝 Installation order:")
        for i, pkg in enumerate(plan['installation_order'], 1):
            status = "✅" if resolver.is_package_installed(pkg) else "❌"
            print(f"   {i}. {status} {pkg}")
        
        print(f"\n⏱️  Estimated time: {plan['estimated_time_minutes']:.1f} minutes")
        
        print(f"\n💻 Commands to run:")
        for cmd in plan['install_commands']:
            print(f"   {cmd}")
    
    if args.missing:
        print(f"\n❌ Missing dependencies for {args.package}:")
        print("=" * 60)
        missing = resolver.get_missing_dependencies(args.package)
        
        if missing:
            for dep in missing:
                print(f"  - {dep.name}: {dep.reason}")
        else:
            print("  All dependencies satisfied!")
    
    if args.export:
        resolver.export_graph_json(args.package, args.export)
    
    # Default: show summary
    if not any([args.tree, args.plan, args.missing, args.export]):
        graph = resolver.resolve_dependencies(args.package)
        print(f"\n📦 {args.package} - Dependency Summary")
        print("=" * 60)
        print(f"Direct dependencies: {len(graph.direct_dependencies)}")
        print(f"Total dependencies: {len(graph.all_dependencies)}")
        satisfied = sum(1 for d in graph.all_dependencies if d.is_satisfied)
        print(f"✅ Satisfied: {satisfied}")
        print(f"❌ Missing: {len(graph.all_dependencies) - satisfied}")
