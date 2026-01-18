import json
from cortex.tarball_helper import TarballHelper

def test_parse_dependencies_cmake():
    helper = TarballHelper()
    content = "find_package(OpenSSL)\nfind_package(ZLIB)"
    deps = helper._parse_dependencies("CMakeLists.txt", content)
    assert set(deps) == {"OpenSSL", "ZLIB"}


def test_parse_dependencies_makefile():
    helper = TarballHelper()
    content = "gcc -lfoo -lbar"
    deps = helper._parse_dependencies("Makefile", content)
    assert set(deps) == {"foo", "bar"}


def test_parse_dependencies_setup_py():
    helper = TarballHelper()
    # AST parseable
    content = "install_requires = ['requests', 'numpy']"
    deps = helper._parse_dependencies("setup.py", content)
    assert set(deps) == {"requests", "numpy"}

    # Regex fallback
    content2 = "install_requires=['pandas', 'scipy']"
    deps2 = helper._parse_dependencies("setup.py", content2)
    assert set(deps2) == {"pandas", "scipy"}

    # Edge case: malformed
    content3 = "install_requires = None"
    deps3 = helper._parse_dependencies("setup.py", content3)
    assert deps3 == []

def test_parse_dependencies_setup_py_multiline():
    helper = TarballHelper()
    content = """
install_requires = [
    'requests',
    'numpy', # comment
    'pandas',
]
"""
    deps = helper._parse_dependencies("setup.py", content)
    assert set(deps) == {"requests", "numpy", "pandas"}


def test_suggest_apt_packages_lib_prefix():
    helper = TarballHelper()
    deps = ["foo", "libbar"]
    mapping = helper.suggest_apt_packages(deps)
    assert mapping["foo"] == "libfoo-dev"
    assert mapping["libbar"] == "libbar-dev"


def test_load_tracked_packages_corrupt(tmp_path, monkeypatch):
    test_file = tmp_path / "manual_builds.json"
    test_file.write_text("{not: valid json}")
    monkeypatch.setattr("cortex.tarball_helper.MANUAL_TRACK_FILE", test_file)
    helper = TarballHelper()
    pkgs = helper._load_tracked_packages()
    assert pkgs == []
def test_install_deps_error_handling(monkeypatch):
    helper = TarballHelper()
    called = []
    def fake_run(args, check):
        called.append(args)
        class Result:
            returncode = 1
        return Result()
    monkeypatch.setattr("subprocess.run", fake_run)
    helper.tracked_packages = []
    helper.install_deps(["libfail-dev"])
    assert "libfail-dev" not in helper.tracked_packages


def test_load_tracked_packages_valid(tmp_path, monkeypatch):
    test_file = tmp_path / "manual_builds.json"
    test_file.write_text(json.dumps({"packages": ["libfoo-dev", "libbar-dev"]}))
    monkeypatch.setattr("cortex.tarball_helper.MANUAL_TRACK_FILE", test_file)
    helper = TarballHelper()
    pkgs2 = helper._load_tracked_packages()
    assert set(pkgs2) == {"libfoo-dev", "libbar-dev"}


def test_install_deps_error_handling(monkeypatch):
    helper = TarballHelper()
    called = []

    def fake_run(args, check):
        called.append(args)

        class Result:
            returncode = 1

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    helper.tracked_packages = []
    helper.install_deps(["libfail-dev"])
    assert "libfail-dev" not in helper.tracked_packages


"""
Unit tests for tarball_helper.py
"""

import json
import os
import shutil
import tempfile

import pytest

from cortex.tarball_helper import MANUAL_TRACK_FILE, TarballHelper


def test_analyze_cmake(tmp_path):
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_text("""
    find_package(OpenSSL)
    find_package(ZLIB)
    """)
    helper = TarballHelper()
    deps = helper.analyze(str(tmp_path))
    assert set(deps) == {"OpenSSL", "ZLIB"}


def test_analyze_meson(tmp_path):
    meson = tmp_path / "meson.build"
    meson.write_text("dependency('libcurl')\ndependency('zlib')")
    helper = TarballHelper()
    deps = helper.analyze(str(tmp_path))
    assert set(deps) == {"libcurl", "zlib"}


def test_suggest_apt_packages():
    helper = TarballHelper()
    mapping = helper.suggest_apt_packages(["OpenSSL", "zlib"])
    assert mapping["OpenSSL"] == "libopenssl-dev"
    assert mapping["zlib"] == "libzlib-dev"


def test_track_and_cleanup(tmp_path, monkeypatch):
    # Patch MANUAL_TRACK_FILE to a temp location
    test_file = tmp_path / "manual_builds.json"
    monkeypatch.setattr("cortex.tarball_helper.MANUAL_TRACK_FILE", test_file)
    helper = TarballHelper()
    helper.track("libfoo-dev")
    assert "libfoo-dev" in helper.tracked_packages
    # Simulate cleanup (mock subprocess)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
    helper.cleanup()
    assert helper.tracked_packages == []
    with open(test_file) as f:
        data = json.load(f)
        assert data["packages"] == []
