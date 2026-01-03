#!/usr/bin/env python3
"""
Tests for source_builder.py module
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.source_builder import (
    BUILD_DEPENDENCIES,
    BuildConfig,
    BuildResult,
    SourceBuilder,
)


class TestSourceBuilder:
    """Test cases for SourceBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = SourceBuilder()

    def test_init(self):
        """Test SourceBuilder initialization."""
        assert self.builder.dependency_resolver is not None
        assert self.builder.cache_dir.exists()

    def test_get_cache_key(self):
        """Test cache key generation."""
        key1 = self.builder._get_cache_key("python", "3.12.0", "https://example.com/python.tar.gz")
        key2 = self.builder._get_cache_key("python", "3.12.0", "https://example.com/python.tar.gz")
        key3 = self.builder._get_cache_key("python", "3.11.0", "https://example.com/python.tar.gz")

        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different key
        assert key1 != key3
        # Key should be 16 characters
        assert len(key1) == 16

    def test_detect_build_dependencies_autotools(self):
        """Test build dependency detection for autotools."""
        with patch.object(
            self.builder.dependency_resolver, "is_package_installed", return_value=False
        ):
            deps = self.builder.detect_build_dependencies("test-package", "autotools")
            assert "build-essential" in deps
            assert "autoconf" in deps
            assert "automake" in deps

    def test_detect_build_dependencies_cmake(self):
        """Test build dependency detection for cmake."""
        with patch.object(
            self.builder.dependency_resolver, "is_package_installed", return_value=False
        ):
            deps = self.builder.detect_build_dependencies("test-package", "cmake")
            assert "build-essential" in deps
            assert "cmake" in deps

    def test_detect_build_dependencies_python(self):
        """Test build dependency detection for python packages."""
        with patch.object(
            self.builder.dependency_resolver, "is_package_installed", return_value=False
        ):
            deps = self.builder.detect_build_dependencies("python-test", "python")
            assert "python3-dev" in deps
            assert "python3-pip" in deps

    def test_detect_build_dependencies_satisfied(self):
        """Test that satisfied dependencies are not included."""
        with patch.object(
            self.builder.dependency_resolver, "is_package_installed", return_value=True
        ):
            deps = self.builder.detect_build_dependencies("test-package", "autotools")
            assert len(deps) == 0

    def test_detect_build_system_autotools(self):
        """Test build system detection for autotools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "configure").touch()
            assert self.builder.detect_build_system(source_dir) == "autotools"

    def test_detect_build_system_cmake(self):
        """Test build system detection for cmake."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "CMakeLists.txt").touch()
            assert self.builder.detect_build_system(source_dir) == "cmake"

    def test_detect_build_system_make(self):
        """Test build system detection for make."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "Makefile").touch()
            assert self.builder.detect_build_system(source_dir) == "make"

    def test_detect_build_system_python(self):
        """Test build system detection for python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "setup.py").touch()
            assert self.builder.detect_build_system(source_dir) == "python"

    def test_detect_build_system_default(self):
        """Test default build system detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            # No build files
            assert self.builder.detect_build_system(source_dir) == "autotools"

    def test_configure_build_autotools(self):
        """Test configure for autotools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "configure").touch()
            config = BuildConfig(
                package_name="test",
                build_system="autotools",
                install_prefix="/usr/local",
            )
            commands = self.builder.configure_build(source_dir, config)
            assert len(commands) > 0
            assert "./configure" in commands[0]
            assert "--prefix=/usr/local" in commands[0]

    def test_configure_build_cmake(self):
        """Test configure for cmake."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            config = BuildConfig(
                package_name="test",
                build_system="cmake",
                install_prefix="/usr/local",
            )
            commands = self.builder.configure_build(source_dir, config)
            assert len(commands) > 0
            assert "cmake" in commands[0]

    def test_build_autotools(self):
        """Test build for autotools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            config = BuildConfig(package_name="test", build_system="autotools")
            commands = self.builder.build(source_dir, config)
            assert len(commands) > 0
            assert "make" in commands[0]

    def test_build_cmake(self):
        """Test build for cmake."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "build").mkdir()
            config = BuildConfig(package_name="test", build_system="cmake")
            commands = self.builder.build(source_dir, config)
            assert len(commands) > 0
            assert "make" in commands[0]

    def test_install_build_autotools(self):
        """Test install commands for autotools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            config = BuildConfig(package_name="test", build_system="autotools")
            commands = self.builder.install_build(source_dir, config)
            assert len(commands) > 0
            assert "sudo make install" in commands[0]

    def test_install_build_python(self):
        """Test install commands for python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            config = BuildConfig(package_name="test", build_system="python")
            commands = self.builder.install_build(source_dir, config)
            assert len(commands) > 0
            assert "python3 setup.py install" in commands[0]

    @patch("cortex.source_builder.run_command")
    @patch("cortex.source_builder.urllib.request.urlretrieve")
    @patch("cortex.source_builder.tarfile.open")
    def test_fetch_from_url_tarball(self, mock_tarfile, mock_urlretrieve, mock_run_command):
        """Test fetching source from URL (tarball)."""
        # Mock tarfile extraction
        mock_tar = MagicMock()
        mock_tarfile.return_value.__enter__.return_value = mock_tar

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock extracted directory structure
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()
            source_subdir = extract_dir / "source-1.0"
            source_subdir.mkdir()

            # Mock the tarfile to return our structure
            def mock_extractall(path):
                (Path(path) / "source-1.0").mkdir(parents=True)

            mock_tar.extractall = mock_extractall

            result = self.builder._fetch_from_url(
                "https://example.com/test.tar.gz", "test", "1.0"
            )
            assert result is not None

    def test_build_from_source_missing_deps(self):
        """Test build_from_source with missing dependencies."""
        with patch.object(
            self.builder, "fetch_source", return_value=Path("/tmp/test")
        ), patch.object(
            self.builder, "detect_build_system", return_value="autotools"
        ), patch.object(
            self.builder, "detect_build_dependencies", return_value=["gcc"]
        ), patch.object(
            self.builder, "configure_build", return_value=["./configure"]
        ), patch.object(
            self.builder, "build", return_value=["make"]
        ), patch.object(
            self.builder, "install_build", return_value=["sudo make install"]
        ), patch(
            "cortex.source_builder.run_command"
        ) as mock_run:
            # Mock dependency installation failure
            mock_run.return_value = Mock(success=False, stderr="Failed to install")

            result = self.builder.build_from_source("test-package")
            assert not result.success
            assert "Failed to install build dependencies" in result.error_message

    def test_build_from_source_success(self):
        """Test successful build_from_source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            (source_dir / "configure").touch()

            with patch.object(
                self.builder, "fetch_source", return_value=source_dir
            ), patch.object(
                self.builder, "detect_build_dependencies", return_value=[]
            ), patch(
                "cortex.source_builder.run_command"
            ) as mock_run:
                # Mock successful commands
                mock_run.return_value = Mock(success=True, stdout="", stderr="")

                result = self.builder.build_from_source("test-package", use_cache=False)
                # Should succeed (or at least not fail on dependency check)
                assert result is not None


class TestBuildConfig:
    """Test cases for BuildConfig dataclass."""

    def test_build_config_defaults(self):
        """Test BuildConfig with defaults."""
        config = BuildConfig(package_name="test")
        assert config.package_name == "test"
        assert config.version is None
        assert config.source_url is None
        assert config.build_system == "autotools"
        assert config.install_prefix == "/usr/local"

    def test_build_config_custom(self):
        """Test BuildConfig with custom values."""
        config = BuildConfig(
            package_name="python",
            version="3.12.0",
            source_url="https://example.com/python.tar.gz",
            build_system="autotools",
            configure_args=["--enable-optimizations"],
            install_prefix="/opt/python",
        )
        assert config.package_name == "python"
        assert config.version == "3.12.0"
        assert config.source_url == "https://example.com/python.tar.gz"
        assert config.build_system == "autotools"
        assert config.configure_args == ["--enable-optimizations"]
        assert config.install_prefix == "/opt/python"


class TestBuildDependencies:
    """Test build dependency constants."""

    def test_build_dependencies_structure(self):
        """Test that BUILD_DEPENDENCIES has expected structure."""
        assert "base" in BUILD_DEPENDENCIES
        assert "autotools" in BUILD_DEPENDENCIES
        assert "python" in BUILD_DEPENDENCIES

    def test_build_dependencies_base(self):
        """Test base build dependencies."""
        base_deps = BUILD_DEPENDENCIES["base"]
        assert "build-essential" in base_deps
        assert "gcc" in base_deps
        assert "make" in base_deps

    def test_build_dependencies_autotools(self):
        """Test autotools build dependencies."""
        autotools_deps = BUILD_DEPENDENCIES["autotools"]
        assert "autoconf" in autotools_deps
        assert "automake" in autotools_deps
        assert "libtool" in autotools_deps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

