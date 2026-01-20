import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from cortex.cli import CortexCLI
from cortex.predictive_prevention import RiskLevel


class CLITestBase(unittest.TestCase):
    """Base class for CLI tests to share common setup and mock helpers."""

    def setUp(self) -> None:
        self.cli = CortexCLI()
        # Use a temp dir for cache isolation
        self._temp_dir = tempfile.TemporaryDirectory()
        self._temp_home = Path(self._temp_dir.name)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _setup_predictive_mock(self, mock_predictive_class: Mock) -> Mock:
        """Helper to configure PredictiveErrorManager mock with default safe response."""
        mock_predictive = Mock()
        mock_prediction = Mock()
        mock_prediction.risk_level = RiskLevel.NONE
        mock_predictive.analyze_installation.return_value = mock_prediction
        mock_predictive_class.return_value = mock_predictive
        return mock_predictive

    def _setup_interpreter_mock(
        self, mock_interpreter_class: Mock, commands: list[str] | None = None
    ) -> Mock:
        """Helper to setup CommandInterpreter mock."""
        if commands is None:
            commands = ["apt update", "apt install docker"]
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = commands
        mock_interpreter_class.return_value = mock_interpreter
        return mock_interpreter

    def _setup_coordinator_mock(
        self, mock_coordinator_class: Mock, success: bool = True, error_message: str | None = None
    ) -> Mock:
        """Helper to setup InstallationCoordinator mock."""
        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = success
        mock_result.total_duration = 1.5
        mock_result.failed_step = 0
        mock_result.error_message = error_message
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator
        return mock_coordinator
