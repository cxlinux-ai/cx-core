#!/usr/bin/env python3
"""
Template System for Cortex Linux Installation Templates

Supports pre-built templates for common development stacks (LAMP, MEAN, MERN, etc.)
and custom template creation, validation, and hardware-aware selection.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.packages import PackageManager, PackageManagerType
from src.hwprofiler import HardwareProfiler


class TemplateFormat(Enum):
    """Supported template formats."""

    YAML = "yaml"
    JSON = "json"


@dataclass
class HardwareRequirements:
    """Hardware requirements for a template."""

    min_ram_mb: int | None = None
    min_cores: int | None = None
    min_storage_mb: int | None = None
    requires_gpu: bool = False
    gpu_vendor: str | None = None  # "NVIDIA", "AMD", "Intel"
    requires_cuda: bool = False
    min_cuda_version: str | None = None


@dataclass
class InstallationStep:
    """A single installation step in a template."""

    command: str
    description: str
    rollback: str | None = None
    verify: str | None = None
    requires_root: bool = True


@dataclass
class Template:
    """Represents an installation template."""

    name: str
    description: str
    version: str
    author: str | None = None
    packages: list[str] = field(default_factory=list)
    steps: list[InstallationStep] = field(default_factory=list)
    hardware_requirements: HardwareRequirements | None = None
    post_install: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert template to dictionary."""
        result = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "packages": self.packages,
            "post_install": self.post_install,
            "verification_commands": self.verification_commands,
            "metadata": self.metadata,
        }

        if self.author:
            result["author"] = self.author

        if self.steps:
            result["steps"] = [
                {
                    "command": step.command,
                    "description": step.description,
                    "rollback": step.rollback,
                    "verify": step.verify,
                    "requires_root": step.requires_root,
                }
                for step in self.steps
            ]

        if self.hardware_requirements:
            hw = self.hardware_requirements
            result["hardware_requirements"] = {
                "min_ram_mb": hw.min_ram_mb,
                "min_cores": hw.min_cores,
                "min_storage_mb": hw.min_storage_mb,
                "requires_gpu": hw.requires_gpu,
                "gpu_vendor": hw.gpu_vendor,
                "requires_cuda": hw.requires_cuda,
                "min_cuda_version": hw.min_cuda_version,
            }

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Template":
        """Create template from dictionary."""
        # Parse hardware requirements
        hw_req = None
        if "hardware_requirements" in data:
            hw_data = data["hardware_requirements"]
            hw_req = HardwareRequirements(
                min_ram_mb=hw_data.get("min_ram_mb"),
                min_cores=hw_data.get("min_cores"),
                min_storage_mb=hw_data.get("min_storage_mb"),
                requires_gpu=hw_data.get("requires_gpu", False),
                gpu_vendor=hw_data.get("gpu_vendor"),
                requires_cuda=hw_data.get("requires_cuda", False),
                min_cuda_version=hw_data.get("min_cuda_version"),
            )

        # Parse installation steps
        steps = []
        if "steps" in data:
            for step_data in data["steps"]:
                steps.append(
                    InstallationStep(
                        command=step_data["command"],
                        description=step_data.get("description", ""),
                        rollback=step_data.get("rollback"),
                        verify=step_data.get("verify"),
                        requires_root=step_data.get("requires_root", True),
                    )
                )

        return cls(
            name=data["name"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            author=data.get("author"),
            packages=data.get("packages", []),
            steps=steps,
            hardware_requirements=hw_req,
            post_install=data.get("post_install", []),
            verification_commands=data.get("verification_commands", []),
            metadata=data.get("metadata", {}),
        )


class TemplateValidator:
    """Validates template structure and content."""

    REQUIRED_FIELDS = ["name", "description", "version"]
    REQUIRED_STEP_FIELDS = ["command", "description"]

    # Allowed post_install commands (whitelist for security)
    ALLOWED_POST_INSTALL_COMMANDS = {
        "echo",  # Safe echo commands
    }

    # Dangerous shell metacharacters that should be rejected
    DANGEROUS_SHELL_CHARS = [";", "|", "&", ">", "<", "`", "\\"]

    @staticmethod
    def _validate_post_install_commands(post_install: list[str]) -> list[str]:
        """
        Validate post_install commands for security.

        Returns:
            List of validation errors
        """
        errors = []

        for i, cmd in enumerate(post_install):
            if not cmd or not cmd.strip():
                continue

            cmd_stripped = cmd.strip()

            # Check for dangerous shell metacharacters
            for char in TemplateValidator.DANGEROUS_SHELL_CHARS:
                if char in cmd_stripped:
                    errors.append(
                        f"post_install[{i}]: Contains dangerous shell character '{char}'. "
                        "Only safe commands like 'echo' are allowed."
                    )
                    break

            # Check for command substitution patterns
            if "$(" in cmd_stripped or "`" in cmd_stripped:
                # Allow $(...) in echo commands for version checks (built-in templates use this)
                if not cmd_stripped.startswith("echo "):
                    errors.append(
                        f"post_install[{i}]: Command substitution only allowed in 'echo' commands"
                    )

            # Check for wildcards/globs
            if "*" in cmd_stripped or "?" in cmd_stripped:
                if not cmd_stripped.startswith("echo "):
                    errors.append(f"post_install[{i}]: Wildcards only allowed in 'echo' commands")

            # Whitelist check - only allow echo commands
            if not cmd_stripped.startswith("echo "):
                errors.append(
                    f"post_install[{i}]: Only 'echo' commands are allowed in post_install. "
                    f"Found: {cmd_stripped[:50]}"
                )

        return errors

    @staticmethod
    def validate(template: Template) -> tuple[bool, list[str]]:
        """
        Validate a template.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check required fields
        if not template.name:
            errors.append("Template name is required")
        if not template.description:
            errors.append("Template description is required")
        if not template.version:
            errors.append("Template version is required")

        # Validate steps
        for i, step in enumerate(template.steps):
            if not step.command:
                errors.append(f"Step {i+1}: command is required")
            if not step.description:
                errors.append(f"Step {i+1}: description is required")

        # Validate packages list
        if not template.packages and not template.steps:
            errors.append("Template must have either packages or steps defined")

        # Validate hardware requirements
        if template.hardware_requirements:
            hw = template.hardware_requirements
            if hw.min_ram_mb is not None and hw.min_ram_mb < 0:
                errors.append("min_ram_mb must be non-negative")
            if hw.min_cores is not None and hw.min_cores < 0:
                errors.append("min_cores must be non-negative")
            if hw.min_storage_mb is not None and hw.min_storage_mb < 0:
                errors.append("min_storage_mb must be non-negative")
            if hw.requires_cuda and not hw.requires_gpu:
                errors.append("requires_cuda is true but requires_gpu is false")

        # Validate post_install commands for security
        if template.post_install:
            post_install_errors = TemplateValidator._validate_post_install_commands(
                template.post_install
            )
            errors.extend(post_install_errors)

        return len(errors) == 0, errors


class TemplateManager:
    """Manages installation templates."""

    def __init__(self, templates_dir: str | None = None):
        """
        Initialize template manager.

        Args:
            templates_dir: Directory containing templates (defaults to built-in templates)
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Default to built-in templates directory
            base_dir = Path(__file__).parent
            self.templates_dir = base_dir / "templates"

        self.user_templates_dir = Path.home() / ".cortex" / "templates"
        self.user_templates_dir.mkdir(parents=True, exist_ok=True)

        self._templates_cache: dict[str, Template] = {}
        self._hardware_profiler = HardwareProfiler()
        self._package_manager = PackageManager()

    def _get_template_path(self, name: str) -> Path | None:
        """Find template file by name."""
        # Check user templates first
        for ext in [".yaml", ".yml", ".json"]:
            user_path = self.user_templates_dir / f"{name}{ext}"
            if user_path.exists():
                return user_path

        # Check built-in templates
        for ext in [".yaml", ".yml", ".json"]:
            builtin_path = self.templates_dir / f"{name}{ext}"
            if builtin_path.exists():
                return builtin_path

        return None

    def load_template(self, name: str) -> Template | None:
        """Load a template by name."""
        if name in self._templates_cache:
            return self._templates_cache[name]

        template_path = self._get_template_path(name)
        if not template_path:
            return None

        try:
            with open(template_path, encoding="utf-8") as f:
                if template_path.suffix in [".yaml", ".yml"]:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

            template = Template.from_dict(data)
            self._templates_cache[name] = template
            return template
        except Exception as e:
            raise ValueError(f"Failed to load template {name}: {str(e)}")

    def save_template(
        self,
        template: Template,
        name: str | None = None,
        format: TemplateFormat = TemplateFormat.YAML,
    ) -> Path:
        """
        Save a template to user templates directory.

        Args:
            template: Template to save
            name: Template name (defaults to template.name)
            format: File format (YAML or JSON)

        Returns:
            Path to saved template file
        """
        # Validate template
        is_valid, errors = TemplateValidator.validate(template)
        if not is_valid:
            raise ValueError(f"Template validation failed: {', '.join(errors)}")

        template_name = name or template.name
        ext = ".yaml" if format == TemplateFormat.YAML else ".json"
        template_path = self.user_templates_dir / f"{template_name}{ext}"

        data = template.to_dict()

        with open(template_path, "w", encoding="utf-8") as f:
            if format == TemplateFormat.YAML:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2)

        return template_path

    def list_templates(self) -> dict[str, dict[str, Any]]:
        """List all available templates."""
        templates = {}

        # List built-in templates (load directly from file to avoid user overrides)
        if self.templates_dir.exists():
            for ext in [".yaml", ".yml", ".json"]:
                for template_file in self.templates_dir.glob(f"*{ext}"):
                    name = template_file.stem
                    if name in templates:
                        # Skip duplicate names across extensions
                        continue
                    try:
                        with open(template_file, "r", encoding="utf-8") as f:
                            if template_file.suffix in [".yaml", ".yml"]:
                                data = yaml.safe_load(f)
                            else:
                                data = json.load(f)
                        template = Template.from_dict(data)
                        templates[name] = {
                            "name": template.name,
                            "description": template.description,
                            "version": template.version,
                            "author": template.author,
                            "type": "built-in",
                            "path": str(template_file),
                        }
                    except Exception:
                        # Ignore malformed built-ins but continue listing others
                        pass

        # List user templates
        if self.user_templates_dir.exists():
            for ext in [".yaml", ".yml", ".json"]:
                for template_file in self.user_templates_dir.glob(f"*{ext}"):
                    name = template_file.stem
                    if name not in templates:  # Don't override built-in
                        try:
                            template = self.load_template(name)
                            if template:
                                templates[name] = {
                                    "name": template.name,
                                    "description": template.description,
                                    "version": template.version,
                                    "author": template.author,
                                    "type": "user",
                                    "path": str(template_file),
                                }
                        except Exception:
                            pass

        return templates

    def check_hardware_compatibility(self, template: Template) -> tuple[bool, list[str]]:
        """
        Check if current hardware meets template requirements.

        Returns:
            Tuple of (is_compatible, list_of_warnings)
        """
        if not template.hardware_requirements:
            return True, []

        hw_profile = self._hardware_profiler.profile()
        hw_req = template.hardware_requirements
        warnings = []

        # Check RAM
        if hw_req.min_ram_mb:
            available_ram = hw_profile.get("ram", 0)
            if available_ram < hw_req.min_ram_mb:
                warnings.append(
                    f"Insufficient RAM: {available_ram}MB available, "
                    f"{hw_req.min_ram_mb}MB required"
                )

        # Check CPU cores
        if hw_req.min_cores:
            available_cores = hw_profile.get("cpu", {}).get("cores", 0)
            if available_cores < hw_req.min_cores:
                warnings.append(
                    f"Insufficient CPU cores: {available_cores} available, "
                    f"{hw_req.min_cores} required"
                )

        # Check storage
        if hw_req.min_storage_mb:
            total_storage = sum(s.get("size", 0) for s in hw_profile.get("storage", []))
            if total_storage < hw_req.min_storage_mb:
                warnings.append(
                    f"Insufficient storage: {total_storage}MB available, "
                    f"{hw_req.min_storage_mb}MB required"
                )

        # Check GPU requirements
        if hw_req.requires_gpu:
            gpus = hw_profile.get("gpu", [])
            if not gpus:
                warnings.append("GPU required but not detected")
            elif hw_req.gpu_vendor:
                vendor_match = any(g.get("vendor") == hw_req.gpu_vendor for g in gpus)
                if not vendor_match:
                    warnings.append(f"{hw_req.gpu_vendor} GPU required but not found")

        # Check CUDA requirements
        if hw_req.requires_cuda:
            gpus = hw_profile.get("gpu", [])
            cuda_found = False
            for gpu in gpus:
                if gpu.get("vendor") == "NVIDIA" and gpu.get("cuda"):
                    cuda_version = gpu.get("cuda", "")
                    if hw_req.min_cuda_version:
                        # Simple version comparison
                        try:
                            gpu_cuda = tuple(map(int, cuda_version.split(".")))
                            req_cuda = tuple(map(int, hw_req.min_cuda_version.split(".")))
                            if gpu_cuda >= req_cuda:
                                cuda_found = True
                                break
                        except ValueError:
                            # If version parsing fails, just check if CUDA exists
                            cuda_found = True
                            break
                    else:
                        cuda_found = True
                        break

            if not cuda_found:
                warnings.append(f"CUDA {hw_req.min_cuda_version or ''} required but not found")

        is_compatible = len(warnings) == 0
        return is_compatible, warnings

    def generate_commands(self, template: Template) -> list[str]:
        """
        Generate installation commands from template.

        Returns:
            List of installation commands
        """
        commands = []

        # If template has explicit steps, use those
        if template.steps:
            commands = [step.command for step in template.steps]
        # Otherwise, generate from packages
        elif template.packages:
            # Use package manager to generate commands
            pm = PackageManager()
            package_list = " ".join(template.packages)
            try:
                commands = pm.parse(f"install {package_list}")
            except ValueError:
                # Fallback: direct apt/yum install
                pm_type = pm.pm_type.value
                commands = [f"{pm_type} install -y {' '.join(template.packages)}"]

        return commands

    def import_template(self, file_path: str, name: str | None = None) -> Template:
        """
        Import a template from a file.

        Args:
            file_path: Path to template file
            name: Optional new name for the template

        Returns:
            Loaded template
        """
        template_path = Path(file_path)
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {file_path}")

        try:
            with open(template_path, encoding="utf-8") as f:
                if template_path.suffix in [".yaml", ".yml"]:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

            template = Template.from_dict(data)

            # Override name if provided
            if name:
                template.name = name

            # Validate
            is_valid, errors = TemplateValidator.validate(template)
            if not is_valid:
                raise ValueError(f"Template validation failed: {', '.join(errors)}")

            return template
        except Exception as e:
            raise ValueError(f"Failed to import template: {str(e)}")

    def export_template(
        self, name: str, file_path: str, format: TemplateFormat = TemplateFormat.YAML
    ) -> Path:
        """
        Export a template to a file.

        Args:
            name: Template name
            file_path: Destination file path
            format: File format

        Returns:
            Path to exported file
        """
        template = self.load_template(name)
        if not template:
            raise ValueError(f"Template not found: {name}")

        export_path = Path(file_path)
        data = template.to_dict()

        with open(export_path, "w", encoding="utf-8") as f:
            if format == TemplateFormat.YAML:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2)

        return export_path
