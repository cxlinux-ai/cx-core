"""
Tests for CLI module.

Comprehensive tests for command-line interface.
"""

import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.tutor.cli import (
    cmd_list_packages,
    cmd_progress,
    cmd_question,
    cmd_reset,
    cmd_teach,
    create_parser,
    main,
)


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_creates_parser(self):
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "tutor"

    def test_package_argument(self):
        """Test parsing package argument."""
        parser = create_parser()
        args = parser.parse_args(["docker"])
        assert args.package == "docker"

    def test_version_flag(self):
        """Test version flag exits."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_verbose_flag(self):
        """Test verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["-v", "docker"])
        assert args.verbose is True

    def test_list_flag(self):
        """Test list flag."""
        parser = create_parser()
        args = parser.parse_args(["--list"])
        assert args.list is True

    def test_progress_flag(self):
        """Test progress flag."""
        parser = create_parser()
        args = parser.parse_args(["--progress"])
        assert args.progress is True

    def test_reset_flag_all(self):
        """Test reset flag without package."""
        parser = create_parser()
        args = parser.parse_args(["--reset"])
        assert args.reset == "__all__"

    def test_reset_flag_package(self):
        """Test reset flag with package."""
        parser = create_parser()
        args = parser.parse_args(["--reset", "docker"])
        assert args.reset == "docker"

    def test_fresh_flag(self):
        """Test fresh flag."""
        parser = create_parser()
        args = parser.parse_args(["--fresh", "docker"])
        assert args.fresh is True

    def test_question_flag(self):
        """Test question flag."""
        parser = create_parser()
        args = parser.parse_args(["docker", "-q", "What is Docker?"])
        assert args.question == "What is Docker?"
        assert args.package == "docker"


class TestCmdTeach:
    """Tests for cmd_teach function."""

    def test_invalid_package_name(self):
        """Test teach with invalid package name."""
        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_teach("")
            assert result == 1

    def test_blocked_package_name(self):
        """Test teach with blocked pattern."""
        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_teach("rm -rf /")
            assert result == 1

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.InteractiveTutor")
    def test_successful_teach(self, mock_tutor_class):
        """Test successful teach session."""
        from cortex.tutor.config import reset_config

        reset_config()  # Reset config singleton

        mock_tutor = Mock()
        mock_tutor_class.return_value = mock_tutor

        result = cmd_teach("docker")
        assert result == 0
        mock_tutor.start.assert_called_once()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.InteractiveTutor")
    def test_teach_with_value_error(self, mock_tutor_class):
        """Test teach handles ValueError."""
        from cortex.tutor.config import reset_config

        reset_config()

        mock_tutor_class.side_effect = ValueError("Test error")

        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_teach("docker")
            assert result == 1

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.InteractiveTutor")
    def test_teach_with_keyboard_interrupt(self, mock_tutor_class):
        """Test teach handles KeyboardInterrupt."""
        from cortex.tutor.config import reset_config

        reset_config()

        mock_tutor = Mock()
        mock_tutor.start.side_effect = KeyboardInterrupt()
        mock_tutor_class.return_value = mock_tutor

        with patch("cortex.tutor.cli.console"):
            with patch("cortex.tutor.cli.tutor_print"):
                result = cmd_teach("docker")
                assert result == 0


class TestCmdQuestion:
    """Tests for cmd_question function."""

    def test_invalid_package(self):
        """Test question with invalid package."""
        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_question("", "What?")
            assert result == 1

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.TutorAgent")
    def test_successful_question(self, mock_agent_class):
        """Test successful question."""
        from cortex.tutor.config import reset_config

        reset_config()

        mock_agent = Mock()
        mock_agent.ask.return_value = {
            "validation_passed": True,
            "content": {
                "answer": "Docker is a container platform.",
                "code_example": None,
                "related_topics": [],
            },
        }
        mock_agent_class.return_value = mock_agent

        with patch("cortex.tutor.cli.console"):
            result = cmd_question("docker", "What is Docker?")
            assert result == 0

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.TutorAgent")
    def test_question_with_code_example(self, mock_agent_class):
        """Test question with code example in response."""
        from cortex.tutor.config import reset_config

        reset_config()

        mock_agent = Mock()
        mock_agent.ask.return_value = {
            "validation_passed": True,
            "content": {
                "answer": "Run a container like this.",
                "code_example": {
                    "code": "docker run nginx",
                    "language": "bash",
                },
                "related_topics": ["containers", "images"],
            },
        }
        mock_agent_class.return_value = mock_agent

        with patch("cortex.tutor.cli.console"):
            with patch("cortex.tutor.branding.print_code_example"):
                result = cmd_question("docker", "How to run?")
                assert result == 0

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.TutorAgent")
    def test_question_validation_failed(self, mock_agent_class):
        """Test question when validation fails."""
        from cortex.tutor.config import reset_config

        reset_config()

        mock_agent = Mock()
        mock_agent.ask.return_value = {"validation_passed": False}
        mock_agent_class.return_value = mock_agent

        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_question("docker", "What?")
            assert result == 1


class TestCmdListPackages:
    """Tests for cmd_list_packages function."""

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_no_packages(self, mock_config_class, mock_store_class):
        """Test list with no packages."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.get_packages_studied.return_value = []
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.tutor_print"):
            result = cmd_list_packages()
            assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_with_packages(self, mock_config_class, mock_store_class):
        """Test list with packages."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.get_packages_studied.return_value = ["docker", "nginx"]
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.console"):
            result = cmd_list_packages()
            assert result == 0

    @patch("cortex.tutor.cli.Config")
    def test_list_with_error(self, mock_config_class):
        """Test list handles errors."""
        mock_config_class.from_env.side_effect = Exception("Test error")

        with patch("cortex.tutor.cli.print_error_panel"):
            result = cmd_list_packages()
            assert result == 1


class TestCmdProgress:
    """Tests for cmd_progress function."""

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_progress_for_package(self, mock_config_class, mock_store_class):
        """Test progress for specific package."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.get_completion_stats.return_value = {
            "completed": 3,
            "total": 5,
            "avg_score": 0.8,
            "total_time_seconds": 600,
        }
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.print_progress_summary"):
            with patch("cortex.tutor.cli.console"):
                result = cmd_progress("docker")
                assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_progress_no_package_found(self, mock_config_class, mock_store_class):
        """Test progress when no progress found."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.get_completion_stats.return_value = None
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.tutor_print"):
            result = cmd_progress("docker")
            assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_progress_all(self, mock_config_class, mock_store_class):
        """Test progress for all packages."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        # Create mock progress objects with attributes
        progress1 = Mock(package_name="docker", topic="basics", completed=True, score=0.9)
        progress2 = Mock(package_name="docker", topic="advanced", completed=False, score=0.5)

        mock_store = Mock()
        mock_store.get_all_progress.return_value = [progress1, progress2]
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.print_table"):
            result = cmd_progress()
            assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    def test_progress_empty(self, mock_config_class, mock_store_class):
        """Test progress when empty."""
        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.get_all_progress.return_value = []
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.tutor_print"):
            result = cmd_progress()
            assert result == 0


class TestCmdReset:
    """Tests for cmd_reset function."""

    @patch("cortex.tutor.cli.get_user_input")
    def test_reset_cancelled(self, mock_input):
        """Test reset when cancelled."""
        mock_input.return_value = "n"

        with patch("cortex.tutor.cli.tutor_print"):
            result = cmd_reset()
            assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    @patch("cortex.tutor.cli.get_user_input")
    def test_reset_confirmed(self, mock_input, mock_config_class, mock_store_class):
        """Test reset when confirmed."""
        mock_input.return_value = "y"

        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.reset_progress.return_value = 5
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.print_success_panel"):
            result = cmd_reset()
            assert result == 0

    @patch("cortex.tutor.cli.SQLiteStore")
    @patch("cortex.tutor.cli.Config")
    @patch("cortex.tutor.cli.get_user_input")
    def test_reset_specific_package(self, mock_input, mock_config_class, mock_store_class):
        """Test reset for specific package."""
        mock_input.return_value = "y"

        mock_config = Mock()
        mock_config.get_db_path.return_value = Path(tempfile.gettempdir()) / "test.db"
        mock_config_class.from_env.return_value = mock_config

        mock_store = Mock()
        mock_store.reset_progress.return_value = 3
        mock_store_class.return_value = mock_store

        with patch("cortex.tutor.cli.print_success_panel"):
            result = cmd_reset("docker")
            assert result == 0


class TestMain:
    """Tests for main entry point."""

    def test_no_args_shows_help(self):
        """Test no arguments shows help."""
        with patch("cortex.tutor.cli.create_parser") as mock_parser:
            mock_p = Mock()
            mock_p.parse_args.return_value = Mock(
                package=None, list=False, progress=False, reset=None, question=None
            )
            mock_parser.return_value = mock_p

            result = main([])
            assert result == 0
            mock_p.print_help.assert_called_once()

    @patch("cortex.tutor.cli.cmd_list_packages")
    def test_list_command(self, mock_list):
        """Test list command."""
        mock_list.return_value = 0
        _result = main(["--list"])
        mock_list.assert_called_once()

    @patch("cortex.tutor.cli.cmd_progress")
    def test_progress_command(self, mock_progress):
        """Test progress command."""
        mock_progress.return_value = 0
        _result = main(["--progress"])
        mock_progress.assert_called_once()

    @patch("cortex.tutor.cli.cmd_reset")
    def test_reset_command(self, mock_reset):
        """Test reset command."""
        mock_reset.return_value = 0
        _result = main(["--reset"])
        mock_reset.assert_called_once()

    @patch("cortex.tutor.cli.cmd_question")
    def test_question_command(self, mock_question):
        """Test question command."""
        mock_question.return_value = 0
        _result = main(["docker", "-q", "What is Docker?"])
        mock_question.assert_called_once()

    @patch("cortex.tutor.cli.cmd_teach")
    @patch("cortex.tutor.cli.print_banner")
    def test_teach_command(self, mock_banner, mock_teach):
        """Test teach command."""
        mock_teach.return_value = 0
        _result = main(["docker"])
        mock_teach.assert_called_once()
        mock_banner.assert_called_once()
