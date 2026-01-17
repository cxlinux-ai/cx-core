"""
Contracts - Pydantic data models for Intelligent Tutor.

Defines structured output schemas for lesson generation, progress tracking, and quizzes.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

# ==============================================================================
# Lesson Context Models
# ==============================================================================


class CodeExample(BaseModel):
    """A code example with description."""

    title: str = Field(..., description="Title of the code example")
    code: str = Field(..., description="The actual code snippet")
    language: str = Field(
        default="bash", description="Programming language for syntax highlighting"
    )
    description: str = Field(..., description="Explanation of what the code does")


class TutorialStep(BaseModel):
    """A step in a tutorial sequence."""

    step_number: int = Field(..., ge=1, description="Step number in sequence")
    title: str = Field(..., description="Brief title for this step")
    content: str = Field(..., description="Detailed instruction for this step")
    code: str | None = Field(default=None, description="Optional code for this step")
    expected_output: str | None = Field(
        default=None, description="Expected output if code is executed"
    )


class LessonContext(BaseModel):
    """
    Output contract for lesson generation.

    Contains all the content generated for a package lesson including
    explanations, best practices, code examples, and tutorials.
    """

    # Core content
    package_name: str = Field(..., description="Name of the package being taught")
    summary: str = Field(
        ...,
        description="Brief 1-2 sentence summary of what the package does",
        max_length=500,
    )
    explanation: str = Field(
        ...,
        description="Detailed explanation of the package functionality",
        max_length=5000,
    )
    use_cases: list[str] = Field(
        default_factory=list,
        description="Common use cases for this package",
        max_length=10,
    )
    best_practices: list[str] = Field(
        default_factory=list,
        description="Best practices when using this package",
        max_length=10,
    )
    code_examples: list[CodeExample] = Field(
        default_factory=list,
        description="Code examples demonstrating package usage",
        max_length=5,
    )
    tutorial_steps: list[TutorialStep] = Field(
        default_factory=list,
        description="Step-by-step tutorial for hands-on learning",
        max_length=10,
    )

    # Package metadata
    installation_command: str = Field(
        ..., description="Command to install the package (apt, pip, etc.)"
    )
    official_docs_url: str | None = Field(default=None, description="URL to official documentation")
    related_packages: list[str] = Field(
        default_factory=list,
        description="Related packages the user might want to learn",
        max_length=5,
    )

    # Metadata
    confidence: float = Field(
        ...,
        description="Confidence score (0-1) based on knowledge quality",
        ge=0.0,
        le=1.0,
    )
    cached: bool = Field(default=False, description="Whether result came from cache")
    cost_gbp: float = Field(default=0.0, description="Cost for LLM calls", ge=0.0)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of generation (UTC)",
    )

    def to_json(self) -> str:
        """Serialize to JSON for caching."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "LessonContext":
        """Deserialize from JSON cache."""
        return cls.model_validate_json(json_str)

    def get_total_steps(self) -> int:
        """Get total number of tutorial steps."""
        return len(self.tutorial_steps)

    def get_practice_count(self) -> int:
        """Get count of best practices."""
        return len(self.best_practices)

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display purposes."""
        return {
            "package": self.package_name,
            "summary": self.summary,
            "explanation": self.explanation,
            "use_cases": self.use_cases,
            "best_practices": self.best_practices,
            "examples_count": len(self.code_examples),
            "tutorial_steps_count": len(self.tutorial_steps),
            "installation": self.installation_command,
            "confidence": f"{self.confidence:.0%}",
        }


class LessonPlanOutput(BaseModel):
    """Output from the PLAN phase for lesson generation."""

    strategy: Literal["use_cache", "generate_full", "generate_quick"] = Field(
        ..., description="Strategy chosen for lesson generation"
    )
    cached_data: dict[str, Any] | None = Field(
        default=None, description="Cached lesson data if strategy is use_cache"
    )
    estimated_cost: float = Field(
        default=0.0, description="Estimated cost for this strategy", ge=0.0
    )
    reasoning: str = Field(..., description="Explanation for why this strategy was chosen")


class LessonReflectionOutput(BaseModel):
    """Output from the REFLECT phase for lesson validation."""

    confidence: float = Field(
        ...,
        description="Overall confidence in the lesson quality",
        ge=0.0,
        le=1.0,
    )
    quality_score: float = Field(
        ...,
        description="Quality score based on completeness and accuracy",
        ge=0.0,
        le=1.0,
    )
    insights: list[str] = Field(
        default_factory=list,
        description="Key insights about the generated lesson",
    )
    improvements: list[str] = Field(
        default_factory=list,
        description="Suggested improvements for future iterations",
    )
    validation_passed: bool = Field(
        ..., description="Whether the lesson passed all validation checks"
    )
    validation_errors: list[str] = Field(
        default_factory=list,
        description="List of validation errors if any",
    )


# ==============================================================================
# Progress Context Models
# ==============================================================================


class TopicProgress(BaseModel):
    """Progress for a single topic within a package."""

    topic: str = Field(..., description="Name of the topic")
    completed: bool = Field(default=False, description="Whether topic is completed")
    score: float = Field(default=0.0, description="Score achieved (0-1)", ge=0.0, le=1.0)
    time_spent_seconds: int = Field(default=0, description="Time spent on topic", ge=0)
    last_accessed: datetime | None = Field(default=None, description="Last access time")


class PackageProgress(BaseModel):
    """Progress for a complete package."""

    package_name: str = Field(..., description="Name of the package")
    topics: list[TopicProgress] = Field(default_factory=list, description="Progress per topic")
    started_at: datetime | None = Field(default=None, description="When learning started")
    last_session: datetime | None = Field(default=None, description="Last learning session")

    @computed_field
    @property
    def completion_percentage(self) -> float:
        """Calculate overall completion percentage."""
        if not self.topics:
            return 0.0
        completed = sum(1 for t in self.topics if t.completed)
        return (completed / len(self.topics)) * 100

    @computed_field
    @property
    def average_score(self) -> float:
        """Calculate average score across topics."""
        if not self.topics:
            return 0.0
        return sum(t.score for t in self.topics) / len(self.topics)

    @computed_field
    @property
    def total_time_seconds(self) -> int:
        """Calculate total time spent."""
        return sum(t.time_spent_seconds for t in self.topics)

    def get_next_topic(self) -> str | None:
        """Get the next uncompleted topic."""
        for topic in self.topics:
            if not topic.completed:
                return topic.topic
        return None

    def is_complete(self) -> bool:
        """Check if all topics are completed."""
        return all(t.completed for t in self.topics) if self.topics else False


class ProgressContext(BaseModel):
    """
    Output contract for progress tracking operations.

    Contains comprehensive learning progress data.
    """

    # Student info
    student_id: str = Field(default="default", description="Unique student identifier")
    learning_style: str = Field(
        default="reading",
        description="Preferred learning style: visual, reading, hands-on",
    )

    # Progress data
    packages: list[PackageProgress] = Field(
        default_factory=list, description="Progress for each package"
    )
    mastered_concepts: list[str] = Field(
        default_factory=list, description="Concepts the student has mastered"
    )
    weak_concepts: list[str] = Field(
        default_factory=list, description="Concepts the student struggles with"
    )

    # Statistics
    total_packages_started: int = Field(default=0, description="Number of packages started")
    total_packages_completed: int = Field(default=0, description="Number of packages completed")
    total_time_learning_seconds: int = Field(default=0, description="Total learning time", ge=0)
    streak_days: int = Field(default=0, description="Current learning streak", ge=0)

    # Metadata
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )

    def get_package_progress(self, package_name: str) -> PackageProgress | None:
        """Get progress for a specific package."""
        for pkg in self.packages:
            if pkg.package_name == package_name:
                return pkg
        return None

    def get_overall_completion(self) -> float:
        """Calculate overall completion percentage across all packages."""
        if not self.packages:
            return 0.0
        return sum(p.completion_percentage for p in self.packages) / len(self.packages)

    def get_recommendations(self) -> list[str]:
        """Get learning recommendations based on progress."""
        recommendations = []

        # Recommend reviewing weak concepts
        if self.weak_concepts:
            recommendations.append(f"Review these concepts: {', '.join(self.weak_concepts[:3])}")

        # Recommend continuing incomplete packages
        for pkg in self.packages:
            if not pkg.is_complete():
                next_topic = pkg.get_next_topic()
                if next_topic:
                    recommendations.append(f"Continue learning {pkg.package_name}: {next_topic}")
                    break

        return recommendations

    def to_summary_dict(self) -> dict[str, Any]:
        """Create a summary dictionary for display."""
        return {
            "packages_started": self.total_packages_started,
            "packages_completed": self.total_packages_completed,
            "overall_completion": f"{self.get_overall_completion():.1f}%",
            "total_time_hours": round(self.total_time_learning_seconds / 3600, 1),
            "streak_days": self.streak_days,
            "mastered_count": len(self.mastered_concepts),
            "weak_count": len(self.weak_concepts),
        }


class QuizContext(BaseModel):
    """Output contract for quiz/assessment results."""

    package_name: str = Field(..., description="Package the quiz is about")
    questions_total: int = Field(..., description="Total number of questions", ge=1)
    questions_correct: int = Field(..., description="Number of correct answers", ge=0)
    score_percentage: float = Field(..., description="Score as percentage", ge=0.0, le=100.0)
    passed: bool = Field(..., description="Whether the quiz was passed (>=70%)")
    feedback: str = Field(..., description="Feedback on quiz performance")
    weak_areas: list[str] = Field(default_factory=list, description="Areas that need improvement")
    strong_areas: list[str] = Field(default_factory=list, description="Areas of strength")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quiz completion time",
    )

    @classmethod
    def from_results(
        cls,
        package_name: str,
        correct: int,
        total: int,
        feedback: str = "",
    ) -> "QuizContext":
        """Create QuizContext from raw results."""
        if total < 1:
            raise ValueError("total must be at least 1")
        if correct < 0:
            raise ValueError("correct must be non-negative")
        if correct > total:
            raise ValueError("correct cannot exceed total")
        score = (correct / total) * 100
        return cls(
            package_name=package_name,
            questions_total=total,
            questions_correct=correct,
            score_percentage=score,
            passed=score >= 70,
            feedback=feedback or f"You scored {score:.0f}%",
        )


# ==============================================================================
# LLM Response Models (for structured output parsing)
# ==============================================================================


class LessonResponse(BaseModel):
    """Raw LLM response for lesson generation."""

    summary: str = Field(..., description="1-2 sentence overview")
    explanation: str = Field(..., description="Detailed explanation")
    use_cases: list[str] = Field(default_factory=list, description="Use cases")
    best_practices: list[str] = Field(default_factory=list, description="Best practices")
    code_examples: list[CodeExample] = Field(default_factory=list, description="Code examples")
    tutorial_steps: list[TutorialStep] = Field(default_factory=list, description="Tutorial steps")
    installation_command: str = Field(..., description="Installation command")
    related_packages: list[str] = Field(default_factory=list, description="Related packages")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")


class QACodeExample(BaseModel):
    """Code example in Q&A response."""

    code: str = Field(..., description="The code snippet")
    language: str = Field(default="bash", description="Programming language")


class QAResponse(BaseModel):
    """Raw LLM response for Q&A."""

    answer: str = Field(..., description="The answer to the question")
    code_example: QACodeExample | None = Field(default=None, description="Optional code example")
    related_topics: list[str] = Field(default_factory=list, description="Related topics")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
