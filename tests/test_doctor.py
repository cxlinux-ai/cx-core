"""
Unit tests for cortex/doctor.py - System Health Check
This tests the SystemDoctor class used by 'cortex status' command.
"""

import sys
from collections import namedtuple
from unittest.mock import MagicMock, mock_open, patch

import pytest

from cortex.doctor import SystemDoctor


class TestSystemDoctorInit:
    def test_init_empty_lists(self):
        doctor = SystemDoctor()
        assert doctor.passes == []
        assert doctor.warnings == []
        assert doctor.failures == []
        assert doctor.suggestions == []


class TestPythonVersionCheck:
    VersionInfo = namedtuple("VersionInfo", "major minor micro releaselevel serial")

    @pytest.mark.parametrize(
        "version_tuple, status",
        [
            ((3, 12, 3), "PASS"),
            ((3, 9, 0), "FAIL"),
            ((3, 7, 0), "FAIL"),
        ],
    )
    def test_python_version_scenarios(self, monkeypatch, version_tuple, status):
        doctor = SystemDoctor()

        vi = self.VersionInfo(version_tuple[0], version_tuple[1], version_tuple[2], "final", 0)
        monkeypatch.setattr(sys, "version_info", vi)

        doctor._check_python()

        version_str = f"Python {version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"

        if status == "PASS":
            assert any(version_str in msg for msg in doctor.passes)
        else:
            assert any(version_str in msg for msg in doctor.failures)


class TestRequirementsTxtDependencies:
    def test_requirements_txt_all_installed(self):
        doctor = SystemDoctor()
        mock_content = "anthropic\nopenai\nrich\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_content)):
                with patch("builtins.__import__", return_value=MagicMock()):
                    doctor._check_dependencies()

        assert "All requirements.txt packages installed" in doctor.passes[0]

    def test_some_dependencies_missing(self):
        doctor = SystemDoctor()
        mock_content = "anthropic\nopenai\nrich\n"

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError()
            return MagicMock()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_content)):
                with patch("builtins.__import__", side_effect=fake_import):
                    doctor._check_dependencies()

        assert any("Missing from requirements.txt: openai" in msg for msg in doctor.warnings)


class TestGPUDriverCheck:
    def test_cpu_only_message(self):
        doctor = SystemDoctor()
        with patch("shutil.which", return_value=None):
            doctor._check_gpu_driver()
        assert "CPU-only mode" in doctor.warnings[0]


class TestSecurityToolsCheck:
    def test_firejail_available(self):
        doctor = SystemDoctor()
        with patch("shutil.which", return_value="/usr/bin/firejail"):
            doctor._check_security_tools()
        assert any("Firejail available" in msg for msg in doctor.passes)

    def test_firejail_not_installed(self):
        doctor = SystemDoctor()
        with patch("shutil.which", return_value=None):
            doctor._check_security_tools()
        assert any("Firejail not installed" in msg for msg in doctor.warnings)


class TestExitCodes:
    """
    IMPORTANT: run_checks() calls all checks; without patching, your real system
    will produce warnings/failures and exit code 2, which is why your previous
    tests saw 2 instead of 1/0.
    """

    @patch.object(SystemDoctor, "_check_python")
    @patch.object(SystemDoctor, "_check_dependencies")
    @patch.object(SystemDoctor, "_check_gpu_driver")
    @patch.object(SystemDoctor, "_check_cuda")
    @patch.object(SystemDoctor, "_check_ollama")
    @patch.object(SystemDoctor, "_check_api_keys")
    @patch.object(SystemDoctor, "_check_security_tools")
    @patch.object(SystemDoctor, "_check_disk_space")
    @patch.object(SystemDoctor, "_check_memory")
    @patch.object(SystemDoctor, "_print_summary")
    def test_exit_codes(self, *_mocks):
        # all good → 0
        d = SystemDoctor()
        d.passes = ["ok"]
        d.warnings = []
        d.failures = []
        assert d.run_checks() == 0

        # warnings only → 1
        d = SystemDoctor()
        d.passes = ["ok"]
        d.warnings = ["warn"]
        d.failures = []
        assert d.run_checks() == 1

        # failures present → 2
        d = SystemDoctor()
        d.passes = ["ok"]
        d.warnings = ["warn"]
        d.failures = ["fail"]
        assert d.run_checks() == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
