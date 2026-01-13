"""
Integration tests for Intelligent Tutor.

Tests for configuration, contracts, branding, and CLI.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex.tutor.branding import console, tutor_print
from cortex.tutor.config import Config, reset_config
from cortex.tutor.contracts.lesson_context import CodeExample, LessonContext
from cortex.tutor.contracts.progress_context import (
    PackageProgress,
    ProgressContext,
    TopicProgress,
)


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global config before each test."""
    reset_config()
    yield
    reset_config()


class TestConfig:
    """Tests for configuration management."""

    def test_config_from_env(self, monkeypatch):
        """Test config loads from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
        monkeypatch.setenv("TUTOR_MODEL", "claude-sonnet-4-20250514")
        monkeypatch.setenv("TUTOR_DEBUG", "true")

        config = Config.from_env()

        assert config.anthropic_api_key == "sk-ant-test123"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.debug is True

    def test_config_missing_api_key(self, monkeypatch):
        """Test config raises error without API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError) as exc_info:
            Config.from_env()

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_config_validate_api_key(self):
        """Test API key validation."""
        config = Config(anthropic_api_key="sk-ant-valid")
        assert config.validate_api_key() is True

        config = Config(anthropic_api_key="invalid")
        assert config.validate_api_key() is False

    def test_config_data_dir_expansion(self):
        """Test data directory path expansion."""
        config = Config(
            anthropic_api_key="test",
            data_dir="~/test_dir",
        )
        assert "~" not in str(config.data_dir)

    def test_ensure_data_dir(self):
        """Test data directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                anthropic_api_key="test",
                data_dir=Path(tmpdir) / "subdir",
            )
            config.ensure_data_dir()
            assert config.data_dir.exists()


class TestLessonContext:
    """Tests for LessonContext contract."""

    def test_lesson_context_creation(self):
        """Test creating a LessonContext."""
        lesson = LessonContext(
            package_name="docker",
            summary="Docker is a container platform.",
            explanation="Docker allows you to package applications.",
            use_cases=["Development", "Deployment"],
            best_practices=["Use official images"],
            installation_command="apt install docker.io",
            confidence=0.9,
        )

        assert lesson.package_name == "docker"
        assert lesson.confidence == pytest.approx(0.9)
        assert len(lesson.use_cases) == 2

    def test_lesson_context_with_examples(self):
        """Test LessonContext with code examples."""
        example = CodeExample(
            title="Run container",
            code="docker run nginx",
            language="bash",
            description="Runs an nginx container",
        )

        lesson = LessonContext(
            package_name="docker",
            summary="Docker summary",
            explanation="Docker explanation",
            code_examples=[example],
            installation_command="apt install docker.io",
            confidence=0.9,
        )

        assert len(lesson.code_examples) == 1
        assert lesson.code_examples[0].title == "Run container"

    def test_lesson_context_serialization(self):
        """Test JSON serialization."""
        lesson = LessonContext(
            package_name="docker",
            summary="Summary",
            explanation="Explanation",
            installation_command="apt install docker.io",
            confidence=0.85,
        )

        json_str = lesson.to_json()
        restored = LessonContext.from_json(json_str)

        assert restored.package_name == "docker"
        assert restored.confidence == pytest.approx(0.85)


class TestProgressContext:
    """Tests for ProgressContext contract."""

    def test_progress_context_creation(self):
        """Test creating ProgressContext."""
        progress = ProgressContext(
            total_packages_started=5,
            total_packages_completed=2,
        )

        assert progress.total_packages_started == 5
        assert progress.total_packages_completed == 2

    def test_package_progress_completion(self):
        """Test PackageProgress completion calculation."""
        topics = [
            TopicProgress(topic="basics", completed=True, score=0.9),
            TopicProgress(topic="advanced", completed=False, score=0.5),
        ]

        package = PackageProgress(
            package_name="docker",
            topics=topics,
        )

        assert package.completion_percentage == pytest.approx(50.0)
        assert package.average_score == pytest.approx(0.7)
        assert not package.is_complete()
        assert package.get_next_topic() == "advanced"


class TestBranding:
    """Tests for branding/UI utilities."""

    def test_tutor_print_success(self, capsys):
        """Test tutor_print with success status."""
        tutor_print("Test message", "success")

    def test_tutor_print_error(self, capsys):
        """Test tutor_print with error status."""
        tutor_print("Error message", "error")

    def test_console_exists(self):
        """Test console is properly initialized."""
        assert console is not None


class TestCLI:
    """Tests for CLI commands."""

    def test_create_parser(self):
        """Test argument parser creation."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_version_flag(self):
        """Test version flag."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_parse_package_argument(self):
        """Test parsing package argument."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["docker"])

        assert args.package == "docker"

    def test_parse_question_flag(self):
        """Test parsing question flag."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["docker", "-q", "What is Docker?"])

        assert args.package == "docker"
        assert args.question == "What is Docker?"

    def test_parse_list_flag(self):
        """Test parsing list flag."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["--list"])

        assert args.list is True
