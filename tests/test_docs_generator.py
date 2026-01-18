import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.docs_generator import DocsGenerator
from cortex.installation_history import InstallationStatus


@pytest.fixture
def docs_gen():
    with (
        patch("cortex.docs_generator.ConfigManager"),
        patch("cortex.docs_generator.InstallationHistory"),
        patch("cortex.docs_generator.detect_hardware"),
    ):
        yield DocsGenerator()


def test_get_system_data(docs_gen):
    docs_gen.config_manager.detect_installed_packages.return_value = [{"name": "pkg1"}]
    with patch("cortex.docs_generator.detect_hardware") as mock_detect:
        mock_detect.return_value.to_dict.return_value = {"cpu": "v1"}
        data = docs_gen._get_system_data()
        assert data["packages"] == [{"name": "pkg1"}]
        assert data["system"] == {"cpu": "v1"}


def test_find_config_files(docs_gen, tmp_path):
    mock_file = MagicMock(spec=Path)
    mock_file.is_file.return_value = True
    mock_file.suffix = ".conf"
    mock_file.__str__.return_value = "/etc/nginx/nginx.conf"

    with (
        patch("os.path.exists", side_effect=lambda x: x == "/etc/nginx"),
        patch("pathlib.Path.is_dir", return_value=True),
        patch("pathlib.Path.glob") as mock_glob,
    ):
        mock_glob.return_value = [mock_file]
        found = docs_gen._find_config_files("nginx")
        assert "/etc/nginx" in found
        assert "/etc/nginx/nginx.conf" in found


def test_get_template_exception(docs_gen):
    with patch("builtins.open", side_effect=Exception("error")):
        template = docs_gen._get_template("any", "any")
        assert "template missing" in template.template


def test_render_methods_complete(docs_gen):
    data = {
        "name": "mypkg",
        "package_info": {"source": "pip", "version": "2.0"},
        "latest_install": MagicMock(
            timestamp="2025-01-01", commands_executed=["pip install mypkg"]
        ),
        "config_files": [],
        "generated_at": "now",
    }

    html = docs_gen._render_installation_guide(data)
    assert "pip install mypkg" in html

    html = docs_gen._render_quick_start(data)
    assert "python3 -m mypkg" in html


def test_get_software_data_logic(docs_gen):
    docs_gen.config_manager.detect_installed_packages.return_value = [
        {"name": "pkg1", "source": "apt"}
    ]
    mock_history = MagicMock()
    mock_history.packages = ["pkg1"]
    mock_history.status = InstallationStatus.SUCCESS
    mock_history.after_snapshot = []
    docs_gen.history.get_history.return_value = [mock_history]

    with patch.object(docs_gen, "_find_config_files", return_value=["/etc/cfg"]):
        data = docs_gen._get_software_data("pkg1")
        assert data["name"] == "pkg1"
        assert data["config_files"] == ["/etc/cfg"]
        assert data["latest_install"] == mock_history


def test_generate_software_docs_real(docs_gen, tmp_path):
    docs_gen.docs_dir = tmp_path / "docs"
    docs_gen.docs_dir.mkdir()

    # Don't mock _get_software_data, use the logic
    docs_gen.config_manager.detect_installed_packages.return_value = [
        {"name": "pkg", "source": "apt"}
    ]
    docs_gen.history.get_history.return_value = []

    paths = docs_gen.generate_software_docs("pkg")
    assert len(paths) == 4
    for path in paths.values():
        assert Path(path).exists()


def test_view_guide_not_found(docs_gen):
    docs_gen.console.print = MagicMock()
    docs_gen.view_guide("unknown", "quick-start")
    assert docs_gen.console.print.called


def test_view_guide_found(docs_gen, tmp_path):
    docs_gen.docs_dir = tmp_path / "docs"
    docs_gen.docs_dir.mkdir()
    pkg_dir = docs_gen.docs_dir / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "Quick_Start.md").write_text("# H")

    docs_gen.console.print = MagicMock()
    docs_gen.view_guide("pkg", "quick-start")
    assert docs_gen.console.print.called


def test_export_docs_md_logic(docs_gen, tmp_path):
    docs_gen.docs_dir = tmp_path / "docs"
    docs_gen.docs_dir.mkdir()
    pkg_dir = docs_gen.docs_dir / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "f.md").write_text("content")

    with patch("os.getcwd", return_value=str(tmp_path)):
        path = docs_gen.export_docs("pkg", format="md")
        assert Path(path).exists()
        assert "content" in Path(path).read_text()


def test_export_docs_html_logic(docs_gen, tmp_path):
    docs_gen.docs_dir = tmp_path / "docs"
    docs_gen.docs_dir.mkdir()
    pkg_dir = docs_gen.docs_dir / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "f.md").write_text("# H")

    mock_markdown = MagicMock()
    mock_markdown.markdown.return_value = "<html></html>"

    with (
        patch("os.getcwd", return_value=str(tmp_path)),
        patch("cortex.docs_generator.markdown", mock_markdown),
    ):
        path = docs_gen.export_docs("pkg", format="html")
        assert Path(path).exists()
        assert "<html></html>" in Path(path).read_text()


def test_export_pdf_full(docs_gen, tmp_path):
    docs_gen.docs_dir = tmp_path / "docs"
    docs_gen.docs_dir.mkdir()
    (docs_gen.docs_dir / "test-pkg").mkdir()
    (docs_gen.docs_dir / "test-pkg" / "test.md").write_text("# Test")

    mock_pdfkit = MagicMock()
    mock_markdown = MagicMock()
    mock_markdown.markdown.return_value = "<html></html>"

    with (
        patch("os.getcwd", return_value=str(tmp_path)),
        patch("cortex.docs_generator.pdfkit", mock_pdfkit),
        patch("cortex.docs_generator.markdown", mock_markdown),
        patch("os.remove"),
    ):

        res = docs_gen.export_docs("test-pkg", format="pdf")
        assert res.endswith(".pdf")
        assert mock_pdfkit.from_file.called
