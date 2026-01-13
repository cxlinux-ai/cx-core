#!/usr/bin/env python3
"""
Dependency Importer Module

Parses dependency files from multiple ecosystems and provides unified installation.
Supports: requirements.txt (Python), package.json (Node), Gemfile (Ruby),
          Cargo.toml (Rust), go.mod (Go)
"""

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse


class PackageEcosystem(Enum):
    """Supported package ecosystems."""

    PYTHON = "python"
    NODE = "node"
    RUBY = "ruby"
    RUST = "rust"
    GO = "go"
    UNKNOWN = "unknown"


@dataclass
class Package:
    """Represents a parsed package dependency."""

    name: str
    version: str | None = None
    ecosystem: PackageEcosystem = PackageEcosystem.UNKNOWN
    is_dev: bool = False
    extras: list[str] = field(default_factory=list)
    source: str | None = None  # git URL, path, etc.
    group: str | None = None  # For Gemfile groups
    features: list[str] = field(default_factory=list)  # For Cargo.toml
    is_indirect: bool = False  # For go.mod indirect deps
    is_optional: bool = False

    def __str__(self) -> str:
        version_str = f"@{self.version}" if self.version else ""
        return f"{self.name}{version_str}"


@dataclass
class ParseResult:
    """Result of parsing a dependency file."""

    file_path: str
    ecosystem: PackageEcosystem
    packages: list[Package]
    dev_packages: list[Package] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of packages (prod + dev)."""
        return len(self.packages) + len(self.dev_packages)

    @property
    def prod_count(self) -> int:
        """Number of production packages."""
        return len(self.packages)

    @property
    def dev_count(self) -> int:
        """Number of dev packages."""
        return len(self.dev_packages)


# Mapping of filenames to ecosystems
DEPENDENCY_FILES = {
    "requirements.txt": PackageEcosystem.PYTHON,
    "requirements-dev.txt": PackageEcosystem.PYTHON,
    "requirements-test.txt": PackageEcosystem.PYTHON,
    "requirements_dev.txt": PackageEcosystem.PYTHON,
    "requirements_test.txt": PackageEcosystem.PYTHON,
    "dev-requirements.txt": PackageEcosystem.PYTHON,
    "test-requirements.txt": PackageEcosystem.PYTHON,
    "package.json": PackageEcosystem.NODE,
    "Gemfile": PackageEcosystem.RUBY,
    "Cargo.toml": PackageEcosystem.RUST,
    "go.mod": PackageEcosystem.GO,
}

# Install commands for each ecosystem
INSTALL_COMMANDS = {
    PackageEcosystem.PYTHON: "pip install -r {file}",
    PackageEcosystem.NODE: "npm install",
    PackageEcosystem.RUBY: "bundle install",
    PackageEcosystem.RUST: "cargo build",
    PackageEcosystem.GO: "go mod download",
}


class DependencyImporter:
    """Parses and imports dependencies from various package manager files."""

    def __init__(self, base_path: str | None = None):
        """Initialize the importer.

        Args:
            base_path: Base directory for resolving relative paths.
                      Defaults to current working directory.
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self._visited_files: set[str] = set()  # Track visited files for -r includes

    def detect_ecosystem(self, file_path: str) -> PackageEcosystem:
        """Detect the ecosystem based on filename.

        Args:
            file_path: Path to the dependency file.

        Returns:
            The detected PackageEcosystem or UNKNOWN.
        """
        filename = os.path.basename(file_path)

        # Exact match
        if filename in DEPENDENCY_FILES:
            return DEPENDENCY_FILES[filename]

        # Pattern matching for requirements*.txt
        if filename.startswith("requirements") and filename.endswith(".txt"):
            return PackageEcosystem.PYTHON

        return PackageEcosystem.UNKNOWN

    def parse(self, file_path: str, include_dev: bool = False) -> ParseResult:
        """Parse a dependency file and extract packages.

        Args:
            file_path: Path to the dependency file.
            include_dev: Whether to include dev dependencies.

        Returns:
            ParseResult containing packages and any errors.
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.base_path / path

        ecosystem = self.detect_ecosystem(str(path))

        if not path.exists():
            return ParseResult(
                file_path=str(path),
                ecosystem=ecosystem,
                packages=[],
                errors=[f"File not found: {path}"],
            )

        try:
            if ecosystem == PackageEcosystem.PYTHON:
                return self._parse_requirements_txt(path, include_dev)
            elif ecosystem == PackageEcosystem.NODE:
                return self._parse_package_json(path, include_dev)
            elif ecosystem == PackageEcosystem.RUBY:
                return self._parse_gemfile(path, include_dev)
            elif ecosystem == PackageEcosystem.RUST:
                return self._parse_cargo_toml(path, include_dev)
            elif ecosystem == PackageEcosystem.GO:
                return self._parse_go_mod(path, include_dev)
            else:
                return ParseResult(
                    file_path=str(path),
                    ecosystem=ecosystem,
                    packages=[],
                    errors=[f"Unknown file type: {path.name}"],
                )
        except Exception as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=ecosystem,
                packages=[],
                errors=[f"Parse error: {str(e)}"],
            )

    def _parse_requirements_txt(self, path: Path, include_dev: bool = False) -> ParseResult:
        """Parse Python requirements.txt file.

        Handles:
        - Package names with version specifiers (==, >=, <=, ~=, !=, <, >)
        - Comments (#)
        - Extras (package[extra1,extra2])
        - -r includes (recursive file imports)
        - Environment markers (; python_version >= "3.8")
        - Git URLs and editable installs (-e)
        """
        packages: list[Package] = []
        dev_packages: list[Package] = []
        errors: list[str] = []
        warnings: list[str] = []

        # Prevent circular includes
        abs_path = str(path.resolve())
        if abs_path in self._visited_files:
            warnings.append(f"Skipping circular include: {path}")
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.PYTHON,
                packages=[],
                warnings=warnings,
            )
        self._visited_files.add(abs_path)

        # Detect if this is a dev requirements file
        is_dev_file = any(x in path.name.lower() for x in ["dev", "test", "development", "testing"])

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Handle -r includes
            if line.startswith("-r ") or line.startswith("--requirement "):
                include_path = line.split(maxsplit=1)[1].strip()
                include_full_path = path.parent / include_path
                if include_full_path.exists():
                    sub_result = self._parse_requirements_txt(include_full_path, include_dev)
                    packages.extend(sub_result.packages)
                    dev_packages.extend(sub_result.dev_packages)
                    errors.extend(sub_result.errors)
                    warnings.extend(sub_result.warnings)
                else:
                    warnings.append(f"Line {line_num}: Include file not found: {include_path}")
                continue

            # Skip options like --index-url, --extra-index-url, --trusted-host
            if line.startswith("-") and not line.startswith("-e"):
                continue

            # Handle editable installs (-e)
            if line.startswith("-e ") or line.startswith("--editable "):
                source = line.split(maxsplit=1)[1].strip()
                # Try to extract package name from path or URL
                pkg_name = self._extract_name_from_source(source)
                if pkg_name:
                    pkg = Package(
                        name=pkg_name,
                        ecosystem=PackageEcosystem.PYTHON,
                        source=source,
                        is_dev=is_dev_file,
                    )
                    if is_dev_file:
                        dev_packages.append(pkg)
                    else:
                        packages.append(pkg)
                else:
                    warnings.append(f"Line {line_num}: Could not parse editable install: {line}")
                continue

            # Handle git URLs without -e
            if line.startswith(("git+", "hg+", "svn+", "bzr+")):
                pkg_name = self._extract_name_from_source(line)
                if pkg_name:
                    pkg = Package(
                        name=pkg_name,
                        ecosystem=PackageEcosystem.PYTHON,
                        source=line,
                        is_dev=is_dev_file,
                    )
                    if is_dev_file:
                        dev_packages.append(pkg)
                    else:
                        packages.append(pkg)
                continue

            # Parse standard package specifier
            pkg = self._parse_python_requirement(line, is_dev_file)
            if pkg:
                if is_dev_file:
                    dev_packages.append(pkg)
                else:
                    packages.append(pkg)

        return ParseResult(
            file_path=str(path),
            ecosystem=PackageEcosystem.PYTHON,
            packages=packages,
            dev_packages=dev_packages if include_dev else [],
            errors=errors,
            warnings=warnings,
        )

    def _parse_python_requirement(self, line: str, is_dev: bool = False) -> Package | None:
        """Parse a single Python requirement line.

        Examples:
        - requests
        - requests==2.28.0
        - requests>=2.20,<3.0
        - requests[security,socks]>=2.20
        - requests; python_version >= "3.8"
        """
        # Remove environment markers
        if ";" in line:
            line = line.split(";")[0].strip()

        # Match package name with optional extras and version
        # Pattern: name[extras]version_spec
        pattern = r"^([a-zA-Z0-9][-a-zA-Z0-9._]*)(\[[^\]]+\])?\s*(.*)$"
        match = re.match(pattern, line)

        if not match:
            return None

        name = match.group(1)
        extras_str = match.group(2)
        version_spec = match.group(3).strip() if match.group(3) else None

        extras: list[str] = []
        if extras_str:
            # Remove brackets and split by comma
            extras = [e.strip() for e in extras_str[1:-1].split(",")]

        # Clean version spec (remove comparison operators for display)
        version = None
        if version_spec:
            # Extract version number from spec like "==2.0.0" or ">=1.0,<2.0"
            version_match = re.search(r"[=<>!~]+\s*([0-9][0-9a-zA-Z._-]*)", version_spec)
            if version_match:
                version = version_spec  # Keep full spec for accuracy

        return Package(
            name=name,
            version=version,
            ecosystem=PackageEcosystem.PYTHON,
            extras=extras,
            is_dev=is_dev,
        )

    def _extract_name_from_source(self, source: str) -> str | None:
        """Extract package name from git URL or path."""
        # Handle egg= fragment
        if "#egg=" in source:
            return source.split("#egg=")[1].split("&")[0]

        # Handle git URLs
        allowed_hosts = {"github.com", "gitlab.com", "bitbucket.org"}
        parsed = urlparse(source)
        host = parsed.netloc

        # Handle URLs where the actual URL is in the path (e.g., git+https://...)
        if not host and parsed.path.startswith("//"):
            path_parsed = urlparse("https:" + parsed.path)
            host = path_parsed.netloc

        if host in allowed_hosts:
            # Extract repo name from URL
            match = re.search(r"/([^/]+?)(?:\.git)?(?:@|#|$)", source)
            if match:
                return match.group(1)

        # Handle local paths
        if source.startswith("./") or source.startswith("../") or source.startswith("/"):
            return os.path.basename(source.rstrip("/"))

        return None

    def _parse_package_json(self, path: Path, include_dev: bool = False) -> ParseResult:
        """Parse Node.js package.json file.

        Handles:
        - dependencies
        - devDependencies
        - peerDependencies (as warnings)
        - optionalDependencies
        - Scoped packages (@scope/name)
        - Version ranges (^, ~, >=, *, latest)
        - Git URLs and local paths
        """
        packages: list[Package] = []
        dev_packages: list[Package] = []
        errors: list[str] = []
        warnings: list[str] = []

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.NODE,
                packages=[],
                errors=[f"Invalid JSON: {str(e)}"],
            )
        except Exception as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.NODE,
                packages=[],
                errors=[f"Read error: {str(e)}"],
            )

        # Parse production dependencies
        deps = data.get("dependencies", {})
        for name, version in deps.items():
            pkg = Package(
                name=name,
                version=version,
                ecosystem=PackageEcosystem.NODE,
                is_dev=False,
            )
            # Check if it's a git or file URL
            if version.startswith(("git", "github:", "gitlab:", "file:")):
                pkg.source = version
            packages.append(pkg)

        # Parse dev dependencies
        dev_deps = data.get("devDependencies", {})
        for name, version in dev_deps.items():
            pkg = Package(
                name=name,
                version=version,
                ecosystem=PackageEcosystem.NODE,
                is_dev=True,
            )
            if version.startswith(("git", "github:", "gitlab:", "file:")):
                pkg.source = version
            dev_packages.append(pkg)

        # Warn about peer dependencies
        peer_deps = data.get("peerDependencies", {})
        if peer_deps:
            warnings.append(
                f"Found {len(peer_deps)} peer dependencies (not auto-installed): "
                f"{', '.join(list(peer_deps.keys())[:3])}..."
            )

        # Parse optional dependencies
        optional_deps = data.get("optionalDependencies", {})
        for name, version in optional_deps.items():
            pkg = Package(
                name=name,
                version=version,
                ecosystem=PackageEcosystem.NODE,
                is_dev=False,
                is_optional=True,
            )
            packages.append(pkg)

        return ParseResult(
            file_path=str(path),
            ecosystem=PackageEcosystem.NODE,
            packages=packages,
            dev_packages=dev_packages if include_dev else [],
            errors=errors,
            warnings=warnings,
        )

    def _parse_gemfile(self, path: Path, include_dev: bool = False) -> ParseResult:
        """Parse Ruby Gemfile.

        Handles:
        - gem declarations with versions
        - Groups (:development, :test, :production)
        - Path-based gems (path: './local')
        - Git-based gems (git: 'https://...')
        - Source declarations
        """
        packages: list[Package] = []
        dev_packages: list[Package] = []
        errors: list[str] = []
        warnings: list[str] = []

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.RUBY,
                packages=[],
                errors=[f"Read error: {str(e)}"],
            )

        current_groups: list[str] = []
        in_group_block = False

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Handle source declarations
            if line.startswith("source "):
                continue

            # Handle ruby version
            if line.startswith("ruby "):
                continue

            # Handle group blocks
            group_match = re.match(r"group\s+(.+?)\s+do", line)
            if group_match:
                groups_str = group_match.group(1)
                # Parse group symbols like :development, :test
                current_groups = re.findall(r":(\w+)", groups_str)
                in_group_block = True
                continue

            if line == "end" and in_group_block:
                current_groups = []
                in_group_block = False
                continue

            # Parse gem declarations
            gem_match = re.match(r"gem\s+['\"]([^'\"]+)['\"](.*)$", line)
            if gem_match:
                name = gem_match.group(1)
                rest = gem_match.group(2).strip() if gem_match.group(2) else ""

                version = None
                source = None
                groups = current_groups.copy()

                # Extract version if present (e.g., gem 'rails', '~> 7.0')
                version_match = re.search(r",\s*['\"]([^'\"]+)['\"]", rest)
                if version_match:
                    version = version_match.group(1)

                # Extract path or git source
                path_match = re.search(r"path:\s*['\"]([^'\"]+)['\"]", rest)
                if path_match:
                    source = f"path:{path_match.group(1)}"

                git_match = re.search(r"git:\s*['\"]([^'\"]+)['\"]", rest)
                if git_match:
                    source = f"git:{git_match.group(1)}"

                # Extract inline group
                inline_group = re.search(r"group:\s*\[?([^\]]+)\]?", rest)
                if inline_group:
                    groups.extend(re.findall(r":(\w+)", inline_group.group(1)))

                # Determine if dev dependency
                is_dev = any(g in ["development", "test", "dev"] for g in groups)

                pkg = Package(
                    name=name,
                    version=version,
                    ecosystem=PackageEcosystem.RUBY,
                    is_dev=is_dev,
                    source=source,
                    group=",".join(groups) if groups else None,
                )

                if is_dev:
                    dev_packages.append(pkg)
                else:
                    packages.append(pkg)

        return ParseResult(
            file_path=str(path),
            ecosystem=PackageEcosystem.RUBY,
            packages=packages,
            dev_packages=dev_packages if include_dev else [],
            errors=errors,
            warnings=warnings,
        )

    def _parse_cargo_toml(self, path: Path, include_dev: bool = False) -> ParseResult:
        """Parse Rust Cargo.toml file.

        Handles:
        - [dependencies]
        - [dev-dependencies]
        - [build-dependencies]
        - Inline tables { version = "1.0", features = ["full"] }
        - Path and git dependencies
        - Optional dependencies
        """
        packages: list[Package] = []
        dev_packages: list[Package] = []
        errors: list[str] = []
        warnings: list[str] = []

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.RUST,
                packages=[],
                errors=[f"Read error: {str(e)}"],
            )

        # Simple TOML parsing (without external library)
        current_section = ""
        current_is_dev = False

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Section headers
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].lower()
                current_is_dev = current_section in [
                    "dev-dependencies",
                    "build-dependencies",
                ]
                continue

            # Skip non-dependency sections
            if current_section not in [
                "dependencies",
                "dev-dependencies",
                "build-dependencies",
            ]:
                # Check for target-specific dependencies
                if ".dependencies" in current_section:
                    pass  # Process it
                else:
                    continue

            # Parse dependency line
            if "=" not in line:
                continue

            parts = line.split("=", 1)
            name = parts[0].strip()
            value = parts[1].strip()

            version = None
            features: list[str] = []
            source = None
            is_optional = False

            # Simple string version: serde = "1.0"
            if value.startswith('"') and value.endswith('"'):
                version = value[1:-1]
            # Inline table: tokio = { version = "1", features = ["full"] }
            elif value.startswith("{"):
                # Extract version
                ver_match = re.search(r'version\s*=\s*"([^"]+)"', value)
                if ver_match:
                    version = ver_match.group(1)

                # Extract features
                feat_match = re.search(r"features\s*=\s*\[([^\]]+)\]", value)
                if feat_match:
                    features = [f.strip().strip('"') for f in feat_match.group(1).split(",")]

                # Extract path
                path_match = re.search(r'path\s*=\s*"([^"]+)"', value)
                if path_match:
                    source = f"path:{path_match.group(1)}"

                # Extract git
                git_match = re.search(r'git\s*=\s*"([^"]+)"', value)
                if git_match:
                    source = f"git:{git_match.group(1)}"

                # Check optional
                if "optional = true" in value.lower():
                    is_optional = True

            pkg = Package(
                name=name,
                version=version,
                ecosystem=PackageEcosystem.RUST,
                is_dev=current_is_dev,
                features=features,
                source=source,
                is_optional=is_optional,
            )

            if current_is_dev:
                dev_packages.append(pkg)
            else:
                packages.append(pkg)

        return ParseResult(
            file_path=str(path),
            ecosystem=PackageEcosystem.RUST,
            packages=packages,
            dev_packages=dev_packages if include_dev else [],
            errors=errors,
            warnings=warnings,
        )

    def _parse_go_mod(self, path: Path, include_dev: bool = False) -> ParseResult:
        """Parse Go go.mod file.

        Handles:
        - require statements (single and block)
        - // indirect comments
        - replace directives (as warnings)
        - exclude directives (as warnings)
        - Go version requirements
        """
        packages: list[Package] = []
        errors: list[str] = []
        warnings: list[str] = []

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ParseResult(
                file_path=str(path),
                ecosystem=PackageEcosystem.GO,
                packages=[],
                errors=[f"Read error: {str(e)}"],
            )

        in_require_block = False
        replace_count = 0
        exclude_count = 0

        for line_num, line in enumerate(content.splitlines(), 1):
            original_line = line
            line = line.strip()

            # Skip empty lines and pure comments
            if not line or (line.startswith("//") and "indirect" not in line):
                continue

            # Module declaration
            if line.startswith("module "):
                continue

            # Go version
            if line.startswith("go "):
                continue

            # Replace directives
            if line.startswith("replace "):
                replace_count += 1
                continue

            # Exclude directives
            if line.startswith("exclude "):
                exclude_count += 1
                continue

            # Require block start
            if line.startswith("require ("):
                in_require_block = True
                continue

            # Block end
            if line == ")":
                in_require_block = False
                continue

            # Single require statement
            if line.startswith("require "):
                parts = line[8:].strip().split()
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1]
                    is_indirect = "// indirect" in original_line
                    pkg = Package(
                        name=name,
                        version=version,
                        ecosystem=PackageEcosystem.GO,
                        is_indirect=is_indirect,
                    )
                    packages.append(pkg)
                continue

            # Dependencies inside require block
            if in_require_block:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    version = parts[1]
                    is_indirect = "// indirect" in original_line
                    pkg = Package(
                        name=name,
                        version=version,
                        ecosystem=PackageEcosystem.GO,
                        is_indirect=is_indirect,
                    )
                    packages.append(pkg)

        # Add warnings for replace/exclude
        if replace_count > 0:
            warnings.append(f"Found {replace_count} replace directive(s)")
        if exclude_count > 0:
            warnings.append(f"Found {exclude_count} exclude directive(s)")

        return ParseResult(
            file_path=str(path),
            ecosystem=PackageEcosystem.GO,
            packages=packages,
            dev_packages=[],  # Go doesn't distinguish dev deps in go.mod
            errors=errors,
            warnings=warnings,
        )

    def scan_directory(
        self, directory: str | None = None, include_dev: bool = False
    ) -> dict[str, ParseResult]:
        """Scan a directory for all supported dependency files.

        Args:
            directory: Directory to scan. Defaults to base_path.
            include_dev: Whether to include dev dependencies.

        Returns:
            Dict mapping file paths to their ParseResults.
        """
        scan_path = Path(directory) if directory else self.base_path
        results: dict[str, ParseResult] = {}

        for filename in DEPENDENCY_FILES:
            file_path = scan_path / filename
            if file_path.exists():
                result = self.parse(str(file_path), include_dev)
                if result.packages or result.dev_packages or result.errors:
                    results[str(file_path)] = result

        return results

    def get_install_command(
        self, ecosystem: PackageEcosystem, file_path: str | None = None
    ) -> str | None:
        """Get the appropriate install command for an ecosystem.

        Args:
            ecosystem: The package ecosystem.
            file_path: Optional file path to include in command.

        Returns:
            Install command string or None if unknown ecosystem.
        """
        if ecosystem not in INSTALL_COMMANDS:
            return None

        cmd = INSTALL_COMMANDS[ecosystem]
        if "{file}" in cmd and file_path:
            return cmd.format(file=file_path)
        return cmd

    def get_install_commands_for_results(
        self, results: dict[str, ParseResult]
    ) -> list[dict[str, str]]:
        """Generate install commands for multiple parse results.

        Args:
            results: Dict of file paths to ParseResults.

        Returns:
            List of dicts with 'command' and 'description' keys.
        """
        commands: list[dict[str, str]] = []
        seen_ecosystems: set[PackageEcosystem] = set()

        for file_path, result in results.items():
            if result.errors:
                continue

            ecosystem = result.ecosystem

            # For Python, we use pip install -r for each file
            if ecosystem == PackageEcosystem.PYTHON:
                if result.packages or result.dev_packages:
                    cmd = self.get_install_command(ecosystem, file_path)
                    if cmd:
                        commands.append(
                            {
                                "command": cmd,
                                "description": f"Install Python packages from {os.path.basename(file_path)}",
                            }
                        )
            # For other ecosystems, one command per ecosystem
            elif ecosystem not in seen_ecosystems:
                cmd = self.get_install_command(ecosystem)
                if cmd and (result.packages or result.dev_packages):
                    commands.append(
                        {
                            "command": cmd,
                            "description": f"Install {ecosystem.value.title()} packages",
                        }
                    )
                    seen_ecosystems.add(ecosystem)

        return commands


def format_package_list(packages: list[Package], max_display: int = 10) -> str:
    """Format a list of packages for display.

    Args:
        packages: List of Package objects.
        max_display: Maximum number to show before truncating.

    Returns:
        Formatted string for display.
    """
    if not packages:
        return "(none)"

    names = [str(pkg) for pkg in packages[:max_display]]
    result = ", ".join(names)

    if len(packages) > max_display:
        result += f" (+{len(packages) - max_display} more)"

    return result
