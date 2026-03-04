import pytest
import asyncio
from unittest.mock import patch, MagicMock
from cx.dependency_guardian.guardian import DependencyGuardian, ConflictReport

@pytest.fixture
def mock_status_file(tmp_path):
    # Multi-line Depends field to test continuation aware parsing
    status_content = (
        "Package: pkg-a\n"
        "Depends: lib-x,\n"
        " lib-y,\n"
        " lib-z\n"
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

@pytest.mark.asyncio
async def test_load_system_state_async(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    await guardian.initialize()
    
    assert "pkg-a" in guardian.installed_packages
    # Verify multi-line continuation worked
    deps = guardian.installed_packages["pkg-a"]["Depends"]
    assert "lib-x" in deps
    assert "lib-y" in deps
    assert "lib-z" in deps
    
    assert "pkg-c" in guardian.installed_packages
    assert "mail-agent" in guardian.virtual_providers
    assert "pkg-a" in guardian.virtual_providers["mail-agent"]

def test_analyze_conflicts_direct(mock_status_file):
    # Synchronous test for core logic
    guardian = DependencyGuardian(status_path=mock_status_file)
    # Mock system state manually for pure logic test
    guardian.installed_packages = {"pkg-a": {}}
    
    report = guardian._analyze_conflicts("new-pkg", [], ["pkg-a"])
    assert report.status == "CONFLICT_DETECTED"
    assert report.predicted_conflicts[0]["type"] == "DIRECT_CONFLICT"

@pytest.mark.asyncio
async def test_simulate_install_success(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    await guardian.initialize()
    
    # Mock asyncio subprocess
    mock_proc = MagicMock()
    mock_proc.communicate = asyncio.coroutine(lambda: (b"  Depends: lib-y\n  Conflicts: pkg-a", b""))
    mock_proc.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=asyncio.coroutine(lambda *args, **kwargs: mock_proc)()):
        report = await guardian.simulate_install("test-pkg")
        assert report is not None
        assert report.target == "test-pkg"
        assert report.status == "CONFLICT_DETECTED"

@pytest.mark.asyncio
async def test_simulate_install_invalid_name():
    guardian = DependencyGuardian()
    # Test regex protection
    report = await guardian.simulate_install("pkg; rm -rf /")
    assert report is None

@pytest.mark.asyncio
async def test_simulate_install_timeout(mock_status_file):
    guardian = DependencyGuardian(status_path=mock_status_file)
    
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Simulate timeout
        mock_exec.side_effect = asyncio.TimeoutError
        report = await guardian.simulate_install("timeout-pkg")
        assert report is None
