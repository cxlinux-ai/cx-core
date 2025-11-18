import json

from packaging.version import Version

from cortex.update_manifest import UpdateChannel, UpdateManifest, SystemInfo
from cortex.versioning import CortexVersion
from cortex.updater import UpdateService


def make_manifest(version: str = "0.2.0", channel: str = "stable"):
    return UpdateManifest.from_dict(
        {
            "releases": [
                {
                    "version": version,
                    "channel": channel,
                    "download_url": "https://example.com/cortex.whl",
                    "sha256": "0" * 64,
                    "release_notes": "Test release",
                    "compatibility": [
                        {
                            "python": ">=3.8",
                            "os": ["linux"],
                            "arch": ["x86_64"],
                        }
                    ],
                }
            ]
        }
    )


def current_system():
    return SystemInfo(
        python_version=Version("3.10.0"),
        os_name="linux",
        architecture="x86_64",
        distro="ubuntu",
    )


def test_manifest_selects_newer_release():
    manifest = UpdateManifest.from_dict(
        {
            "releases": [
                {
                    "version": "0.1.5",
                    "channel": "stable",
                    "download_url": "https://example.com/old.whl",
                    "sha256": "1" * 64,
                },
                {
                    "version": "0.2.0",
                    "channel": "stable",
                    "download_url": "https://example.com/new.whl",
                    "sha256": "2" * 64,
                },
            ]
        }
    )
    current = CortexVersion.from_string("0.1.0")
    latest = manifest.find_latest(current_version=current, channel=UpdateChannel.STABLE, system=current_system())

    assert latest is not None
    assert latest.version.raw == "0.2.0"


def test_update_service_persists_channel_choice(tmp_path):
    state_file = tmp_path / "state.json"
    log_file = tmp_path / "update.log"

    service = UpdateService(
        manifest_url="https://invalid.local",
        state_file=state_file,
        log_file=log_file,
        system_info=current_system(),
    )

    service.set_channel(UpdateChannel.BETA)
    assert service.get_channel() == UpdateChannel.BETA

    service.set_channel(UpdateChannel.STABLE)
    assert service.get_channel() == UpdateChannel.STABLE

    with state_file.open() as fh:
        data = json.load(fh)
        assert data["channel"] == "stable"


def test_perform_update_dry_run(monkeypatch, tmp_path):
    state_file = tmp_path / "state.json"
    log_file = tmp_path / "update.log"

    service = UpdateService(
        manifest_url="https://invalid.local",
        state_file=state_file,
        log_file=log_file,
        system_info=current_system(),
    )

    manifest = make_manifest()

    monkeypatch.setattr("cortex.updater.get_installed_version", lambda: CortexVersion.from_string("0.1.0"))
    monkeypatch.setattr(UpdateService, "_fetch_manifest", lambda self: manifest)

    result = service.perform_update(dry_run=True)

    assert result.release is not None
    assert result.updated is False
    assert result.release.version.raw == "0.2.0"
    assert "dry run" in (result.message or "").lower()

