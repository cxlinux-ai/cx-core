#!/usr/bin/env python3
"""
Unit tests for the dependency_importer module.

Tests parsing of:
- requirements.txt (Python)
- package.json (Node)
- Gemfile (Ruby)
- Cargo.toml (Rust)
- go.mod (Go)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.dependency_importer import (
    DEPENDENCY_FILES,
    INSTALL_COMMANDS,
    DependencyImporter,
    Package,
    PackageEcosystem,
    ParseResult,
    format_package_list,
)


class TestPackageEcosystem(unittest.TestCase):
    """Tests for PackageEcosystem enum."""

    def test_ecosystem_values(self):
        self.assertEqual(PackageEcosystem.PYTHON.value, "python")
        self.assertEqual(PackageEcosystem.NODE.value, "node")
        self.assertEqual(PackageEcosystem.RUBY.value, "ruby")
        self.assertEqual(PackageEcosystem.RUST.value, "rust")
        self.assertEqual(PackageEcosystem.GO.value, "go")
        self.assertEqual(PackageEcosystem.UNKNOWN.value, "unknown")


class TestPackage(unittest.TestCase):
    """Tests for Package dataclass."""

    def test_package_creation(self):
        pkg = Package(name="requests", version="2.28.0", ecosystem=PackageEcosystem.PYTHON)
        self.assertEqual(pkg.name, "requests")
        self.assertEqual(pkg.version, "2.28.0")
        self.assertEqual(pkg.ecosystem, PackageEcosystem.PYTHON)
        self.assertFalse(pkg.is_dev)

    def test_package_str_with_version(self):
        pkg = Package(name="requests", version="2.28.0")
        self.assertEqual(str(pkg), "requests@2.28.0")

    def test_package_str_without_version(self):
        pkg = Package(name="requests")
        self.assertEqual(str(pkg), "requests")

    def test_package_defaults(self):
        pkg = Package(name="test")
        self.assertIsNone(pkg.version)
        self.assertEqual(pkg.ecosystem, PackageEcosystem.UNKNOWN)
        self.assertFalse(pkg.is_dev)
        self.assertEqual(pkg.extras, [])
        self.assertIsNone(pkg.source)
        self.assertIsNone(pkg.group)
        self.assertEqual(pkg.features, [])
        self.assertFalse(pkg.is_indirect)
        self.assertFalse(pkg.is_optional)


class TestParseResult(unittest.TestCase):
    """Tests for ParseResult dataclass."""

    def test_parse_result_counts(self):
        packages = [Package(name="pkg1"), Package(name="pkg2")]
        dev_packages = [Package(name="dev1")]
        result = ParseResult(
            file_path="/test/file",
            ecosystem=PackageEcosystem.PYTHON,
            packages=packages,
            dev_packages=dev_packages,
        )
        self.assertEqual(result.prod_count, 2)
        self.assertEqual(result.dev_count, 1)
        self.assertEqual(result.total_count, 3)

    def test_parse_result_empty(self):
        result = ParseResult(
            file_path="/test/file",
            ecosystem=PackageEcosystem.PYTHON,
            packages=[],
        )
        self.assertEqual(result.prod_count, 0)
        self.assertEqual(result.dev_count, 0)
        self.assertEqual(result.total_count, 0)


class TestDependencyImporter(unittest.TestCase):
    """Tests for DependencyImporter class."""

    def setUp(self):
        self.importer = DependencyImporter()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_temp_file(self, filename: str, content: str) -> str:
        """Helper to create a temporary file."""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path


class TestEcosystemDetection(TestDependencyImporter):
    """Tests for ecosystem detection."""

    def test_detect_requirements_txt(self):
        self.assertEqual(
            self.importer.detect_ecosystem("requirements.txt"),
            PackageEcosystem.PYTHON,
        )

    def test_detect_requirements_dev_txt(self):
        self.assertEqual(
            self.importer.detect_ecosystem("requirements-dev.txt"),
            PackageEcosystem.PYTHON,
        )

    def test_detect_requirements_pattern(self):
        self.assertEqual(
            self.importer.detect_ecosystem("requirements-prod.txt"),
            PackageEcosystem.PYTHON,
        )

    def test_detect_package_json(self):
        self.assertEqual(
            self.importer.detect_ecosystem("package.json"),
            PackageEcosystem.NODE,
        )

    def test_detect_gemfile(self):
        self.assertEqual(
            self.importer.detect_ecosystem("Gemfile"),
            PackageEcosystem.RUBY,
        )

    def test_detect_cargo_toml(self):
        self.assertEqual(
            self.importer.detect_ecosystem("Cargo.toml"),
            PackageEcosystem.RUST,
        )

    def test_detect_go_mod(self):
        self.assertEqual(
            self.importer.detect_ecosystem("go.mod"),
            PackageEcosystem.GO,
        )

    def test_detect_unknown(self):
        self.assertEqual(
            self.importer.detect_ecosystem("unknown.file"),
            PackageEcosystem.UNKNOWN,
        )

    def test_detect_with_path(self):
        self.assertEqual(
            self.importer.detect_ecosystem("/some/path/requirements.txt"),
            PackageEcosystem.PYTHON,
        )


class TestRequirementsTxtParsing(TestDependencyImporter):
    """Tests for requirements.txt parsing."""

    def test_parse_simple_packages(self):
        content = """requests
flask
django
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(result.ecosystem, PackageEcosystem.PYTHON)
        self.assertEqual(len(result.packages), 3)
        self.assertEqual(result.packages[0].name, "requests")
        self.assertEqual(result.packages[1].name, "flask")
        self.assertEqual(result.packages[2].name, "django")

    def test_parse_with_versions(self):
        content = """requests==2.28.0
flask>=2.0.0
django~=4.0
numpy!=1.0.0
pandas<2.0,>=1.0
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 5)
        self.assertEqual(result.packages[0].name, "requests")
        self.assertEqual(result.packages[0].version, "==2.28.0")

    def test_parse_with_comments(self):
        content = """# This is a comment
requests  # inline comment should be handled
# Another comment
flask
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        self.assertEqual(result.packages[0].name, "requests")

    def test_parse_with_extras(self):
        content = """requests[security,socks]>=2.20.0
celery[redis]
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        self.assertEqual(result.packages[0].name, "requests")
        self.assertIn("security", result.packages[0].extras)
        self.assertIn("socks", result.packages[0].extras)

    def test_parse_with_environment_markers(self):
        content = """pywin32; sys_platform == 'win32'
requests>=2.20.0; python_version >= "3.6"
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        self.assertEqual(result.packages[0].name, "pywin32")
        self.assertEqual(result.packages[1].name, "requests")

    def test_parse_empty_file(self):
        content = ""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 0)
        self.assertEqual(len(result.errors), 0)

    def test_parse_only_comments(self):
        content = """# Just comments
# Nothing else
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 0)

    def test_parse_with_blank_lines(self):
        content = """requests

flask

django
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 3)

    def test_parse_skips_options(self):
        content = """--index-url https://pypi.org/simple
--extra-index-url https://custom.pypi.org
--trusted-host custom.pypi.org
requests
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "requests")

    def test_parse_recursive_includes(self):
        # Create base requirements
        base_content = """flask
django
"""
        base_path = self._create_temp_file("base.txt", base_content)

        # Create main requirements with -r include
        main_content = """-r base.txt
requests
"""
        main_path = self._create_temp_file("requirements.txt", main_content)

        importer = DependencyImporter(base_path=self.temp_dir)
        result = importer.parse(main_path)

        self.assertEqual(len(result.packages), 3)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("flask", names)
        self.assertIn("django", names)
        self.assertIn("requests", names)

    def test_parse_missing_include_warning(self):
        content = """-r nonexistent.txt
requests
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertTrue(len(result.warnings) > 0)

    def test_parse_dev_requirements_file(self):
        content = """pytest
black
mypy
"""
        file_path = self._create_temp_file("requirements-dev.txt", content)
        result = self.importer.parse(file_path, include_dev=True)

        # Dev file packages should be in dev_packages
        self.assertEqual(len(result.dev_packages), 3)
        self.assertTrue(all(pkg.is_dev for pkg in result.dev_packages))

    def test_parse_git_url(self):
        content = """git+https://github.com/user/repo.git#egg=mypackage
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        # The #egg= fragment specifies the package name
        self.assertEqual(result.packages[0].name, "mypackage")

    def test_parse_editable_install(self):
        content = """-e git+https://github.com/user/myproject.git#egg=myproject
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIsNotNone(result.packages[0].source)

    def test_parse_git_url_github(self):
        content = """git+https://github.com/user/repo.git
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "repo")

    def test_parse_git_url_gitlab(self):
        content = """git+https://gitlab.com/user/repo.git
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "repo")

    def test_parse_git_url_bitbucket(self):
        content = """git+https://bitbucket.org/user/repo.git
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "repo")

    def test_parse_malicious_git_url_substring_attack(self):
        # Test that URLs with allowed hostnames as substrings are rejected
        malicious_urls = [
            "git+https://evilgithub.com/user/repo.git",
            "git+https://github.com.evil.com/user/repo.git",
            "git+https://evilgitlab.com/user/repo.git",
            "git+https://gitlab.com.evil.com/user/repo.git",
            "git+https://evilbitbucket.org/user/repo.git",
            "git+https://bitbucket.org.evil.com/user/repo.git",
        ]

        for malicious_url in malicious_urls:
            content = f"{malicious_url}\n"
            file_path = self._create_temp_file("requirements.txt", content)
            result = self.importer.parse(file_path)

            # Should not parse any packages from malicious URLs
            self.assertEqual(
                len(result.packages), 0, f"Malicious URL {malicious_url} was incorrectly parsed"
            )

    def test_parse_git_url_with_branch(self):
        content = """git+https://github.com/user/repo.git@branch
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "repo")

    def test_parse_git_url_without_git_extension(self):
        content = """git+https://github.com/user/repo
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "repo")

    def test_file_not_found(self):
        result = self.importer.parse("/nonexistent/requirements.txt")

        self.assertEqual(len(result.packages), 0)
        self.assertTrue(len(result.errors) > 0)
        self.assertIn("not found", result.errors[0].lower())


class TestPackageJsonParsing(TestDependencyImporter):
    """Tests for package.json parsing."""

    def test_parse_simple_dependencies(self):
        content = json.dumps(
            {
                "name": "test-project",
                "dependencies": {
                    "express": "^4.18.0",
                    "lodash": "~4.17.21",
                },
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(result.ecosystem, PackageEcosystem.NODE)
        self.assertEqual(len(result.packages), 2)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("express", names)
        self.assertIn("lodash", names)

    def test_parse_dev_dependencies(self):
        content = json.dumps(
            {
                "dependencies": {"express": "^4.18.0"},
                "devDependencies": {
                    "jest": "^29.0.0",
                    "typescript": "^5.0.0",
                },
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path, include_dev=True)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(len(result.dev_packages), 2)
        self.assertTrue(all(pkg.is_dev for pkg in result.dev_packages))

    def test_parse_scoped_packages(self):
        content = json.dumps(
            {
                "dependencies": {
                    "@types/node": "^18.0.0",
                    "@babel/core": "^7.0.0",
                }
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("@types/node", names)
        self.assertIn("@babel/core", names)

    def test_parse_optional_dependencies(self):
        content = json.dumps(
            {
                "dependencies": {"express": "^4.18.0"},
                "optionalDependencies": {"fsevents": "^2.3.0"},
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        optional_pkgs = [pkg for pkg in result.packages if pkg.is_optional]
        self.assertEqual(len(optional_pkgs), 1)
        self.assertEqual(optional_pkgs[0].name, "fsevents")

    def test_parse_peer_dependencies_warning(self):
        content = json.dumps(
            {
                "dependencies": {"express": "^4.18.0"},
                "peerDependencies": {"react": "^18.0.0"},
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("peer", result.warnings[0].lower())

    def test_parse_empty_dependencies(self):
        content = json.dumps(
            {
                "name": "test-project",
                "version": "1.0.0",
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 0)
        self.assertEqual(len(result.errors), 0)

    def test_parse_invalid_json(self):
        content = "{ invalid json }"
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 0)
        self.assertTrue(len(result.errors) > 0)
        self.assertIn("json", result.errors[0].lower())

    def test_parse_git_url_version(self):
        content = json.dumps(
            {
                "dependencies": {
                    "mypackage": "git+https://github.com/user/repo.git",
                }
            }
        )
        file_path = self._create_temp_file("package.json", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIsNotNone(result.packages[0].source)


class TestGemfileParsing(TestDependencyImporter):
    """Tests for Gemfile parsing."""

    def test_parse_simple_gems(self):
        content = """source 'https://rubygems.org'

gem 'rails'
gem 'pg'
gem 'puma'
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(result.ecosystem, PackageEcosystem.RUBY)
        self.assertEqual(len(result.packages), 3)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("rails", names)
        self.assertIn("pg", names)
        self.assertIn("puma", names)

    def test_parse_gems_with_versions(self):
        content = """gem 'rails', '~> 7.0'
gem 'pg', '>= 1.0'
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        self.assertEqual(result.packages[0].version, "~> 7.0")

    def test_parse_group_block(self):
        content = """gem 'rails'

group :development, :test do
  gem 'rspec'
  gem 'factory_bot'
end
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path, include_dev=True)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(len(result.dev_packages), 2)
        self.assertTrue(all(pkg.is_dev for pkg in result.dev_packages))

    def test_parse_inline_group(self):
        content = """gem 'rails'
gem 'rspec', group: :test
gem 'rubocop', group: [:development, :test]
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path, include_dev=True)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(len(result.dev_packages), 2)

    def test_parse_path_gem(self):
        content = """gem 'my_local_gem', path: './gems/local'
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIn("path:", result.packages[0].source)

    def test_parse_git_gem(self):
        content = """gem 'my_gem', git: 'https://github.com/user/repo.git'
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIn("git:", result.packages[0].source)

    def test_parse_ruby_version_ignored(self):
        content = """ruby '3.2.0'

gem 'rails'
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "rails")

    def test_parse_comments_ignored(self):
        content = """# Production gems
gem 'rails'  # Main framework
# gem 'old_gem'  # Commented out
"""
        file_path = self._create_temp_file("Gemfile", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)


class TestCargoTomlParsing(TestDependencyImporter):
    """Tests for Cargo.toml parsing."""

    def test_parse_simple_dependencies(self):
        content = """[package]
name = "my_project"
version = "0.1.0"

[dependencies]
serde = "1.0"
tokio = "1.0"
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(result.ecosystem, PackageEcosystem.RUST)
        self.assertEqual(len(result.packages), 2)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("serde", names)
        self.assertIn("tokio", names)

    def test_parse_inline_table(self):
        content = """[dependencies]
tokio = { version = "1.0", features = ["full"] }
serde = { version = "1.0", features = ["derive"] }
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        tokio = next(pkg for pkg in result.packages if pkg.name == "tokio")
        self.assertEqual(tokio.version, "1.0")
        self.assertIn("full", tokio.features)

    def test_parse_dev_dependencies(self):
        content = """[dependencies]
serde = "1.0"

[dev-dependencies]
criterion = "0.4"
proptest = "1.0"
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path, include_dev=True)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(len(result.dev_packages), 2)

    def test_parse_build_dependencies(self):
        content = """[dependencies]
serde = "1.0"

[build-dependencies]
cc = "1.0"
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path, include_dev=True)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(len(result.dev_packages), 1)

    def test_parse_path_dependency(self):
        content = """[dependencies]
my_crate = { path = "../my_crate" }
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIn("path:", result.packages[0].source)

    def test_parse_git_dependency(self):
        content = """[dependencies]
my_crate = { git = "https://github.com/user/repo.git" }
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIn("git:", result.packages[0].source)

    def test_parse_optional_dependency(self):
        content = """[dependencies]
serde = { version = "1.0", optional = true }
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertTrue(result.packages[0].is_optional)

    def test_parse_ignores_other_sections(self):
        content = """[package]
name = "test"
version = "0.1.0"

[dependencies]
serde = "1.0"

[profile.release]
opt-level = 3
"""
        file_path = self._create_temp_file("Cargo.toml", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)


class TestGoModParsing(TestDependencyImporter):
    """Tests for go.mod parsing."""

    def test_parse_simple_requires(self):
        content = """module example.com/mymodule

go 1.21

require (
    github.com/gin-gonic/gin v1.9.0
    github.com/go-redis/redis/v8 v8.11.5
)
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertEqual(result.ecosystem, PackageEcosystem.GO)
        self.assertEqual(len(result.packages), 2)
        names = [pkg.name for pkg in result.packages]
        self.assertIn("github.com/gin-gonic/gin", names)

    def test_parse_single_require(self):
        content = """module example.com/mymodule

go 1.21

require github.com/gin-gonic/gin v1.9.0
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0].name, "github.com/gin-gonic/gin")
        self.assertEqual(result.packages[0].version, "v1.9.0")

    def test_parse_indirect_dependencies(self):
        content = """module example.com/mymodule

go 1.21

require (
    github.com/gin-gonic/gin v1.9.0
    github.com/indirect/dep v1.0.0 // indirect
)
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 2)
        indirect_pkg = next(pkg for pkg in result.packages if "indirect" in pkg.name)
        self.assertTrue(indirect_pkg.is_indirect)

    def test_parse_replace_directive_warning(self):
        content = """module example.com/mymodule

go 1.21

require github.com/gin-gonic/gin v1.9.0

replace github.com/old/pkg => github.com/new/pkg v1.0.0
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("replace", result.warnings[0].lower())

    def test_parse_exclude_directive_warning(self):
        content = """module example.com/mymodule

go 1.21

require github.com/gin-gonic/gin v1.9.0

exclude github.com/bad/pkg v1.0.0
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("exclude", result.warnings[0].lower())

    def test_parse_pseudo_version(self):
        content = """module example.com/mymodule

go 1.21

require (
    golang.org/x/sync v0.0.0-20220722155255-886fb9371eb4
)
"""
        file_path = self._create_temp_file("go.mod", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)
        self.assertIn("v0.0.0-", result.packages[0].version)


class TestDirectoryScan(TestDependencyImporter):
    """Tests for directory scanning."""

    def test_scan_empty_directory(self):
        results = self.importer.scan_directory(self.temp_dir)
        self.assertEqual(len(results), 0)

    def test_scan_single_file(self):
        content = "requests\nflask"
        self._create_temp_file("requirements.txt", content)

        importer = DependencyImporter(base_path=self.temp_dir)
        results = importer.scan_directory()

        self.assertEqual(len(results), 1)
        self.assertTrue(any("requirements.txt" in path for path in results.keys()))

    def test_scan_multiple_files(self):
        self._create_temp_file("requirements.txt", "requests")
        self._create_temp_file("package.json", json.dumps({"dependencies": {"express": "^4.0.0"}}))

        importer = DependencyImporter(base_path=self.temp_dir)
        results = importer.scan_directory()

        self.assertEqual(len(results), 2)


class TestInstallCommands(TestDependencyImporter):
    """Tests for install command generation."""

    def test_get_python_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.PYTHON, "requirements.txt")
        self.assertEqual(cmd, "pip install -r requirements.txt")

    def test_get_node_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.NODE)
        self.assertEqual(cmd, "npm install")

    def test_get_ruby_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.RUBY)
        self.assertEqual(cmd, "bundle install")

    def test_get_rust_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.RUST)
        self.assertEqual(cmd, "cargo build")

    def test_get_go_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.GO)
        self.assertEqual(cmd, "go mod download")

    def test_get_unknown_install_command(self):
        cmd = self.importer.get_install_command(PackageEcosystem.UNKNOWN)
        self.assertIsNone(cmd)

    def test_get_install_commands_for_results(self):
        self._create_temp_file("requirements.txt", "requests")
        self._create_temp_file("package.json", json.dumps({"dependencies": {"express": "^4.0.0"}}))

        importer = DependencyImporter(base_path=self.temp_dir)
        results = importer.scan_directory()
        commands = importer.get_install_commands_for_results(results)

        self.assertEqual(len(commands), 2)
        self.assertTrue(all("command" in cmd for cmd in commands))
        self.assertTrue(all("description" in cmd for cmd in commands))


class TestFormatPackageList(unittest.TestCase):
    """Tests for format_package_list helper."""

    def test_format_empty_list(self):
        result = format_package_list([])
        self.assertEqual(result, "(none)")

    def test_format_single_package(self):
        packages = [Package(name="requests", version="2.28.0")]
        result = format_package_list(packages)
        self.assertEqual(result, "requests@2.28.0")

    def test_format_multiple_packages(self):
        packages = [
            Package(name="requests"),
            Package(name="flask"),
            Package(name="django"),
        ]
        result = format_package_list(packages)
        self.assertEqual(result, "requests, flask, django")

    def test_format_with_truncation(self):
        packages = [Package(name=f"pkg{i}") for i in range(15)]
        result = format_package_list(packages, max_display=10)
        self.assertIn("(+5 more)", result)


class TestEdgeCases(TestDependencyImporter):
    """Tests for edge cases and error handling."""

    def test_parse_unknown_file_type(self):
        content = "some content"
        file_path = self._create_temp_file("unknown.xyz", content)
        result = self.importer.parse(file_path)

        self.assertTrue(len(result.errors) > 0)

    def test_parse_with_unicode(self):
        content = """# Comment with unicode: café ñ 日本語
requests
"""
        file_path = self._create_temp_file("requirements.txt", content)
        result = self.importer.parse(file_path)

        self.assertEqual(len(result.packages), 1)

    def test_circular_include_prevention(self):
        # Create files that include each other
        content_a = """-r b.txt
requests
"""
        content_b = """-r a.txt
flask
"""
        self._create_temp_file("a.txt", content_a)
        self._create_temp_file("b.txt", content_b)

        # Rename to requirements pattern
        os.rename(
            os.path.join(self.temp_dir, "a.txt"),
            os.path.join(self.temp_dir, "requirements.txt"),
        )
        os.rename(
            os.path.join(self.temp_dir, "b.txt"),
            os.path.join(self.temp_dir, "requirements-base.txt"),
        )

        importer = DependencyImporter(base_path=self.temp_dir)
        # Should not infinite loop
        result = importer.parse(os.path.join(self.temp_dir, "requirements.txt"))

        # Should have warnings about circular include
        self.assertTrue(len(result.packages) >= 1)


class TestDependencyFilesMapping(unittest.TestCase):
    """Tests for DEPENDENCY_FILES constant."""

    def test_all_ecosystems_covered(self):
        ecosystems_in_mapping = set(DEPENDENCY_FILES.values())
        # Should have Python, Node, Ruby, Rust, Go
        self.assertIn(PackageEcosystem.PYTHON, ecosystems_in_mapping)
        self.assertIn(PackageEcosystem.NODE, ecosystems_in_mapping)
        self.assertIn(PackageEcosystem.RUBY, ecosystems_in_mapping)
        self.assertIn(PackageEcosystem.RUST, ecosystems_in_mapping)
        self.assertIn(PackageEcosystem.GO, ecosystems_in_mapping)

    def test_install_commands_for_all_ecosystems(self):
        for ecosystem in [
            PackageEcosystem.PYTHON,
            PackageEcosystem.NODE,
            PackageEcosystem.RUBY,
            PackageEcosystem.RUST,
            PackageEcosystem.GO,
        ]:
            self.assertIn(ecosystem, INSTALL_COMMANDS)


if __name__ == "__main__":
    unittest.main()
