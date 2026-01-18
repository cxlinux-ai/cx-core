import sys
from unittest.mock import MagicMock, patch

import pytest

from cortex.cli import main


@pytest.fixture
def mock_docs_gen():
    with patch("cortex.cli.DocsGenerator") as mock:
        yield mock.return_value


def test_cli_docs_generate(mock_docs_gen):
    mock_docs_gen.generate_software_docs.return_value = {
        "Test.md": "/home/user/.cortex/docs/nginx/Test.md"
    }

    with patch("sys.argv", ["cortex", "docs", "generate", "nginx"]):
        assert main() == 0
        mock_docs_gen.generate_software_docs.assert_called_once_with("nginx")


def test_cli_docs_export(mock_docs_gen):
    mock_docs_gen.export_docs.return_value = "/home/user/nginx_docs.md"

    with patch("sys.argv", ["cortex", "docs", "export", "nginx", "--format", "pdf"]):
        assert main() == 0
        mock_docs_gen.export_docs.assert_called_once_with("nginx", format="pdf")


def test_cli_docs_view(mock_docs_gen):
    with patch("sys.argv", ["cortex", "docs", "view", "nginx", "quick-start"]):
        assert main() == 0
        mock_docs_gen.view_guide.assert_called_once_with("nginx", "quick-start")
