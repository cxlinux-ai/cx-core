"""
Lesson Generator Tool - Agentic tool for generating educational content.

This tool uses LLM (Claude via LangChain) to generate comprehensive lessons.
It is used when no cached lesson is available.
"""

from pathlib import Path
from typing import Any

from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from cortex.tutor.config import get_config


# Load prompt template
def _load_prompt_template() -> str:
    """Load the lesson generator prompt from file."""
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "tools" / "lesson_generator.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    # Fallback inline prompt
    return """You are a lesson content generator. Generate comprehensive educational content
    for the package: {package_name}

    Student level: {student_level}
    Learning style: {learning_style}
    Focus areas: {focus_areas}

    Return a JSON object with: summary, explanation, use_cases, best_practices,
    code_examples, tutorial_steps, installation_command, confidence."""


class LessonGeneratorTool(BaseTool):
    """
    Agentic tool for generating lesson content using LLM.

    This tool generates comprehensive lessons including:
    - Package explanations
    - Best practices
    - Code examples
    - Step-by-step tutorials

    Cost: ~$0.02 per generation
    """

    name: str = "lesson_generator"
    description: str = (
        "Generate comprehensive lesson content for a package using AI. "
        "Use this when no cached lesson exists. "
        "Returns structured lesson with explanations, examples, and tutorials."
    )

    llm: ChatAnthropic | None = Field(default=None, exclude=True)
    model_name: str | None = Field(default=None, description="Model name, defaults to config.model")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, model_name: str | None = None) -> None:
        """
        Initialize the lesson generator tool.

        Args:
            model_name: LLM model to use. Uses config default if not provided.
        """
        super().__init__()
        config = get_config()
        self.model_name = model_name or config.model
        self.llm = ChatAnthropic(
            model=self.model_name,
            api_key=config.anthropic_api_key,
            temperature=0,
            max_tokens=4096,
        )

    def _run(
        self,
        package_name: str,
        student_level: str = "beginner",
        learning_style: str = "reading",
        focus_areas: list[str] | None = None,
        skip_areas: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generate lesson content for a package.

        Args:
            package_name: Name of the package to generate lesson for.
            student_level: Student level (beginner, intermediate, advanced).
            learning_style: Learning style (visual, reading, hands-on).
            focus_areas: Specific topics to emphasize.
            skip_areas: Topics already mastered to skip.

        Returns:
            Dict containing generated lesson content.
        """
        try:
            # Build the prompt
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._get_system_prompt()),
                    ("human", self._get_generation_prompt()),
                ]
            )

            # Create the chain
            chain = prompt | self.llm | JsonOutputParser()

            # Generate lesson
            result = chain.invoke(
                {
                    "package_name": package_name,
                    "student_level": student_level,
                    "learning_style": learning_style,
                    "focus_areas": ", ".join(focus_areas or []) or "all topics",
                    "skip_areas": ", ".join(skip_areas or []) or "none",
                }
            )

            # Validate and structure the response
            lesson = self._structure_response(result, package_name)

            return {
                "success": True,
                "lesson": lesson,
                "cost_gbp": 0.02,  # Estimated cost
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "lesson": None,
            }

    async def _arun(
        self,
        package_name: str,
        student_level: str = "beginner",
        learning_style: str = "reading",
        focus_areas: list[str] | None = None,
        skip_areas: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async version of lesson generation."""
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._get_system_prompt()),
                    ("human", self._get_generation_prompt()),
                ]
            )

            chain = prompt | self.llm | JsonOutputParser()

            result = await chain.ainvoke(
                {
                    "package_name": package_name,
                    "student_level": student_level,
                    "learning_style": learning_style,
                    "focus_areas": ", ".join(focus_areas or []) or "all topics",
                    "skip_areas": ", ".join(skip_areas or []) or "none",
                }
            )

            lesson = self._structure_response(result, package_name)

            return {
                "success": True,
                "lesson": lesson,
                "cost_gbp": 0.02,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "lesson": None,
            }

    def _get_system_prompt(self) -> str:
        """Get the system prompt for lesson generation."""
        return """You are an expert educational content creator specializing in software packages and tools.
Your role is to create comprehensive, accurate, and engaging lessons.

CRITICAL RULES:
1. NEVER invent features that don't exist in the package
2. NEVER fabricate URLs - suggest "official documentation" instead
3. NEVER claim specific version features unless certain
4. Express confidence levels honestly
5. Focus on stable, well-documented functionality

Your lessons should be:
- Clear and accessible to the specified student level
- Practical with real-world examples
- Progressive in complexity
- Safe to follow (no destructive commands without warnings)"""

    def _get_generation_prompt(self) -> str:
        """Get the generation prompt template."""
        return """Generate a comprehensive lesson for: {package_name}

Student Level: {student_level}
Learning Style: {learning_style}
Focus Areas: {focus_areas}
Skip Areas: {skip_areas}

Return a JSON object with this exact structure:
{{
    "package_name": "{package_name}",
    "summary": "1-2 sentence overview",
    "explanation": "Detailed explanation of what the package does and why it's useful",
    "use_cases": ["use case 1", "use case 2", "use case 3", "use case 4"],
    "best_practices": ["practice 1", "practice 2", "practice 3", "practice 4", "practice 5"],
    "code_examples": [
        {{
            "title": "Example title",
            "code": "actual code",
            "language": "bash",
            "description": "what it does"
        }}
    ],
    "tutorial_steps": [
        {{
            "step_number": 1,
            "title": "Step title",
            "content": "Step instruction",
            "code": "optional code",
            "expected_output": "optional expected output"
        }}
    ],
    "installation_command": "apt install package or pip install package",
    "related_packages": ["related1", "related2"],
    "confidence": 0.9
}}

Ensure:
- Summary is concise (max 2 sentences)
- Explanation covers core functionality
- Use cases are practical and relatable
- Best practices are actionable
- Code examples are safe and correct
- Tutorial steps have logical progression
- Confidence reflects your actual certainty (0.5-1.0)"""

    def _structure_response(self, response: dict[str, Any], package_name: str) -> dict[str, Any]:
        """
        Structure and validate the LLM response.

        Args:
            response: Raw LLM response.
            package_name: Package name for validation.

        Returns:
            Structured lesson dictionary.
        """
        # Ensure required fields with defaults
        structured = {
            "package_name": response.get("package_name", package_name),
            "summary": response.get("summary", f"A lesson about {package_name}"),
            "explanation": response.get("explanation", ""),
            "use_cases": response.get("use_cases", [])[:5],
            "best_practices": response.get("best_practices", [])[:7],
            "code_examples": [],
            "tutorial_steps": [],
            "installation_command": response.get(
                "installation_command", f"apt install {package_name}"
            ),
            "related_packages": response.get("related_packages", [])[:5],
            "confidence": min(max(response.get("confidence", 0.8), 0.0), 1.0),
        }

        # Structure code examples
        for ex in response.get("code_examples", [])[:5]:
            if isinstance(ex, dict) and ex.get("code"):
                structured["code_examples"].append(
                    {
                        "title": ex.get("title", "Example"),
                        "code": ex.get("code", ""),
                        "language": ex.get("language", "bash"),
                        "description": ex.get("description", ""),
                    }
                )

        # Structure tutorial steps
        for i, step in enumerate(response.get("tutorial_steps", [])[:10], 1):
            if isinstance(step, dict):
                structured["tutorial_steps"].append(
                    {
                        "step_number": step.get("step_number", i),
                        "title": step.get("title", f"Step {i}"),
                        "content": step.get("content", ""),
                        "code": step.get("code"),
                        "expected_output": step.get("expected_output"),
                    }
                )

        return structured


def generate_lesson(
    package_name: str,
    student_level: str = "beginner",
    learning_style: str = "reading",
) -> dict[str, Any]:
    """
    Convenience function to generate a lesson.

    Args:
        package_name: Package to generate lesson for.
        student_level: Student level.
        learning_style: Preferred learning style.

    Returns:
        Generated lesson dictionary.
    """
    tool = LessonGeneratorTool()
    return tool._run(
        package_name=package_name,
        student_level=student_level,
        learning_style=learning_style,
    )
