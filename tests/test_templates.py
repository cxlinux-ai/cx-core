#!/usr/bin/env python3
"""
Unit tests for Cortex Linux Template System
"""

import unittest
import tempfile
import shutil
import os
import json
import yaml
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.templates import (
    Template,
    TemplateManager,
    TemplateValidator,
    TemplateFormat,
    HardwareRequirements,
    InstallationStep
)


class TestTemplate(unittest.TestCase):
    """Test Template dataclass."""
    
    def test_template_creation(self):
        """Test creating a template."""
        template = Template(
            name="test-template",
            description="Test template",
            version="1.0.0",
            author="Test Author",
            packages=["package1", "package2"]
        )
        
        self.assertEqual(template.name, "test-template")
        self.assertEqual(template.description, "Test template")
        self.assertEqual(template.version, "1.0.0")
        self.assertEqual(template.author, "Test Author")
        self.assertEqual(len(template.packages), 2)
    
    def test_template_to_dict(self):
        """Test converting template to dictionary."""
        template = Template(
            name="test",
            description="Test",
            version="1.0.0",
            packages=["pkg1", "pkg2"]
        )
        
        data = template.to_dict()
        
        self.assertEqual(data["name"], "test")
        self.assertEqual(data["description"], "Test")
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["packages"], ["pkg1", "pkg2"])
    
    def test_template_from_dict(self):
        """Test creating template from dictionary."""
        data = {
            "name": "test",
            "description": "Test description",
            "version": "1.0.0",
            "packages": ["pkg1", "pkg2"],
            "steps": [
                {
                    "command": "apt install pkg1",
                    "description": "Install package 1",
                    "requires_root": True
                }
            ]
        }
        
        template = Template.from_dict(data)
        
        self.assertEqual(template.name, "test")
        self.assertEqual(template.description, "Test description")
        self.assertEqual(len(template.packages), 2)
        self.assertEqual(len(template.steps), 1)
        self.assertEqual(template.steps[0].command, "apt install pkg1")
    
    def test_template_with_hardware_requirements(self):
        """Test template with hardware requirements."""
        hw_req = HardwareRequirements(
            min_ram_mb=4096,
            min_cores=4,
            requires_gpu=True,
            gpu_vendor="NVIDIA"
        )
        
        template = Template(
            name="gpu-template",
            description="GPU template",
            version="1.0.0",
            hardware_requirements=hw_req
        )
        
        self.assertIsNotNone(template.hardware_requirements)
        self.assertEqual(template.hardware_requirements.min_ram_mb, 4096)
        self.assertEqual(template.hardware_requirements.requires_gpu, True)


class TestTemplateValidator(unittest.TestCase):
    """Test TemplateValidator."""
    
    def test_validate_valid_template(self):
        """Test validating a valid template."""
        template = Template(
            name="valid-template",
            description="Valid template",
            version="1.0.0",
            packages=["pkg1"]
        )
        
        is_valid, errors = TemplateValidator.validate(template)
        
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_validate_missing_name(self):
        """Test validating template with missing name."""
        template = Template(
            name="",
            description="Test",
            version="1.0.0"
        )
        
        is_valid, errors = TemplateValidator.validate(template)
        
        self.assertFalse(is_valid)
        self.assertIn("name is required", errors[0])
    
    def test_validate_missing_packages_and_steps(self):
        """Test validating template with no packages or steps."""
        template = Template(
            name="empty-template",
            description="Empty template",
            version="1.0.0"
        )
        
        is_valid, errors = TemplateValidator.validate(template)
        
        self.assertFalse(is_valid)
        self.assertIn("packages or steps", errors[0])
    
    def test_validate_invalid_hardware_requirements(self):
        """Test validating template with invalid hardware requirements."""
        hw_req = HardwareRequirements(min_ram_mb=-1)
        template = Template(
            name="invalid-hw",
            description="Invalid hardware",
            version="1.0.0",
            packages=["pkg1"],
            hardware_requirements=hw_req
        )
        
        is_valid, errors = TemplateValidator.validate(template)
        
        self.assertFalse(is_valid)
        self.assertIn("min_ram_mb", errors[0])


class TestTemplateManager(unittest.TestCase):
    """Test TemplateManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.template_dir = Path(self.temp_dir) / "templates"
        self.template_dir.mkdir()
        
        # Create a test template
        self.test_template_data = {
            "name": "test-template",
            "description": "Test template",
            "version": "1.0.0",
            "packages": ["package1", "package2"],
            "steps": [
                {
                    "command": "apt update",
                    "description": "Update packages",
                    "requires_root": True
                }
            ]
        }
        
        # Write test template to file
        template_file = self.template_dir / "test-template.yaml"
        with open(template_file, 'w') as f:
            yaml.dump(self.test_template_data, f)
    
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
    
    def test_load_template(self):
        """Test loading a template."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        template = manager.load_template("test-template")
        
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "test-template")
        self.assertEqual(len(template.packages), 2)
    
    def test_load_nonexistent_template(self):
        """Test loading a non-existent template."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        template = manager.load_template("nonexistent")
        
        self.assertIsNone(template)
    
    def test_save_template(self):
        """Test saving a template."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template = Template(
            name="new-template",
            description="New template",
            version="1.0.0",
            packages=["pkg1"]
        )
        
        template_path = manager.save_template(template, "new-template")
        
        self.assertTrue(template_path.exists())
        
        # Verify it can be loaded
        loaded = manager.load_template("new-template")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "new-template")
    
    def test_list_templates(self):
        """Test listing templates."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        templates = manager.list_templates()
        
        self.assertIn("test-template", templates)
        self.assertEqual(templates["test-template"]["name"], "test-template")
    
    def test_generate_commands_from_packages(self):
        """Test generating commands from packages."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template = Template(
            name="test",
            description="Test",
            version="1.0.0",
            packages=["package1", "package2"]
        )
        
        commands = manager.generate_commands(template)
        
        self.assertGreater(len(commands), 0)
        self.assertTrue(any("package1" in cmd or "package2" in cmd for cmd in commands))
    
    def test_generate_commands_from_steps(self):
        """Test generating commands from steps."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template = Template(
            name="test",
            description="Test",
            version="1.0.0",
            steps=[
                InstallationStep(
                    command="apt install pkg1",
                    description="Install pkg1"
                )
            ]
        )
        
        commands = manager.generate_commands(template)
        
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0], "apt install pkg1")
    
    def test_import_template(self):
        """Test importing a template from file."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        # Create a temporary template file
        temp_file = Path(self.temp_dir) / "import-template.yaml"
        with open(temp_file, 'w') as f:
            yaml.dump(self.test_template_data, f)
        
        template = manager.import_template(str(temp_file))
        
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "test-template")
    
    def test_export_template(self):
        """Test exporting a template to file."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        export_path = Path(self.temp_dir) / "exported-template.yaml"
        manager.export_template("test-template", str(export_path))
        
        self.assertTrue(export_path.exists())
        
        # Verify content
        with open(export_path, 'r') as f:
            data = yaml.safe_load(f)
            self.assertEqual(data["name"], "test-template")


class TestHardwareCompatibility(unittest.TestCase):
    """Test hardware compatibility checking."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = TemplateManager()
    
    def test_check_hardware_compatibility_no_requirements(self):
        """Test checking compatibility with no requirements."""
        template = Template(
            name="test",
            description="Test",
            version="1.0.0",
            packages=["pkg1"]
        )
        
        is_compatible, warnings = self.manager.check_hardware_compatibility(template)
        
        self.assertTrue(is_compatible)
        self.assertEqual(len(warnings), 0)
    
    def test_check_hardware_compatibility_with_requirements(self):
        """Test checking compatibility with requirements."""
        hw_req = HardwareRequirements(
            min_ram_mb=1024,
            min_cores=2
        )
        
        template = Template(
            name="test",
            description="Test",
            version="1.0.0",
            packages=["pkg1"],
            hardware_requirements=hw_req
        )
        
        is_compatible, warnings = self.manager.check_hardware_compatibility(template)
        
        # Result depends on actual hardware, but should not crash
        self.assertIsInstance(is_compatible, bool)
        self.assertIsInstance(warnings, list)


class TestTemplateFormat(unittest.TestCase):
    """Test template format handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.template_dir = Path(self.temp_dir) / "templates"
        self.template_dir.mkdir()
    
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
    
    def test_save_yaml_format(self):
        """Test saving template in YAML format."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template = Template(
            name="yaml-test",
            description="YAML test",
            version="1.0.0",
            packages=["pkg1"]
        )
        
        template_path = manager.save_template(template, "yaml-test", TemplateFormat.YAML)
        
        self.assertTrue(template_path.exists())
        self.assertEqual(template_path.suffix, ".yaml")
        
        # Verify it's valid YAML
        with open(template_path, 'r') as f:
            data = yaml.safe_load(f)
            self.assertEqual(data["name"], "yaml-test")
    
    def test_save_json_format(self):
        """Test saving template in JSON format."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template = Template(
            name="json-test",
            description="JSON test",
            version="1.0.0",
            packages=["pkg1"]
        )
        
        template_path = manager.save_template(template, "json-test", TemplateFormat.JSON)
        
        self.assertTrue(template_path.exists())
        self.assertEqual(template_path.suffix, ".json")
        
        # Verify it's valid JSON
        with open(template_path, 'r') as f:
            data = json.load(f)
            self.assertEqual(data["name"], "json-test")
    
    def test_load_yaml_template(self):
        """Test loading YAML template."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template_data = {
            "name": "yaml-load",
            "description": "YAML load test",
            "version": "1.0.0",
            "packages": ["pkg1"]
        }
        
        template_file = self.template_dir / "yaml-load.yaml"
        with open(template_file, 'w') as f:
            yaml.dump(template_data, f)
        
        template = manager.load_template("yaml-load")
        
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "yaml-load")
    
    def test_load_json_template(self):
        """Test loading JSON template."""
        manager = TemplateManager(templates_dir=str(self.template_dir))
        
        template_data = {
            "name": "json-load",
            "description": "JSON load test",
            "version": "1.0.0",
            "packages": ["pkg1"]
        }
        
        template_file = self.template_dir / "json-load.json"
        with open(template_file, 'w') as f:
            json.dump(template_data, f)
        
        template = manager.load_template("json-load")
        
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "json-load")


if __name__ == '__main__':
    unittest.main()

