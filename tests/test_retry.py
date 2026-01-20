import time
import unittest
from unittest.mock import Mock, patch

from cortex.error_parser import ErrorCategory
from cortex.utils.retry import SmartRetry


class TestSmartRetry(unittest.TestCase):
    def setUp(self):
        self.retry = SmartRetry(max_retries=3, backoff_factor=0.01)

    def test_success_first_try(self):
        mock_func = Mock()
        mock_result = Mock()
        mock_result.returncode = 0
        mock_func.return_value = mock_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, mock_result)
        self.assertEqual(mock_func.call_count, 1)

    @patch("time.sleep")
    def test_retry_on_transient_error(self, mock_sleep):
        mock_func = Mock()

        # Fail twice with network error, then succeed
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

    @patch("time.sleep")
    def test_fail_fast_on_permanent_error(self, mock_sleep):
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Permission denied"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        self.assertEqual(mock_func.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    def test_max_retries_exceeded(self, mock_sleep):
        mock_func = Mock()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Connection timed out"

        mock_func.return_value = fail_result

        result = self.retry.run(mock_func)

        self.assertEqual(result, fail_result)
        self.assertEqual(mock_func.call_count, 4)  # Initial + 3 retries
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("time.sleep")
    def test_exception_retry(self, mock_sleep):
        mock_func = Mock()
        mock_func.side_effect = [Exception("Network error"), Mock(returncode=0)]

        # We need to mock ErrorParser to classify "Network error" as transient if it's not standard
        # But SmartRetry defaults to retry on unknown errors, so generic Exception should trigger retry

        result = self.retry.run(mock_func)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(mock_func.call_count, 2)

    @patch("time.sleep")
    def test_callback_notification(self, mock_sleep):
        callback = Mock()
        retry = SmartRetry(max_retries=1, backoff_factor=0.01, status_callback=callback)

        mock_func = Mock()
        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stderr = "Connection timed out"

        mock_func.side_effect = [fail_result, Mock(returncode=0)]

        retry.run(mock_func)

        callback.assert_called_once()
        self.assertIn("Retrying", callback.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
