# Dependency Resolution System

AI-powered dependency detection and resolution for Cortex Linux.

## Features

- ✅ Automatic dependency detection via apt-cache
- ✅ Predefined patterns for 8+ common packages
- ✅ Transitive dependency resolution
- ✅ Conflict detection
- ✅ Optimal installation order calculation
- ✅ Installation plan generation
- ✅ Dependency tree visualization
- ✅ JSON export for automation

## Usage

### Show Dependency Tree

```bash
python3 dependency_resolver.py docker --tree
```

Output:
```
📦 Dependency tree for docker:
============================================================
❌ docker
  ❌ containerd - Required dependency
  ❌ docker-ce-cli - Required dependency
  ❌ docker-buildx-plugin - Required dependency
  ✅ iptables (1.8.7-1) - System dependency
  ✅ ca-certificates (20230311) - System dependency
```

### Generate Installation Plan

```bash
python3 dependency_resolver.py postgresql --plan
```

Output:
```
📋 Installation plan for postgresql:
============================================================

Package: postgresql
Total dependencies: 5
✅ Already satisfied: 2
❌ Need to install: 3

📝 Installation order:
   1. ❌ postgresql-common
   2. ❌ postgresql-client
   3. ❌ postgresql

⏱️  Estimated time: 1.5 minutes

💻 Commands to run:
   sudo apt-get update
   sudo apt-get install -y postgresql-common
   sudo apt-get install -y postgresql-client
   sudo apt-get install -y postgresql
```

### Show Missing Dependencies Only

```bash
python3 dependency_resolver.py nginx --missing
```

### Export to JSON

```bash
python3 dependency_resolver.py redis-server --export redis-deps.json
```

## Programmatic Usage

```python
from dependency_resolver import DependencyResolver

resolver = DependencyResolver()

# Get dependency graph
graph = resolver.resolve_dependencies('docker')

print(f"Total dependencies: {len(graph.all_dependencies)}")
print(f"Installation order: {graph.installation_order}")

# Check for conflicts
if graph.conflicts:
    print("⚠️ Conflicts detected:")
    for pkg1, pkg2 in graph.conflicts:
        print(f"  {pkg1} <-> {pkg2}")

# Get missing dependencies
missing = resolver.get_missing_dependencies('docker')
for dep in missing:
    print(f"Need to install: {dep.name} ({dep.reason})")

# Generate installation plan
plan = resolver.generate_install_plan('nginx')
print(f"Estimated install time: {plan['estimated_time_minutes']} minutes")

# Execute installation commands
for cmd in plan['install_commands']:
    print(f"Run: {cmd}")
```

## Supported Packages

Predefined dependency patterns for:
- docker
- postgresql
- mysql-server
- nginx
- apache2
- nodejs
- redis-server
- python3-pip

For other packages, uses apt-cache dependency data.

## Architecture

### Dependency Class
Represents a single package dependency:
- `name`: Package name
- `version`: Required version (optional)
- `reason`: Why this dependency exists
- `is_satisfied`: Whether already installed
- `installed_version`: Current version if installed

### DependencyGraph Class
Complete dependency information:
- `package_name`: Target package
- `direct_dependencies`: Immediate dependencies
- `all_dependencies`: Including transitive deps
- `conflicts`: Conflicting packages
- `installation_order`: Optimal install sequence

### DependencyResolver Class
Main resolver with:
- **Dependency Detection**: Via apt-cache and predefined patterns
- **Conflict Detection**: Identifies incompatible packages
- **Installation Planning**: Generates optimal install sequence
- **Caching**: Speeds up repeated queries

## Conflict Detection

Detects known conflicts:
- mysql-server ↔ mariadb-server
- apache2 ↔ nginx (port conflicts)

Example:
```python
resolver = DependencyResolver()
graph = resolver.resolve_dependencies('mysql-server')

if graph.conflicts:
    print("Cannot install - conflicts detected!")
```

## Installation Order

Uses intelligent ordering:
1. System libraries (libc, libssl, etc.)
2. Base dependencies (ca-certificates, curl, etc.)
3. Package-specific dependencies
4. Target package

This minimizes installation failures.

## Integration with Cortex

```python
# In cortex install command
from dependency_resolver import DependencyResolver

resolver = DependencyResolver()

# Get installation plan
plan = resolver.generate_install_plan(package_name)

# Check for conflicts
if plan['conflicts']:
    raise InstallationError(f"Conflicts: {plan['conflicts']}")

# Execute in order
for package in plan['installation_order']:
    if not resolver.is_package_installed(package):
        install_package(package)
```

## Testing

```bash
python3 test_dependency_resolver.py
```

## Performance

- **Cache**: Dependency graphs are cached per session
- **Speed**: ~0.5s per package for apt-cache queries
- **Memory**: <50MB for typical dependency graphs

## Future Enhancements

- [ ] Support for pip/npm dependencies
- [ ] AI-powered dependency suggestions
- [ ] Version constraint resolution
- [ ] Automatic conflict resolution
- [ ] PPA repository detection
- [ ] Circular dependency detection
- [ ] Parallel installation planning

## Example: Complete Workflow

```python
from dependency_resolver import DependencyResolver
from installation_verifier import InstallationVerifier

# Step 1: Resolve dependencies
resolver = DependencyResolver()
plan = resolver.generate_install_plan('docker')

# Step 2: Check conflicts
if plan['conflicts']:
    print("⚠️ Resolve conflicts first")
    exit(1)

# Step 3: Install in order
for package in plan['installation_order']:
    if not resolver.is_package_installed(package):
        print(f"Installing {package}...")
        # execute: apt-get install package
        
# Step 4: Verify installation
verifier = InstallationVerifier()
result = verifier.verify_package('docker')

if result.status == VerificationStatus.SUCCESS:
    print("✅ Installation complete and verified!")
```

## License

MIT License - Part of Cortex Linux
