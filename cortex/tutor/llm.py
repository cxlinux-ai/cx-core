"""
LLM functions for the Intelligent Tutor.

Uses cortex.llm_router for LLM calls with layered prompt methodology.
"""

import logging
import re

from pydantic import BaseModel, ValidationError

from cortex.llm_router import LLMRouter, TaskType
from cortex.tutor.contracts import LessonResponse, QAResponse

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


def _extract_json_content(content: str) -> str:
    """Extract JSON content from LLM response, handling markdown fences."""
    content = content.strip()
    # Handle markdown code fences with any language specifier
    if content.startswith("```"):
        # Use regex to extract content between fences
        match = re.search(r"```(?:\w+)?\s*\n?(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
    return content


def _parse_structured_response(content: str, model: type[BaseModel]) -> BaseModel:
    """Parse LLM response into a Pydantic model for validation."""
    json_content = _extract_json_content(content)
    return model.model_validate_json(json_content)


# ==============================================================================
# Layered Prompts - Lesson Generator
# ==============================================================================

LESSON_SYSTEM_PROMPT = """## Layer 1: IDENTITY

You are a **Lesson Content Generator**, a specialized AI component for creating educational content about software packages and tools.

**You ARE:**
- A curriculum designer for technical education
- An expert at structuring learning materials
- A creator of practical examples and tutorials

**You are NOT:**
- A live documentation fetcher
- A package installer or executor
- A source of real-time package information

---

## Layer 2: ROLE & BOUNDARIES

### Your Role:
Generate structured lesson content including:
- Clear explanations of functionality
- Practical use cases
- Best practices
- Code examples
- Step-by-step tutorials

### Boundaries:
- Generate content based on well-known package knowledge
- Do not claim features you're uncertain about
- Focus on stable, documented functionality
- Keep examples safe and non-destructive

---

## Layer 3: ANTI-HALLUCINATION RULES

**CRITICAL - Adhere strictly:**

1. **NEVER invent command flags** - Only use flags you are certain exist
2. **NEVER fabricate URLs** - Suggest "official documentation" instead
3. **NEVER claim specific versions** - Use "recent versions" or "modern installations"
4. **Express uncertainty clearly** - Use confidence indicators
5. **Validate against common knowledge** - Only include widely-known information

---

## Layer 4: OUTPUT FORMAT

Return ONLY valid JSON (no markdown fences, no extra text):

{
  "summary": "1-2 sentence overview",
  "explanation": "Detailed explanation of what the package does and why it's useful",
  "use_cases": ["use case 1", "use case 2", "use case 3"],
  "best_practices": ["practice 1", "practice 2", "practice 3"],
  "code_examples": [
    {"title": "Example Title", "code": "actual code", "language": "bash", "description": "what it does"}
  ],
  "tutorial_steps": [
    {"step_number": 1, "title": "Step Title", "content": "instruction", "code": "optional code"}
  ],
  "installation_command": "apt install package-name",
  "related_packages": ["related1", "related2"],
  "confidence": 0.9
}

**Confidence Guidelines:**
- 0.9-1.0: Well-known, stable packages (docker, git, nginx)
- 0.7-0.9: Less common but documented packages
- 0.5-0.7: Uncertain or niche packages"""


def _build_lesson_user_prompt(
    package_name: str,
    student_level: str,
    learning_style: str,
    skip_areas: list[str] | None,
) -> str:
    """Build user prompt for lesson generation."""
    skip_text = ", ".join(skip_areas) if skip_areas else "none"

    return f"""## Layer 5: CONTEXT

Generate a comprehensive lesson for: **{package_name}**

**Student Profile:**
- Level: {student_level}
- Learning Style: {learning_style}
- Skip Topics: {skip_text}

---

## Layer 6: GENERATION GUIDELINES

1. **ANALYZE** the package category (system tool, library, service, etc.)
2. **STRUCTURE** content appropriate to student level:
   - Beginner: More explanation, simpler examples
   - Intermediate: Focus on practical usage
   - Advanced: Cover edge cases, performance tips
3. **ADAPT** to learning style:
   - Visual: Use clear structure and formatting
   - Reading: Provide detailed explanations
   - Hands-on: Emphasize code examples and tutorials
4. **VALIDATE** all code examples are safe and correct

Return ONLY the JSON object, no other text."""


def generate_lesson(
    package_name: str,
    student_level: str = "beginner",
    learning_style: str = "reading",
    skip_areas: list[str] | None = None,
) -> dict:
    """
    Generate a lesson for a package using layered prompt methodology.

    Args:
        package_name: Name of the package to teach.
        student_level: Student level (beginner, intermediate, advanced).
        learning_style: Learning style (visual, reading, hands-on).
        skip_areas: Topics to skip (already mastered).

    Returns:
        Dict with success status, lesson content, and cost.
    """
    router = get_router()

    user_prompt = _build_lesson_user_prompt(package_name, student_level, learning_style, skip_areas)

    try:
        response = router.complete(
            messages=[
                {"role": "system", "content": LESSON_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task_type=TaskType.CODE_GENERATION,
            temperature=0.3,
            max_tokens=4096,
        )
        lesson = _parse_structured_response(response.content, LessonResponse)
        return {"success": True, "lesson": lesson.model_dump(), "cost_usd": response.cost_usd}

    except ValidationError as e:
        logger.error("Failed to validate lesson response: %s", e)
        return {"success": False, "error": str(e), "lesson": None}
    except Exception as e:
        logger.error("Failed to generate lesson: %s", e)
        return {"success": False, "error": str(e), "lesson": None}


# ==============================================================================
# Layered Prompts - Q&A Handler
# ==============================================================================

QA_SYSTEM_PROMPT = """## Layer 1: IDENTITY

You are a **Q&A Handler**, a specialized AI component that answers user questions about software packages in an educational context.

**You ARE:**
- A patient teacher answering student questions
- An expert at clarifying technical concepts
- A guide who builds on existing knowledge

**You are NOT:**
- A search engine or documentation fetcher
- A system administrator
- A source of absolute truth

---

## Layer 2: ROLE & BOUNDARIES

### Your Role:
Answer questions by:
- Understanding the user's actual question
- Providing clear, accurate responses
- Including relevant examples when helpful
- Suggesting related topics for exploration

### Boundaries:
- Answer based on package knowledge
- Acknowledge uncertainty honestly
- Do not execute commands
- Stay focused on the learning context

---

## Layer 3: ANTI-HALLUCINATION RULES

**CRITICAL - Adhere strictly:**

1. **NEVER fabricate features** - Only describe functionality you're confident exists
2. **NEVER invent comparison data** - Don't make up benchmarks or statistics
3. **NEVER generate fake URLs** - Suggest searching for official docs
4. **Express confidence levels** - High/Medium/Low confidence
5. **Admit knowledge limits** - "I don't have specific information about..."

---

## Layer 4: OUTPUT FORMAT

Return ONLY valid JSON (no markdown fences, no extra text):

{
  "answer": "Clear, detailed answer to the question",
  "code_example": {"code": "example if relevant", "language": "bash"} or null,
  "related_topics": ["topic1", "topic2"],
  "confidence": 0.9
}

**Confidence Guidelines:**
- 0.9-1.0: Common knowledge, confident answer
- 0.7-0.9: Likely correct, recommend verification
- 0.5-0.7: Uncertain, suggest official documentation"""


def _build_qa_user_prompt(
    package_name: str,
    question: str,
    context: str | None,
) -> str:
    """Build user prompt for Q&A."""
    context_text = f"\n**Additional Context:** {context}" if context else ""

    return f"""## Layer 5: CONTEXT

**Package:** {package_name}
**Question:** {question}{context_text}

---

## Layer 6: ANSWER GUIDELINES

1. **PARSE** the question - What is being asked? (concept, usage, comparison, troubleshooting)
2. **FORMULATE** a direct, helpful answer
3. **INCLUDE** code example if it helps clarify
4. **VALIDATE** accuracy - Are you confident in this answer?
5. **SUGGEST** related topics for further learning

Return ONLY the JSON object, no other text."""


def answer_question(
    package_name: str,
    question: str,
    context: str | None = None,
) -> dict:
    """
    Answer a question about a package using layered prompt methodology.

    Args:
        package_name: Package context for the question.
        question: The user's question.
        context: Optional additional context.

    Returns:
        Dict with success status, answer content, and cost.
    """
    router = get_router()

    user_prompt = _build_qa_user_prompt(package_name, question, context)

    try:
        response = router.complete(
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task_type=TaskType.USER_CHAT,
            temperature=0.5,
            max_tokens=2048,
        )
        answer = _parse_structured_response(response.content, QAResponse)
        return {"success": True, "answer": answer.model_dump(), "cost_usd": response.cost_usd}

    except ValidationError as e:
        logger.error("Failed to validate answer response: %s", e)
        return {"success": False, "error": str(e), "answer": None}
    except Exception as e:
        logger.error("Failed to answer question: %s", e)
        return {"success": False, "error": str(e), "answer": None}
