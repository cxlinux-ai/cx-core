import pytest
import asyncio
from unittest.mock import patch, MagicMock
from cx.dependency_guardian.guardian import DependencyGuardian, ConflictReport

@pytest.fixture
def mock_status_file(tmp_path):
    status_content = (
        "Package: pkg-a\n"
        "Depends: lib-x\n"
        "Conflicts: pkg-b\n"
        "Provides: mail-agent\n"
        "\n"
        "Package: pkg-c\n"
        "Provides: mail-agent\n"
    )
    d = tmp_path / "dpkg"
    d.mkdir()
    f = d / "status"
    f.write_text(status_content)
    return str(f)

def test_load_system_state(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    assert "pkg-a" in guardian.installed_packages
    assert "pkg-c" in guardian.installed_packages
    assert "mail-agent" in guardian.virtual_providers
    assert "pkg-a" in guardian.virtual_providers["mail-agent"]

def test_analyze_conflicts_direct(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    # Simulate a package that conflicts with installed pkg-a
    report = guardian._analyze_conflicts("new-pkg", [], ["pkg-a"])
    assert report.status == "CONFLICT_DETECTED"
    assert report.predicted_conflicts[0]["type"] == "DIRECT_CONFLICT"

def test_analyze_conflicts_virtual(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    # Simulate a package that conflicts with 'mail-agent'
    report = guardian._analyze_conflicts("new-pkg", [], ["mail-agent"])
    assert report.status == "CONFLICT_DETECTED"
    assert any(c["type"] == "VIRTUAL_CONFLICT" for c in report.predicted_conflicts)

@pytest.mark.asyncio
async def test_simulate_install_async(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "  Depends: lib-y\n  Conflicts: pkg-a"
        report = await guardian.simulate_install_async("test-pkg")
        assert report is not None
        assert report.status == "CONFLICT_DETECTED"

def test_simulate_install_not_found(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    with patch("subprocess.run", side_effect=FileNotFoundError):
        report = guardian.simulate_install("invalid-pkg")
        assert report is None
