"""
Environment Variable Manager for Cortex CLI.

Provides first-class environment variable management with:
- Per-application environment variable storage
- Encrypted storage for secrets using Fernet encryption
- Environment templates with validation
- Integration with services for auto-loading

Storage location: ~/.cortex/environments/<app>.json
Encryption key: ~/.cortex/.env_key (chmod 600)
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Lazy import for cryptography to handle optional dependency
_fernet_module = None


def _get_fernet():
    """Lazy load Fernet to handle cases where cryptography is not installed."""
    global _fernet_module
    if _fernet_module is None:
        try:
            from cryptography.fernet import Fernet

            _fernet_module = Fernet
        except ImportError:
            raise ImportError(
                "cryptography package is required for encryption. "
                "Install it with: pip install cryptography"
            )
    return _fernet_module


class VariableType(Enum):
    """Types of environment variables for validation."""

    STRING = "string"
    URL = "url"
    PORT = "port"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    PATH = "path"


@dataclass
class EnvironmentVariable:
    """Represents a single environment variable."""

    key: str
    value: str
    encrypted: bool = False
    description: str = ""
    var_type: str = "string"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "value": self.value,
            "encrypted": self.encrypted,
            "description": self.description,
            "var_type": self.var_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentVariable:
        """Create from dictionary."""
        return cls(
            key=data["key"],
            value=data["value"],
            encrypted=data.get("encrypted", False),
            description=data.get("description", ""),
            var_type=data.get("var_type", "string"),
        )


@dataclass
class TemplateVariable:
    """Definition of a variable in a template."""

    name: str
    required: bool = True
    default: str | None = None
    var_type: str = "string"
    description: str = ""
    validation_pattern: str | None = None


@dataclass
class EnvironmentTemplate:
    """Reusable environment template definition."""

    name: str
    description: str
    variables: list[TemplateVariable] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "variables": [asdict(v) for v in self.variables],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentTemplate:
        """Create from dictionary."""
        variables = [TemplateVariable(**v) for v in data.get("variables", [])]
        return cls(
            name=data["name"],
            description=data["description"],
            variables=variables,
        )


@dataclass
class ValidationResult:
    """Result of environment variable validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Built-in templates
BUILTIN_TEMPLATES: dict[str, EnvironmentTemplate] = {
    "nodejs": EnvironmentTemplate(
        name="nodejs",
        description="Standard Node.js application environment",
        variables=[
            TemplateVariable(
                name="NODE_ENV",
                required=True,
                default="development",
                var_type="string",
                description="Node environment (development, production, test)",
            ),
            TemplateVariable(
                name="PORT",
                required=False,
                default="3000",
                var_type="port",
                description="Application port",
            ),
            TemplateVariable(
                name="LOG_LEVEL",
                required=False,
                default="info",
                var_type="string",
                description="Logging level",
            ),
        ],
    ),
    "python": EnvironmentTemplate(
        name="python",
        description="Standard Python application environment",
        variables=[
            TemplateVariable(
                name="PYTHONPATH",
                required=False,
                var_type="path",
                description="Python module search path",
            ),
            TemplateVariable(
                name="PYTHONDONTWRITEBYTECODE",
                required=False,
                default="1",
                var_type="boolean",
                description="Prevent .pyc file generation",
            ),
            TemplateVariable(
                name="PYTHONUNBUFFERED",
                required=False,
                default="1",
                var_type="boolean",
                description="Force unbuffered stdout/stderr",
            ),
            TemplateVariable(
                name="LOG_LEVEL",
                required=False,
                default="INFO",
                var_type="string",
                description="Logging level",
            ),
        ],
    ),
    "django": EnvironmentTemplate(
        name="django",
        description="Django web application environment",
        variables=[
            TemplateVariable(
                name="DJANGO_SETTINGS_MODULE",
                required=True,
                var_type="string",
                description="Django settings module path",
            ),
            TemplateVariable(
                name="SECRET_KEY",
                required=True,
                var_type="string",
                description="Django secret key (should be encrypted)",
            ),
            TemplateVariable(
                name="DEBUG",
                required=False,
                default="False",
                var_type="boolean",
                description="Django debug mode",
            ),
            TemplateVariable(
                name="ALLOWED_HOSTS",
                required=False,
                default="localhost,127.0.0.1",
                var_type="string",
                description="Comma-separated allowed hosts",
            ),
            TemplateVariable(
                name="DATABASE_URL",
                required=False,
                var_type="url",
                description="Database connection URL",
            ),
        ],
    ),
    "flask": EnvironmentTemplate(
        name="flask",
        description="Flask web application environment",
        variables=[
            TemplateVariable(
                name="FLASK_APP",
                required=True,
                var_type="string",
                description="Flask application module",
            ),
            TemplateVariable(
                name="FLASK_ENV",
                required=False,
                default="development",
                var_type="string",
                description="Flask environment",
            ),
            TemplateVariable(
                name="FLASK_DEBUG",
                required=False,
                default="0",
                var_type="boolean",
                description="Flask debug mode",
            ),
            TemplateVariable(
                name="SECRET_KEY",
                required=True,
                var_type="string",
                description="Flask secret key (should be encrypted)",
            ),
        ],
    ),
    "docker": EnvironmentTemplate(
        name="docker",
        description="Docker containerized application environment",
        variables=[
            TemplateVariable(
                name="DOCKER_HOST",
                required=False,
                var_type="url",
                description="Docker daemon socket",
            ),
            TemplateVariable(
                name="COMPOSE_PROJECT_NAME",
                required=False,
                var_type="string",
                description="Docker Compose project name",
            ),
            TemplateVariable(
                name="COMPOSE_FILE",
                required=False,
                default="docker-compose.yml",
                var_type="path",
                description="Docker Compose file path",
            ),
        ],
    ),
    "database": EnvironmentTemplate(
        name="database",
        description="Database connection environment",
        variables=[
            TemplateVariable(
                name="DATABASE_URL",
                required=True,
                var_type="url",
                description="Database connection URL",
            ),
            TemplateVariable(
                name="DB_HOST",
                required=False,
                default="localhost",
                var_type="string",
                description="Database host",
            ),
            TemplateVariable(
                name="DB_PORT",
                required=False,
                default="5432",
                var_type="port",
                description="Database port",
            ),
            TemplateVariable(
                name="DB_NAME",
                required=False,
                var_type="string",
                description="Database name",
            ),
            TemplateVariable(
                name="DB_USER",
                required=False,
                var_type="string",
                description="Database user",
            ),
            TemplateVariable(
                name="DB_PASSWORD",
                required=False,
                var_type="string",
                description="Database password (should be encrypted)",
            ),
        ],
    ),
    "aws": EnvironmentTemplate(
        name="aws",
        description="AWS cloud services environment",
        variables=[
            TemplateVariable(
                name="AWS_ACCESS_KEY_ID",
                required=True,
                var_type="string",
                description="AWS access key ID (should be encrypted)",
            ),
            TemplateVariable(
                name="AWS_SECRET_ACCESS_KEY",
                required=True,
                var_type="string",
                description="AWS secret access key (should be encrypted)",
            ),
            TemplateVariable(
                name="AWS_DEFAULT_REGION",
                required=False,
                default="us-east-1",
                var_type="string",
                description="AWS default region",
            ),
            TemplateVariable(
                name="AWS_PROFILE",
                required=False,
                var_type="string",
                description="AWS named profile",
            ),
        ],
    ),
}


class EnvironmentValidator:
    """Validates environment variable values based on type."""

    # URL pattern: protocol://host[:port][/path]
    URL_PATTERN = re.compile(
        r"^[a-zA-Z][a-zA-Z0-9+.-]*://"  # scheme
        r"[^\s/$.?#]"  # at least one character for host
        r"[^\s]*$",  # rest of URL
        re.IGNORECASE,
    )

    # Port: 1-65535
    PORT_PATTERN = re.compile(
        r"^([1-9]\d{0,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$"
    )

    # Boolean: common boolean representations
    BOOLEAN_VALUES = {"true", "false", "1", "0", "yes", "no", "on", "off"}

    @classmethod
    def validate(
        cls,
        value: str,
        var_type: str,
        custom_pattern: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Validate a value against a type.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if custom_pattern:
            try:
                if not re.match(custom_pattern, value):
                    return False, f"Value does not match pattern: {custom_pattern}"
            except re.error as e:
                return False, f"Invalid validation pattern: {e}"

        try:
            vtype = VariableType(var_type)
        except ValueError:
            # Unknown type, treat as string (always valid)
            return True, None

        if vtype == VariableType.STRING:
            return True, None

        elif vtype == VariableType.URL:
            if not cls.URL_PATTERN.match(value):
                return False, f"Invalid URL format: {value}"
            return True, None

        elif vtype == VariableType.PORT:
            if not cls.PORT_PATTERN.match(value):
                return False, f"Invalid port number: {value} (must be 1-65535)"
            return True, None

        elif vtype == VariableType.BOOLEAN:
            if value.lower() not in cls.BOOLEAN_VALUES:
                return (
                    False,
                    f"Invalid boolean value: {value} (use true/false, 1/0, yes/no, on/off)",
                )
            return True, None

        elif vtype == VariableType.INTEGER:
            try:
                int(value)
                return True, None
            except ValueError:
                return False, f"Invalid integer value: {value}"

        elif vtype == VariableType.PATH:
            # Path validation: just check it's not empty
            if not value.strip():
                return False, "Path cannot be empty"
            return True, None

        return True, None


class EncryptionManager:
    """Manages encryption keys and encrypts/decrypts values."""

    def __init__(self, key_path: Path | None = None):
        """
        Initialize encryption manager.

        Args:
            key_path: Path to encryption key file. Defaults to ~/.cortex/.env_key
        """
        if key_path is None:
            key_path = Path.home() / ".cortex" / ".env_key"
        self.key_path = key_path
        self._fernet: Any = None

    def _ensure_key_exists(self) -> bytes:
        """Ensure encryption key exists, create if needed."""
        if self.key_path.exists():
            return self.key_path.read_bytes()

        # Create new key
        Fernet = _get_fernet()
        key = Fernet.generate_key()

        # Ensure parent directory exists
        self.key_path.parent.mkdir(parents=True, exist_ok=True)

        # Write key with secure permissions (atomic write)
        fd = os.open(
            str(self.key_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,  # 0600
        )
        try:
            os.write(fd, key)
        finally:
            os.close(fd)

        return key

    def _get_fernet(self) -> Any:
        """Get or create Fernet instance."""
        if self._fernet is None:
            Fernet = _get_fernet()
            key = self._ensure_key_exists()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, value: str) -> str:
        """
        Encrypt a value.

        Args:
            value: Plaintext value to encrypt

        Returns:
            Base64-encoded encrypted value
        """
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(value.encode("utf-8"))
        return encrypted.decode("utf-8")

    def decrypt(self, encrypted_value: str) -> str:
        """
        Decrypt a value.

        Args:
            encrypted_value: Base64-encoded encrypted value

        Returns:
            Decrypted plaintext value

        Raises:
            ValueError: If decryption fails (invalid key, corrupted data, etc.)
        """
        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted_value.encode("utf-8"))
            return decrypted.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}") from e

    def is_key_available(self) -> bool:
        """Check if encryption is available (key exists or can be created)."""
        try:
            self._ensure_key_exists()
            return True
        except Exception:
            return False


class EnvironmentStorage:
    """Manages persistent storage of environment variables."""

    def __init__(self, base_path: Path | None = None):
        """
        Initialize storage.

        Args:
            base_path: Base directory for environment storage.
                       Defaults to ~/.cortex/environments
        """
        if base_path is None:
            base_path = Path.home() / ".cortex" / "environments"
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_app_path(self, app: str) -> Path:
        """Get the storage path for an application."""
        # Sanitize app name for filesystem
        safe_name = re.sub(r"[^\w\-.]", "_", app)
        return self.base_path / f"{safe_name}.json"

    def _get_safe_app_name(self, app: str) -> str:
        """Get a filesystem-safe version of the app name."""
        return re.sub(r"[^\w\-.]", "_", app)

    def load(self, app: str) -> dict[str, EnvironmentVariable]:
        """
        Load environment variables for an application.

        Args:
            app: Application name

        Returns:
            Dictionary mapping variable names to EnvironmentVariable objects
        """
        app_path = self._get_app_path(app)

        if not app_path.exists():
            return {}

        try:
            with open(app_path, encoding="utf-8") as f:
                data = json.load(f)

            return {
                var_data["key"]: EnvironmentVariable.from_dict(var_data)
                for var_data in data.get("variables", [])
            }
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Corrupted environment file for {app}: {e}")

    def save(self, app: str, variables: dict[str, EnvironmentVariable]) -> None:
        """
        Save environment variables for an application (atomic write).

        Args:
            app: Application name
            variables: Dictionary of environment variables
        """
        app_path = self._get_app_path(app)

        data = {
            "app": app,
            "variables": [var.to_dict() for var in variables.values()],
        }

        # Atomic write: write to temp file, then rename
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Use safe app name for temp file prefix
        safe_prefix = self._get_safe_app_name(app)

        fd, temp_path = tempfile.mkstemp(
            dir=self.base_path,
            suffix=".tmp",
            prefix=f"{safe_prefix}_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, app_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def delete_app(self, app: str) -> bool:
        """
        Delete all environment data for an application.

        Args:
            app: Application name

        Returns:
            True if data was deleted, False if app didn't exist
        """
        app_path = self._get_app_path(app)

        if app_path.exists():
            app_path.unlink()
            return True
        return False

    def list_apps(self) -> list[str]:
        """
        List all applications with stored environments.

        Returns:
            List of application names
        """
        apps = []
        for path in self.base_path.glob("*.json"):
            # Extract app name from filename
            app_name = path.stem
            apps.append(app_name)
        return sorted(apps)


class EnvironmentManager:
    """
    Main environment manager class.

    Provides high-level API for managing environment variables
    with encryption, templates, and validation.
    """

    def __init__(
        self,
        storage: EnvironmentStorage | None = None,
        encryption: EncryptionManager | None = None,
    ):
        """
        Initialize the environment manager.

        Args:
            storage: Custom storage backend (optional)
            encryption: Custom encryption manager (optional)
        """
        self.storage = storage or EnvironmentStorage()
        self.encryption = encryption or EncryptionManager()
        self.templates = dict(BUILTIN_TEMPLATES)

    def set_variable(
        self,
        app: str,
        key: str,
        value: str,
        encrypt: bool = False,
        var_type: str = "string",
        description: str = "",
    ) -> EnvironmentVariable:
        """
        Set an environment variable for an application.

        Args:
            app: Application name
            key: Variable name
            value: Variable value
            encrypt: Whether to encrypt the value
            var_type: Variable type for validation
            description: Optional description

        Returns:
            The created/updated EnvironmentVariable
        """
        # Validate the value if type is specified
        if var_type != "string":
            is_valid, error = EnvironmentValidator.validate(value, var_type)
            if not is_valid:
                raise ValueError(error)

        # Load existing variables
        variables = self.storage.load(app)

        # Encrypt if requested
        stored_value = value
        if encrypt:
            stored_value = self.encryption.encrypt(value)

        # Create or update variable
        env_var = EnvironmentVariable(
            key=key,
            value=stored_value,
            encrypted=encrypt,
            description=description,
            var_type=var_type,
        )

        variables[key] = env_var
        self.storage.save(app, variables)

        return env_var

    def get_variable(
        self,
        app: str,
        key: str,
        decrypt: bool = True,
    ) -> str | None:
        """
        Get an environment variable value.

        Args:
            app: Application name
            key: Variable name
            decrypt: Whether to decrypt encrypted values

        Returns:
            Variable value or None if not found
        """
        variables = self.storage.load(app)

        if key not in variables:
            return None

        var = variables[key]

        if var.encrypted and decrypt:
            return self.encryption.decrypt(var.value)

        return var.value

    def get_variable_info(self, app: str, key: str) -> EnvironmentVariable | None:
        """
        Get full information about a variable.

        Args:
            app: Application name
            key: Variable name

        Returns:
            EnvironmentVariable object or None if not found
        """
        variables = self.storage.load(app)
        return variables.get(key)

    def list_variables(self, app: str) -> list[EnvironmentVariable]:
        """
        List all environment variables for an application.

        Args:
            app: Application name

        Returns:
            List of EnvironmentVariable objects
        """
        variables = self.storage.load(app)
        return list(variables.values())

    def delete_variable(self, app: str, key: str) -> bool:
        """
        Delete an environment variable.

        Args:
            app: Application name
            key: Variable name

        Returns:
            True if variable was deleted, False if not found
        """
        variables = self.storage.load(app)

        if key not in variables:
            return False

        del variables[key]
        self.storage.save(app, variables)
        return True

    def clear_app(self, app: str) -> bool:
        """
        Clear all environment variables for an application.

        Args:
            app: Application name

        Returns:
            True if app existed and was cleared
        """
        return self.storage.delete_app(app)

    def list_apps(self) -> list[str]:
        """
        List all applications with stored environments.

        Returns:
            List of application names
        """
        return self.storage.list_apps()

    def export_env(self, app: str, include_encrypted: bool = False) -> str:
        """
        Export environment variables in .env format.

        Args:
            app: Application name
            include_encrypted: Whether to decrypt and include encrypted values

        Returns:
            Environment file content as string
        """
        variables = self.storage.load(app)
        lines = []

        for var in sorted(variables.values(), key=lambda v: v.key):
            if var.encrypted:
                if include_encrypted:
                    value = self.encryption.decrypt(var.value)
                    lines.append(
                        f"# [encrypted] {var.description}" if var.description else "# [encrypted]"
                    )
                    lines.append(f'{var.key}="{value}"')
                else:
                    lines.append(f"# {var.key}=[encrypted - use --include-encrypted to export]")
            else:
                if var.description:
                    lines.append(f"# {var.description}")
                # Quote values with special characters
                if any(c in var.value for c in " \t\n'\"$`\\"):
                    lines.append(f'{var.key}="{var.value}"')
                else:
                    lines.append(f"{var.key}={var.value}")

        return "\n".join(lines) + "\n" if lines else ""

    def import_env(
        self,
        app: str,
        content: str,
        encrypt_keys: list[str] | None = None,
    ) -> tuple[int, list[str]]:
        """
        Import environment variables from .env format.

        Args:
            app: Application name
            content: .env file content
            encrypt_keys: List of keys to encrypt during import

        Returns:
            Tuple of (count of imported variables, list of errors)
        """
        encrypt_keys = set(encrypt_keys or [])
        variables = self.storage.load(app)
        imported = 0
        errors = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse KEY=value
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if not match:
                errors.append(f"Line {line_num}: Invalid format")
                continue

            key = match.group(1)
            value = match.group(2)

            # Handle quoted values
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            # Encrypt if key is in encrypt_keys
            encrypt = key in encrypt_keys

            if encrypt:
                value = self.encryption.encrypt(value)

            variables[key] = EnvironmentVariable(
                key=key,
                value=value,
                encrypted=encrypt,
            )
            imported += 1

        if imported > 0:
            self.storage.save(app, variables)

        return imported, errors

    def load_to_environ(self, app: str) -> int:
        """
        Load environment variables into os.environ.

        Args:
            app: Application name

        Returns:
            Number of variables loaded
        """
        variables = self.storage.load(app)
        loaded = 0

        for var in variables.values():
            if var.encrypted:
                value = self.encryption.decrypt(var.value)
            else:
                value = var.value

            os.environ[var.key] = value
            loaded += 1

        return loaded

    # Template management

    def list_templates(self) -> list[EnvironmentTemplate]:
        """
        List all available templates.

        Returns:
            List of EnvironmentTemplate objects
        """
        return list(self.templates.values())

    def get_template(self, name: str) -> EnvironmentTemplate | None:
        """
        Get a template by name.

        Args:
            name: Template name

        Returns:
            EnvironmentTemplate or None if not found
        """
        return self.templates.get(name.lower())

    def apply_template(
        self,
        template_name: str,
        app: str,
        values: dict[str, str] | None = None,
        encrypt_keys: list[str] | None = None,
    ) -> ValidationResult:
        """
        Apply a template to an application.

        Args:
            template_name: Name of template to apply
            app: Application name
            values: Values for template variables
            encrypt_keys: Keys to encrypt

        Returns:
            ValidationResult with any errors/warnings
        """
        template = self.get_template(template_name)
        if not template:
            return ValidationResult(
                valid=False,
                errors=[f"Template '{template_name}' not found"],
            )

        values = values or {}
        encrypt_keys = set(encrypt_keys or [])
        errors = []
        warnings = []

        variables = self.storage.load(app)

        for tvar in template.variables:
            if tvar.name in values:
                # Use provided value
                value = values[tvar.name]
            elif tvar.default is not None:
                # Use default
                value = tvar.default
            elif tvar.required:
                errors.append(f"Required variable '{tvar.name}' not provided")
                continue
            else:
                # Optional with no default - skip
                continue

            # Validate value
            is_valid, error = EnvironmentValidator.validate(
                value,
                tvar.var_type,
                tvar.validation_pattern,
            )

            if not is_valid:
                errors.append(f"{tvar.name}: {error}")
                continue

            # Check if should encrypt
            encrypt = tvar.name in encrypt_keys

            stored_value = value
            if encrypt:
                stored_value = self.encryption.encrypt(value)

            variables[tvar.name] = EnvironmentVariable(
                key=tvar.name,
                value=stored_value,
                encrypted=encrypt,
                description=tvar.description,
                var_type=tvar.var_type,
            )

        if not errors:
            self.storage.save(app, variables)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_app(
        self,
        app: str,
        template_name: str | None = None,
    ) -> ValidationResult:
        """
        Validate environment variables for an application.

        Args:
            app: Application name
            template_name: Optional template to validate against

        Returns:
            ValidationResult with any errors/warnings
        """
        variables = self.storage.load(app)
        errors = []
        warnings = []

        # Validate all variable types
        for var in variables.values():
            is_valid, error = EnvironmentValidator.validate(
                var.value if not var.encrypted else "placeholder",
                var.var_type,
            )
            if not is_valid and not var.encrypted:
                errors.append(f"{var.key}: {error}")

        # If template specified, check required variables
        if template_name:
            template = self.get_template(template_name)
            if not template:
                errors.append(f"Template '{template_name}' not found")
            else:
                for tvar in template.variables:
                    if tvar.required and tvar.name not in variables:
                        errors.append(f"Required variable '{tvar.name}' missing")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


def get_env_manager() -> EnvironmentManager:
    """Get the default environment manager instance."""
    return EnvironmentManager()
