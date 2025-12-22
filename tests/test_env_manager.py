"""
Comprehensive unit tests for cortex/env_manager.py - Environment Variable Manager

Tests cover:
- Environment variable storage and retrieval
- Per-application isolation
- Encryption and decryption of secrets
- Environment templates and validation
- Import/export functionality
- Edge cases and error handling

Target: >80% code coverage
"""

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from cortex.env_manager import (
    BUILTIN_TEMPLATES,
    EncryptionManager,
    EnvironmentManager,
    EnvironmentStorage,
    EnvironmentTemplate,
    EnvironmentValidator,
    EnvironmentVariable,
    TemplateVariable,
    ValidationResult,
    VariableType,
    get_env_manager,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create a storage instance with temporary directory."""
    return EnvironmentStorage(base_path=temp_dir / "environments")


@pytest.fixture
def encryption_manager(temp_dir):
    """Create an encryption manager with temporary key path."""
    return EncryptionManager(key_path=temp_dir / ".env_key")


@pytest.fixture
def env_manager(temp_dir):
    """Create a full environment manager with temporary paths."""
    storage = EnvironmentStorage(base_path=temp_dir / "environments")
    encryption = EncryptionManager(key_path=temp_dir / ".env_key")
    return EnvironmentManager(storage=storage, encryption=encryption)


# =============================================================================
# EnvironmentVariable Tests
# =============================================================================


class TestEnvironmentVariable:
    """Tests for EnvironmentVariable dataclass."""

    def test_create_basic_variable(self):
        """Test creating a basic environment variable."""
        var = EnvironmentVariable(key="DATABASE_URL", value="postgres://localhost/db")
        assert var.key == "DATABASE_URL"
        assert var.value == "postgres://localhost/db"
        assert var.encrypted is False
        assert var.description == ""
        assert var.var_type == "string"

    def test_create_encrypted_variable(self):
        """Test creating an encrypted variable."""
        var = EnvironmentVariable(
            key="API_KEY",
            value="encrypted_value_here",
            encrypted=True,
            description="API key for external service",
            var_type="string",
        )
        assert var.encrypted is True
        assert var.description == "API key for external service"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        var = EnvironmentVariable(
            key="PORT",
            value="3000",
            encrypted=False,
            description="Server port",
            var_type="port",
        )
        data = var.to_dict()

        assert data["key"] == "PORT"
        assert data["value"] == "3000"
        assert data["encrypted"] is False
        assert data["description"] == "Server port"
        assert data["var_type"] == "port"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "key": "NODE_ENV",
            "value": "production",
            "encrypted": False,
            "description": "Node environment",
            "var_type": "string",
        }
        var = EnvironmentVariable.from_dict(data)

        assert var.key == "NODE_ENV"
        assert var.value == "production"
        assert var.encrypted is False

    def test_from_dict_minimal(self):
        """Test deserialization with minimal data (defaults)."""
        data = {"key": "SIMPLE", "value": "test"}
        var = EnvironmentVariable.from_dict(data)

        assert var.key == "SIMPLE"
        assert var.encrypted is False
        assert var.description == ""
        assert var.var_type == "string"


# =============================================================================
# EnvironmentValidator Tests
# =============================================================================


class TestEnvironmentValidator:
    """Tests for environment variable validation."""

    def test_validate_string_always_valid(self):
        """String type should accept any value."""
        is_valid, error = EnvironmentValidator.validate("anything", "string")
        assert is_valid is True
        assert error is None

    def test_validate_valid_url(self):
        """Test valid URL validation."""
        valid_urls = [
            "http://localhost",
            "https://example.com",
            "postgres://user:pass@localhost:5432/db",
            "redis://localhost:6379",
            "ftp://files.example.com/path",
        ]
        for url in valid_urls:
            is_valid, error = EnvironmentValidator.validate(url, "url")
            assert is_valid is True, f"URL should be valid: {url}"

    def test_validate_invalid_url(self):
        """Test invalid URL validation."""
        invalid_urls = [
            "not-a-url",
            "localhost:3000",
            "//missing-scheme.com",
        ]
        for url in invalid_urls:
            is_valid, error = EnvironmentValidator.validate(url, "url")
            assert is_valid is False, f"URL should be invalid: {url}"
            assert "Invalid URL" in error

    def test_validate_valid_port(self):
        """Test valid port numbers."""
        valid_ports = ["1", "80", "443", "3000", "8080", "65535"]
        for port in valid_ports:
            is_valid, error = EnvironmentValidator.validate(port, "port")
            assert is_valid is True, f"Port should be valid: {port}"

    def test_validate_invalid_port(self):
        """Test invalid port numbers."""
        invalid_ports = ["0", "-1", "65536", "abc", "3000.5"]
        for port in invalid_ports:
            is_valid, error = EnvironmentValidator.validate(port, "port")
            assert is_valid is False, f"Port should be invalid: {port}"
            assert "Invalid port" in error

    def test_validate_valid_boolean(self):
        """Test valid boolean values."""
        valid_booleans = ["true", "false", "True", "FALSE", "1", "0", "yes", "no", "on", "off"]
        for val in valid_booleans:
            is_valid, error = EnvironmentValidator.validate(val, "boolean")
            assert is_valid is True, f"Boolean should be valid: {val}"

    def test_validate_invalid_boolean(self):
        """Test invalid boolean values."""
        is_valid, error = EnvironmentValidator.validate("maybe", "boolean")
        assert is_valid is False
        assert "Invalid boolean" in error

    def test_validate_valid_integer(self):
        """Test valid integer values."""
        valid_integers = ["0", "1", "-5", "12345", "999999999"]
        for val in valid_integers:
            is_valid, error = EnvironmentValidator.validate(val, "integer")
            assert is_valid is True, f"Integer should be valid: {val}"

    def test_validate_invalid_integer(self):
        """Test invalid integer values."""
        is_valid, error = EnvironmentValidator.validate("3.14", "integer")
        assert is_valid is False
        assert "Invalid integer" in error

    def test_validate_path(self):
        """Test path validation."""
        is_valid, error = EnvironmentValidator.validate("/usr/local/bin", "path")
        assert is_valid is True

        is_valid, error = EnvironmentValidator.validate("", "path")
        assert is_valid is False
        assert "cannot be empty" in error

    def test_validate_unknown_type(self):
        """Unknown types should be treated as strings (always valid)."""
        is_valid, error = EnvironmentValidator.validate("anything", "unknown_type")
        assert is_valid is True

    def test_validate_custom_pattern(self):
        """Test custom regex pattern validation."""
        # Valid pattern match
        is_valid, error = EnvironmentValidator.validate(
            "ABC123", "string", custom_pattern=r"^[A-Z0-9]+$"
        )
        assert is_valid is True

        # Invalid pattern match
        is_valid, error = EnvironmentValidator.validate("abc", "string", custom_pattern=r"^[A-Z]+$")
        assert is_valid is False
        assert "does not match pattern" in error

    def test_validate_invalid_custom_pattern(self):
        """Test handling of invalid regex patterns."""
        is_valid, error = EnvironmentValidator.validate(
            "test", "string", custom_pattern=r"[invalid"
        )
        assert is_valid is False
        assert "Invalid validation pattern" in error


# =============================================================================
# EncryptionManager Tests
# =============================================================================


class TestEncryptionManager:
    """Tests for encryption functionality."""

    def test_create_encryption_manager(self, temp_dir):
        """Test creating an encryption manager."""
        key_path = temp_dir / ".env_key"
        manager = EncryptionManager(key_path=key_path)
        assert manager.key_path == key_path

    def test_encrypt_and_decrypt(self, encryption_manager):
        """Test encrypting and decrypting a value."""
        original = "my-secret-value"
        encrypted = encryption_manager.encrypt(original)

        # Encrypted value should be different from original
        assert encrypted != original
        assert len(encrypted) > len(original)  # Fernet adds overhead

        # Should be able to decrypt back to original
        decrypted = encryption_manager.decrypt(encrypted)
        assert decrypted == original

    def test_key_file_created_with_secure_permissions(self, temp_dir):
        """Test that key file is created with chmod 600."""
        key_path = temp_dir / ".env_key"
        manager = EncryptionManager(key_path=key_path)

        # Trigger key creation
        manager.encrypt("test")

        # Check file exists and has correct permissions
        assert key_path.exists()
        mode = stat.S_IMODE(key_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"

    def test_key_persistence(self, temp_dir):
        """Test that encryption key persists across instances."""
        key_path = temp_dir / ".env_key"

        # First manager creates key and encrypts
        manager1 = EncryptionManager(key_path=key_path)
        encrypted = manager1.encrypt("persistent-secret")

        # Second manager should use same key
        manager2 = EncryptionManager(key_path=key_path)
        decrypted = manager2.decrypt(encrypted)

        assert decrypted == "persistent-secret"

    def test_is_key_available(self, encryption_manager):
        """Test key availability check."""
        assert encryption_manager.is_key_available() is True

    def test_encrypt_empty_string(self, encryption_manager):
        """Test encrypting an empty string."""
        encrypted = encryption_manager.encrypt("")
        decrypted = encryption_manager.decrypt(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode(self, encryption_manager):
        """Test encrypting unicode characters."""
        original = "héllo wörld 🔐 密码"
        encrypted = encryption_manager.encrypt(original)
        decrypted = encryption_manager.decrypt(encrypted)
        assert decrypted == original


# =============================================================================
# EnvironmentStorage Tests
# =============================================================================


class TestEnvironmentStorage:
    """Tests for environment storage functionality."""

    def test_create_storage(self, temp_dir):
        """Test creating storage creates directories."""
        base_path = temp_dir / "environments"
        storage = EnvironmentStorage(base_path=base_path)
        assert base_path.exists()

    def test_save_and_load(self, storage):
        """Test saving and loading variables."""
        variables = {
            "DB_URL": EnvironmentVariable(key="DB_URL", value="postgres://localhost/db"),
            "PORT": EnvironmentVariable(key="PORT", value="3000", var_type="port"),
        }

        storage.save("myapp", variables)
        loaded = storage.load("myapp")

        assert len(loaded) == 2
        assert loaded["DB_URL"].value == "postgres://localhost/db"
        assert loaded["PORT"].var_type == "port"

    def test_load_nonexistent_app(self, storage):
        """Test loading non-existent app returns empty dict."""
        result = storage.load("nonexistent")
        assert result == {}

    def test_app_isolation(self, storage):
        """Test that apps are isolated from each other."""
        storage.save("app1", {"KEY": EnvironmentVariable(key="KEY", value="value1")})
        storage.save("app2", {"KEY": EnvironmentVariable(key="KEY", value="value2")})

        app1_vars = storage.load("app1")
        app2_vars = storage.load("app2")

        assert app1_vars["KEY"].value == "value1"
        assert app2_vars["KEY"].value == "value2"

    def test_delete_app(self, storage):
        """Test deleting an application's data."""
        storage.save("to_delete", {"KEY": EnvironmentVariable(key="KEY", value="val")})

        assert storage.delete_app("to_delete") is True
        assert storage.load("to_delete") == {}

    def test_delete_nonexistent_app(self, storage):
        """Test deleting non-existent app returns False."""
        assert storage.delete_app("nonexistent") is False

    def test_list_apps(self, storage):
        """Test listing all apps with stored environments."""
        storage.save("app1", {"K": EnvironmentVariable(key="K", value="v")})
        storage.save("app2", {"K": EnvironmentVariable(key="K", value="v")})
        storage.save("app3", {"K": EnvironmentVariable(key="K", value="v")})

        apps = storage.list_apps()
        assert set(apps) == {"app1", "app2", "app3"}

    def test_list_apps_empty(self, storage):
        """Test listing apps when none exist."""
        apps = storage.list_apps()
        assert apps == []

    def test_safe_app_name(self, storage):
        """Test that app names are sanitized for filesystem."""
        # Names with special characters should be sanitized
        storage.save("my/app:name", {"K": EnvironmentVariable(key="K", value="v")})

        apps = storage.list_apps()
        assert len(apps) == 1
        # The app should be accessible
        loaded = storage.load("my/app:name")
        assert "K" in loaded

    def test_atomic_write(self, storage, temp_dir):
        """Test that writes are atomic (no partial files on failure)."""
        # First, write some valid data
        storage.save("test_app", {"KEY": EnvironmentVariable(key="KEY", value="original")})

        # Verify original data exists
        loaded = storage.load("test_app")
        assert loaded["KEY"].value == "original"


# =============================================================================
# EnvironmentManager Tests
# =============================================================================


class TestEnvironmentManager:
    """Tests for the main EnvironmentManager class."""

    def test_set_and_get_variable(self, env_manager):
        """Test setting and getting a variable."""
        env_manager.set_variable("myapp", "DATABASE_URL", "postgres://localhost/db")

        value = env_manager.get_variable("myapp", "DATABASE_URL")
        assert value == "postgres://localhost/db"

    def test_set_encrypted_variable(self, env_manager):
        """Test setting an encrypted variable."""
        env_manager.set_variable("myapp", "API_KEY", "secret123", encrypt=True)

        # Get with decryption
        value = env_manager.get_variable("myapp", "API_KEY", decrypt=True)
        assert value == "secret123"

        # Get without decryption should return encrypted blob
        var_info = env_manager.get_variable_info("myapp", "API_KEY")
        assert var_info.encrypted is True
        assert var_info.value != "secret123"

    def test_get_nonexistent_variable(self, env_manager):
        """Test getting a non-existent variable returns None."""
        value = env_manager.get_variable("myapp", "NONEXISTENT")
        assert value is None

    def test_list_variables(self, env_manager):
        """Test listing all variables for an app."""
        env_manager.set_variable("myapp", "VAR1", "value1")
        env_manager.set_variable("myapp", "VAR2", "value2")
        env_manager.set_variable("myapp", "VAR3", "value3")

        variables = env_manager.list_variables("myapp")
        assert len(variables) == 3

        keys = {v.key for v in variables}
        assert keys == {"VAR1", "VAR2", "VAR3"}

    def test_delete_variable(self, env_manager):
        """Test deleting a variable."""
        env_manager.set_variable("myapp", "TO_DELETE", "value")

        assert env_manager.delete_variable("myapp", "TO_DELETE") is True
        assert env_manager.get_variable("myapp", "TO_DELETE") is None

    def test_delete_nonexistent_variable(self, env_manager):
        """Test deleting non-existent variable returns False."""
        result = env_manager.delete_variable("myapp", "NONEXISTENT")
        assert result is False

    def test_clear_app(self, env_manager):
        """Test clearing all variables for an app."""
        env_manager.set_variable("myapp", "VAR1", "value1")
        env_manager.set_variable("myapp", "VAR2", "value2")

        assert env_manager.clear_app("myapp") is True
        assert env_manager.list_variables("myapp") == []

    def test_list_apps(self, env_manager):
        """Test listing all apps."""
        env_manager.set_variable("app1", "K", "v")
        env_manager.set_variable("app2", "K", "v")

        apps = env_manager.list_apps()
        assert set(apps) == {"app1", "app2"}

    def test_set_variable_with_type_validation(self, env_manager):
        """Test that variable values are validated against type."""
        # Valid port
        env_manager.set_variable("myapp", "PORT", "3000", var_type="port")
        assert env_manager.get_variable("myapp", "PORT") == "3000"

        # Invalid port should raise
        with pytest.raises(ValueError) as exc_info:
            env_manager.set_variable("myapp", "BAD_PORT", "99999", var_type="port")
        assert "Invalid port" in str(exc_info.value)

    def test_export_env(self, env_manager):
        """Test exporting to .env format."""
        env_manager.set_variable("myapp", "DATABASE_URL", "postgres://localhost/db")
        env_manager.set_variable("myapp", "PORT", "3000")

        content = env_manager.export_env("myapp")

        assert "DATABASE_URL=" in content
        assert "PORT=3000" in content

    def test_export_env_with_encrypted(self, env_manager):
        """Test exporting with encrypted variables."""
        env_manager.set_variable("myapp", "PUBLIC_KEY", "public_value")
        env_manager.set_variable("myapp", "SECRET_KEY", "secret_value", encrypt=True)

        # Without include_encrypted
        content = env_manager.export_env("myapp", include_encrypted=False)
        assert "PUBLIC_KEY=public_value" in content
        assert "secret_value" not in content
        assert "[encrypted" in content.lower()

        # With include_encrypted
        content_with = env_manager.export_env("myapp", include_encrypted=True)
        assert "SECRET_KEY=" in content_with
        assert "secret_value" in content_with

    def test_import_env(self, env_manager):
        """Test importing from .env format."""
        content = """
# Database configuration
DATABASE_URL=postgres://localhost/db
PORT=3000
NODE_ENV=production
"""
        count, errors = env_manager.import_env("myapp", content)

        assert count == 3
        assert errors == []
        assert env_manager.get_variable("myapp", "DATABASE_URL") == "postgres://localhost/db"
        assert env_manager.get_variable("myapp", "PORT") == "3000"
        assert env_manager.get_variable("myapp", "NODE_ENV") == "production"

    def test_import_env_with_quotes(self, env_manager):
        """Test importing values with quotes."""
        content = """
DOUBLE_QUOTED="hello world"
SINGLE_QUOTED='another value'
NO_QUOTES=simple
"""
        count, errors = env_manager.import_env("myapp", content)

        assert count == 3
        assert env_manager.get_variable("myapp", "DOUBLE_QUOTED") == "hello world"
        assert env_manager.get_variable("myapp", "SINGLE_QUOTED") == "another value"
        assert env_manager.get_variable("myapp", "NO_QUOTES") == "simple"

    def test_import_env_with_encryption(self, env_manager):
        """Test importing with selective encryption."""
        content = """
PUBLIC_VAR=public_value
SECRET_VAR=secret_value
"""
        count, errors = env_manager.import_env("myapp", content, encrypt_keys=["SECRET_VAR"])

        assert count == 2

        # PUBLIC_VAR should not be encrypted
        public_info = env_manager.get_variable_info("myapp", "PUBLIC_VAR")
        assert public_info.encrypted is False

        # SECRET_VAR should be encrypted
        secret_info = env_manager.get_variable_info("myapp", "SECRET_VAR")
        assert secret_info.encrypted is True
        assert env_manager.get_variable("myapp", "SECRET_VAR", decrypt=True) == "secret_value"

    def test_import_env_invalid_lines(self, env_manager):
        """Test importing with invalid lines."""
        content = """
VALID=value
invalid line without equals
ALSO_VALID=another
"""
        count, errors = env_manager.import_env("myapp", content)

        assert count == 2
        assert len(errors) == 1
        assert "Line 3" in errors[0]

    def test_load_to_environ(self, env_manager):
        """Test loading variables into os.environ."""
        env_manager.set_variable("myapp", "TEST_VAR_1", "value1")
        env_manager.set_variable("myapp", "TEST_VAR_2", "value2")
        env_manager.set_variable("myapp", "TEST_VAR_SECRET", "secret", encrypt=True)

        # Clean up any existing test vars
        for key in ["TEST_VAR_1", "TEST_VAR_2", "TEST_VAR_SECRET"]:
            if key in os.environ:
                del os.environ[key]

        count = env_manager.load_to_environ("myapp")

        assert count == 3
        assert os.environ.get("TEST_VAR_1") == "value1"
        assert os.environ.get("TEST_VAR_2") == "value2"
        assert os.environ.get("TEST_VAR_SECRET") == "secret"  # Decrypted

        # Clean up
        for key in ["TEST_VAR_1", "TEST_VAR_2", "TEST_VAR_SECRET"]:
            if key in os.environ:
                del os.environ[key]


# =============================================================================
# Template Tests
# =============================================================================


class TestEnvironmentTemplates:
    """Tests for environment templates."""

    def test_builtin_templates_exist(self):
        """Test that built-in templates are defined."""
        assert "nodejs" in BUILTIN_TEMPLATES
        assert "python" in BUILTIN_TEMPLATES
        assert "django" in BUILTIN_TEMPLATES
        assert "flask" in BUILTIN_TEMPLATES
        assert "docker" in BUILTIN_TEMPLATES
        assert "database" in BUILTIN_TEMPLATES
        assert "aws" in BUILTIN_TEMPLATES

    def test_list_templates(self, env_manager):
        """Test listing available templates."""
        templates = env_manager.list_templates()

        assert len(templates) >= 7  # At least the built-in ones
        names = {t.name for t in templates}
        assert "nodejs" in names
        assert "python" in names

    def test_get_template(self, env_manager):
        """Test getting a template by name."""
        template = env_manager.get_template("nodejs")

        assert template is not None
        assert template.name == "nodejs"
        assert "Node" in template.description

        # Should have expected variables
        var_names = {v.name for v in template.variables}
        assert "NODE_ENV" in var_names
        assert "PORT" in var_names

    def test_get_nonexistent_template(self, env_manager):
        """Test getting a non-existent template returns None."""
        result = env_manager.get_template("nonexistent")
        assert result is None

    def test_apply_template_with_defaults(self, env_manager):
        """Test applying a template using default values."""
        result = env_manager.apply_template("nodejs", "myapp")

        assert result.valid is True
        assert result.errors == []

        # Check defaults were applied
        assert env_manager.get_variable("myapp", "NODE_ENV") == "development"
        assert env_manager.get_variable("myapp", "PORT") == "3000"

    def test_apply_template_with_custom_values(self, env_manager):
        """Test applying a template with custom values."""
        result = env_manager.apply_template(
            "nodejs",
            "myapp",
            values={
                "NODE_ENV": "production",
                "PORT": "8080",
            },
        )

        assert result.valid is True
        assert env_manager.get_variable("myapp", "NODE_ENV") == "production"
        assert env_manager.get_variable("myapp", "PORT") == "8080"

    def test_apply_template_missing_required(self, env_manager):
        """Test applying a template with missing required variables."""
        result = env_manager.apply_template(
            "django",
            "myapp",
            values={},  # Missing DJANGO_SETTINGS_MODULE and SECRET_KEY
        )

        assert result.valid is False
        assert any("DJANGO_SETTINGS_MODULE" in e for e in result.errors)
        assert any("SECRET_KEY" in e for e in result.errors)

    def test_apply_template_invalid_value(self, env_manager):
        """Test applying a template with invalid values."""
        result = env_manager.apply_template(
            "nodejs",
            "myapp",
            values={
                "PORT": "not-a-port",
            },
        )

        assert result.valid is False
        assert any("PORT" in e for e in result.errors)

    def test_apply_template_with_encryption(self, env_manager):
        """Test applying a template with some values encrypted."""
        result = env_manager.apply_template(
            "django",
            "myapp",
            values={
                "DJANGO_SETTINGS_MODULE": "myapp.settings",
                "SECRET_KEY": "my-secret-key",
            },
            encrypt_keys=["SECRET_KEY"],
        )

        assert result.valid is True

        # SECRET_KEY should be encrypted
        var_info = env_manager.get_variable_info("myapp", "SECRET_KEY")
        assert var_info.encrypted is True

    def test_apply_nonexistent_template(self, env_manager):
        """Test applying a non-existent template."""
        result = env_manager.apply_template("nonexistent", "myapp")

        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_validate_app_valid(self, env_manager):
        """Test validating an app with valid variables."""
        env_manager.set_variable("myapp", "PORT", "3000", var_type="port")
        env_manager.set_variable("myapp", "DEBUG", "true", var_type="boolean")

        result = env_manager.validate_app("myapp")

        assert result.valid is True
        assert result.errors == []

    def test_validate_app_against_template(self, env_manager):
        """Test validating an app against a template."""
        # Set some variables but miss required ones
        env_manager.set_variable("myapp", "NODE_ENV", "production")

        result = env_manager.validate_app("myapp", template_name="django")

        assert result.valid is False
        assert any("DJANGO_SETTINGS_MODULE" in e for e in result.errors)


# =============================================================================
# Template Dataclass Tests
# =============================================================================


class TestTemplateDataclasses:
    """Tests for template-related dataclasses."""

    def test_template_variable_creation(self):
        """Test creating a TemplateVariable."""
        var = TemplateVariable(
            name="DATABASE_URL",
            required=True,
            default=None,
            var_type="url",
            description="Database connection URL",
        )

        assert var.name == "DATABASE_URL"
        assert var.required is True
        assert var.default is None
        assert var.var_type == "url"

    def test_template_to_dict(self):
        """Test converting template to dictionary."""
        template = EnvironmentTemplate(
            name="test",
            description="Test template",
            variables=[
                TemplateVariable(name="VAR1", required=True),
                TemplateVariable(name="VAR2", required=False, default="default"),
            ],
        )

        data = template.to_dict()

        assert data["name"] == "test"
        assert data["description"] == "Test template"
        assert len(data["variables"]) == 2

    def test_template_from_dict(self):
        """Test creating template from dictionary."""
        data = {
            "name": "custom",
            "description": "Custom template",
            "variables": [
                {"name": "CUSTOM_VAR", "required": True, "var_type": "string"},
            ],
        }

        template = EnvironmentTemplate.from_dict(data)

        assert template.name == "custom"
        assert len(template.variables) == 1
        assert template.variables[0].name == "CUSTOM_VAR"


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_with_errors(self):
        """Test creating an invalid result with errors."""
        result = ValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


# =============================================================================
# get_env_manager Tests
# =============================================================================


class TestGetEnvManager:
    """Tests for the get_env_manager factory function."""

    def test_get_env_manager_returns_instance(self):
        """Test that get_env_manager returns an EnvironmentManager instance."""
        manager = get_env_manager()
        assert isinstance(manager, EnvironmentManager)

    def test_get_env_manager_uses_default_paths(self):
        """Test that default manager uses expected paths."""
        manager = get_env_manager()

        # Should use ~/.cortex/environments
        expected_base = Path.home() / ".cortex" / "environments"
        assert manager.storage.base_path == expected_base

        # Should use ~/.cortex/.env_key
        expected_key = Path.home() / ".cortex" / ".env_key"
        assert manager.encryption.key_path == expected_key


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_app_name(self, env_manager):
        """Test handling of empty app name."""
        # Should still work (empty string is valid)
        env_manager.set_variable("", "KEY", "value")
        assert env_manager.get_variable("", "KEY") == "value"

    def test_special_characters_in_value(self, env_manager):
        """Test handling of special characters in values."""
        special_value = "value with $pecial ch@rs & 'quotes' \"double\" and=equals"
        env_manager.set_variable("myapp", "SPECIAL", special_value)

        retrieved = env_manager.get_variable("myapp", "SPECIAL")
        assert retrieved == special_value

    def test_multiline_value(self, env_manager):
        """Test handling of multiline values."""
        multiline = "line1\nline2\nline3"
        env_manager.set_variable("myapp", "MULTILINE", multiline)

        retrieved = env_manager.get_variable("myapp", "MULTILINE")
        assert retrieved == multiline

    def test_unicode_in_value(self, env_manager):
        """Test handling of unicode characters."""
        unicode_value = "日本語 中文 한국어 🎉"
        env_manager.set_variable("myapp", "UNICODE", unicode_value)

        retrieved = env_manager.get_variable("myapp", "UNICODE")
        assert retrieved == unicode_value

    def test_very_long_value(self, env_manager):
        """Test handling of very long values."""
        long_value = "x" * 100000  # 100KB
        env_manager.set_variable("myapp", "LONG", long_value)

        retrieved = env_manager.get_variable("myapp", "LONG")
        assert retrieved == long_value

    def test_rapid_sequential_writes_same_app(self, env_manager):
        """Test that multiple rapid sequential writes to same app don't lose data."""
        # Write multiple variables rapidly
        for i in range(10):
            env_manager.set_variable("myapp", f"VAR_{i}", f"value_{i}")

        # All should be present
        for i in range(10):
            assert env_manager.get_variable("myapp", f"VAR_{i}") == f"value_{i}"

    def test_overwrite_variable(self, env_manager):
        """Test overwriting an existing variable."""
        env_manager.set_variable("myapp", "KEY", "original")
        env_manager.set_variable("myapp", "KEY", "updated")

        assert env_manager.get_variable("myapp", "KEY") == "updated"

    def test_overwrite_plain_with_encrypted(self, env_manager):
        """Test overwriting a plain variable with encrypted one."""
        env_manager.set_variable("myapp", "KEY", "plain_value", encrypt=False)
        env_manager.set_variable("myapp", "KEY", "secret_value", encrypt=True)

        var_info = env_manager.get_variable_info("myapp", "KEY")
        assert var_info.encrypted is True
        assert env_manager.get_variable("myapp", "KEY", decrypt=True) == "secret_value"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_workflow(self, env_manager):
        """Test a complete workflow: set, list, export, import, delete."""
        # Set some variables
        env_manager.set_variable("myapp", "DATABASE_URL", "postgres://localhost/db")
        env_manager.set_variable("myapp", "API_KEY", "secret123", encrypt=True)
        env_manager.set_variable("myapp", "DEBUG", "false")

        # List variables
        variables = env_manager.list_variables("myapp")
        assert len(variables) == 3

        # Export
        content = env_manager.export_env("myapp", include_encrypted=True)
        assert "DATABASE_URL=" in content
        assert "API_KEY=" in content
        assert "secret123" in content

        # Clear and reimport
        env_manager.clear_app("myapp")
        assert env_manager.list_variables("myapp") == []

        # Import (without encryption this time)
        count, errors = env_manager.import_env("myapp", content)
        assert count >= 2  # At least DATABASE_URL and DEBUG

        # Verify
        assert env_manager.get_variable("myapp", "DATABASE_URL") == "postgres://localhost/db"

    def test_template_then_customize(self, env_manager):
        """Test applying a template then customizing values."""
        # Apply template
        result = env_manager.apply_template(
            "nodejs",
            "myapp",
            values={"NODE_ENV": "development"},
        )
        assert result.valid is True

        # Customize
        env_manager.set_variable("myapp", "NODE_ENV", "production")
        env_manager.set_variable("myapp", "CUSTOM_VAR", "custom_value")

        # Verify
        assert env_manager.get_variable("myapp", "NODE_ENV") == "production"
        assert env_manager.get_variable("myapp", "CUSTOM_VAR") == "custom_value"
        assert env_manager.get_variable("myapp", "PORT") == "3000"  # From template

    def test_multiple_apps_isolation(self, env_manager):
        """Test that multiple apps remain fully isolated."""
        # Set same key with different values in different apps
        env_manager.set_variable("app1", "DATABASE_URL", "postgres://host1/db1")
        env_manager.set_variable("app2", "DATABASE_URL", "postgres://host2/db2")
        env_manager.set_variable("app3", "DATABASE_URL", "postgres://host3/db3")

        # Apply different templates
        env_manager.apply_template("nodejs", "app1", values={"NODE_ENV": "dev"})
        env_manager.apply_template("python", "app2")

        # Verify isolation
        assert env_manager.get_variable("app1", "DATABASE_URL") == "postgres://host1/db1"
        assert env_manager.get_variable("app2", "DATABASE_URL") == "postgres://host2/db2"
        assert env_manager.get_variable("app3", "DATABASE_URL") == "postgres://host3/db3"

        # app1 has NODE_ENV, app2 has PYTHONUNBUFFERED, app3 has neither
        assert env_manager.get_variable("app1", "NODE_ENV") == "dev"
        assert env_manager.get_variable("app2", "PYTHONUNBUFFERED") == "1"
        assert env_manager.get_variable("app3", "NODE_ENV") is None

        # Clearing one app doesn't affect others
        env_manager.clear_app("app2")
        assert env_manager.get_variable("app1", "DATABASE_URL") == "postgres://host1/db1"
        assert env_manager.get_variable("app3", "DATABASE_URL") == "postgres://host3/db3"
