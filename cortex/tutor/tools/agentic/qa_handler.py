"""
Q&A Handler Tool - Agentic tool for handling user questions.

This tool uses LLM (Claude via LangChain) to answer questions about packages.
"""

from typing import TYPE_CHECKING, Any

from langchain.tools import BaseTool
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from cortex.tutor.config import get_config
from cortex.tutor.tools.deterministic.validators import (
    validate_package_name,
    validate_question,
)

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic


class QAHandlerTool(BaseTool):
    """
    Agentic tool for handling Q&A using LLM.

    Answers user questions about packages in an educational context,
    building on their existing knowledge.

    Cost: ~£0.02 per question
    """

    name: str = "qa_handler"
    description: str = (
        "Answer user questions about a package. "
        "Use this for free-form Q&A outside the structured lesson flow. "
        "Provides contextual answers based on student profile."
    )

    llm: "ChatAnthropic | None" = Field(default=None, exclude=True)
    model_name: str = Field(default="claude-sonnet-4-20250514")

    # Constants for default values
    _NONE_SPECIFIED: str = "none specified"

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        """Post-init hook (Pydantic v2 pattern)."""
        config = get_config()
        if self.model_name == "claude-sonnet-4-20250514":
            self.model_name = config.model

    def _get_llm(self) -> "ChatAnthropic":
        """Lazily initialize and return the LLM."""
        if self.llm is None:
            from langchain_anthropic import ChatAnthropic

            config = get_config()
            self.llm = ChatAnthropic(
                model=self.model_name,
                api_key=config.anthropic_api_key,
                temperature=0.1,
                max_tokens=2048,
            )
        return self.llm

    def _validate_inputs(self, package_name: str, question: str) -> tuple[bool, str | None]:
        """Validate package name and question inputs."""
        is_valid, error = validate_package_name(package_name)
        if not is_valid:
            return False, f"Invalid package name: {error}"

        is_valid, error = validate_question(question)
        if not is_valid:
            return False, f"Invalid question: {error}"

        return True, None

    def _build_chain(self) -> Any:
        """Build the QA chain (shared by sync and async)."""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._get_system_prompt()),
                ("human", self._get_qa_prompt()),
            ]
        )
        return prompt | self._get_llm() | JsonOutputParser()

    def _build_invoke_params(
        self,
        package_name: str,
        question: str,
        learning_style: str,
        mastered_concepts: list[str] | None,
        weak_concepts: list[str] | None,
        lesson_context: str | None,
    ) -> dict[str, str]:
        """Build invocation parameters."""
        return {
            "package_name": package_name,
            "question": question,
            "learning_style": learning_style,
            "mastered_concepts": ", ".join(mastered_concepts or []) or self._NONE_SPECIFIED,
            "weak_concepts": ", ".join(weak_concepts or []) or self._NONE_SPECIFIED,
            "lesson_context": lesson_context or "starting fresh",
        }

    def _run(
        self,
        package_name: str,
        question: str,
        learning_style: str = "reading",
        mastered_concepts: list[str] | None = None,
        weak_concepts: list[str] | None = None,
        lesson_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Answer a user question about a package.

        Args:
            package_name: Current package context.
            question: The user's question.
            learning_style: User's learning preference.
            mastered_concepts: Concepts user has mastered.
            weak_concepts: Concepts user struggles with.
            lesson_context: What they've learned so far.

        Returns:
            Dict containing the answer and related info.
        """
        # Validate inputs
        is_valid, error = self._validate_inputs(package_name, question)
        if not is_valid:
            return {"success": False, "error": error, "answer": None}

        try:
            chain = self._build_chain()
            params = self._build_invoke_params(
                package_name,
                question,
                learning_style,
                mastered_concepts,
                weak_concepts,
                lesson_context,
            )

            result = chain.invoke(params)
            answer = self._structure_response(result, package_name, question)

            return {
                "success": True,
                "answer": answer,
                "cost_gbp": 0.02,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "answer": None,
            }

    async def _arun(
        self,
        package_name: str,
        question: str,
        learning_style: str = "reading",
        mastered_concepts: list[str] | None = None,
        weak_concepts: list[str] | None = None,
        lesson_context: str | None = None,
    ) -> dict[str, Any]:
        """Async version of Q&A handling."""
        # Validate inputs
        is_valid, error = self._validate_inputs(package_name, question)
        if not is_valid:
            return {"success": False, "error": error, "answer": None}

        try:
            chain = self._build_chain()
            params = self._build_invoke_params(
                package_name,
                question,
                learning_style,
                mastered_concepts,
                weak_concepts,
                lesson_context,
            )

            result = await chain.ainvoke(params)
            answer = self._structure_response(result, package_name, question)

            return {
                "success": True,
                "answer": answer,
                "cost_gbp": 0.02,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "answer": None,
            }

    def _get_system_prompt(self) -> str:
        """Get the system prompt for Q&A."""
        return """You are a patient, knowledgeable tutor answering questions about software packages.

CRITICAL RULES:
1. NEVER fabricate features - only describe functionality you're confident exists
2. NEVER invent comparison data or benchmarks
3. NEVER generate fake URLs
4. Express confidence levels: "I'm confident...", "I believe...", "You should verify..."
5. Admit knowledge limits honestly

Your answers should:
- Be clear and educational
- Build on the student's existing knowledge
- Avoid re-explaining concepts they've mastered
- Provide extra detail for their weak areas
- Match their preferred learning style"""

    def _get_qa_prompt(self) -> str:
        """Get the Q&A prompt template."""
        return """Package context: {package_name}
Question: {question}

Student Profile:
- Learning style: {learning_style}
- Already mastered: {mastered_concepts}
- Struggles with: {weak_concepts}
- Current lesson context: {lesson_context}

Answer the question considering their profile. Return JSON:
{{
    "question_understood": "Rephrased question for clarity",
    "answer": "Main answer to the question",
    "explanation": "Detailed explanation if needed",
    "code_example": {{
        "code": "relevant code if applicable",
        "language": "bash",
        "description": "what the code does"
    }},
    "related_topics": ["related topic 1", "related topic 2"],
    "follow_up_suggestions": [
        "Consider also learning about...",
        "A related concept is..."
    ],
    "confidence": 0.9,
    "verification_note": "Optional note if user should verify something"
}}

If you don't know the answer, be honest and suggest where they might find it.
If the question is unclear, ask for clarification in the answer field."""

    def _structure_response(
        self, response: dict[str, Any], package_name: str, question: str
    ) -> dict[str, Any]:
        """Structure and validate the LLM response."""
        # Ensure response is a dict
        if not isinstance(response, dict):
            response = {}

        # Safely extract and validate related_topics
        related_topics_raw = response.get("related_topics", [])
        if isinstance(related_topics_raw, list):
            related_topics = [str(t) for t in related_topics_raw][:5]
        else:
            related_topics = []

        # Safely extract and validate follow_up_suggestions
        follow_ups_raw = response.get("follow_up_suggestions", [])
        if isinstance(follow_ups_raw, list):
            follow_ups = [str(s) for s in follow_ups_raw][:3]
        else:
            follow_ups = []

        # Safely extract and validate confidence
        try:
            confidence = float(response.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = min(max(confidence, 0.0), 1.0)

        structured = {
            "package_name": package_name,
            "original_question": question,
            "question_understood": response.get("question_understood", question),
            "answer": response.get("answer", "I couldn't generate an answer."),
            "explanation": response.get("explanation"),
            "code_example": None,
            "related_topics": related_topics,
            "follow_up_suggestions": follow_ups,
            "confidence": confidence,
            "verification_note": response.get("verification_note"),
        }

        # Structure code example if present - with type validation
        code_ex = response.get("code_example")
        if isinstance(code_ex, dict) and code_ex.get("code"):
            structured["code_example"] = {
                "code": str(code_ex.get("code", "")),
                "language": str(code_ex.get("language", "bash")),
                "description": str(code_ex.get("description", "")),
            }
        elif isinstance(code_ex, str) and code_ex:
            # Handle case where code_example is just a string
            structured["code_example"] = {
                "code": code_ex,
                "language": "bash",
                "description": "",
            }

        return structured


def answer_question(
    package_name: str,
    question: str,
    learning_style: str = "reading",
) -> dict[str, Any]:
    """
    Convenience function to answer a question.

    Args:
        package_name: Package context.
        question: User's question.
        learning_style: Learning preference.

    Returns:
        Answer dictionary.
    """
    tool = QAHandlerTool()
    return tool._run(
        package_name=package_name,
        question=question,
        learning_style=learning_style,
    )


# Maximum conversation history entries to prevent unbounded growth
_MAX_HISTORY_SIZE = 50


class ConversationHandler:
    """
    Handles multi-turn Q&A conversations with context.

    Maintains conversation history for more contextual responses.
    """

    def __init__(self, package_name: str) -> None:
        """
        Initialize conversation handler.

        Args:
            package_name: Package being discussed.
        """
        self.package_name = package_name
        self.history: list[dict[str, str]] = []
        self.qa_tool: QAHandlerTool | None = None  # Lazy initialization

    def ask(
        self,
        question: str,
        learning_style: str = "reading",
        mastered_concepts: list[str] | None = None,
        weak_concepts: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Ask a question with conversation history.

        Args:
            question: The question to ask.
            learning_style: Learning preference.
            mastered_concepts: Mastered concepts.
            weak_concepts: Weak concepts.

        Returns:
            Answer with context.
        """
        # Lazy-init QA tool on first use
        if self.qa_tool is None:
            self.qa_tool = QAHandlerTool()

        # Build context from history
        context = self._build_context()

        # Get answer
        result = self.qa_tool._run(
            package_name=self.package_name,
            question=question,
            learning_style=learning_style,
            mastered_concepts=mastered_concepts,
            weak_concepts=weak_concepts,
            lesson_context=context,
        )

        # Update history
        if result.get("success"):
            self.history.append(
                {
                    "question": question,
                    "answer": result["answer"].get("answer", ""),
                }
            )
            # Bound history to prevent unbounded growth
            self.history = self.history[-_MAX_HISTORY_SIZE:]

        return result

    def _build_context(self) -> str:
        """Build context string from conversation history."""
        if not self.history:
            return "Starting fresh conversation"

        recent = self.history[-3:]  # Last 3 exchanges
        context_parts = []
        for h in recent:
            context_parts.append(f"Q: {h['question'][:100]}")
            context_parts.append(f"A: {h['answer'][:100]}")

        return "Recent discussion: " + " | ".join(context_parts)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history = []
