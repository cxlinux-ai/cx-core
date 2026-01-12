"""
Tests for TutorAgent and LangGraph workflow.

Tests the main agent orchestrator and state management.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.tutor.agents.tutor_agent.graph import (
    fail_node,
    load_cache_node,
    plan_node,
    reflect_node,
    route_after_act,
    route_after_plan,
)
from cortex.tutor.agents.tutor_agent.state import (
    TutorAgentState,
    add_checkpoint,
    add_cost,
    add_error,
    create_initial_state,
    get_package_name,
    get_session_type,
    has_critical_error,
)


class TestTutorAgentState:
    """Tests for TutorAgentState and state utilities."""

    def test_create_initial_state(self):
        """Test creating initial state."""
        state = create_initial_state(
            package_name="docker",
            session_type="lesson",
        )

        assert state["input"]["package_name"] == "docker"
        assert state["input"]["session_type"] == "lesson"
        assert state["force_fresh"] is False
        assert state["errors"] == []
        assert state["cost_gbp"] == pytest.approx(0.0)

    def test_create_initial_state_qa_mode(self):
        """Test creating initial state for Q&A."""
        state = create_initial_state(
            package_name="docker",
            session_type="qa",
            question="What is Docker?",
        )

        assert state["input"]["session_type"] == "qa"
        assert state["input"]["question"] == "What is Docker?"

    def test_add_error(self):
        """Test adding errors to state."""
        state = create_initial_state("docker")
        add_error(state, "test_node", "Test error", recoverable=True)

        assert len(state["errors"]) == 1
        assert state["errors"][0]["node"] == "test_node"
        assert state["errors"][0]["error"] == "Test error"
        assert state["errors"][0]["recoverable"] is True

    def test_add_checkpoint(self):
        """Test adding checkpoints to state."""
        state = create_initial_state("docker")
        add_checkpoint(state, "plan_start", "ok", "Planning started")

        assert len(state["checkpoints"]) == 1
        assert state["checkpoints"][0]["name"] == "plan_start"
        assert state["checkpoints"][0]["status"] == "ok"

    def test_add_cost(self):
        """Test adding cost to state."""
        state = create_initial_state("docker")
        add_cost(state, 0.02)
        add_cost(state, 0.01)

        assert state["cost_gbp"] == pytest.approx(0.03)

    def test_has_critical_error_false(self):
        """Test has_critical_error returns False when no critical errors."""
        state = create_initial_state("docker")
        add_error(state, "test", "Recoverable error", recoverable=True)

        assert has_critical_error(state) is False

    def test_has_critical_error_true(self):
        """Test has_critical_error returns True when critical error exists."""
        state = create_initial_state("docker")
        add_error(state, "test", "Critical error", recoverable=False)

        assert has_critical_error(state) is True

    def test_get_session_type(self):
        """Test get_session_type utility."""
        state = create_initial_state("docker", session_type="qa")
        assert get_session_type(state) == "qa"

    def test_get_package_name(self):
        """Test get_package_name utility."""
        state = create_initial_state("nginx")
        assert get_package_name(state) == "nginx"


class TestGraphNodes:
    """Tests for LangGraph node functions."""

    @patch("cortex.tutor.agents.tutor_agent.graph.ProgressTrackerTool")
    @patch("cortex.tutor.agents.tutor_agent.graph.LessonLoaderTool")
    def test_plan_node_cache_hit(self, mock_loader_class, mock_tracker_class):
        """Test plan_node with cache hit."""
        # Mock tracker
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

        # Mock loader with cache hit
        mock_loader = Mock()
        mock_loader._run.return_value = {
            "cache_hit": True,
            "lesson": {"summary": "Cached lesson"},
        }
        mock_loader_class.return_value = mock_loader

        state = create_initial_state("docker")
        result = plan_node(state)

        assert result["plan"]["strategy"] == "use_cache"
        assert result["cache_hit"] is True

    @patch("cortex.tutor.agents.tutor_agent.graph.ProgressTrackerTool")
    @patch("cortex.tutor.agents.tutor_agent.graph.LessonLoaderTool")
    def test_plan_node_cache_miss(self, mock_loader_class, mock_tracker_class):
        """Test plan_node with cache miss."""
        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True, "profile": {}}
        mock_tracker_class.return_value = mock_tracker

        mock_loader = Mock()
        mock_loader._run.return_value = {"cache_hit": False, "lesson": None}
        mock_loader_class.return_value = mock_loader

        state = create_initial_state("docker")
        result = plan_node(state)

        assert result["plan"]["strategy"] == "generate_full"

    @patch("cortex.tutor.agents.tutor_agent.graph.ProgressTrackerTool")
    def test_plan_node_qa_mode(self, mock_tracker_class):
        """Test plan_node in Q&A mode."""
        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True, "profile": {}}
        mock_tracker_class.return_value = mock_tracker

        state = create_initial_state("docker", session_type="qa", question="What?")
        result = plan_node(state)

        assert result["plan"]["strategy"] == "qa_mode"

    def test_load_cache_node(self):
        """Test load_cache_node with cached data."""
        state = create_initial_state("docker")
        state["plan"] = {
            "strategy": "use_cache",
            "cached_data": {"summary": "Cached lesson", "explanation": "..."},
        }

        result = load_cache_node(state)

        assert result["lesson_content"]["summary"] == "Cached lesson"
        assert result["results"]["source"] == "cache"

    def test_load_cache_node_missing_data(self):
        """Test load_cache_node handles missing cache data."""
        state = create_initial_state("docker")
        state["plan"] = {"strategy": "use_cache", "cached_data": None}

        result = load_cache_node(state)

        assert len(result["errors"]) > 0

    def test_reflect_node_success(self):
        """Test reflect_node with successful results."""
        state = create_initial_state("docker")
        state["results"] = {
            "type": "lesson",
            "content": {"summary": "Test"},
            "source": "generated",
        }
        state["errors"] = []
        state["cost_gbp"] = 0.02

        result = reflect_node(state)

        assert result["output"]["validation_passed"] is True
        assert result["output"]["cost_gbp"] == pytest.approx(0.02)

    def test_reflect_node_failure(self):
        """Test reflect_node with missing results."""
        state = create_initial_state("docker")
        state["results"] = {}

        result = reflect_node(state)

        assert result["output"]["validation_passed"] is False
        assert "No content" in str(result["output"]["validation_errors"])

    def test_fail_node(self):
        """Test fail_node creates proper error output."""
        state = create_initial_state("docker")
        add_error(state, "test", "Test error")
        state["cost_gbp"] = 0.01

        result = fail_node(state)

        assert result["output"]["type"] == "error"
        assert result["output"]["validation_passed"] is False
        assert "Test error" in result["output"]["validation_errors"]


class TestRouting:
    """Tests for routing functions."""

    def test_route_after_plan_use_cache(self):
        """Test routing to cache path."""
        state = create_initial_state("docker")
        state["plan"] = {"strategy": "use_cache"}

        route = route_after_plan(state)
        assert route == "load_cache"

    def test_route_after_plan_generate(self):
        """Test routing to generation path."""
        state = create_initial_state("docker")
        state["plan"] = {"strategy": "generate_full"}

        route = route_after_plan(state)
        assert route == "generate_lesson"

    def test_route_after_plan_qa(self):
        """Test routing to Q&A path."""
        state = create_initial_state("docker")
        state["plan"] = {"strategy": "qa_mode"}

        route = route_after_plan(state)
        assert route == "qa"

    def test_route_after_plan_critical_error(self):
        """Test routing to fail on critical error."""
        state = create_initial_state("docker")
        add_error(state, "test", "Critical", recoverable=False)

        route = route_after_plan(state)
        assert route == "fail"

    def test_route_after_act_success(self):
        """Test routing after successful act phase."""
        state = create_initial_state("docker")
        state["results"] = {"type": "lesson", "content": {}}

        route = route_after_act(state)
        assert route == "reflect"

    def test_route_after_act_no_results(self):
        """Test routing to fail when no results."""
        state = create_initial_state("docker")
        state["results"] = {}

        route = route_after_act(state)
        assert route == "fail"


class TestTutorAgentIntegration:
    """Integration tests for TutorAgent."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    def test_teach_validation(self, mock_graph):
        """Test teach validates package name."""
        from cortex.tutor.agents.tutor_agent import TutorAgent
        from cortex.tutor.config import reset_config

        reset_config()

        with pytest.raises(ValueError) as exc_info:
            agent = TutorAgent()
            agent.teach("")

        assert "Invalid package name" in str(exc_info.value)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test-key"})
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    def test_ask_validation(self, mock_graph):
        """Test ask validates inputs."""
        from cortex.tutor.agents.tutor_agent import TutorAgent
        from cortex.tutor.config import reset_config

        reset_config()

        agent = TutorAgent()

        with pytest.raises(ValueError):
            agent.ask("", "question")

        with pytest.raises(ValueError):
            agent.ask("docker", "")
