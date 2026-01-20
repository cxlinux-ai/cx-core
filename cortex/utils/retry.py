import logging
import time
from collections.abc import Callable
from typing import Any

from cortex.error_parser import ErrorCategory, ErrorParser

logger = logging.getLogger(__name__)


class SmartRetry:
    """
    Implements smart retry logic with exponential backoff.
    Uses ErrorParser to distinguish between transient and permanent errors.
    """

    def __init__(
        self,
        max_retries: int = 5,
        backoff_factor: float = 1.0,
        status_callback: Callable[[str], None] | None = None,
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
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

        while attempt <= self.max_retries:
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
                elif hasattr(result, "stdout") and result.stdout:
                    error_msg = result.stdout

                if not self._should_retry(error_msg):
                    return result

            except Exception as e:
                last_exception = e
                if not self._should_retry(str(e)):
                    raise e

            # If we are here, we need to retry (unless max retries reached)
            if attempt == self.max_retries:
                break

            attempt += 1
            sleep_time = self.backoff_factor * (2 ** (attempt - 1))

            msg = f"⚠️ Transient error detected. Retrying in {sleep_time}s... (Attempt {attempt}/{self.max_retries})"
            logger.warning(msg)
            if self.status_callback:
                self.status_callback(msg)

            time.sleep(sleep_time)

        if last_exception:
            raise last_exception
        return last_result

    def _should_retry(self, error_message: str) -> bool:
        """
        Determine if we should retry based on the error message.
        """
        if not error_message:
            # If no error message, assume it's a generic failure that might be transient
            return True

        analysis = self.error_parser.parse_error(error_message)
        category = analysis.primary_category

        # Retry on network errors, lock errors, or unknown errors (conservative)
        if category in [
            ErrorCategory.NETWORK_ERROR,
            ErrorCategory.LOCK_ERROR,
            ErrorCategory.UNKNOWN,
        ]:
            return True

        # Fail fast on permanent errors
        if category in [
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.PACKAGE_NOT_FOUND,
            ErrorCategory.CONFIGURATION_ERROR,
            ErrorCategory.DEPENDENCY_MISSING,
            ErrorCategory.CONFLICT,
        ]:
            return False

        # Default to retry for safety if not explicitly categorized as permanent
        return True
