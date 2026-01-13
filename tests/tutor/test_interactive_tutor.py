"""
Tests for InteractiveTutor class.

Tests the interactive menu-driven tutoring interface.
"""

from unittest.mock import MagicMock, Mock, call, patch

import pytest


class TestInteractiveTutorInit:
    """Tests for InteractiveTutor initialization."""

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.TutorAgent")
    def test_init(self, mock_agent_class):
        """Test InteractiveTutor initialization."""
        from cortex.tutor.agents.tutor_agent import InteractiveTutor

        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent

        tutor = InteractiveTutor("docker")

        assert tutor.package_name == "docker"
        assert tutor.lesson is None


class TestInteractiveTutorStart:
    """Tests for InteractiveTutor.start method."""

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.TutorAgent")
    @patch("cortex.tutor.branding.get_user_input")
    @patch("cortex.tutor.branding.print_menu")
    @patch("cortex.tutor.branding.print_lesson_header")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.console")
    def test_start_loads_lesson(
        self, mock_console, mock_tutor_print, mock_header, mock_menu, mock_input, mock_agent_class
    ):
        """Test start loads lesson and shows menu."""
        from cortex.tutor.agents.tutor_agent import InteractiveTutor

        mock_agent = Mock()
        mock_agent.teach.return_value = {
            "validation_passed": True,
            "content": {
                "summary": "Docker is a container platform.",
                "explanation": "Details...",
            },
        }
        mock_agent_class.return_value = mock_agent

        # User selects Exit (7)
        mock_input.return_value = "7"

        tutor = InteractiveTutor("docker")
        tutor.start()

        mock_agent.teach.assert_called_once()
        mock_header.assert_called_once_with("docker")

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.TutorAgent")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_start_handles_failed_lesson(self, mock_tutor_print, mock_agent_class):
        """Test start handles failed lesson load."""
        from cortex.tutor.agents.tutor_agent import InteractiveTutor

        mock_agent = Mock()
        mock_agent.teach.return_value = {"validation_passed": False}
        mock_agent_class.return_value = mock_agent

        tutor = InteractiveTutor("docker")
        tutor.start()

        # Should print error
        mock_tutor_print.assert_any_call("Failed to load lesson. Please try again.", "error")


class TestInteractiveTutorMenuOptions:
    """Tests for InteractiveTutor menu options."""

    @pytest.fixture
    def mock_tutor(self):
        """Create a mock InteractiveTutor."""
        with patch("cortex.tutor.agents.tutor_agent.tutor_agent.TutorAgent"):
            from cortex.tutor.agents.tutor_agent import InteractiveTutor

            tutor = InteractiveTutor("docker")
            tutor.lesson = {
                "summary": "Docker summary",
                "explanation": "Docker explanation",
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
                        "content": "Install Docker first",
                        "code": "apt install docker",
                        "expected_output": "Done",
                    }
                ],
                "best_practices": ["Use official images", "Keep images small"],
            }
            tutor.agent = Mock()
            tutor.agent.mark_completed.return_value = True
            tutor.agent.ask.return_value = {
                "validation_passed": True,
                "content": {"answer": "Test answer"},
            }
            tutor.agent.get_progress.return_value = {
                "success": True,
                "stats": {"completed": 2, "total": 5},
            }
            return tutor

    @patch("cortex.tutor.branding.print_markdown")
    def test_show_concepts(self, mock_markdown, mock_tutor):
        """Test showing concepts."""
        mock_tutor._show_concepts()

        mock_markdown.assert_called_once()
        mock_tutor.agent.mark_completed.assert_called_with("docker", "concepts", 0.5)

    @patch("cortex.tutor.branding.print_code_example")
    @patch("cortex.tutor.branding.console")
    def test_show_examples(self, mock_console, mock_code_example, mock_tutor):
        """Test showing code examples."""
        mock_tutor._show_examples()

        mock_code_example.assert_called()
        mock_tutor.agent.mark_completed.assert_called_with("docker", "examples", 0.7)

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_show_examples_empty(self, mock_print, mock_tutor):
        """Test showing examples when none available."""
        mock_tutor.lesson["code_examples"] = []
        mock_tutor._show_examples()

        mock_print.assert_called_with("No examples available", "info")

    @patch("cortex.tutor.branding.print_tutorial_step")
    @patch("cortex.tutor.branding.get_user_input")
    @patch("cortex.tutor.branding.console")
    def test_run_tutorial(self, mock_console, mock_input, mock_step, mock_tutor):
        """Test running tutorial."""
        mock_input.return_value = ""  # Press Enter to continue

        mock_tutor._run_tutorial()

        mock_step.assert_called()
        mock_tutor.agent.mark_completed.assert_called_with("docker", "tutorial", 0.9)

    @patch("cortex.tutor.branding.print_tutorial_step")
    @patch("cortex.tutor.branding.get_user_input")
    def test_run_tutorial_quit(self, mock_input, mock_step, mock_tutor):
        """Test quitting tutorial early."""
        mock_input.return_value = "q"

        mock_tutor._run_tutorial()

        # Should still mark as completed
        mock_tutor.agent.mark_completed.assert_called()

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_run_tutorial_empty(self, mock_print, mock_tutor):
        """Test tutorial with no steps."""
        mock_tutor.lesson["tutorial_steps"] = []
        mock_tutor._run_tutorial()

        mock_print.assert_called_with("No tutorial available", "info")

    @patch("cortex.tutor.branding.print_best_practice")
    @patch("cortex.tutor.branding.console")
    def test_show_best_practices(self, mock_console, mock_practice, mock_tutor):
        """Test showing best practices."""
        mock_tutor._show_best_practices()

        assert mock_practice.call_count == 2
        mock_tutor.agent.mark_completed.assert_called_with("docker", "best_practices", 0.6)

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_show_best_practices_empty(self, mock_print, mock_tutor):
        """Test best practices when none available."""
        mock_tutor.lesson["best_practices"] = []
        mock_tutor._show_best_practices()

        mock_print.assert_called_with("No best practices available", "info")

    @patch("cortex.tutor.branding.get_user_input")
    @patch("cortex.tutor.branding.print_markdown")
    @patch("cortex.tutor.branding.tutor_print")
    def test_ask_question(self, mock_print, mock_markdown, mock_input, mock_tutor):
        """Test asking a question."""
        mock_input.return_value = "What is Docker?"

        mock_tutor._ask_question()

        mock_tutor.agent.ask.assert_called_with("docker", "What is Docker?")
        mock_markdown.assert_called()

    @patch("cortex.tutor.branding.get_user_input")
    def test_ask_question_empty(self, mock_input, mock_tutor):
        """Test asking with empty question."""
        mock_input.return_value = ""

        mock_tutor._ask_question()

        mock_tutor.agent.ask.assert_not_called()

    @patch("cortex.tutor.branding.get_user_input")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_ask_question_failed(self, mock_print, mock_input, mock_tutor):
        """Test asking question with failed response."""
        mock_input.return_value = "What?"
        mock_tutor.agent.ask.return_value = {"validation_passed": False}

        mock_tutor._ask_question()

        mock_print.assert_any_call("Sorry, I couldn't answer that question.", "error")

    @patch("cortex.tutor.branding.print_progress_summary")
    def test_show_progress(self, mock_progress, mock_tutor):
        """Test showing progress."""
        mock_tutor._show_progress()

        mock_progress.assert_called_with(2, 5, "docker")

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print")
    def test_show_progress_failed(self, mock_print, mock_tutor):
        """Test showing progress when failed."""
        mock_tutor.agent.get_progress.return_value = {"success": False}

        mock_tutor._show_progress()

        mock_print.assert_called_with("Could not load progress", "warning")


class TestInteractiveTutorNoLesson:
    """Tests for InteractiveTutor when lesson is None."""

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.TutorAgent")
    def test_methods_with_no_lesson(self, mock_agent_class):
        """Test methods handle None lesson gracefully."""
        from cortex.tutor.agents.tutor_agent import InteractiveTutor

        tutor = InteractiveTutor("docker")
        tutor.lesson = None
        tutor.agent = Mock()

        # These should not raise errors
        tutor._show_concepts()
        tutor._show_examples()
        tutor._run_tutorial()
        tutor._show_best_practices()
