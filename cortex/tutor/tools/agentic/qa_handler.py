"""
Q&A Handler Tool - Agentic tool for handling user questions.

This tool uses LLM (Claude via LangChain) to answer questions about packages.
"""

from pathlib import Path
from typing import Any

from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from cortex.tutor.config import get_config


class QAHandlerTool(BaseTool):
    """
    Agentic tool for handling Q&A using LLM.

    Answers user questions about packages in an educational context,
    building on their existing knowledge.

    Cost: ~$0.02 per question
    """

    name: str = "qa_handler"
    description: str = (
        "Answer user questions about a package. "
        "Use this for free-form Q&A outside the structured lesson flow. "
        "Provides contextual answers based on student profile."
    )

    llm: ChatAnthropic | None = Field(default=None, exclude=True)
    model_name: str = Field(default="claude-sonnet-4-20250514")

    # Constants for default values
    _NONE_SPECIFIED: str = "none specified"

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, model_name: str | None = None) -> None:
        """
        Initialize the Q&A handler tool.

        Args:
            model_name: LLM model to use.
        """
        super().__init__()
        config = get_config()
        self.model_name = model_name or config.model
        self.llm = ChatAnthropic(
            model=self.model_name,
            api_key=config.anthropic_api_key,
            temperature=0.1,  # Slight creativity for natural responses
            max_tokens=2048,
        )

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
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._get_system_prompt()),
                    ("human", self._get_qa_prompt()),
                ]
            )

            chain = prompt | self.llm | JsonOutputParser()

            result = chain.invoke(
                {
                    "package_name": package_name,
                    "question": question,
                    "learning_style": learning_style,
                    "mastered_concepts": ", ".join(mastered_concepts or []) or self._NONE_SPECIFIED,
                    "weak_concepts": ", ".join(weak_concepts or []) or self._NONE_SPECIFIED,
                    "lesson_context": lesson_context or "starting fresh",
                }
            )

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
        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._get_system_prompt()),
                    ("human", self._get_qa_prompt()),
                ]
            )

            chain = prompt | self.llm | JsonOutputParser()

            result = await chain.ainvoke(
                {
                    "package_name": package_name,
                    "question": question,
                    "learning_style": learning_style,
                    "mastered_concepts": ", ".join(mastered_concepts or []) or self._NONE_SPECIFIED,
                    "weak_concepts": ", ".join(weak_concepts or []) or self._NONE_SPECIFIED,
                    "lesson_context": lesson_context or "starting fresh",
                }
            )

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
        structured = {
            "package_name": package_name,
            "original_question": question,
            "question_understood": response.get("question_understood", question),
            "answer": response.get("answer", "I couldn't generate an answer."),
            "explanation": response.get("explanation"),
            "code_example": None,
            "related_topics": response.get("related_topics", [])[:5],
            "follow_up_suggestions": response.get("follow_up_suggestions", [])[:3],
            "confidence": min(max(response.get("confidence", 0.7), 0.0), 1.0),
            "verification_note": response.get("verification_note"),
        }

        # Structure code example if present
        code_ex = response.get("code_example")
        if isinstance(code_ex, dict) and code_ex.get("code"):
            structured["code_example"] = {
                "code": code_ex.get("code", ""),
                "language": code_ex.get("language", "bash"),
                "description": code_ex.get("description", ""),
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
        self.qa_tool = QAHandlerTool()

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
