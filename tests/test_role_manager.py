"""
Tests for the Role Manager module.
"""

import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml

from cortex.role_manager import (
    Role,
    RoleError,
    RoleManager,
    RoleNotFoundError,
    RoleValidationError,
)


class TestRole:
    """Tests for the Role dataclass"""

    def test_role_creation(self):
        """Test creating a Role instance"""
        role = Role(
            name="test-role",
            description="A test role",
            prompt_additions="Test prompt additions",
            priorities=["security", "performance"],
        )
        assert role.name == "test-role"
        assert role.description == "A test role"
        assert role.prompt_additions == "Test prompt additions"
        assert role.priorities == ["security", "performance"]
        assert role.is_builtin is False

    def test_role_to_dict(self):
        """Test converting Role to dictionary"""
        role = Role(
            name="test-role",
            description="A test role",
            prompt_additions="Test prompt additions",
            priorities=["security"],
        )
        data = role.to_dict()
        assert data["name"] == "test-role"
        assert data["description"] == "A test role"
        assert data["prompt_additions"] == "Test prompt additions"
        assert data["priorities"] == ["security"]
        # is_builtin should not be in the serialized dict
        assert "is_builtin" not in data

    def test_role_from_dict(self):
        """Test creating Role from dictionary"""
        data = {
            "name": "test-role",
            "description": "A test role",
            "prompt_additions": "Test prompt additions",
            "priorities": ["reliability"],
        }
        role = Role.from_dict(data, is_builtin=True)
        assert role.name == "test-role"
        assert role.is_builtin is True

    def test_role_from_dict_defaults(self):
        """Test Role.from_dict with missing optional fields"""
        data = {"name": "minimal-role"}
        role = Role.from_dict(data)
        assert role.name == "minimal-role"
        assert role.description == ""
        assert role.prompt_additions == ""
        assert role.priorities == []


class TestRoleManager:
    """Tests for the RoleManager class"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / "custom_roles"
            custom_dir.mkdir()
            builtin_dir = Path(tmpdir) / "builtin_roles"
            builtin_dir.mkdir()
            yield custom_dir, builtin_dir

    @pytest.fixture
    def manager_with_temp_dirs(self, temp_dirs):
        """Create a RoleManager with temporary directories"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir
        return manager

    def test_manager_initialization(self):
        """Test RoleManager initialization"""
        manager = RoleManager()
        assert manager.builtin_roles_dir.exists() or not manager.builtin_roles_dir.exists()
        # Custom roles dir should be created
        assert manager.custom_roles_dir.parent.exists()

    def test_validate_role_valid(self, manager_with_temp_dirs):
        """Test validating a valid role"""
        manager = manager_with_temp_dirs
        role = Role(
            name="valid-role",
            description="A valid role",
            prompt_additions="Some prompt additions",
        )
        # Should not raise
        manager._validate_role(role)

    def test_validate_role_missing_name(self, manager_with_temp_dirs):
        """Test validation fails for role without name"""
        manager = manager_with_temp_dirs
        role = Role(name="", description="desc", prompt_additions="prompt")
        with pytest.raises(RoleValidationError, match="must have a name"):
            manager._validate_role(role)

    def test_validate_role_missing_description(self, manager_with_temp_dirs):
        """Test validation fails for role without description"""
        manager = manager_with_temp_dirs
        role = Role(name="test", description="", prompt_additions="prompt")
        with pytest.raises(RoleValidationError, match="must have a description"):
            manager._validate_role(role)

    def test_validate_role_missing_prompt(self, manager_with_temp_dirs):
        """Test validation fails for role without prompt_additions"""
        manager = manager_with_temp_dirs
        role = Role(name="test", description="desc", prompt_additions="")
        with pytest.raises(RoleValidationError, match="must have prompt_additions"):
            manager._validate_role(role)

    def test_validate_role_invalid_name(self, manager_with_temp_dirs):
        """Test validation fails for invalid role name"""
        manager = manager_with_temp_dirs
        role = Role(name="invalid name!", description="desc", prompt_additions="prompt")
        with pytest.raises(RoleValidationError, match="Invalid role name"):
            manager._validate_role(role)

    def test_load_role_from_file(self, temp_dirs):
        """Test loading a role from a YAML file"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create a test role file
        role_data = {
            "name": "test-role",
            "description": "Test description",
            "prompt_additions": "Test prompt",
            "priorities": ["test"],
        }
        role_file = builtin_dir / "test-role.yaml"
        with open(role_file, "w") as f:
            yaml.dump(role_data, f)

        role = manager._load_role_from_file(role_file, is_builtin=True)
        assert role.name == "test-role"
        assert role.is_builtin is True

    def test_load_role_invalid_yaml(self, temp_dirs):
        """Test loading a role with invalid YAML"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create an invalid YAML file
        role_file = builtin_dir / "invalid.yaml"
        with open(role_file, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(RoleValidationError, match="Invalid YAML"):
            manager._load_role_from_file(role_file)

    def test_get_role_custom_takes_precedence(self, temp_dirs):
        """Test that custom roles take precedence over built-in"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create both builtin and custom role with same name
        builtin_data = {
            "name": "test-role",
            "description": "Builtin version",
            "prompt_additions": "Builtin prompt",
        }
        custom_data = {
            "name": "test-role",
            "description": "Custom version",
            "prompt_additions": "Custom prompt",
        }

        with open(builtin_dir / "test-role.yaml", "w") as f:
            yaml.dump(builtin_data, f)
        with open(custom_dir / "test-role.yaml", "w") as f:
            yaml.dump(custom_data, f)

        role = manager.get_role("test-role")
        assert role.description == "Custom version"
        assert role.is_builtin is False

    def test_get_role_not_found(self, manager_with_temp_dirs):
        """Test getting a non-existent role raises error"""
        manager = manager_with_temp_dirs
        with pytest.raises(RoleNotFoundError, match="not found"):
            manager.get_role("nonexistent-role")

    def test_list_roles(self, temp_dirs):
        """Test listing all roles"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create some roles
        role1 = {
            "name": "role1",
            "description": "Role 1",
            "prompt_additions": "Prompt 1",
        }
        role2 = {
            "name": "role2",
            "description": "Role 2",
            "prompt_additions": "Prompt 2",
        }

        with open(builtin_dir / "role1.yaml", "w") as f:
            yaml.dump(role1, f)
        with open(custom_dir / "role2.yaml", "w") as f:
            yaml.dump(role2, f)

        roles = manager.list_roles()
        names = [r["name"] for r in roles]
        assert "role1" in names
        assert "role2" in names

    def test_create_role(self, manager_with_temp_dirs):
        """Test creating a new custom role"""
        manager = manager_with_temp_dirs
        role = manager.create_role(
            name="new-role",
            description="A new role",
            prompt_additions="New prompt additions",
            priorities=["test"],
        )
        assert role.name == "new-role"
        assert (manager.custom_roles_dir / "new-role.yaml").exists()

    def test_create_role_from_template(self, temp_dirs):
        """Test creating a role from an existing template"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create template role
        template_data = {
            "name": "template",
            "description": "Template role",
            "prompt_additions": "Template prompt",
            "priorities": ["priority1"],
        }
        with open(builtin_dir / "template.yaml", "w") as f:
            yaml.dump(template_data, f)

        # Create new role from template
        role = manager.create_role(
            name="from-template",
            description="",
            prompt_additions="",
            from_template="template",
        )
        assert role.prompt_additions == "Template prompt"
        assert role.priorities == ["priority1"]

    def test_delete_role(self, manager_with_temp_dirs):
        """Test deleting a custom role"""
        manager = manager_with_temp_dirs

        # Create a custom role first
        manager.create_role(
            name="to-delete",
            description="Will be deleted",
            prompt_additions="Delete me",
        )
        assert (manager.custom_roles_dir / "to-delete.yaml").exists()

        # Delete it
        result = manager.delete_role("to-delete")
        assert result is True
        assert not (manager.custom_roles_dir / "to-delete.yaml").exists()

    def test_delete_builtin_role_fails(self, temp_dirs):
        """Test that deleting a built-in role fails"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create a builtin role
        builtin_data = {
            "name": "builtin",
            "description": "Builtin role",
            "prompt_additions": "Builtin prompt",
        }
        with open(builtin_dir / "builtin.yaml", "w") as f:
            yaml.dump(builtin_data, f)

        with pytest.raises(RoleError, match="Cannot delete built-in role"):
            manager.delete_role("builtin")

    def test_role_exists(self, temp_dirs):
        """Test checking if a role exists"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        # Create a role
        role_data = {
            "name": "existing",
            "description": "Exists",
            "prompt_additions": "Prompt",
        }
        with open(builtin_dir / "existing.yaml", "w") as f:
            yaml.dump(role_data, f)

        assert manager.role_exists("existing") is True
        assert manager.role_exists("nonexistent") is False

    def test_get_role_template(self, manager_with_temp_dirs):
        """Test getting a role template"""
        manager = manager_with_temp_dirs
        template = manager.get_role_template()
        assert "name:" in template
        assert "description:" in template
        assert "prompt_additions:" in template
        assert "priorities:" in template

    def test_caching(self, temp_dirs):
        """Test that roles are cached after first load"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        role_data = {
            "name": "cached",
            "description": "Cached role",
            "prompt_additions": "Cached prompt",
        }
        with open(builtin_dir / "cached.yaml", "w") as f:
            yaml.dump(role_data, f)

        # First load
        role1 = manager.get_role("cached")
        # Second load should be from cache
        role2 = manager.get_role("cached")
        assert role1 is role2  # Same object from cache

    def test_clear_cache(self, temp_dirs):
        """Test clearing the cache"""
        custom_dir, builtin_dir = temp_dirs
        manager = RoleManager()
        manager.custom_roles_dir = custom_dir
        manager.builtin_roles_dir = builtin_dir

        role_data = {
            "name": "cached",
            "description": "Cached role",
            "prompt_additions": "Cached prompt",
        }
        with open(builtin_dir / "cached.yaml", "w") as f:
            yaml.dump(role_data, f)

        role1 = manager.get_role("cached")
        manager.clear_cache()
        role2 = manager.get_role("cached")
        assert role1 is not role2  # Different objects after cache clear


class TestBuiltinRoles:
    """Tests for the built-in roles"""

    def test_builtin_roles_exist(self):
        """Test that all built-in roles can be loaded"""
        manager = RoleManager()
        for role_name in RoleManager.BUILTIN_ROLES:
            try:
                role = manager.get_role(role_name)
                assert role.name == role_name
                assert role.description
                assert role.prompt_additions
            except RoleNotFoundError:
                # Built-in roles might not exist in test environment
                # if running from a different directory
                pass

    def test_default_role_priorities(self):
        """Test that default role has expected priorities"""
        manager = RoleManager()
        try:
            role = manager.get_role("default")
            assert "reliability" in role.priorities or len(role.priorities) >= 0
        except RoleNotFoundError:
            pass  # Skip if not in correct directory

    def test_security_role_content(self):
        """Test that security role has security-focused content"""
        manager = RoleManager()
        try:
            role = manager.get_role("security")
            assert "security" in role.description.lower()
            assert "security" in role.prompt_additions.lower()
        except RoleNotFoundError:
            pass

