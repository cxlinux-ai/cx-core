"""
Tutor Agent - Main orchestrator for interactive tutoring.

Simplified implementation using cortex.llm_router directly.
"""

from typing import Any

from cortex.tutor.branding import console, tutor_print
from cortex.tutor.config import DEFAULT_TUTOR_TOPICS
from cortex.tutor.llm import answer_question, generate_lesson
from cortex.tutor.tools.deterministic.lesson_loader import LessonLoaderTool
from cortex.tutor.tools.deterministic.progress_tracker import ProgressTrackerTool
from cortex.tutor.tools.deterministic.validators import (
    validate_package_name,
    validate_question,
)


class TutorAgent:
    """
    Main Tutor Agent for interactive package education.

    Example:
        >>> agent = TutorAgent()
        >>> result = agent.teach("docker")
        >>> print(result.get("summary"))
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize the Tutor Agent."""
        self.verbose = verbose
        self.progress_tool = ProgressTrackerTool()
        self.loader = LessonLoaderTool()

    def teach(
        self,
        package_name: str,
        force_fresh: bool = False,
    ) -> dict[str, Any]:
        """
        Start a tutoring session for a package.

        Args:
            package_name: Name of the package to teach.
            force_fresh: Skip cache and generate fresh content.

        Returns:
            Dict containing lesson content and metadata.
        """
        is_valid, error = validate_package_name(package_name)
        if not is_valid:
            raise ValueError(f"Invalid package name: {error}")

        if self.verbose:
            tutor_print(f"Starting lesson for {package_name}...", "tutor")

        # Check cache first (free)
        if not force_fresh:
            cache_result = self.loader._run(package_name)
            if cache_result.get("cache_hit"):
                if self.verbose:
                    tutor_print("Using cached lesson", "info")
                return {
                    "type": "lesson",
                    "content": cache_result["lesson"],
                    "source": "cache",
                    "cache_hit": True,
                    "cost_usd": 0.0,
                    "validation_passed": True,
                }

        # Get student profile for personalization
        profile = self._get_profile()

        # Generate new lesson
        if self.verbose:
            tutor_print("Generating lesson...", "info")

        result = generate_lesson(
            package_name=package_name,
            student_level=profile.get("student_level", "beginner"),
            learning_style=profile.get("learning_style", "reading"),
            skip_areas=profile.get("mastered_concepts", []),
        )

        if not result.get("success"):
            return {
                "type": "error",
                "content": None,
                "source": "failed",
                "validation_passed": False,
                "validation_errors": [result.get("error", "Unknown error")],
            }

        # Cache the lesson
        lesson = result["lesson"]
        self.loader.cache_lesson(package_name, lesson)

        # Update progress
        self.progress_tool._run(
            "update_progress",
            package_name=package_name,
            topic="overview",
        )

        return {
            "type": "lesson",
            "content": lesson,
            "source": "generated",
            "cache_hit": False,
            "cost_usd": result.get("cost_usd", 0.0),
            "validation_passed": True,
        }

    def ask(
        self,
        package_name: str,
        question: str,
    ) -> dict[str, Any]:
        """
        Ask a question about a package.

        Args:
            package_name: Package context for the question.
            question: The question to ask.

        Returns:
            Dict containing the answer and related info.
        """
        is_valid, error = validate_package_name(package_name)
        if not is_valid:
            raise ValueError(f"Invalid package name: {error}")

        is_valid, error = validate_question(question)
        if not is_valid:
            raise ValueError(f"Invalid question: {error}")

        if self.verbose:
            tutor_print(f"Answering question about {package_name}...", "tutor")

        result = answer_question(package_name=package_name, question=question)

        if not result.get("success"):
            return {
                "type": "error",
                "content": None,
                "validation_passed": False,
                "validation_errors": [result.get("error", "Unknown error")],
            }

        return {
            "type": "qa",
            "content": result["answer"],
            "source": "generated",
            "cost_usd": result.get("cost_usd", 0.0),
            "validation_passed": True,
        }

    def _get_profile(self) -> dict:
        """Get student profile from progress tracker."""
        result = self.progress_tool._run("get_profile")
        return result.get("profile", {}) if result.get("success") else {}

    def get_progress(self, package_name: str | None = None) -> dict[str, Any]:
        """Get learning progress."""
        if package_name:
            return self.progress_tool._run("get_stats", package_name=package_name)
        return self.progress_tool._run("get_all_progress")

    def get_profile(self) -> dict[str, Any]:
        """Get student profile."""
        return self.progress_tool._run("get_profile")

    def update_learning_style(self, style: str) -> bool:
        """Update preferred learning style."""
        valid_styles = {"visual", "reading", "hands-on"}
        if style not in valid_styles:
            return False
        result = self.progress_tool._run("update_profile", learning_style=style)
        return result.get("success", False)

    def mark_completed(self, package_name: str, topic: str, score: float = 1.0) -> bool:
        """Mark a topic as completed."""
        if not 0.0 <= score <= 1.0:
            return False
        result = self.progress_tool._run(
            "mark_completed",
            package_name=package_name,
            topic=topic,
            score=score,
        )
        return result.get("success", False)

    def reset_progress(self, package_name: str | None = None) -> int:
        """Reset learning progress."""
        result = self.progress_tool._run("reset", package_name=package_name)
        return result.get("count", 0) if result.get("success") else 0

    def get_packages_studied(self) -> list[str]:
        """Get list of packages that have been studied."""
        result = self.progress_tool._run("get_packages")
        return result.get("packages", []) if result.get("success") else []


class InteractiveTutor:
    """Interactive tutoring session manager."""

    def __init__(self, package_name: str, force_fresh: bool = False) -> None:
        """Initialize interactive tutor for a package."""
        self.package_name = package_name
        self.force_fresh = force_fresh
        self.agent = TutorAgent(verbose=False)
        self.lesson: dict[str, Any] | None = None

    def start(self) -> None:
        """Start the interactive tutoring session."""
        from cortex.tutor.branding import (
            get_user_input,
            print_best_practice,
            print_code_example,
            print_lesson_header,
            print_markdown,
            print_menu,
            print_progress_summary,
            print_tutorial_step,
        )

        tutor_print(f"Loading lesson for {self.package_name}...", "tutor")
        result = self.agent.teach(self.package_name, force_fresh=self.force_fresh)

        if not result.get("validation_passed"):
            tutor_print("Failed to load lesson. Please try again.", "error")
            return

        self.lesson = result.get("content", {})
        print_lesson_header(self.package_name)
        console.print(f"\n{self.lesson.get('summary', '')}\n")

        while True:
            print_menu(
                [
                    "Learn basic concepts",
                    "See code examples",
                    "Follow tutorial",
                    "View best practices",
                    "Ask a question",
                    "Check progress",
                    "Exit",
                ]
            )

            choice = get_user_input("Select option")
            if not choice:
                continue

            try:
                option = int(choice)
            except ValueError:
                tutor_print("Please enter a number", "warning")
                continue

            if option == 1:
                self._show_concepts()
            elif option == 2:
                self._show_examples()
            elif option == 3:
                self._run_tutorial()
            elif option == 4:
                self._show_best_practices()
            elif option == 5:
                self._ask_question()
            elif option == 6:
                self._show_progress()
            elif option == 7:
                tutor_print("Thanks for learning! Goodbye.", "success")
                break
            else:
                tutor_print("Invalid option", "warning")

    def _show_concepts(self) -> None:
        """Show basic concepts."""
        from cortex.tutor.branding import print_markdown

        if self.lesson:
            explanation = self.lesson.get("explanation", "No explanation available.")
            print_markdown(f"## Concepts\n\n{explanation}")
            self.agent.mark_completed(self.package_name, "concepts", 0.5)

    def _show_examples(self) -> None:
        """Show code examples."""
        from cortex.tutor.branding import print_code_example

        if not self.lesson:
            return

        examples = self.lesson.get("code_examples", [])
        if not examples:
            tutor_print("No examples available", "info")
            return

        for ex in examples:
            print_code_example(
                ex.get("code", ""),
                ex.get("language", "bash"),
                ex.get("title", "Example"),
            )
            console.print(f"[dim]{ex.get('description', '')}[/dim]\n")

        self.agent.mark_completed(self.package_name, "examples", 0.7)

    def _run_tutorial(self) -> None:
        """Run step-by-step tutorial."""
        from cortex.tutor.branding import get_user_input, print_tutorial_step

        if not self.lesson:
            return

        steps = self.lesson.get("tutorial_steps", [])
        if not steps:
            tutor_print("No tutorial available", "info")
            return

        for step in steps:
            print_tutorial_step(
                step.get("content", ""),
                step.get("step_number", 1),
                len(steps),
            )

            if step.get("code"):
                console.print(f"\n[cyan]Code:[/cyan] {step['code']}")

            response = get_user_input("Press Enter to continue (or 'q' to quit)")
            if response.lower() == "q":
                break

        self.agent.mark_completed(self.package_name, "tutorial", 0.9)

    def _show_best_practices(self) -> None:
        """Show best practices."""
        from cortex.tutor.branding import print_best_practice

        if not self.lesson:
            return

        practices = self.lesson.get("best_practices", [])
        if not practices:
            tutor_print("No best practices available", "info")
            return

        console.print("\n[bold]Best Practices[/bold]")
        for i, practice in enumerate(practices, 1):
            print_best_practice(practice, i)

        self.agent.mark_completed(self.package_name, "best_practices", 0.6)

    def _ask_question(self) -> None:
        """Handle Q&A."""
        from cortex.tutor.branding import get_user_input, print_markdown

        question = get_user_input("Your question")
        if not question:
            return

        tutor_print("Thinking...", "info")
        try:
            result = self.agent.ask(self.package_name, question)
        except ValueError as e:
            tutor_print(f"Invalid question: {e}", "error")
            return

        if result.get("validation_passed"):
            content = result.get("content", {})
            answer = content.get("answer", "I couldn't find an answer.")
            print_markdown(f"\n**Answer:** {answer}")

            if content.get("code_example"):
                from cortex.tutor.branding import print_code_example

                ex = content["code_example"]
                print_code_example(ex.get("code", ""), ex.get("language", "bash"))
        else:
            tutor_print("Sorry, I couldn't answer that question.", "error")

    def _show_progress(self) -> None:
        """Show learning progress."""
        from cortex.tutor.branding import print_progress_summary

        result = self.agent.get_progress(self.package_name)
        if result.get("success"):
            stats = result.get("stats", {})
            print_progress_summary(
                stats.get("completed", 0),
                stats.get("total", 0) or DEFAULT_TUTOR_TOPICS,
                self.package_name,
            )
        else:
            tutor_print("Could not load progress", "warning")
