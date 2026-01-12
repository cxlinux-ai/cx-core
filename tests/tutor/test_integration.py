"""
Integration tests for Intelligent Tutor.

End-to-end tests for the complete tutoring workflow.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.tutor.branding import console, print_banner, tutor_print
from cortex.tutor.config import Config, get_config, reset_config
from cortex.tutor.contracts.lesson_context import CodeExample, LessonContext, TutorialStep
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

    def test_lesson_context_display_dict(self):
        """Test to_display_dict method."""
        lesson = LessonContext(
            package_name="docker",
            summary="Summary",
            explanation="Explanation",
            use_cases=["Use 1", "Use 2"],
            best_practices=["Practice 1"],
            installation_command="apt install docker.io",
            confidence=0.9,
        )

        display = lesson.to_display_dict()

        assert display["package"] == "docker"
        assert display["confidence"] == "90%"


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

    def test_progress_context_recommendations(self):
        """Test getting learning recommendations."""
        progress = ProgressContext(
            weak_concepts=["networking", "volumes"],
            packages=[
                PackageProgress(
                    package_name="docker",
                    topics=[TopicProgress(topic="basics", completed=False)],
                )
            ],
        )

        recommendations = progress.get_recommendations()

        assert len(recommendations) >= 1
        assert any("networking" in r.lower() or "docker" in r.lower() for r in recommendations)


class TestBranding:
    """Tests for branding/UI utilities."""

    def test_tutor_print_success(self, capsys):
        """Test tutor_print with success status."""
        tutor_print("Test message", "success")
        _captured = capsys.readouterr()
        # Rich console output is complex, just ensure no errors

    def test_tutor_print_error(self, capsys):
        """Test tutor_print with error status."""
        tutor_print("Error message", "error")
        _captured = capsys.readouterr()

    def test_console_exists(self):
        """Test console is properly initialized."""
        assert console is not None


class TestCLI:
    """Tests for CLI commands."""

    def test_create_parser(self):
        """Test argument parser creation."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()

        # Test help doesn't raise
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

    def test_parse_progress_flag(self):
        """Test parsing progress flag."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["--progress"])

        assert args.progress is True

    def test_parse_reset_flag(self):
        """Test parsing reset flag."""
        from cortex.tutor.cli import create_parser

        parser = create_parser()

        # Reset all
        args = parser.parse_args(["--reset"])
        assert args.reset == "__all__"

        # Reset specific package
        args = parser.parse_args(["--reset", "docker"])
        assert args.reset == "docker"


class TestEndToEnd:
    """End-to-end workflow tests."""

    @patch("cortex.tutor.agents.tutor_agent.graph.LessonGeneratorTool")
    @patch("cortex.tutor.agents.tutor_agent.graph.LessonLoaderTool")
    @patch("cortex.tutor.agents.tutor_agent.graph.ProgressTrackerTool")
    def test_full_lesson_workflow_with_cache(
        self, mock_tracker_class, mock_loader_class, mock_generator_class
    ):
        """Test complete lesson workflow with cache hit."""
        # Set up mocks
        mock_tracker = Mock()
        mock_tracker._run.return_value = {
            "success": True,
            "profile": {
                "learning_style": "reading",
                "mastered_concepts": [],
                "weak_concepts": [],
            },
        }
        mock_tracker_class.return_value = mock_tracker

        cached_lesson = {
            "package_name": "docker",
            "summary": "Docker is a containerization platform.",
            "explanation": "Docker allows...",
            "use_cases": ["Development"],
            "best_practices": ["Use official images"],
            "code_examples": [],
            "tutorial_steps": [],
            "installation_command": "apt install docker.io",
            "confidence": 0.9,
        }

        mock_loader = Mock()
        mock_loader._run.return_value = {
            "cache_hit": True,
            "lesson": cached_lesson,
            "cost_saved_gbp": 0.02,
        }
        mock_loader.cache_lesson.return_value = True
        mock_loader_class.return_value = mock_loader

        # Run workflow
        from cortex.tutor.agents.tutor_agent.graph import (
            load_cache_node,
            plan_node,
            reflect_node,
        )
        from cortex.tutor.agents.tutor_agent.state import create_initial_state

        state = create_initial_state("docker")

        # Execute nodes
        state = plan_node(state)
        assert state["plan"]["strategy"] == "use_cache"
        assert state["cache_hit"] is True

        state = load_cache_node(state)
        assert state["results"]["type"] == "lesson"

        state = reflect_node(state)
        assert state["output"]["validation_passed"] is True
        assert state["output"]["cache_hit"] is True

    # Note: Real API test removed - use manual testing for API integration
    # Run: python -m cortex.tutor.cli docker
