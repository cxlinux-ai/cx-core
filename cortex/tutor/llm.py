"""
LLM functions for the Intelligent Tutor.

Uses cortex.llm_router for LLM calls.
"""

import json
import logging

from cortex.llm_router import LLMRouter, TaskType

# Suppress verbose logging from llm_router
logging.getLogger("cortex.llm_router").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    """Get or create the LLM router instance."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def _parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)


def generate_lesson(
    package_name: str,
    student_level: str = "beginner",
    learning_style: str = "reading",
    skip_areas: list[str] | None = None,
) -> dict:
    """Generate a lesson for a package."""
    router = get_router()

    system_prompt = """You are an expert technical educator.
Generate a comprehensive lesson about a software package.
Return valid JSON only, no markdown fences."""

    user_prompt = f"""Generate a lesson for: {package_name}

Student level: {student_level}
Learning style: {learning_style}
Skip topics: {', '.join(skip_areas or []) or 'none'}

Return JSON:
{{
    "summary": "1-2 sentence overview",
    "explanation": "What the package does and why it's useful",
    "use_cases": ["use case 1", "use case 2"],
    "best_practices": ["practice 1", "practice 2"],
    "code_examples": [
        {{"title": "Example", "code": "code here", "language": "bash", "description": "what it does"}}
    ],
    "tutorial_steps": [
        {{"step_number": 1, "title": "Step", "content": "instruction", "code": "optional"}}
    ],
    "installation_command": "apt install {package_name}",
    "related_packages": ["related1"]
}}"""

    try:
        response = router.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            task_type=TaskType.CODE_GENERATION,
            temperature=0.3,
            max_tokens=4096,
        )
        lesson = _parse_json_response(response.content)
        return {"success": True, "lesson": lesson, "cost_usd": response.cost_usd}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse lesson JSON: {e}")
        return {"success": False, "error": str(e), "lesson": None}
    except Exception as e:
        logger.error(f"Failed to generate lesson: {e}")
        return {"success": False, "error": str(e), "lesson": None}


def answer_question(
    package_name: str,
    question: str,
    context: str | None = None,
) -> dict:
    """Answer a question about a package."""
    router = get_router()

    system_prompt = """You are a helpful technical assistant.
Answer questions about software packages clearly and accurately.
Return valid JSON only, no markdown fences."""

    user_prompt = f"""Package: {package_name}
Question: {question}
{f'Context: {context}' if context else ''}

Return JSON:
{{
    "answer": "your detailed answer",
    "code_example": {{"code": "example if relevant", "language": "bash"}} or null,
    "related_topics": ["topic1", "topic2"],
    "confidence": 0.9
}}"""

    try:
        response = router.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            task_type=TaskType.USER_CHAT,
            temperature=0.5,
            max_tokens=2048,
        )
        answer = _parse_json_response(response.content)
        return {"success": True, "answer": answer, "cost_usd": response.cost_usd}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse answer JSON: {e}")
        return {"success": False, "error": str(e), "answer": None}
    except Exception as e:
        logger.error(f"Failed to answer question: {e}")
        return {"success": False, "error": str(e), "answer": None}
