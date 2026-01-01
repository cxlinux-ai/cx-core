from pathlib import Path
from unittest.mock import patch

from cortex.config.git_manager import GitManager


@patch("subprocess.run")
def test_init_repo_creates_git(mock_run, tmp_path):
    gm = GitManager(str(tmp_path))
    assert gm.init_repo() is True


@patch("subprocess.run")
def test_init_repo_when_exists(mock_run, tmp_path):
    (tmp_path / ".git").mkdir()
    gm = GitManager(str(tmp_path))
    assert gm.init_repo() is False


@patch("subprocess.run")
def test_commit_all_success(mock_run, tmp_path):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Committed"
    gm = GitManager(str(tmp_path))
    assert gm.commit_all("Test commit") is True


@patch("subprocess.run")
def test_commit_all_no_changes(mock_run, tmp_path):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = "nothing to commit"
    gm = GitManager(str(tmp_path))
    assert gm.commit_all("No changes") is False


@patch("subprocess.run")
def test_history_empty(mock_run, tmp_path):
    mock_run.return_value.returncode = 1
    gm = GitManager(str(tmp_path))
    assert gm.history() == ""


@patch("subprocess.run")
def test_rollback(mock_run, tmp_path):
    gm = GitManager(str(tmp_path))
    gm.rollback("abc123")
    mock_run.assert_called()
