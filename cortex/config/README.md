# Configuration File Template System

A comprehensive system to generate common configuration files from templates with validation and backup support.

## Features

- ✅ **5+ Configuration Types**: nginx, PostgreSQL, Redis, Docker Compose, Apache
- ✅ **Variable Substitution**: Flexible Jinja2-based templating
- ✅ **Validation**: Pre-write validation for all config types
- ✅ **Backup System**: Automatic backup of existing configurations
- ✅ **Dry Run Mode**: Preview configurations before writing
- ✅ **Clean API**: Simple, intuitive interface

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install specific dependencies
pip install jinja2 pytest
```

## Quick Start

```python
from cortex.config import ConfigGenerator

# Create generator instance
cg = ConfigGenerator()

# Generate nginx reverse proxy configuration
cg.generate(
    "nginx",
    reverse_proxy=True,
    target_port=3000,
    server_name="example.com"
)
# Creates nginx configuration file
```

## Supported Configuration Types

### 1. Nginx

Generate nginx web server and reverse proxy configurations.

### Example: Nginx Reverse Proxy
```python
cg = ConfigGenerator()
cg.generate(
    "nginx",
    reverse_proxy=True,
    target_port=3000,
    target_host="localhost",
    server_name="app.example.com",
    port=80,
    enable_logging=True
)
```

### Example: Nginx Static Web Server
```python
cg.generate(
    "nginx",
    reverse_proxy=False,
    port=8080,
    server_name="static.example.com",
    document_root="/var/www/html",
    enable_gzip=True
)
```

### Example: Nginx SSL Configuration
```python
cg.generate(
    "nginx",
    reverse_proxy=True,
    target_port=3000,
    ssl_enabled=True,
    ssl_port=443,
    ssl_certificate="/etc/ssl/certs/server.crt",
    ssl_certificate_key="/etc/ssl/private/server.key"
)
```

**Available Parameters:**
- `reverse_proxy` (bool): Enable reverse proxy mode
- `port` (int): HTTP port (default: 80)
- `ssl_port` (int): HTTPS port (default: 443)
- `server_name` (str): Server name/domain
- `target_host` (str): Proxy target host
- `target_port` (int): Proxy target port
- `ssl_enabled` (bool): Enable SSL/TLS
- `ssl_certificate` (str): SSL certificate path
- `ssl_certificate_key` (str): SSL key path
- `enable_gzip` (bool): Enable gzip compression
- `enable_logging` (bool): Enable access/error logging
- `proxy_timeout` (int): Proxy timeout in seconds

### 2. PostgreSQL

Generate PostgreSQL database configurations.

### Example: PostgreSQL Basic Configuration
```python
cg.generate(
    "postgres",
    port=5432,
    max_connections=200,
    shared_buffers="256MB",
    effective_cache_size="8GB"
)
```

### Example: PostgreSQL Replication Setup
```python
cg.generate(
    "postgres",
    enable_replication=True,
    max_wal_senders=10,
    wal_keep_size="2GB",
    hot_standby="on"
)
```

### Example: PostgreSQL SSL Configuration
```python
cg.generate(
    "postgres",
    enable_ssl=True,
    ssl_cert_file="/etc/postgresql/server.crt",
    ssl_key_file="/etc/postgresql/server.key"
)
```

**Available Parameters:**
- `listen_addresses` (str): Listen addresses
- `port` (int): PostgreSQL port (default: 5432)
- `max_connections` (int): Maximum connections
- `shared_buffers` (str): Shared buffer size
- `effective_cache_size` (str): Effective cache size
- `work_mem` (str): Work memory
- `maintenance_work_mem` (str): Maintenance work memory
- `enable_replication` (bool): Enable replication
- `enable_ssl` (bool): Enable SSL
- `log_slow_queries` (bool): Log slow queries

### 3. Redis

Generate Redis cache server configurations.

### Example: Redis Basic Configuration
```python
cg.generate(
    "redis",
    port=6379,
    bind_address="127.0.0.1",
    maxmemory="512mb",
    maxmemory_policy="allkeys-lru"
)
```

### Example: Redis Persistence Enabled
```python
cg.generate(
    "redis",
    persistence=True,
    appendonly="yes",
    data_directory="/var/lib/redis"
)
```

### Example: Redis Replication Setup
```python
cg.generate(
    "redis",
    enable_replication=True,
    replica_host="master.example.com",
    replica_port=6379
)
```

**Available Parameters:**
- `bind_address` (str): Bind address
- `port` (int): Redis port (default: 6379)
- `password` (str): Authentication password
- `maxmemory` (str): Maximum memory limit
- `maxmemory_policy` (str): Eviction policy
- `persistence` (bool): Enable persistence
- `appendonly` (bool): Enable AOF
- `enable_replication` (bool): Enable replication
- `replica_host` (str): Master host for replication
- `replica_port` (int): Master port for replication

### 4. Docker Compose

Generate Docker Compose orchestration files.

### Example: Docker Compose Web + Database Stack
```python
services = [
    {
        "name": "web",
        "image": "nginx:latest",
        "ports": ["80:80", "443:443"],
        "volumes": ["./html:/usr/share/nginx/html"],
        "depends_on": ["db"],
        "restart": "always"
    },
    {
        "name": "db",
        "image": "postgres:13",
        "environment": {
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_DB": "myapp"
        },
        "volumes": ["postgres_data:/var/lib/postgresql/data"],
        "restart": "always"
    }
]

cg.generate(
    "docker-compose",
    version="3.8",
    services=services,
    volumes={"postgres_data": {}},
    networks={"app_network": {"driver": "bridge"}}
)
```

### Example: Docker Compose Microservices Architecture
```python
services = [
    {
        "name": "api",
        "build": {"context": "./api", "dockerfile": "Dockerfile"},
        "ports": ["3000:3000"],
        "environment": {"NODE_ENV": "production"},
        "networks": ["backend"]
    },
    {
        "name": "frontend",
        "build": {"context": "./frontend"},
        "ports": ["8080:80"],
        "networks": ["frontend", "backend"]
    },
    {
        "name": "redis",
        "image": "redis:alpine",
        "networks": ["backend"]
    }
]

cg.generate(
    "docker-compose",
    version="3.8",
    services=services,
    networks={
        "frontend": {"driver": "bridge"},
        "backend": {"driver": "bridge"}
    }
)
```

**Available Parameters:**
- `version` (str): Docker Compose version
- `services` (list): List of service definitions
- `networks` (dict): Network definitions
- `volumes` (dict): Volume definitions

### 5. Apache

Generate Apache web server configurations.

### Example: Apache Reverse Proxy
```python
cg.generate(
    "apache",
    reverse_proxy=True,
    port=80,
    server_name="app.example.com",
    target_host="localhost",
    target_port=8000
)
```

### Example: Apache Static Web Server
```python
cg.generate(
    "apache",
    reverse_proxy=False,
    port=80,
    server_name="www.example.com",
    document_root="/var/www/html",
    allow_override="All"
)
```

**Available Parameters:**
- `reverse_proxy` (bool): Enable reverse proxy mode
- `port` (int): HTTP port
- `server_name` (str): Server name
- `server_alias` (str): Server alias
- `target_host` (str): Proxy target host
- `target_port` (int): Proxy target port
- `document_root` (str): Document root path
- `ssl_enabled` (bool): Enable SSL
- `enable_logging` (bool): Enable logging

## Advanced Usage

### Custom Output Paths

```python
cg = ConfigGenerator()

# Specify custom output path
cg.generate(
    "nginx",
    output_path="/custom/path/nginx.conf",
    reverse_proxy=True,
    target_port=3000
)
```

### Dry Run Mode

Preview configuration without writing to disk:

```python
cg = ConfigGenerator()

# Generate config without writing
config_content = cg.generate(
    "nginx",
    dry_run=True,
    reverse_proxy=True,
    target_port=3000
)

print(config_content)  # View configuration
```

### Disable Validation

```python
# Create generator without validation
cg = ConfigGenerator(validate_configs=False)

cg.generate("nginx", reverse_proxy=True, target_port=3000)
```

### Disable Backups

```python
# Create generator without backups
cg = ConfigGenerator(create_backups=False)

cg.generate("nginx", reverse_proxy=True, target_port=3000)
```

### Custom Directories

```python
cg = ConfigGenerator(
    output_dir="./configs",
    backup_dir="./config_backups",
    template_dir="./custom_templates"
)
```

## Backup and Restore

### List Backups

```python
cg = ConfigGenerator()

# List all backups
backups = cg.list_backups()
for backup in backups:
    print(backup)
```

### Restore from Backup

```python
cg = ConfigGenerator()

# Restore a configuration
cg.restore_backup("nginx", "app.conf.20240101_120000.backup")
```

## Template Information

### List Available Templates

```python
cg = ConfigGenerator()

templates = cg.list_templates()
print(templates)  # ['nginx', 'postgres', 'redis', 'docker-compose', 'apache']
```

### Get Template Details

```python
cg = ConfigGenerator()

info = cg.get_template_info("nginx")
print(info)
# {
#     'type': 'nginx',
#     'template_file': 'nginx.conf.template',
#     'default_path': '/etc/nginx/sites-available/app.conf',
#     'validator_available': True
# }
```

## Validation

The system automatically validates configurations before writing. Validation checks include:

### Nginx Validation
- Valid server block structure
- Port number ranges (1-65535)
- SSL certificate paths when SSL is enabled
- Listen directives

### PostgreSQL Validation
- Port number ranges
- Memory setting formats
- Common configuration parameters

### Redis Validation
- Port number ranges
- Memory format validation
- Persistence configuration consistency

### Docker Compose Validation
- Services definition
- Version format
- Image name format
- Network configuration

### Apache Validation
- VirtualHost structure
- DocumentRoot presence
- Port number ranges
- SSL configuration completeness

## Error Handling

The system provides clear error messages for different failure scenarios:

```python
from cortex.config import ConfigGenerator
from cortex.config.exceptions import (
    ConfigError,
    ValidationError,
    TemplateError,
    BackupError
)

try:
    cg = ConfigGenerator()
    cg.generate("nginx", reverse_proxy=True, port=99999)
except ValidationError as e:
    print(f"Validation failed: {e}")
except ConfigError as e:
    print(f"Configuration error: {e}")
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest cortex/config/test_config_generator.py -v

# Run specific test
pytest cortex/config/test_config_generator.py::TestConfigGenerator::test_nginx_reverse_proxy_generation -v

# Run with coverage
pytest cortex/config/test_config_generator.py --cov=cortex.config --cov-report=html
```

## Examples

Complete working examples are available in `cortex/config/examples.py`.

## Contributing

Contributions are welcome! To add a new configuration type:

1. Create a template file in `cortex/config/templates/`
2. Add a validator in `cortex/config/validators.py`
3. Register the config type in `ConfigGenerator.TEMPLATE_EXTENSIONS`
4. Add tests in `test_config_generator.py`
5. Update documentation

## License

Part of the Cortex Linux project.

## Support

For issues and questions:
- GitHub Issues: [cortex/issues](../../issues)
- [Discord](https://discord.gg/uCqHvxjU83)
- Email: mike@cortexlinux.com

