"""
Examples Provider Tool - Agentic tool for generating code examples.

This tool uses LLM (Claude via LangChain) to generate contextual code examples.
"""

from typing import Any

from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from cortex.tutor.config import get_config


class ExamplesProviderTool(BaseTool):
    """
    Agentic tool for generating code examples using LLM.

    Generates contextual, educational code examples for specific
    package features and topics.

    Cost: ~$0.01 per generation
    """

    name: str = "examples_provider"
    description: str = (
        "Generate contextual code examples for a package topic. "
        "Use this when the user wants to see practical code demonstrations. "
        "Returns examples with progressive complexity."
    )

    llm: ChatAnthropic | None = Field(default=None, exclude=True)
    model_name: str | None = Field(default=None, description="Model name, defaults to config.model")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, model_name: str | None = None) -> None:
        """
        Initialize the examples provider tool.

        Args:
            model_name: LLM model to use.
        """
        super().__init__()
        config = get_config()
        self.model_name = model_name or config.model
        self.llm = ChatAnthropic(
            model=self.model_name,
            api_key=config.anthropic_api_key,
            temperature=0,
            max_tokens=2048,
        )

    def _run(
        self,
        package_name: str,
        topic: str,
        difficulty: str = "beginner",
        learning_style: str = "hands-on",
        existing_knowledge: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generate code examples for a package topic.

        Args:
            package_name: Name of the package.
            topic: Specific topic or feature to demonstrate.
            difficulty: Example difficulty level.
            learning_style: User's learning style.
            existing_knowledge: Concepts user already knows.

        Returns:
            Dict containing generated examples.
        """
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._get_system_prompt()),
                    ("human", self._get_generation_prompt()),
                ]
            )

            chain = prompt | self.llm | JsonOutputParser()

            result = chain.invoke(
                {
                    "package_name": package_name,
                    "topic": topic,
                    "difficulty": difficulty,
                    "learning_style": learning_style,
                    "existing_knowledge": ", ".join(existing_knowledge or []) or "basics",
                }
            )

            examples = self._structure_response(result, package_name, topic)

            return {
                "success": True,
                "examples": examples,
                "cost_gbp": 0.01,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "examples": None,
            }

    async def _arun(
        self,
        package_name: str,
        topic: str,
        difficulty: str = "beginner",
        learning_style: str = "hands-on",
        existing_knowledge: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async version of example generation."""
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
                    "topic": topic,
                    "difficulty": difficulty,
                    "learning_style": learning_style,
                    "existing_knowledge": ", ".join(existing_knowledge or []) or "basics",
                }
            )

            examples = self._structure_response(result, package_name, topic)

            return {
                "success": True,
                "examples": examples,
                "cost_gbp": 0.01,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "examples": None,
            }

    def _get_system_prompt(self) -> str:
        """Get the system prompt for example generation."""
        return """You are an expert code example generator for educational purposes.

CRITICAL RULES:
1. NEVER invent command flags that don't exist
2. NEVER generate fake output - use realistic but generic examples
3. NEVER include real credentials - use placeholders like 'your_api_key'
4. Flag potentially dangerous commands with warnings
5. Keep examples focused, practical, and safe to run

Your examples should:
- Progress from simple to complex
- Include clear explanations
- Be safe and non-destructive
- Match the specified difficulty level"""

    def _get_generation_prompt(self) -> str:
        """Get the generation prompt template."""
        return """Generate code examples for: {package_name}
Topic: {topic}
Difficulty: {difficulty}
Learning style: {learning_style}
User already knows: {existing_knowledge}

Return a JSON object with this structure:
{{
    "package_name": "{package_name}",
    "topic": "{topic}",
    "examples": [
        {{
            "title": "Example Title",
            "difficulty": "beginner",
            "code": "actual code here",
            "language": "bash",
            "description": "What this example demonstrates",
            "expected_output": "Sample output (optional)",
            "warnings": ["Any safety warnings"],
            "prerequisites": ["Required setup steps"]
        }}
    ],
    "tips": ["Additional usage tips"],
    "common_mistakes": ["Mistakes to avoid"],
    "confidence": 0.9
}}

Generate 2-4 examples with progressive complexity.
Ensure all examples are safe and educational."""

    def _structure_response(
        self, response: dict[str, Any], package_name: str, topic: str
    ) -> dict[str, Any]:
        """Structure and validate the LLM response."""
        structured = {
            "package_name": response.get("package_name", package_name),
            "topic": response.get("topic", topic),
            "examples": [],
            "tips": response.get("tips", [])[:5],
            "common_mistakes": response.get("common_mistakes", [])[:5],
            "confidence": min(max(response.get("confidence", 0.8), 0.0), 1.0),
        }

        for ex in response.get("examples", [])[:4]:
            if isinstance(ex, dict) and ex.get("code"):
                structured["examples"].append(
                    {
                        "title": ex.get("title", "Example"),
                        "difficulty": ex.get("difficulty", "beginner"),
                        "code": ex.get("code", ""),
                        "language": ex.get("language", "bash"),
                        "description": ex.get("description", ""),
                        "expected_output": ex.get("expected_output"),
                        "warnings": ex.get("warnings", []),
                        "prerequisites": ex.get("prerequisites", []),
                    }
                )

        return structured


def generate_examples(
    package_name: str,
    topic: str,
    difficulty: str = "beginner",
) -> dict[str, Any]:
    """
    Convenience function to generate code examples.

    Args:
        package_name: Package name.
        topic: Topic to demonstrate.
        difficulty: Example difficulty.

    Returns:
        Generated examples dictionary.
    """
    tool = ExamplesProviderTool()
    return tool._run(
        package_name=package_name,
        topic=topic,
        difficulty=difficulty,
    )
