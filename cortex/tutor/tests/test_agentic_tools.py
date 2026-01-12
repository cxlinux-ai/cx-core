"""
Tests for agentic tools structure methods.

Tests the _structure_response methods with mocked responses.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestLessonGeneratorStructure:
    """Tests for LessonGeneratorTool structure methods."""

    @patch("cortex.tutor.tools.agentic.lesson_generator.get_config")
    @patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic")
    def test_structure_response_full(self, mock_llm_class, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = LessonGeneratorTool()

        response = {
            "package_name": "docker",
            "summary": "Docker is a platform.",
            "explanation": "Docker allows...",
            "use_cases": ["Dev", "Prod"],
            "best_practices": ["Use official images"],
            "code_examples": [{"title": "Run", "code": "docker run", "language": "bash"}],
            "tutorial_steps": [{"step_number": 1, "title": "Start", "content": "Begin"}],
            "installation_command": "apt install docker",
            "related_packages": ["podman"],
            "confidence": 0.9,
        }

        result = tool._structure_response(response, "docker")

        assert result["package_name"] == "docker"
        assert result["summary"] == "Docker is a platform."
        assert len(result["use_cases"]) == 2
        assert result["confidence"] == pytest.approx(0.9)

    @patch("cortex.tutor.tools.agentic.lesson_generator.get_config")
    @patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic")
    def test_structure_response_minimal(self, mock_llm_class, mock_config):
        """Test structure_response with minimal response."""
        from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = LessonGeneratorTool()

        response = {
            "package_name": "test",
            "summary": "Test summary",
        }

        result = tool._structure_response(response, "test")

        assert result["package_name"] == "test"
        assert result["use_cases"] == []
        assert result["best_practices"] == []


class TestExamplesProviderStructure:
    """Tests for ExamplesProviderTool structure methods."""

    @patch("cortex.tutor.tools.agentic.examples_provider.get_config")
    @patch("cortex.tutor.tools.agentic.examples_provider.ChatAnthropic")
    def test_structure_response_full(self, mock_llm_class, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.examples_provider import ExamplesProviderTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = ExamplesProviderTool()

        response = {
            "package_name": "git",
            "topic": "branching",
            "examples": [{"title": "Create", "code": "git checkout -b", "language": "bash"}],
            "tips": ["Use descriptive names"],
            "common_mistakes": ["Forgetting to commit"],
            "confidence": 0.95,
        }

        result = tool._structure_response(response, "git", "branching")

        assert result["package_name"] == "git"
        assert result["topic"] == "branching"
        assert len(result["examples"]) == 1


class TestQAHandlerStructure:
    """Tests for QAHandlerTool structure methods."""

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    @patch("cortex.tutor.tools.agentic.qa_handler.ChatAnthropic")
    def test_structure_response_full(self, mock_llm_class, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = QAHandlerTool()

        response = {
            "question_understood": "What is Docker?",
            "answer": "Docker is a container platform.",
            "explanation": "It allows packaging applications.",
            "code_example": {"code": "docker run", "language": "bash"},
            "related_topics": ["containers", "images"],
            "confidence": 0.9,
        }

        result = tool._structure_response(response, "docker", "What is Docker?")

        assert result["answer"] == "Docker is a container platform."
        assert result["code_example"] is not None


class TestConversationHandler:
    """Tests for ConversationHandler."""

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    @patch("cortex.tutor.tools.agentic.qa_handler.ChatAnthropic")
    def test_build_context_empty(self, mock_llm_class, mock_config):
        """Test context building with empty history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        handler = ConversationHandler("docker")
        handler.history = []

        context = handler._build_context()
        assert "Starting fresh" in context

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    @patch("cortex.tutor.tools.agentic.qa_handler.ChatAnthropic")
    def test_build_context_with_history(self, mock_llm_class, mock_config):
        """Test context building with history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        handler = ConversationHandler("docker")
        handler.history = [
            {"question": "What is Docker?", "answer": "A platform"},
        ]

        context = handler._build_context()
        assert "What is Docker?" in context

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    @patch("cortex.tutor.tools.agentic.qa_handler.ChatAnthropic")
    def test_clear_history(self, mock_llm_class, mock_config):
        """Test clearing history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        handler = ConversationHandler("docker")
        handler.history = [{"q": "test"}]
        handler.clear_history()

        assert len(handler.history) == 0
