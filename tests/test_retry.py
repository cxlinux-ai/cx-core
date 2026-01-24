import unittest
from unittest.mock import Mock, patch

from cortex.error_parser import ErrorCategory
from cortex.utils.retry import (
    DEFAULT_STRATEGIES,
    PERMANENT_ERRORS,
    RetryStrategy,
    SmartRetry,
    load_strategies_from_env,
)


class TestRetryStrategy(unittest.TestCase):
    """Tests for the RetryStrategy dataclass."""

    def test_strategy_creation(self) -> None:
        strategy = RetryStrategy(max_retries=5, backoff_factor=1.0, description="Test")
        self.assertEqual(strategy.max_retries, 5)
        self.assertEqual(strategy.backoff_factor, 1.0)
        self.assertEqual(strategy.description, "Test")


class TestDefaultStrategies(unittest.TestCase):
    """Tests for default strategy configurations."""

    def test_network_error_strategy(self) -> None:
        strategy = DEFAULT_STRATEGIES[ErrorCategory.NETWORK_ERROR]
        self.assertEqual(strategy.max_retries, 5)
        self.assertEqual(strategy.backoff_factor, 1.0)

    def test_lock_error_strategy(self) -> None:
        strategy = DEFAULT_STRATEGIES[ErrorCategory.LOCK_ERROR]
        self.assertEqual(strategy.max_retries, 3)
        self.assertEqual(strategy.backoff_factor, 5.0)

    def test_unknown_error_strategy(self) -> None:
        strategy = DEFAULT_STRATEGIES[ErrorCategory.UNKNOWN]
        self.assertEqual(strategy.max_retries, 2)
        self.assertEqual(strategy.backoff_factor, 2.0)

    def test_permanent_errors_not_in_strategies(self) -> None:
        for error in PERMANENT_ERRORS:
            self.assertNotIn(error, DEFAULT_STRATEGIES)


class TestLoadStrategiesFromEnv(unittest.TestCase):
    """Tests for environment variable configuration."""

    def test_default_strategies_when_no_env_vars(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            strategies = load_strategies_from_env()
            self.assertEqual(strategies[ErrorCategory.NETWORK_ERROR].max_retries, 5)

    def test_network_override_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"CORTEX_RETRY_NETWORK_MAX": "10", "CORTEX_RETRY_NETWORK_BACKOFF": "0.5"},
            clear=True,
        ):
            strategies = load_strategies_from_env()
            self.assertEqual(strategies[ErrorCategory.NETWORK_ERROR].max_retries, 10)
            self.assertEqual(strategies[ErrorCategory.NETWORK_ERROR].backoff_factor, 0.5)

    def test_lock_override_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"CORTEX_RETRY_LOCK_MAX": "6", "CORTEX_RETRY_LOCK_BACKOFF": "10.0"},
            clear=True,
        ):
            strategies = load_strategies_from_env()
            self.assertEqual(strategies[ErrorCategory.LOCK_ERROR].max_retries, 6)
            self.assertEqual(strategies[ErrorCategory.LOCK_ERROR].backoff_factor, 10.0)


class TestSmartRetry(unittest.TestCase):
    """Tests for SmartRetry class."""

    def setUp(self):
        # Use custom strategies with short backoff for fast tests
        self.fast_strategies = {
            ErrorCategory.NETWORK_ERROR: RetryStrategy(3, 0.01, "Test network"),
            ErrorCategory.LOCK_ERROR: RetryStrategy(2, 0.01, "Test lock"),
            ErrorCategory.UNKNOWN: RetryStrategy(2, 0.01, "Test unknown"),
        }
        self.retry = SmartRetry(strategies=self.fast_strategies)

    def test_success_first_try(self) -> None:
        mock_func = Mock()
        mock_result = Mock()
        mock_result.returncode = 0
        mock_func.return_value = mock_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, mock_result)
        self.assertEqual(mock_func.call_count, 1)

    @patch("cortex.utils.retry.time.sleep")
    def test_retry_on_network_error(self, mock_sleep) -> None:
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Connection timed out"

        success_result = Mock()
        success_result.returncode = 0

        mock_func.side_effect = [fail_result, fail_result, success_result]

        result = self.retry.run(mock_func)

        self.assertEqual(result, success_result)
        self.assertEqual(mock_func.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("cortex.utils.retry.time.sleep")
    def test_fail_fast_on_permission_denied(self, mock_sleep) -> None:
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Permission denied"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        self.assertEqual(mock_func.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("cortex.utils.retry.time.sleep")
    def test_fail_fast_on_disk_space(self, mock_sleep) -> None:
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "No space left on device"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        self.assertEqual(mock_func.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("cortex.utils.retry.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep) -> None:
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Connection timed out"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        # 1 initial + 3 retries for network error strategy
        self.assertEqual(mock_func.call_count, 4)
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("cortex.utils.retry.time.sleep")
    def test_different_strategy_for_lock_error(self, mock_sleep) -> None:
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Could not get lock /var/lib/apt/lists/lock"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        # Lock error strategy has max_retries=2, so 1 initial + 2 retries = 3
        self.assertEqual(mock_func.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("cortex.utils.retry.time.sleep")
    def test_callback_notification(self, mock_sleep) -> None:
        callback = Mock()
        retry = SmartRetry(strategies=self.fast_strategies, status_callback=callback)

        mock_func = Mock()
        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Connection timed out"

        mock_func.side_effect = [fail_result, Mock(returncode=0)]

        retry.run(mock_func)

        callback.assert_called_once()
        self.assertIn("NETWORK_ERROR", callback.call_args[0][0])
        self.assertIn("Retrying", callback.call_args[0][0])

    @patch("cortex.utils.retry.time.sleep")
    def test_exception_retry(self, mock_sleep) -> None:
        mock_func = Mock()
        mock_func.side_effect = [Exception("Network error"), Mock(returncode=0)]

        result = self.retry.run(mock_func)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(mock_func.call_count, 2)


if __name__ == "__main__":
    unittest.main()
