#!/usr/bin/env python3
"""
Tests for tarball_helper.py
Tests the tarball build helper functionality including:
- Configure script parsing
- CMakeLists.txt parsing
- Dependency detection
- Package mapping
- Installation tracking
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cortex.tarball_helper import (
    BuildSystem,
    DependencyRequirement,
    TarballAnalysis,
    TarballHelper,
)


class TestTarballHelper(unittest.TestCase):
    """Test cases for TarballHelper"""

    def setUp(self):
        self.helper = TarballHelper(track_installations=False)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_project(self):
        path = Path(self.temp_dir) / "test-project"
        path.mkdir(exist_ok=True)
        return path

    # --------------------------------------------------
    # Build system detection
    # --------------------------------------------------

    def test_detect_build_system_autotools(self):
        source_dir = self._make_project()
        (source_dir / "configure").touch()
        self.assertEqual(
            self.helper._detect_build_system(source_dir),
            BuildSystem.AUTOTOOLS,
        )

    def test_detect_build_system_cmake(self):
        source_dir = self._make_project()
        (source_dir / "CMakeLists.txt").touch()
        self.assertEqual(
            self.helper._detect_build_system(source_dir),
            BuildSystem.CMAKE,
        )

    def test_detect_build_system_meson(self):
        source_dir = self._make_project()
        (source_dir / "meson.build").touch()
        self.assertEqual(
            self.helper._detect_build_system(source_dir),
            BuildSystem.MESON,
        )

    def test_detect_build_system_unknown(self):
        source_dir = self._make_project()
        self.assertEqual(
            self.helper._detect_build_system(source_dir),
            BuildSystem.UNKNOWN,
        )

    # --------------------------------------------------
    # Autotools parsing
    # --------------------------------------------------

    def test_parse_configure_script_ac_check_lib(self):
        source_dir = self._make_project()
        (source_dir / "configure").write_text("""
AC_CHECK_LIB(ssl, SSL_new)
AC_CHECK_LIB(z, deflate)
AC_CHECK_LIB(png, png_create_read_struct)
""")

        deps = self.helper._parse_configure_script(source_dir)
        libs = {d.library_name for d in deps}
        self.assertTrue({"ssl", "z", "png"}.issubset(libs))

    def test_parse_configure_script_pkg_check_modules(self):
        source_dir = self._make_project()
        (source_dir / "configure").write_text("""
PKG_CHECK_MODULES([GTK], [gtk+-3.0])
PKG_CHECK_MODULES([GLIB], [glib-2.0])
""")

        deps = self.helper._parse_configure_script(source_dir)
        pkgs = {d.pkg_config for d in deps}
        self.assertIn("gtk+-3.0", pkgs)
        self.assertIn("glib-2.0", pkgs)

    def test_parse_configure_script_ac_check_header(self):
        source_dir = self._make_project()
        (source_dir / "configure").write_text("""
AC_CHECK_HEADER(openssl/ssl.h)
AC_CHECK_HEADER(zlib.h)
""")

        deps = self.helper._parse_configure_script(source_dir)
        headers = {d.header_file for d in deps}
        self.assertIn("openssl/ssl.h", headers)
        self.assertIn("zlib.h", headers)

    # --------------------------------------------------
    # CMake parsing
    # --------------------------------------------------

    def test_parse_cmake_lists_find_package(self):
        source_dir = self._make_project()
        (source_dir / "CMakeLists.txt").write_text("""
find_package(OpenSSL REQUIRED)
find_package(ZLIB 1.2.8)
find_package(PNG)
""")

        deps = self.helper._parse_cmake_lists(source_dir)
        names = {d.name for d in deps}
        self.assertTrue({"OpenSSL", "ZLIB", "PNG"}.issubset(names))

    def test_parse_cmake_lists_find_library(self):
        source_dir = self._make_project()
        (source_dir / "CMakeLists.txt").write_text("""
find_library(SSL_LIBRARY NAMES ssl)
find_library(Z_LIBRARY NAMES z)
""")

        deps = self.helper._parse_cmake_lists(source_dir)
        self.assertGreater(len(deps), 0)

    def test_parse_cmake_lists_pkg_check_modules(self):
        source_dir = self._make_project()
        (source_dir / "CMakeLists.txt").write_text("""
pkg_check_modules(GTK REQUIRED gtk+-3.0)
pkg_check_modules(GLIB glib-2.0)
""")

        deps = self.helper._parse_cmake_lists(source_dir)
        self.assertGreater(len(deps), 0)

    # --------------------------------------------------
    # Package mapping
    # --------------------------------------------------

    def test_find_package_for_library(self):
        self.assertEqual(self.helper._find_package_for_library("ssl"), "libssl-dev")
        self.assertEqual(self.helper._find_package_for_library("z"), "zlib1g-dev")
        self.assertEqual(self.helper._find_package_for_library("png"), "libpng-dev")

    def test_find_package_for_header(self):
        self.assertEqual(
            self.helper._find_package_for_header("openssl/ssl.h"),
            "libssl-dev",
        )
        self.assertEqual(
            self.helper._find_package_for_header("zlib.h"),
            "zlib1g-dev",
        )

    def test_library_to_dev_package_mapping(self):
        self.assertEqual(self.helper.LIBRARY_TO_DEV_PACKAGE["ssl"], "libssl-dev")
        self.assertEqual(self.helper.LIBRARY_TO_DEV_PACKAGE["z"], "zlib1g-dev")
        self.assertEqual(self.helper.LIBRARY_TO_DEV_PACKAGE["png"], "libpng-dev")
        self.assertEqual(self.helper.LIBRARY_TO_DEV_PACKAGE["jpeg"], "libjpeg-dev")

    def test_header_to_package_mapping(self):
        self.assertEqual(
            self.helper.HEADER_TO_PACKAGE["openssl/ssl.h"],
            "libssl-dev",
        )
        self.assertEqual(
            self.helper.HEADER_TO_PACKAGE["zlib.h"],
            "zlib1g-dev",
        )
        self.assertEqual(
            self.helper.HEADER_TO_PACKAGE["png.h"],
            "libpng-dev",
        )

    def test_package_alternatives_mapping(self):
        self.assertIn("libssl-dev", self.helper.PACKAGE_ALTERNATIVES)

    def test_suggest_alternatives(self):
        """Test suggesting alternative packages"""
        # Test with a package that has alternatives
        if "libssl-dev" in self.helper.PACKAGE_ALTERNATIVES:
            alternatives = self.helper.suggest_alternatives("libssl-dev")
            self.assertIsInstance(alternatives, list)

        # Test with a package that doesn't have alternatives
        alternatives = self.helper.suggest_alternatives("nonexistent-package")
        self.assertEqual(alternatives, [])

    # --------------------------------------------------
    # Dependency installation
    # --------------------------------------------------

    @patch("cortex.tarball_helper.TarballHelper._check_package_installed")
    def test_install_missing_dependencies_dry_run(self, mock_check):
        mock_check.return_value = False

        dep = DependencyRequirement(
            name="ssl",
            library_name="ssl",
            suggested_package="libssl-dev",
            found=False,
        )

        analysis = TarballAnalysis(
            tarball_path="/tmp/test.tar.gz",
            build_system=BuildSystem.AUTOTOOLS,
            dependencies=[dep],
            missing_dependencies=[dep],
        )

        success, planned = self.helper.install_missing_dependencies(
            analysis,
            dry_run=True,
        )

        self.assertTrue(success)
        self.assertIn("libssl-dev", planned)

    # --------------------------------------------------
    # Cleanup tracking
    # --------------------------------------------------

    def test_get_cleanup_commands(self):
        self.helper.installed_packages = ["libssl-dev", "zlib1g-dev"]
        cmds = self.helper.get_cleanup_commands()
        self.assertTrue(any("libssl-dev" in c for c in cmds))
        self.assertTrue(any("zlib1g-dev" in c for c in cmds))

    def test_get_cleanup_commands_empty(self):
        self.helper.installed_packages = []
        self.assertEqual(self.helper.get_cleanup_commands(), [])

    # --------------------------------------------------
    # Tarball analysis
    # --------------------------------------------------

    @patch("cortex.tarball_helper.tarfile")
    @patch("cortex.tarball_helper.TarballHelper._detect_build_system")
    @patch("cortex.tarball_helper.TarballHelper._parse_configure_script")
    def test_analyze_tarball_autotools(
        self, mock_parse, mock_detect, mock_tarfile
    ):
        mock_detect.return_value = BuildSystem.AUTOTOOLS
        mock_parse.return_value = [
            DependencyRequirement(
                name="ssl",
                library_name="ssl",
                suggested_package="libssl-dev",
            )
        ]

        mock_tar = MagicMock()
        mock_tar.getmembers.return_value = [
            MagicMock(name="test-project/configure")
        ]
        mock_tarfile.open.return_value.__enter__.return_value = mock_tar

        tarball_path = Path(self.temp_dir) / "test.tar.gz"
        tarball_path.touch()

        analysis = self.helper.analyze_tarball(str(tarball_path))
        self.assertEqual(analysis.build_system, BuildSystem.AUTOTOOLS)
        self.assertIsNotNone(analysis.extracted_path)

    # --------------------------------------------------
    # Dataclass defaults
    # --------------------------------------------------

    def test_dependency_requirement_defaults(self):
        dep = DependencyRequirement(name="test", library_name="test")
        self.assertTrue(dep.required)
        self.assertFalse(dep.found)
        self.assertEqual(dep.alternatives, [])

    def test_tarball_analysis_defaults(self):
        analysis = TarballAnalysis(tarball_path="/tmp/test.tar.gz")
        self.assertEqual(analysis.tarball_path, "/tmp/test.tar.gz")
        self.assertEqual(analysis.build_system, BuildSystem.UNKNOWN)
        self.assertEqual(analysis.dependencies, [])
        self.assertEqual(analysis.missing_dependencies, [])


if __name__ == "__main__":
    unittest.main()
