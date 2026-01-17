"""Tests for cortex.tutor.llm module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


class TestExtractJsonContent:
    """Tests for _extract_json_content function."""

    def test_extract_plain_json(self):
        """Test extracting plain JSON."""
        from cortex.tutor.llm import _extract_json_content

        content = '{"key": "value"}'
        result = _extract_json_content(content)
        assert result == '{"key": "value"}'

    def test_extract_json_with_markdown_fence(self):
        """Test extracting JSON wrapped in markdown fences."""
        from cortex.tutor.llm import _extract_json_content

        content = '```json\n{"key": "value"}\n```'
        result = _extract_json_content(content)
        assert result == '{"key": "value"}'

    def test_extract_json_with_plain_fence(self):
        """Test extracting JSON wrapped in plain markdown fences."""
        from cortex.tutor.llm import _extract_json_content

        content = '```\n{"key": "value"}\n```'
        result = _extract_json_content(content)
        assert result == '{"key": "value"}'

    def test_extract_json_with_python_fence(self):
        """Test extracting JSON wrapped in python markdown fences."""
        from cortex.tutor.llm import _extract_json_content

        content = '```python\n{"key": "value"}\n```'
        result = _extract_json_content(content)
        assert result == '{"key": "value"}'

    def test_extract_json_with_whitespace(self):
        """Test extracting JSON with extra whitespace."""
        from cortex.tutor.llm import _extract_json_content

        content = '  \n  {"key": "value"}  \n  '
        result = _extract_json_content(content)
        assert result == '{"key": "value"}'


class TestParseStructuredResponse:
    """Tests for _parse_structured_response function."""

    def test_parse_valid_lesson_response(self):
        """Test parsing valid lesson response."""
        from cortex.tutor.contracts import LessonResponse
        from cortex.tutor.llm import _parse_structured_response

        content = json.dumps(
            {
                "summary": "Test summary",
                "explanation": "Test explanation",
                "installation_command": "apt install test",
                "confidence": 0.9,
            }
        )
        result = _parse_structured_response(content, LessonResponse)
        assert result.summary == "Test summary"
        assert result.confidence == pytest.approx(0.9)

    def test_parse_invalid_response_raises(self):
        """Test that invalid response raises ValidationError."""
        from cortex.tutor.contracts import LessonResponse
        from cortex.tutor.llm import _parse_structured_response

        with pytest.raises(ValidationError):
            _parse_structured_response('{"invalid": "data"}', LessonResponse)


class TestGetRouter:
    """Tests for get_router function."""

    def test_get_router_creates_singleton(self):
        """Test that get_router creates a singleton instance."""
        from cortex.tutor import llm

        # Reset the global router
        llm._router = None

        with patch.object(llm, "LLMRouter") as mock_router_class:
            mock_router = MagicMock()
            mock_router_class.return_value = mock_router

            router1 = llm.get_router()
            router2 = llm.get_router()

            # Should only create one instance
            assert mock_router_class.call_count == 1
            assert router1 is router2

        # Clean up
        llm._router = None


class TestGenerateLesson:
    """Tests for generate_lesson function."""

    def test_generate_lesson_success(self):
        """Test successful lesson generation."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "summary": "Test summary",
                "explanation": "Test explanation",
                "use_cases": ["use case 1"],
                "best_practices": ["practice 1"],
                "code_examples": [],
                "tutorial_steps": [],
                "installation_command": "apt install test",
                "related_packages": [],
                "confidence": 0.9,
            }
        )
        mock_response.cost_usd = 0.01

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.generate_lesson("docker")

            assert result["success"] is True
            assert result["lesson"]["summary"] == "Test summary"
            assert result["cost_usd"] == pytest.approx(0.01)

    def test_generate_lesson_with_options(self):
        """Test lesson generation with custom options."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "summary": "Advanced lesson",
                "explanation": "Advanced explanation",
                "installation_command": "apt install nginx",
                "confidence": 0.85,
            }
        )
        mock_response.cost_usd = 0.02

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.generate_lesson(
                "nginx",
                student_level="advanced",
                learning_style="hands-on",
                skip_areas=["basics", "intro"],
            )

            assert result["success"] is True
            # Verify the prompt includes skip areas
            call_args = mock_router.complete.call_args
            user_msg = call_args[1]["messages"][1]["content"]
            assert "basics" in user_msg
            assert "intro" in user_msg

    def test_generate_lesson_json_error(self):
        """Test lesson generation with JSON parse error."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = "not valid json"

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.generate_lesson("docker")

            assert result["success"] is False
            assert "error" in result
            assert result["lesson"] is None

    def test_generate_lesson_api_error(self):
        """Test lesson generation with API error."""
        from cortex.tutor import llm

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.side_effect = Exception("API error")
            mock_get_router.return_value = mock_router

            result = llm.generate_lesson("docker")

            assert result["success"] is False
            assert "API error" in result["error"]


class TestAnswerQuestion:
    """Tests for answer_question function."""

    def test_answer_question_success(self):
        """Test successful question answering."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "answer": "Docker is a containerization platform",
                "code_example": {"code": "docker ps", "language": "bash"},
                "related_topics": ["containers", "images"],
                "confidence": 0.95,
            }
        )
        mock_response.cost_usd = 0.005

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.answer_question("docker", "What is Docker?")

            assert result["success"] is True
            assert "containerization" in result["answer"]["answer"]
            assert result["cost_usd"] == pytest.approx(0.005)

    def test_answer_question_with_context(self):
        """Test question answering with context."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "answer": "test",
                "confidence": 0.9,
                "related_topics": [],
            }
        )
        mock_response.cost_usd = 0.01

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.answer_question(
                "docker",
                "How do I build?",
                context="Learning about Dockerfiles",
            )

            assert result["success"] is True
            # Verify context is in the prompt
            call_args = mock_router.complete.call_args
            user_msg = call_args[1]["messages"][1]["content"]
            assert "Learning about Dockerfiles" in user_msg

    def test_answer_question_json_error(self):
        """Test question answering with JSON parse error."""
        from cortex.tutor import llm

        mock_response = MagicMock()
        mock_response.content = "invalid json response"

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.return_value = mock_response
            mock_get_router.return_value = mock_router

            result = llm.answer_question("docker", "What is Docker?")

            assert result["success"] is False
            assert result["answer"] is None

    def test_answer_question_api_error(self):
        """Test question answering with API error."""
        from cortex.tutor import llm

        with patch.object(llm, "get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.complete.side_effect = RuntimeError("Connection failed")
            mock_get_router.return_value = mock_router

            result = llm.answer_question("docker", "What is Docker?")

            assert result["success"] is False
            assert "Connection failed" in result["error"]
