"""
Role Manager for Cortex Linux
Manages role-based prompt customization for specialized tasks.

Roles allow users to switch between different personas (security, devops, etc.)
that modify how the LLM interprets and generates commands.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class RoleError(Exception):
    """Custom exception for role-related errors"""

    pass


class RoleNotFoundError(RoleError):
    """Raised when a role cannot be found"""

    pass


class RoleValidationError(RoleError):
    """Raised when a role fails validation"""

    pass


@dataclass
class Role:
    """Represents a Cortex role with its configuration"""

    name: str
    description: str
    prompt_additions: str
    priorities: list[str] = field(default_factory=list)
    is_builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert role to dictionary for YAML serialization"""
        return {
            "name": self.name,
            "description": self.description,
            "prompt_additions": self.prompt_additions,
            "priorities": self.priorities,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], is_builtin: bool = False) -> "Role":
        """Create a Role from a dictionary"""
        return cls(
            name=data.get("name", "unknown"),
            description=data.get("description", ""),
            prompt_additions=data.get("prompt_additions", ""),
            priorities=data.get("priorities", []),
            is_builtin=is_builtin,
        )


class RoleManager:
    """
    Manages role loading, creation, and validation.

    Roles are loaded from two locations:
    1. Built-in roles: Bundled with the cortex package (cortex/roles/)
    2. Custom roles: User-defined roles (~/.cortex/roles/)

    Custom roles take precedence over built-in roles with the same name.
    """

    # Built-in role names
    BUILTIN_ROLES = ["default", "security", "devops", "datascience", "sysadmin"]

    def __init__(self):
        """Initialize the RoleManager"""
        # Built-in roles directory (relative to this file)
        self.builtin_roles_dir = Path(__file__).parent / "roles"

        # Custom roles directory
        self.custom_roles_dir = Path.home() / ".cortex" / "roles"
        self.custom_roles_dir.mkdir(parents=True, exist_ok=True)

        # Cache for loaded roles
        self._roles_cache: dict[str, Role] = {}

    def _load_role_from_file(self, filepath: Path, is_builtin: bool = False) -> Role:
        """
        Load a role from a YAML file.

        Args:
            filepath: Path to the YAML file
            is_builtin: Whether this is a built-in role

        Returns:
            Role object

        Raises:
            RoleValidationError: If the role file is invalid
        """
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)

            if not data:
                raise RoleValidationError(f"Empty role file: {filepath}")

            role = Role.from_dict(data, is_builtin=is_builtin)
            self._validate_role(role)
            return role

        except yaml.YAMLError as e:
            raise RoleValidationError(f"Invalid YAML in role file {filepath}: {e}")
        except OSError as e:
            raise RoleNotFoundError(f"Cannot read role file {filepath}: {e}")

    def _validate_role(self, role: Role) -> None:
        """
        Validate a role's structure and content.

        Args:
            role: Role to validate

        Raises:
            RoleValidationError: If validation fails
        """
        if not role.name:
            raise RoleValidationError("Role must have a name")

        if not role.name.isidentifier() and not role.name.replace("-", "_").isidentifier():
            raise RoleValidationError(
                f"Invalid role name '{role.name}'. Use alphanumeric characters and hyphens only."
            )

        if not role.description:
            raise RoleValidationError("Role must have a description")

        if not role.prompt_additions:
            raise RoleValidationError("Role must have prompt_additions")

    def get_role(self, name: str) -> Role:
        """
        Get a role by name.

        Custom roles take precedence over built-in roles.

        Args:
            name: Role name

        Returns:
            Role object

        Raises:
            RoleNotFoundError: If role doesn't exist
        """
        # Check cache first
        if name in self._roles_cache:
            return self._roles_cache[name]

        # Try custom role first
        custom_path = self.custom_roles_dir / f"{name}.yaml"
        if custom_path.exists():
            role = self._load_role_from_file(custom_path, is_builtin=False)
            self._roles_cache[name] = role
            return role

        # Try built-in role
        builtin_path = self.builtin_roles_dir / f"{name}.yaml"
        if builtin_path.exists():
            role = self._load_role_from_file(builtin_path, is_builtin=True)
            self._roles_cache[name] = role
            return role

        raise RoleNotFoundError(f"Role '{name}' not found")

    def list_roles(self) -> list[dict[str, Any]]:
        """
        List all available roles (built-in and custom).

        Returns:
            List of role info dictionaries with keys: name, description, is_builtin, is_custom_override
        """
        roles = []
        seen_names = set()

        # List custom roles first (they take precedence)
        if self.custom_roles_dir.exists():
            for filepath in sorted(self.custom_roles_dir.glob("*.yaml")):
                try:
                    role = self._load_role_from_file(filepath, is_builtin=False)
                    is_override = role.name in self.BUILTIN_ROLES
                    roles.append(
                        {
                            "name": role.name,
                            "description": role.description,
                            "is_builtin": False,
                            "is_custom_override": is_override,
                            "priorities": role.priorities,
                        }
                    )
                    seen_names.add(role.name)
                except RoleError:
                    # Skip invalid role files
                    continue

        # List built-in roles (skip if overridden by custom)
        if self.builtin_roles_dir.exists():
            for filepath in sorted(self.builtin_roles_dir.glob("*.yaml")):
                try:
                    role = self._load_role_from_file(filepath, is_builtin=True)
                    if role.name not in seen_names:
                        roles.append(
                            {
                                "name": role.name,
                                "description": role.description,
                                "is_builtin": True,
                                "is_custom_override": False,
                                "priorities": role.priorities,
                            }
                        )
                        seen_names.add(role.name)
                except RoleError:
                    continue

        return roles

    def create_role(
        self,
        name: str,
        description: str,
        prompt_additions: str,
        priorities: list[str] | None = None,
        from_template: str | None = None,
    ) -> Role:
        """
        Create a new custom role.

        Args:
            name: Role name (alphanumeric and hyphens)
            description: Short description of the role
            prompt_additions: Additional prompt text for the LLM
            priorities: Optional list of priorities
            from_template: Optional existing role name to copy from

        Returns:
            Created Role object

        Raises:
            RoleError: If creation fails
        """
        # If copying from template, load it first
        if from_template:
            template_role = self.get_role(from_template)
            if not description:
                description = f"Custom role based on {from_template}"
            if not prompt_additions:
                prompt_additions = template_role.prompt_additions
            if not priorities:
                priorities = template_role.priorities.copy()

        role = Role(
            name=name,
            description=description,
            prompt_additions=prompt_additions,
            priorities=priorities or [],
            is_builtin=False,
        )

        # Validate
        self._validate_role(role)

        # Save to file
        filepath = self.custom_roles_dir / f"{name}.yaml"
        self._save_role(role, filepath)

        # Clear cache for this role
        self._roles_cache.pop(name, None)

        return role

    def _save_role(self, role: Role, filepath: Path) -> None:
        """
        Save a role to a YAML file.

        Args:
            role: Role to save
            filepath: Destination path
        """
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically
        temp_path = filepath.with_suffix(".yaml.tmp")
        try:
            with open(temp_path, "w") as f:
                yaml.dump(role.to_dict(), f, default_flow_style=False, sort_keys=False)
            temp_path.replace(filepath)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise RoleError(f"Failed to save role: {e}")

    def delete_role(self, name: str) -> bool:
        """
        Delete a custom role.

        Args:
            name: Role name to delete

        Returns:
            True if deleted

        Raises:
            RoleError: If deletion fails or trying to delete built-in role
        """
        # Check if it's a built-in role without custom override
        builtin_path = self.builtin_roles_dir / f"{name}.yaml"
        custom_path = self.custom_roles_dir / f"{name}.yaml"

        if builtin_path.exists() and not custom_path.exists():
            raise RoleError(f"Cannot delete built-in role '{name}'")

        if not custom_path.exists():
            raise RoleNotFoundError(f"Custom role '{name}' not found")

        try:
            custom_path.unlink()
            self._roles_cache.pop(name, None)
            return True
        except OSError as e:
            raise RoleError(f"Failed to delete role '{name}': {e}")

    def get_role_template(self) -> str:
        """
        Get a template for creating new roles.

        Returns:
            YAML template string
        """
        return '''name: my-custom-role
description: "Brief description of what this role does"
prompt_additions: |
  Additional guidelines for this role:
  - Specific instruction 1
  - Specific instruction 2
  - Focus areas and priorities
priorities:
  - priority1
  - priority2
'''

    def role_exists(self, name: str) -> bool:
        """
        Check if a role exists.

        Args:
            name: Role name

        Returns:
            True if role exists (built-in or custom)
        """
        custom_path = self.custom_roles_dir / f"{name}.yaml"
        builtin_path = self.builtin_roles_dir / f"{name}.yaml"
        return custom_path.exists() or builtin_path.exists()

    def clear_cache(self) -> None:
        """Clear the roles cache"""
        self._roles_cache.clear()

