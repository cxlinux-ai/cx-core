"""
Tutor Agent Graph - LangGraph workflow definition.

Implements the Plan→Act→Reflect pattern for interactive tutoring.
"""

from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from cortex.tutor.agents.tutor_agent.state import (
    TutorAgentState,
    add_checkpoint,
    add_cost,
    add_error,
    get_package_name,
    get_session_type,
    has_critical_error,
)
from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool
from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool
from cortex.tutor.tools.deterministic.lesson_loader import LessonLoaderTool
from cortex.tutor.tools.deterministic.progress_tracker import ProgressTrackerTool

# ==================== Node Functions ====================


def plan_node(state: TutorAgentState) -> TutorAgentState:
    """
    PLAN Phase: Decide on strategy for handling the request.

    Implements hybrid approach:
    1. Check cache first (deterministic, free)
    2. Use rules for simple requests
    3. Use LLM planner for complex decisions
    """
    package_name = get_package_name(state)
    session_type = get_session_type(state)
    force_fresh = state.get("force_fresh", False)

    add_checkpoint(state, "plan_start", "ok", f"Planning for {package_name}")

    # Load student profile (deterministic)
    progress_tool = ProgressTrackerTool()
    profile_result = progress_tool._run("get_profile")
    if profile_result.get("success"):
        state["student_profile"] = profile_result["profile"]

    # Q&A mode - skip cache, go directly to Q&A
    if session_type == "qa":
        state["plan"] = {
            "strategy": "qa_mode",
            "cached_data": None,
            "estimated_cost": 0.02,
            "reasoning": "Q&A session requested, using qa_handler",
        }
        add_checkpoint(state, "plan_complete", "ok", "Strategy: qa_mode")
        return state

    # Check cache (deterministic, free)
    if not force_fresh:
        loader = LessonLoaderTool()
        cache_result = loader._run(package_name)

        if cache_result.get("cache_hit"):
            state["plan"] = {
                "strategy": "use_cache",
                "cached_data": cache_result["lesson"],
                "estimated_cost": 0.0,
                "reasoning": "Valid cache found, reusing existing lesson",
            }
            state["cache_hit"] = True
            state["cost_saved_gbp"] = 0.02
            add_checkpoint(state, "plan_complete", "ok", "Strategy: use_cache")
            return state

    # No cache - need to generate
    state["plan"] = {
        "strategy": "generate_full",
        "cached_data": None,
        "estimated_cost": 0.02,
        "reasoning": "No valid cache, generating fresh lesson",
    }
    add_checkpoint(state, "plan_complete", "ok", "Strategy: generate_full")
    return state


def load_cache_node(state: TutorAgentState) -> TutorAgentState:
    """
    ACT Phase - Cache Path: Load lesson from cache.

    This node is reached when plan.strategy == "use_cache".
    """
    cached_data = state.get("plan", {}).get("cached_data", {})

    if cached_data:
        state["lesson_content"] = cached_data
        state["results"] = {
            "type": "lesson",
            "content": cached_data,
            "source": "cache",
        }
        add_checkpoint(state, "cache_load", "ok", "Loaded lesson from cache")
    else:
        add_error(state, "load_cache", "Cache data missing", recoverable=True)

    return state


def _infer_student_level(profile: dict) -> str:
    """Infer student level from profile based on mastered concepts."""
    mastered = profile.get("mastered_concepts", [])
    mastered_count = len(mastered)

    if mastered_count >= 10:
        return "advanced"
    elif mastered_count >= 5:
        return "intermediate"
    return "beginner"


def generate_lesson_node(state: TutorAgentState) -> TutorAgentState:
    """
    ACT Phase - Generation Path: Generate new lesson content.

    Uses LessonGeneratorTool to create comprehensive lesson.
    """
    package_name = get_package_name(state)
    profile = state.get("student_profile", {})

    add_checkpoint(state, "generate_start", "ok", f"Generating lesson for {package_name}")

    # Determine student level dynamically from profile
    student_level = profile.get("student_level") or _infer_student_level(profile)

    try:
        generator = LessonGeneratorTool()
        result = generator._run(
            package_name=package_name,
            student_level=student_level,
            learning_style=profile.get("learning_style", "reading"),
            skip_areas=profile.get("mastered_concepts", []),
        )

        if result.get("success"):
            state["lesson_content"] = result["lesson"]
            state["results"] = {
                "type": "lesson",
                "content": result["lesson"],
                "source": "generated",
            }
            add_cost(state, result.get("cost_gbp", 0.02))

            # Cache the generated lesson
            loader = LessonLoaderTool()
            loader.cache_lesson(package_name, result["lesson"])

            add_checkpoint(state, "generate_complete", "ok", "Lesson generated and cached")
        else:
            add_error(state, "generate_lesson", result.get("error", "Unknown error"))
            add_checkpoint(state, "generate_complete", "error", "Generation failed")

    except Exception as e:
        add_error(state, "generate_lesson", str(e))
        add_checkpoint(state, "generate_complete", "error", str(e))

    return state


def qa_node(state: TutorAgentState) -> TutorAgentState:
    """
    ACT Phase - Q&A Path: Handle user questions.

    Uses QAHandlerTool for free-form questions.
    """
    input_data = state.get("input", {})
    question = input_data.get("question", "")
    package_name = get_package_name(state)
    profile = state.get("student_profile", {})

    if not question:
        add_error(state, "qa", "No question provided", recoverable=False)
        return state

    add_checkpoint(state, "qa_start", "ok", f"Answering question about {package_name}")

    try:
        qa_handler = QAHandlerTool()
        result = qa_handler._run(
            package_name=package_name,
            question=question,
            learning_style=profile.get("learning_style", "reading"),
            mastered_concepts=profile.get("mastered_concepts", []),
            weak_concepts=profile.get("weak_concepts", []),
        )

        if result.get("success"):
            state["qa_result"] = result["answer"]
            state["results"] = {
                "type": "qa",
                "content": result["answer"],
                "source": "generated",
            }
            add_cost(state, result.get("cost_gbp", 0.02))
            add_checkpoint(state, "qa_complete", "ok", "Question answered")
        else:
            add_error(state, "qa", result.get("error", "Unknown error"))

    except Exception as e:
        add_error(state, "qa", str(e))

    return state


def reflect_node(state: TutorAgentState) -> TutorAgentState:
    """
    REFLECT Phase: Validate results and prepare output.

    1. Deterministic validation (free)
    2. Prepare final output
    """
    add_checkpoint(state, "reflect_start", "ok", "Validating results")

    results = state.get("results", {})
    errors = state.get("errors", [])

    # Deterministic validation
    validation_errors = []

    # Check for content
    if not results.get("content"):
        validation_errors.append("No content generated")

    # Check for critical errors
    if has_critical_error(state):
        validation_errors.append("Critical errors occurred during processing")

    # Calculate confidence
    confidence = 1.0
    if errors:
        confidence -= 0.1 * len(errors)
    if state.get("cache_hit"):
        confidence = min(confidence, 0.95)  # Cached content might be stale

    # Prepare output
    content = results.get("content", {})
    output = {
        "type": results.get("type", "unknown"),
        "package_name": get_package_name(state),
        "content": content,
        "source": results.get("source", "unknown"),
        "confidence": max(confidence, 0.0),
        "cost_gbp": state.get("cost_gbp", 0.0),
        "cost_saved_gbp": state.get("cost_saved_gbp", 0.0),
        "cache_hit": state.get("cache_hit", False),
        "validation_passed": len(validation_errors) == 0,
        "validation_errors": validation_errors,
        "checkpoints": state.get("checkpoints", []),
    }

    state["output"] = output
    add_checkpoint(state, "reflect_complete", "ok", f"Validation: {len(validation_errors)} errors")

    return state


def fail_node(state: TutorAgentState) -> TutorAgentState:
    """
    Failure node: Handle unrecoverable errors.
    """
    errors = state.get("errors", [])
    error_messages = [e.get("error", "Unknown") for e in errors]

    state["output"] = {
        "type": "error",
        "package_name": get_package_name(state),
        "content": None,
        "source": "failed",
        "confidence": 0.0,
        "cost_gbp": state.get("cost_gbp", 0.0),
        "cost_saved_gbp": 0.0,
        "cache_hit": False,
        "validation_passed": False,
        "validation_errors": error_messages,
        "checkpoints": state.get("checkpoints", []),
    }

    return state


# ==================== Routing Functions ====================


def route_after_plan(
    state: TutorAgentState,
) -> Literal["load_cache", "generate_lesson", "qa", "fail"]:
    """
    Route after PLAN phase based on strategy.
    """
    if has_critical_error(state):
        return "fail"

    strategy = state.get("plan", {}).get("strategy", "generate_full")

    if strategy == "use_cache":
        return "load_cache"
    elif strategy == "qa_mode":
        return "qa"
    else:
        return "generate_lesson"


def route_after_act(state: TutorAgentState) -> Literal["reflect", "fail"]:
    """
    Route after ACT phase.
    """
    if has_critical_error(state):
        return "fail"

    # Check if we have results
    if not state.get("results"):
        return "fail"

    return "reflect"


# ==================== Graph Builder ====================


def create_tutor_graph() -> CompiledStateGraph:
    """
    Create the LangGraph workflow for the Tutor Agent.

    Returns:
        Compiled StateGraph ready for execution.
    """
    # Create graph with state schema
    graph = StateGraph(TutorAgentState)

    # Add nodes
    graph.add_node("plan", plan_node)
    graph.add_node("load_cache", load_cache_node)
    graph.add_node("generate_lesson", generate_lesson_node)
    graph.add_node("qa", qa_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("fail", fail_node)

    # Set entry point
    graph.set_entry_point("plan")

    # Add conditional edges after PLAN
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "load_cache": "load_cache",
            "generate_lesson": "generate_lesson",
            "qa": "qa",
            "fail": "fail",
        },
    )

    # Add edges from ACT nodes to REFLECT
    graph.add_conditional_edges(
        "load_cache",
        route_after_act,
        {"reflect": "reflect", "fail": "fail"},
    )

    graph.add_conditional_edges(
        "generate_lesson",
        route_after_act,
        {"reflect": "reflect", "fail": "fail"},
    )

    graph.add_conditional_edges(
        "qa",
        route_after_act,
        {"reflect": "reflect", "fail": "fail"},
    )

    # End edges
    graph.add_edge("reflect", END)
    graph.add_edge("fail", END)

    return graph.compile()


# Create singleton graph instance
_graph: CompiledStateGraph | None = None


def get_tutor_graph() -> CompiledStateGraph:
    """
    Get the singleton Tutor Agent graph.

    Returns:
        Compiled StateGraph.
    """
    global _graph
    if _graph is None:
        _graph = create_tutor_graph()
    return _graph
