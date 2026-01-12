"""
Tests for deterministic and agentic tools.

Tests tool functionality with mocked LLM calls.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.tutor.tools.agentic.examples_provider import ExamplesProviderTool
from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool
from cortex.tutor.tools.agentic.qa_handler import ConversationHandler, QAHandlerTool
from cortex.tutor.tools.deterministic.lesson_loader import (
    FALLBACK_LESSONS,
    LessonLoaderTool,
    get_fallback_lesson,
    load_lesson_with_fallback,
)


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


class TestLessonLoaderTool:
    """Tests for LessonLoaderTool."""

    def test_cache_miss(self, temp_db):
        """Test cache miss returns appropriate response."""
        loader = LessonLoaderTool(temp_db)
        result = loader._run("unknown_package")

        assert result["success"]
        assert not result["cache_hit"]
        assert result["lesson"] is None

    def test_force_fresh(self, temp_db):
        """Test force_fresh skips cache."""
        loader = LessonLoaderTool(temp_db)

        # Cache a lesson
        loader.cache_lesson("docker", {"summary": "cached"})

        # Force fresh should skip cache
        result = loader._run("docker", force_fresh=True)
        assert not result["cache_hit"]

    def test_cache_lesson_and_retrieve(self, temp_db):
        """Test caching and retrieving a lesson."""
        loader = LessonLoaderTool(temp_db)

        lesson = {"summary": "Docker is...", "explanation": "A container platform"}
        loader.cache_lesson("docker", lesson, ttl_hours=24)

        result = loader._run("docker")
        assert result["success"]
        assert result["cache_hit"]
        assert result["lesson"]["summary"] == "Docker is..."


class TestFallbackLessons:
    """Tests for fallback lesson templates."""

    def test_docker_fallback(self):
        """Test Docker fallback exists."""
        fallback = get_fallback_lesson("docker")
        assert fallback is not None
        assert fallback["package_name"] == "docker"
        assert "summary" in fallback

    def test_git_fallback(self):
        """Test Git fallback exists."""
        fallback = get_fallback_lesson("git")
        assert fallback is not None

    def test_nginx_fallback(self):
        """Test Nginx fallback exists."""
        fallback = get_fallback_lesson("nginx")
        assert fallback is not None

    def test_unknown_fallback(self):
        """Test unknown package returns None."""
        fallback = get_fallback_lesson("unknown_package")
        assert fallback is None

    def test_case_insensitive(self):
        """Test fallback lookup is case insensitive."""
        fallback = get_fallback_lesson("DOCKER")
        assert fallback is not None


class TestLoadLessonWithFallback:
    """Tests for load_lesson_with_fallback function."""

    def test_returns_cache_if_available(self, temp_db):
        """Test returns cached lesson if available."""
        # First cache a lesson
        from cortex.tutor.memory.sqlite_store import SQLiteStore

        store = SQLiteStore(temp_db)
        store.cache_lesson("docker", {"summary": "cached"}, ttl_hours=24)

        result = load_lesson_with_fallback("docker", temp_db)
        assert result["source"] == "cache"

    def test_returns_fallback_if_no_cache(self, temp_db):
        """Test returns fallback if no cache."""
        result = load_lesson_with_fallback("docker", temp_db)
        assert result["source"] == "fallback_template"

    def test_returns_none_for_unknown(self, temp_db):
        """Test returns none for unknown package."""
        result = load_lesson_with_fallback("totally_unknown", temp_db)
        assert result["source"] == "none"
        assert result["needs_generation"]


class TestLessonGeneratorTool:
    """Tests for LessonGeneratorTool with mocked LLM."""

    @patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic")
    @patch("cortex.tutor.tools.agentic.lesson_generator.get_config")
    def test_generate_lesson_structure(self, mock_config, mock_llm_class):
        """Test lesson generation returns proper structure."""
        # Mock config
        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        # Mock LLM response
        mock_response = {
            "package_name": "docker",
            "summary": "Docker is a containerization platform.",
            "explanation": "Docker allows you to...",
            "use_cases": ["Development", "Deployment"],
            "best_practices": ["Use official images"],
            "code_examples": [
                {
                    "title": "Run container",
                    "code": "docker run nginx",
                    "language": "bash",
                    "description": "Runs nginx",
                }
            ],
            "tutorial_steps": [
                {
                    "step_number": 1,
                    "title": "Install",
                    "content": "First, install Docker",
                }
            ],
            "installation_command": "apt install docker.io",
            "related_packages": ["podman"],
            "confidence": 0.9,
        }

        mock_chain = Mock()
        mock_chain.invoke.return_value = mock_response
        mock_llm = Mock()
        mock_llm.__or__ = Mock(return_value=mock_chain)
        mock_llm_class.return_value = mock_llm

        # Create tool and test
        tool = LessonGeneratorTool()
        tool.llm = mock_llm

        # Directly test structure method
        result = tool._structure_response(mock_response, "docker")

        assert result["package_name"] == "docker"
        assert "summary" in result
        assert "explanation" in result
        assert len(result["code_examples"]) == 1
        assert result["confidence"] == pytest.approx(0.9)

    def test_structure_response_handles_missing_fields(self):
        """Test structure_response handles missing fields gracefully."""
        # Skip LLM initialization by mocking
        with patch("cortex.tutor.tools.agentic.lesson_generator.get_config") as mock_config:
            mock_config.return_value = Mock(
                anthropic_api_key="test_key",
                model="claude-sonnet-4-20250514",
            )
            with patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic"):
                tool = LessonGeneratorTool()

                incomplete_response = {
                    "package_name": "test",
                    "summary": "Test summary",
                }

                result = tool._structure_response(incomplete_response, "test")

                assert result["package_name"] == "test"
                assert result["summary"] == "Test summary"
                assert result["use_cases"] == []
                assert result["best_practices"] == []


class TestExamplesProviderTool:
    """Tests for ExamplesProviderTool with mocked LLM."""

    def test_structure_response(self):
        """Test structure_response formats examples correctly."""
        with patch("cortex.tutor.tools.agentic.examples_provider.get_config") as mock_config:
            mock_config.return_value = Mock(
                anthropic_api_key="test_key",
                model="claude-sonnet-4-20250514",
            )
            with patch("cortex.tutor.tools.agentic.examples_provider.ChatAnthropic"):
                tool = ExamplesProviderTool()

                response = {
                    "package_name": "git",
                    "topic": "branching",
                    "examples": [
                        {
                            "title": "Create branch",
                            "code": "git checkout -b feature",
                            "language": "bash",
                            "description": "Creates new branch",
                        }
                    ],
                    "tips": ["Use descriptive names"],
                    "common_mistakes": ["Forgetting to commit"],
                    "confidence": 0.95,
                }

                result = tool._structure_response(response, "git", "branching")

                assert result["package_name"] == "git"
                assert result["topic"] == "branching"
                assert len(result["examples"]) == 1
                assert result["examples"][0]["title"] == "Create branch"


class TestQAHandlerTool:
    """Tests for QAHandlerTool with mocked LLM."""

    def test_structure_response(self):
        """Test structure_response formats answers correctly."""
        with patch("cortex.tutor.tools.agentic.qa_handler.get_config") as mock_config:
            mock_config.return_value = Mock(
                anthropic_api_key="test_key",
                model="claude-sonnet-4-20250514",
            )
            with patch("cortex.tutor.tools.agentic.qa_handler.ChatAnthropic"):
                tool = QAHandlerTool()

                response = {
                    "question_understood": "What is Docker?",
                    "answer": "Docker is a containerization platform.",
                    "explanation": "It allows you to package applications.",
                    "code_example": {
                        "code": "docker run hello-world",
                        "language": "bash",
                        "description": "Runs test container",
                    },
                    "related_topics": ["containers", "images"],
                    "confidence": 0.9,
                }

                result = tool._structure_response(response, "docker", "What is Docker?")

                assert result["answer"] == "Docker is a containerization platform."
                assert result["code_example"] is not None
                assert len(result["related_topics"]) == 2


class TestConversationHandler:
    """Tests for ConversationHandler."""

    def test_build_context_empty(self):
        """Test context building with empty history."""
        with patch("cortex.tutor.tools.agentic.qa_handler.get_config"):
            handler = ConversationHandler.__new__(ConversationHandler)
            handler.history = []

            context = handler._build_context()
            assert "Starting fresh" in context

    def test_build_context_with_history(self):
        """Test context building with history."""
        with patch("cortex.tutor.tools.agentic.qa_handler.get_config"):
            handler = ConversationHandler.__new__(ConversationHandler)
            handler.history = [
                {"question": "What is Docker?", "answer": "A platform"},
                {"question": "How to install?", "answer": "Use apt"},
            ]

            context = handler._build_context()
            assert "What is Docker?" in context
            assert "Recent discussion" in context

    def test_clear_history(self):
        """Test clearing conversation history."""
        with patch("cortex.tutor.tools.agentic.qa_handler.get_config"):
            handler = ConversationHandler.__new__(ConversationHandler)
            handler.history = [{"question": "test", "answer": "test"}]

            handler.clear_history()
            assert len(handler.history) == 0
