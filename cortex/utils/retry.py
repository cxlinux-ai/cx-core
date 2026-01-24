import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cortex.error_parser import ErrorCategory, ErrorParser

logger = logging.getLogger(__name__)

# Default maximum number of retries for the global retry setting
DEFAULT_MAX_RETRIES = 5


@dataclass
class RetryStrategy:
    """Configuration for how to retry a specific error type."""

    max_retries: int
    backoff_factor: float
    description: str


# Default strategies for each retryable error category
DEFAULT_STRATEGIES: dict[ErrorCategory, RetryStrategy] = {
    ErrorCategory.NETWORK_ERROR: RetryStrategy(
        max_retries=DEFAULT_MAX_RETRIES,
        backoff_factor=1.0,
        description="Network issues - retry aggressively with short backoff",
    ),
    ErrorCategory.LOCK_ERROR: RetryStrategy(
        max_retries=3,
        backoff_factor=5.0,
        description="Lock contention - wait longer between retries",
    ),
    ErrorCategory.UNKNOWN: RetryStrategy(
        max_retries=2,
        backoff_factor=2.0,
        description="Unknown errors - conservative retry",
    ),
}

# Permanent error categories that should never be retried
PERMANENT_ERRORS: set[ErrorCategory] = {
    ErrorCategory.PERMISSION_DENIED,
    ErrorCategory.PACKAGE_NOT_FOUND,
    ErrorCategory.CONFIGURATION_ERROR,
    ErrorCategory.DEPENDENCY_MISSING,
    ErrorCategory.CONFLICT,
    ErrorCategory.DISK_SPACE,
}


def load_strategies_from_env() -> dict[ErrorCategory, RetryStrategy]:
    """
    Load retry strategies from environment variables, falling back to defaults.

    Environment variables:
        CORTEX_RETRY_NETWORK_MAX: Max retries for network errors (default: 5)
        CORTEX_RETRY_NETWORK_BACKOFF: Backoff factor for network errors (default: 1.0)
        CORTEX_RETRY_LOCK_MAX: Max retries for lock errors (default: 3)
        CORTEX_RETRY_LOCK_BACKOFF: Backoff factor for lock errors (default: 5.0)
        CORTEX_RETRY_UNKNOWN_MAX: Max retries for unknown errors (default: 2)
        CORTEX_RETRY_UNKNOWN_BACKOFF: Backoff factor for unknown errors (default: 2.0)
    """
    strategies = dict(DEFAULT_STRATEGIES)

    # Network error overrides
    if os.getenv("CORTEX_RETRY_NETWORK_MAX") or os.getenv("CORTEX_RETRY_NETWORK_BACKOFF"):
        strategies[ErrorCategory.NETWORK_ERROR] = RetryStrategy(
            max_retries=int(os.getenv("CORTEX_RETRY_NETWORK_MAX", "5")),
            backoff_factor=float(os.getenv("CORTEX_RETRY_NETWORK_BACKOFF", "1.0")),
            description="Network issues (user-configured)",
        )

    # Lock error overrides
    if os.getenv("CORTEX_RETRY_LOCK_MAX") or os.getenv("CORTEX_RETRY_LOCK_BACKOFF"):
        strategies[ErrorCategory.LOCK_ERROR] = RetryStrategy(
            max_retries=int(os.getenv("CORTEX_RETRY_LOCK_MAX", "3")),
            backoff_factor=float(os.getenv("CORTEX_RETRY_LOCK_BACKOFF", "5.0")),
            description="Lock contention (user-configured)",
        )

    # Unknown error overrides
    if os.getenv("CORTEX_RETRY_UNKNOWN_MAX") or os.getenv("CORTEX_RETRY_UNKNOWN_BACKOFF"):
        strategies[ErrorCategory.UNKNOWN] = RetryStrategy(
            max_retries=int(os.getenv("CORTEX_RETRY_UNKNOWN_MAX", "2")),
            backoff_factor=float(os.getenv("CORTEX_RETRY_UNKNOWN_BACKOFF", "2.0")),
            description="Unknown errors (user-configured)",
        )

    return strategies


class SmartRetry:
    """
    Implements smart retry logic with exponential backoff.
    Uses ErrorParser to distinguish between transient and permanent errors.
    Supports different retry strategies per error category.
    """

    def __init__(
        self,
        strategies: dict[ErrorCategory, RetryStrategy] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ):
        """
        Initialize SmartRetry with optional custom strategies.

        Args:
            strategies: Custom retry strategies per error category.
                        If None, loads from environment or uses defaults.
            status_callback: Optional callback for status messages.
        """
        self.strategies = strategies if strategies is not None else load_strategies_from_env()

        # Validate strategies
        for category, strategy in self.strategies.items():
            if strategy.max_retries < 0:
                raise ValueError(f"Strategy for {category.name}: max_retries must be non-negative")
            if strategy.backoff_factor <= 0:
                raise ValueError(f"Strategy for {category.name}: backoff_factor must be positive")

        self.status_callback = status_callback
        self.error_parser = ErrorParser()

    def run(self, func: Callable[[], Any]) -> Any:
        """
        Run a function with smart retry logic.

        Args:
            func: The function to execute. Expected to return a result object
                  that has `returncode`, `stdout`, and `stderr` attributes
                  (like subprocess.CompletedProcess), or raise an exception.

        Returns:
            The result of the function call.
        """
        attempt = 0
        last_exception = None
        last_result = None
        current_strategy: RetryStrategy | None = None

        while True:
            try:
                result = func()
                last_result = result

                # If result indicates success (returncode 0), return immediately
                if hasattr(result, "returncode") and result.returncode == 0:
                    return result

                # If result indicates failure, analyze it
                error_msg = ""
                if hasattr(result, "stderr") and result.stderr:
                    error_msg = result.stderr

                category = self._get_error_category(error_msg)
                current_strategy = self._get_strategy(category)

                if current_strategy is None:
                    # Permanent error - fail fast
                    return result

            except Exception as e:
                last_exception = e
                category = self._get_error_category(str(e))
                current_strategy = self._get_strategy(category)

                if current_strategy is None:
                    # Permanent error - fail fast
                    raise

            # Check if we've exhausted retries for this strategy
            if current_strategy is None or attempt >= current_strategy.max_retries:
                break

            attempt += 1
            sleep_time = current_strategy.backoff_factor * (2 ** (attempt - 1))

            category_name = category.name if category else "UNKNOWN"
            msg = (
                f"⚠️ {category_name} detected. "
                f"Retrying in {sleep_time}s... (Retry {attempt}/{current_strategy.max_retries})"
            )
            logger.warning(msg)
            if self.status_callback:
                self.status_callback(msg)

            time.sleep(sleep_time)

        if last_exception:
            raise last_exception
        return last_result

    def _get_error_category(self, error_message: str) -> ErrorCategory | None:
        """Classify the error message into a category."""
        if not error_message:
            logger.warning("Retry: Empty error message detected. Assuming UNKNOWN (transient).")
            return ErrorCategory.UNKNOWN

        analysis = self.error_parser.parse_error(error_message)

        # If the error is explicitly marked as not fixable, treat as permanent
        if not analysis.is_fixable:
            return None

        return analysis.primary_category

    def _get_strategy(self, category: ErrorCategory | None) -> RetryStrategy | None:
        """
        Get the retry strategy for a given error category.
        Returns None for permanent errors (should not retry).
        """
        if category is None:
            return None

        if category in PERMANENT_ERRORS:
            return None

        return self.strategies.get(category)
