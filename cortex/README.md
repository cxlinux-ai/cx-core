# Cortex Package Manager Wrapper

Intelligent package manager wrapper that translates natural language into package installation commands.

## Features

- **Natural Language Processing**: Convert user-friendly descriptions into package manager commands
- **Multi-Package Manager Support**: Works with apt (Debian/Ubuntu), yum, and dnf (RHEL/CentOS/Fedora)
- **Intelligent Matching**: Handles package name variations and synonyms
- **20+ Software Categories**: Supports common development tools, databases, web servers, and more
- **Error Handling**: Comprehensive error handling and validation

## Installation

The package manager wrapper is part of the Cortex Linux project. No additional installation is required beyond the project dependencies.

## Usage

### Basic Usage

```python
from cortex.packages import PackageManager

# Initialize package manager (auto-detects system)
pm = PackageManager()

# Parse natural language request
commands = pm.parse("install python with data science libraries")
# Returns: ["apt update", "apt install -y python3 python3-pip python3-numpy python3-pandas python3-scipy python3-matplotlib jupyter ipython3"]

# Execute commands (requires appropriate permissions)
for cmd in commands:
    print(cmd)
    # subprocess.run(cmd.split(), check=True)
```

### Specify Package Manager

```python
# Explicitly specify package manager
pm = PackageManager(package_manager="apt")
commands = pm.parse("install docker")
```

### Supported Package Managers

- `apt` - Debian/Ubuntu (default)
- `yum` - RHEL/CentOS 7 and older
- `dnf` - RHEL/CentOS 8+ and Fedora

### Search for Packages

```python
pm = PackageManager()
results = pm.search_packages("python")
# Returns: {"python_dev": [...], "python_data_science": [...]}
```

### Get Supported Software

```python
pm = PackageManager()
supported = pm.get_supported_software()
# Returns: ["python_dev", "docker", "git", ...]
```

## Supported Software Categories

The package manager supports 20+ common software categories:

### Development Tools
- **Python Development**: `install python development tools`
- **Python Data Science**: `install python with data science libraries`
- **Python Machine Learning**: `install machine learning libraries`
- **Build Tools**: `install build tools`, `install compiler`
- **Node.js**: `install nodejs`
- **Git**: `install git`
- **Java**: `install java`
- **Go**: `install go`
- **Rust**: `install rust`
- **Ruby**: `install ruby`
- **PHP**: `install php`

### Web Servers & Databases
- **Nginx**: `install nginx`
- **Apache**: `install apache`
- **MySQL**: `install mysql`
- **PostgreSQL**: `install postgresql`
- **Redis**: `install redis`
- **MongoDB**: `install mongodb`

### DevOps & Infrastructure
- **Docker**: `install docker`
- **Kubernetes**: `install kubernetes`
- **Ansible**: `install ansible`
- **Terraform**: `install terraform`

### System Tools
- **Network Tools**: `install network tools`
- **SSH**: `install ssh`
- **Security Tools**: `install security tools`
- **Media Tools**: `install ffmpeg`

### Applications
- **LibreOffice**: `install libreoffice`
- **Firefox**: `install firefox`
- **Vim**: `install vim`

## Examples

### Example 1: Python Development

```python
from cortex.packages import PackageManager

pm = PackageManager()
commands = pm.parse("install python development tools")
print(commands)
# Output: ["apt update", "apt install -y python3 python3-pip python3-dev python3-venv"]
```

### Example 2: Data Science Stack

```python
pm = PackageManager()
commands = pm.parse("install python with data science libraries")
print(commands)
# Output: ["apt update", "apt install -y python3 python3-pip python3-numpy python3-pandas python3-scipy python3-matplotlib jupyter ipython3"]
```

### Example 3: Web Development Stack

```python
pm = PackageManager()
commands = pm.parse("install nginx with mysql and redis")
print(commands)
# Output: ["apt update", "apt install -y nginx mysql-server mysql-client redis-server"]
```

### Example 4: Remove Packages

```python
pm = PackageManager()
commands = pm.parse("remove python")
print(commands)
# Output: ["apt remove -y python3 python3-pip python3-dev python3-venv"]
```

### Example 5: Update Packages

```python
pm = PackageManager()
commands = pm.parse("update packages")
print(commands)
# Output: ["apt update"]
```

## Package Manager Differences

The wrapper handles differences between package managers:

| Software | apt (Debian/Ubuntu) | yum/dnf (RHEL/CentOS/Fedora) |
|----------|---------------------|------------------------------|
| Apache   | apache2             | httpd                        |
| MySQL    | mysql-server        | mysql-server                 |
| Redis    | redis-server        | redis                        |
| Python   | python3-dev         | python3-devel                |

## Error Handling

The package manager wrapper includes comprehensive error handling:

```python
from cortex.packages import PackageManager, PackageManagerError

pm = PackageManager()

try:
    commands = pm.parse("install unknown-package-xyz")
except PackageManagerError as e:
    print(f"Error: {e}")
```

## Testing

Run the test suite:

```bash
python -m pytest test_packages.py -v
```

Or using unittest:

```bash
python test_packages.py
```

## Architecture

### Knowledge Base

The package manager uses a knowledge base of common software requests. Each entry includes:
- Keywords for matching
- Package names for each supported package manager
- Category grouping

### Matching Algorithm

1. Normalize input text (lowercase, strip whitespace)
2. Find matching categories based on keywords
3. Score matches by keyword relevance
4. Merge packages from top matching categories
5. Generate appropriate package manager commands

### Command Generation

Commands are generated based on:
- Package manager type (apt/yum/dnf)
- Action (install/remove/update)
- Package names from knowledge base

## Contributing

To add new software categories:

1. Add entry to `_build_knowledge_base()` in `packages.py`
2. Include keywords for matching
3. Add package names for each supported package manager
4. Add unit tests in `test_packages.py`

## License

Part of the Cortex Linux project. See LICENSE file for details.

## See Also

- [Cortex Linux README](../README.md)
- [LLM Integration Layer](../LLM/SUMMARY.md)
- [Sandbox Executor](../src/sandbox_executor.py)
