# Configuration Management for Cortex Linux

## Overview

Cortex Linux's Configuration Management feature enables you to export, share, and import system configurations for reproducibility and team collaboration. This feature is essential for:

- **Team Collaboration**: Share exact development environments with team members
- **Infrastructure as Code**: Version control your system configurations
- **Disaster Recovery**: Quickly restore systems to known-good states
- **Onboarding**: New team members can replicate production environments instantly
- **CI/CD**: Ensure consistent environments across development, staging, and production

## Installation

### Prerequisites

- Python 3.8 or higher
- Cortex Linux 0.2.0 or compatible version
- System package managers: apt, pip3, npm (depending on what you want to export/import)

### Dependencies

Install required Python dependencies:

```bash
pip3 install pyyaml>=6.0.1 packaging>=23.0
```

### System Requirements

- Ubuntu 24.04 LTS (or compatible Debian-based distribution)
- Sufficient disk space for configuration files
- Root/sudo access for package installation

## Usage

The Configuration Manager provides three main commands:

1. **export** - Export current system configuration
2. **import** - Import and apply configuration
3. **diff** - Compare current system with configuration file

### Exporting Configuration

#### Basic Export

Export your current system configuration:

```bash
python3 config_manager.py export --output my-config.yaml
```

This creates a YAML file containing:
- Cortex version
- OS version
- Installed packages (apt, pip, npm)
- User preferences
- Selected environment variables

#### Export with Hardware Information

Include hardware profile in the export:

```bash
python3 config_manager.py export --output dev-machine.yaml --include-hardware
```

Hardware information includes:
- CPU model and core count
- GPU details (NVIDIA, AMD, Intel)
- RAM size
- Storage devices
- Network interfaces

#### Export Packages Only

Export only package information (no preferences or hardware):

```bash
python3 config_manager.py export --output packages.yaml --packages-only
```

#### Export Without Preferences

Export everything except user preferences:

```bash
python3 config_manager.py export --output config.yaml --no-preferences
```

### Importing Configuration

#### Preview Changes (Dry-Run)

Preview what would change without applying anything:

```bash
python3 config_manager.py import dev-machine.yaml --dry-run
```

Output shows:
- Packages to install
- Packages to upgrade/downgrade
- Preferences that will change
- Warnings about compatibility

#### Apply Configuration

Import and apply the configuration:

```bash
python3 config_manager.py import dev-machine.yaml
```

This will:
1. Validate compatibility
2. Install missing packages
3. Upgrade outdated packages
4. Update user preferences

#### Force Import

Skip compatibility checks (use with caution):

```bash
python3 config_manager.py import dev-machine.yaml --force
```

#### Selective Import

Import only packages:

```bash
python3 config_manager.py import dev-machine.yaml --packages-only
```

Import only preferences:

```bash
python3 config_manager.py import dev-machine.yaml --preferences-only
```

### Comparing Configurations

Show differences between current system and configuration file:

```bash
python3 config_manager.py diff production-config.yaml
```

Output includes:
- Number of packages to install
- Number of packages to upgrade/downgrade
- Packages already installed
- Changed preferences
- Compatibility warnings

## Configuration File Format

Configuration files are in YAML format with the following structure:

```yaml
cortex_version: 0.2.0
exported_at: '2025-11-14T14:23:15.123456'
os: ubuntu-24.04

hardware:  # Optional
  cpu:
    model: AMD Ryzen 9 5950X
    cores: 16
    architecture: x86_64
  gpu:
    - vendor: NVIDIA
      model: RTX 4090
      vram: 24576
      cuda: '12.3'
  ram: 65536
  storage:
    - type: nvme
      size: 2097152
      device: nvme0n1
  network:
    interfaces:
      - name: eth0
        speed_mbps: 1000
    max_speed_mbps: 1000

packages:
  - name: docker
    version: 24.0.7-1
    source: apt
  - name: numpy
    version: 1.24.0
    source: pip
  - name: typescript
    version: 5.0.0
    source: npm

preferences:
  confirmations: minimal
  verbosity: normal

environment_variables:
  LANG: en_US.UTF-8
  SHELL: /bin/bash
```

### Field Descriptions

- **cortex_version**: Version of Cortex Linux that created this config
- **exported_at**: ISO timestamp of export
- **os**: Operating system identifier (e.g., ubuntu-24.04)
- **hardware**: Optional hardware profile from HardwareProfiler
- **packages**: List of installed packages with name, version, and source
- **preferences**: User preferences for Cortex behavior
- **environment_variables**: Selected environment variables (exported for reference only; not automatically restored during import)

### Package Sources

Supported package sources:

- **apt**: System packages via APT/dpkg
- **pip**: Python packages via pip/pip3
- **npm**: Node.js global packages via npm

## Integration with SandboxExecutor

For enhanced security, ConfigManager can integrate with SandboxExecutor to safely install packages:

```python
from config_manager import ConfigManager
from sandbox_executor import SandboxExecutor

# Create instances
executor = SandboxExecutor()
manager = ConfigManager(sandbox_executor=executor)

# All package installations will go through sandbox
manager.import_configuration('config.yaml')
```

Benefits:
- Commands are validated before execution
- Resource limits prevent runaway installations
- Audit logging of all operations
- Rollback capability on failures

## Best Practices

### Version Control Your Configs

Store configuration files in Git:

```bash
git add environments/
git commit -m "Add production environment config"
git push
```

### Use Meaningful Filenames

Name files descriptively:

```text
dev-machine-john.yaml
production-web-server.yaml
ml-training-gpu-rig.yaml
team-baseline-2024-11.yaml
```

### Always Test with Dry-Run First

Before applying any configuration:

```bash
# 1. Check differences
python3 config_manager.py diff config.yaml

# 2. Dry-run to see exactly what will happen
python3 config_manager.py import config.yaml --dry-run

# 3. Apply if everything looks good
python3 config_manager.py import config.yaml
```

### Regular Backups

Export your configuration regularly:

```bash
# Daily backup script
python3 config_manager.py export \
  --output "backups/config-$(date +%Y-%m-%d).yaml" \
  --include-hardware
```

### Team Onboarding Workflow

1. **Team Lead**: Export reference configuration
   ```bash
   python3 config_manager.py export --output team-baseline.yaml --include-hardware
   ```

2. **Share**: Commit to repository or share via secure channel

3. **New Member**: Preview then import
   ```bash
   python3 config_manager.py import team-baseline.yaml --dry-run
   python3 config_manager.py import team-baseline.yaml
   ```

### Environment-Specific Configs

Maintain separate configs for different environments:

```text
configs/
├── development.yaml
├── staging.yaml
└── production.yaml
```

### Selective Operations

Use selective import for fine-grained control:

```bash
# Update only packages, keep local preferences
python3 config_manager.py import prod.yaml --packages-only

# Update only preferences, keep packages
python3 config_manager.py import team-prefs.yaml --preferences-only
```

## Troubleshooting

### Compatibility Errors

**Problem**: "Incompatible configuration: Incompatible major version"

**Solution**: Configuration was created with a different major version of Cortex. Use `--force` to bypass (risky) or update Cortex version.

### OS Mismatch Warnings

**Problem**: "Warning: OS mismatch (config=ubuntu-24.04, current=ubuntu-22.04)"

**Solution**: Configuration may not work perfectly on different OS versions. Proceed with caution or update your OS.

### Package Installation Failures

**Problem**: Some packages fail to install

**Solution**:
1. Check network connectivity
2. Update package indexes: `sudo apt-get update`
3. Check for conflicting packages
4. Review failed packages in output and install manually if needed

### Permission Errors

**Problem**: "Permission denied" when installing packages

**Solution**: Run with appropriate privileges:
```bash
# Use sudo for system package installation
sudo python3 config_manager.py import config.yaml
```

### Missing Package Managers

**Problem**: npm or pip packages fail because manager not installed

**Solution**: Install missing package managers first:
```bash
sudo apt-get install npm python3-pip
```

### Large Package Lists

**Problem**: Import takes very long with many packages

**Solution**:
1. Use `--packages-only` to skip other operations
2. Consider splitting into smaller configs
3. Increase timeout if using SandboxExecutor

### YAML Syntax Errors

**Problem**: "Failed to load configuration file: YAML error"

**Solution**: Validate YAML syntax:
```bash
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

## Advanced Usage

### Programmatic API

Use ConfigManager in Python scripts:

```python
from config_manager import ConfigManager

manager = ConfigManager()

# Export
manager.export_configuration(
    output_path='config.yaml',
    include_hardware=True,
    package_sources=['apt', 'pip']
)

# Import with dry-run
result = manager.import_configuration(
    config_path='config.yaml',
    dry_run=True
)

# Check diff - load the config file first
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
diff = manager.diff_configuration(config)
print(f"To install: {len(diff['packages_to_install'])}")
```

### Custom Package Sources

Extend detection for additional package managers:

```python
class CustomConfigManager(ConfigManager):
    def detect_cargo_packages(self):
        # Implement Rust cargo package detection
        pass
    
    def detect_installed_packages(self, sources=None):
        packages = super().detect_installed_packages(sources)
        if 'cargo' in (sources or []):
            packages.extend(self.detect_cargo_packages())
        return packages
```

### Batch Operations

Process multiple configurations:

```bash
# Export all team members
for user in team_members; do
    python3 config_manager.py export \
      --output "team/$user-config.yaml"
done

# Compare all configs
for config in team/*.yaml; do
    echo "=== $config ==="
    python3 config_manager.py diff "$config"
done
```

## Security Considerations

### Sensitive Data

Configuration files may contain sensitive information:

- Package versions that reveal security vulnerabilities
- Environment variables with API keys or tokens
- Hardware details useful for targeted attacks

**Recommendations**:
- Review exported configs before sharing
- Sanitize environment variables
- Use `.gitignore` for sensitive configs
- Encrypt configs containing secrets

### Sandboxed Installation

Always use SandboxExecutor for production imports:

```python
from sandbox_executor import SandboxExecutor
from config_manager import ConfigManager

executor = SandboxExecutor(
    max_memory_mb=2048,
    timeout_seconds=600,
    enable_rollback=True
)
manager = ConfigManager(sandbox_executor=executor)
```

### Validation

Configuration validation checks:
- Version compatibility
- OS compatibility  
- Package source availability

Use `--dry-run` extensively before applying configurations.

## API Reference

### ConfigManager Class

#### Constructor

```python
ConfigManager(sandbox_executor=None)
```

Parameters:
- `sandbox_executor` (optional): SandboxExecutor instance for safe command execution

#### Methods

##### export_configuration()

```python
export_configuration(
    output_path: str,
    include_hardware: bool = True,
    include_preferences: bool = True,
    package_sources: List[str] = None
) -> str
```

Export system configuration to YAML file.

##### import_configuration()

```python
import_configuration(
    config_path: str,
    dry_run: bool = False,
    selective: Optional[List[str]] = None,
    force: bool = False
) -> Dict[str, Any]
```

Import configuration from YAML file.

##### diff_configuration()

```python
diff_configuration(config: Dict[str, Any]) -> Dict[str, Any]
```

Compare current system state with configuration.

##### validate_compatibility()

```python
validate_compatibility(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]
```

Validate if configuration can be imported.

##### detect_installed_packages()

```python
detect_installed_packages(sources: List[str] = None) -> List[Dict[str, Any]]
```

Detect all installed packages from specified sources.

## Contributing

Contributions are welcome! Areas for improvement:

- Additional package manager support (cargo, gem, etc.)
- Configuration validation schemas
- Migration tools between versions
- GUI for configuration management
- Cloud storage integration

## License

Cortex Linux Configuration Management is part of the Cortex Linux project.

## Support

- **Issues**: [https://github.com/cortexlinux/cortex/issues](https://github.com/cortexlinux/cortex/issues)
- **Discord**: [https://discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- **Email**: [mike@cortexlinux.com](mailto:mike@cortexlinux.com)

---

**Version**: 0.2.0  
**Last Updated**: November 2024
