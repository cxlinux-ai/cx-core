"""
Tests for validators module.

Tests input validation functions for security and format checking.
"""

import pytest

from cortex.tutor.tools.deterministic.validators import (
    MAX_INPUT_LENGTH,
    MAX_PACKAGE_NAME_LENGTH,
    ValidationResult,
    extract_package_name,
    get_validation_errors,
    sanitize_input,
    validate_all,
    validate_input,
    validate_learning_style,
    validate_package_name,
    validate_question,
    validate_score,
    validate_topic,
)


class TestValidatePackageName:
    """Tests for validate_package_name function."""

    def test_valid_package_names(self):
        """Test valid package names pass validation."""
        valid_names = [
            "docker",
            "git",
            "nginx",
            "python3",
            "node-js",
            "my_package",
            "package.name",
            "a",
            "a1",
        ]
        for name in valid_names:
            is_valid, error = validate_package_name(name)
            assert is_valid, f"Expected {name} to be valid, got error: {error}"
            assert error is None

    def test_empty_package_name(self):
        """Test empty package name fails."""
        is_valid, error = validate_package_name("")
        assert not is_valid
        assert "empty" in error.lower()

    def test_whitespace_only(self):
        """Test whitespace-only input fails."""
        is_valid, _ = validate_package_name("   ")
        assert not is_valid

    def test_too_long_package_name(self):
        """Test package name exceeding max length fails."""
        long_name = "a" * (MAX_PACKAGE_NAME_LENGTH + 1)
        is_valid, error = validate_package_name(long_name)
        assert not is_valid
        assert "too long" in error.lower()

    def test_blocked_patterns(self):
        """Test blocked patterns are rejected."""
        dangerous_inputs = [
            "rm -rf /",
            "curl foo | sh",
            "wget bar | sh",
            "dd if=/dev/zero",
        ]
        for inp in dangerous_inputs:
            is_valid, error = validate_package_name(inp)
            assert not is_valid, f"Expected {inp} to be blocked"
            assert "blocked pattern" in error.lower()

    def test_invalid_characters(self):
        """Test invalid characters fail."""
        invalid_names = [
            "-starts-with-dash",
            ".starts-with-dot",
            "has spaces",
            "has@symbol",
            "has#hash",
        ]
        for name in invalid_names:
            is_valid, _ = validate_package_name(name)
            assert not is_valid, f"Expected {name} to be invalid"


class TestValidateInput:
    """Tests for validate_input function."""

    def test_valid_input(self):
        """Test valid input passes."""
        is_valid, error = validate_input("What is Docker?")
        assert is_valid
        assert error is None

    def test_empty_input_not_allowed(self):
        """Test empty input fails by default."""
        is_valid, _ = validate_input("")
        assert not is_valid

    def test_empty_input_allowed(self):
        """Test empty input passes when allowed."""
        is_valid, _ = validate_input("", allow_empty=True)
        assert is_valid

    def test_max_length(self):
        """Test input exceeding max length fails."""
        long_input = "a" * (MAX_INPUT_LENGTH + 1)
        is_valid, error = validate_input(long_input)
        assert not is_valid
        assert "too long" in error.lower()

    def test_custom_max_length(self):
        """Test custom max length works."""
        is_valid, _ = validate_input("hello", max_length=3)
        assert not is_valid

    def test_blocked_patterns_in_input(self):
        """Test blocked patterns are caught."""
        is_valid, error = validate_input("Let's run rm -rf / to clean up")
        assert not is_valid
        assert "blocked pattern" in error.lower()


class TestValidateQuestion:
    """Tests for validate_question function."""

    def test_valid_question(self):
        """Test valid questions pass."""
        is_valid, _ = validate_question("What is the difference between Docker and VMs?")
        assert is_valid

    def test_empty_question(self):
        """Test empty question fails."""
        is_valid, _ = validate_question("")
        assert not is_valid


class TestValidateTopic:
    """Tests for validate_topic function."""

    def test_valid_topic(self):
        """Test valid topics pass."""
        valid_topics = [
            "basic concepts",
            "installation",
            "advanced usage",
            "best-practices",
        ]
        for topic in valid_topics:
            is_valid, _ = validate_topic(topic)
            assert is_valid, f"Expected {topic} to be valid"

    def test_empty_topic(self):
        """Test empty topic fails."""
        is_valid, _ = validate_topic("")
        assert not is_valid


class TestValidateScore:
    """Tests for validate_score function."""

    def test_valid_scores(self):
        """Test valid scores pass."""
        valid_scores = [0.0, 0.5, 1.0, 0.75]
        for score in valid_scores:
            is_valid, _ = validate_score(score)
            assert is_valid

    def test_out_of_range_scores(self):
        """Test out-of-range scores fail."""
        invalid_scores = [-0.1, 1.1, -1, 2]
        for score in invalid_scores:
            is_valid, _ = validate_score(score)
            assert not is_valid


class TestValidateLearningStyle:
    """Tests for validate_learning_style function."""

    def test_valid_styles(self):
        """Test valid learning styles pass."""
        valid_styles = ["visual", "reading", "hands-on"]
        for style in valid_styles:
            is_valid, _ = validate_learning_style(style)
            assert is_valid

    def test_invalid_style(self):
        """Test invalid styles fail."""
        is_valid, _ = validate_learning_style("invalid")
        assert not is_valid


class TestSanitizeInput:
    """Tests for sanitize_input function."""

    def test_strips_whitespace(self):
        """Test whitespace is stripped."""
        assert sanitize_input("  hello  ") == "hello"

    def test_removes_null_bytes(self):
        """Test null bytes are removed."""
        assert sanitize_input("hello\x00world") == "helloworld"

    def test_truncates_long_input(self):
        """Test long input is truncated."""
        long_input = "a" * 2000
        result = sanitize_input(long_input)
        assert len(result) == MAX_INPUT_LENGTH

    def test_handles_empty(self):
        """Test empty input returns empty string."""
        assert sanitize_input("") == ""
        assert sanitize_input(None) == ""


class TestExtractPackageName:
    """Tests for extract_package_name function."""

    def test_extract_from_phrases(self):
        """Test package extraction from various phrases."""
        test_cases = [
            ("Tell me about docker", "docker"),
            ("I want to learn git", "git"),
            ("teach me nginx", "nginx"),
            ("explain python", "python"),
            ("how to use curl", "curl"),
            ("what is redis", "redis"),
            ("docker", "docker"),
        ]
        for phrase, expected in test_cases:
            result = extract_package_name(phrase)
            assert result == expected, f"Expected {expected} from '{phrase}', got {result}"

    def test_returns_none_for_invalid(self):
        """Test None is returned for invalid inputs."""
        assert extract_package_name("") is None
        assert extract_package_name(None) is None


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_bool_conversion(self):
        """Test boolean conversion."""
        valid = ValidationResult(True)
        invalid = ValidationResult(False, ["error"])

        assert bool(valid) is True
        assert bool(invalid) is False

    def test_str_representation(self):
        """Test string representation."""
        valid = ValidationResult(True)
        invalid = ValidationResult(False, ["error1", "error2"])

        assert "passed" in str(valid).lower()
        assert "error1" in str(invalid)


class TestGetValidationErrors:
    """Tests for get_validation_errors function."""

    def test_no_errors_when_all_valid(self):
        """Test empty list when all inputs are valid."""
        errors = get_validation_errors(
            package_name="docker",
            topic="basics",
            question="What is it?",
            score=0.8,
        )
        assert errors == []

    def test_collects_all_errors(self):
        """Test all errors are collected."""
        errors = get_validation_errors(
            package_name="",
            topic="",
            score=1.5,
        )
        assert len(errors) == 3


class TestValidateAll:
    """Tests for validate_all function."""

    def test_valid_inputs(self):
        """Test valid inputs return success."""
        result = validate_all(package_name="docker", score=0.8)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_inputs(self):
        """Test invalid inputs return failure."""
        result = validate_all(package_name="", score=2.0)
        assert not result.is_valid
        assert len(result.errors) == 2
