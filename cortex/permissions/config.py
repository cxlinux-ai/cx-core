"""
Configuration for Permission Auditor & Fixer.
"""

DANGEROUS_PERMISSIONS = {
    0o777: "Full read/write/execute for everyone (rwxrwxrwx)",
    0o666: "Read/write for everyone (rw-rw-rw-)",
    0o000: "No permissions for anyone (---------)",
}

# World-writable flag
WORLD_WRITABLE_FLAG = 0o002  # S_IWOTH

# Paths to ignore during scanning
IGNORE_PATTERNS = [
    "/proc/*",
    "/sys/*",
    "/dev/*",
    "/run/*",
    "*.pyc",
    "__pycache__",
    ".git/*",
    ".env",
    "venv/*",
    "node_modules/*",
    "*.swp",
    "*.tmp",
]

# Docker-specific paths that need special handling
DOCKER_PATTERNS = [
    "/var/lib/docker/*",
    "/var/run/docker.sock",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    ".dockerignore",
]

# Sensitive files that should never be world-readable
SENSITIVE_FILES = [
    ".env",
    ".ssh/id_rsa",
    ".ssh/id_rsa.pub",
    ".aws/credentials",
    ".docker/config.json",
    "id_rsa",
    "id_rsa.pub",
]

# Recommended permissions by file type
RECOMMENDED_PERMISSIONS = {
    "directory": 0o755,  # drwxr-xr-x
    "executable": 0o755,  # -rwxr-xr-x
    "config_file": 0o644,  # -rw-r--r--
    "data_file": 0o644,  # -rw-r--r--
    "log_file": 0o640,  # -rw-r-----
    "secret_file": 0o600,  # -rw-------
    "docker_socket": 0o660,  # Docker socket special permissions
}

# Common Docker UID/GID mappings
COMMON_DOCKER_UIDS = {
    0: "root",
    1: "daemon",
    33: "www-data",
    999: "postgres",
    101: "nginx",
    102: "redis",
    103: "mysql",
    104: "mongodb",
}

# Docker-specific recommended permissions
DOCKER_RECOMMENDED_PERMISSIONS = {
    "volume_directory": 0o755,
    "config_directory": 0o755,
    "data_directory": 0o755,
    "log_directory": 0o755,
    "compose_file": 0o644,
    "dockerfile": 0o644,
}
