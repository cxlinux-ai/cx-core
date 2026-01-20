import json
import unittest
from unittest.mock import MagicMock, patch

from cortex.hardware_detection import CPUInfo, MemoryInfo, StorageInfo, SystemInfo
from cortex.installation_history import InstallationRecord, InstallationStatus, InstallationType
from cortex.predictive_prevention import PredictiveErrorManager, RiskLevel


@patch("cortex.hardware_detection.HardwareDetector.detect")
@patch("cortex.installation_history.InstallationHistory.get_history")
@patch("cortex.llm_router.LLMRouter.complete")
class TestPredictiveErrorManager(unittest.TestCase):
    def setUp(self):
        # Use 'fake' provider by default to ensure no real network calls
        self.manager = PredictiveErrorManager(api_key="fake-key", provider="fake")

    def _get_mock_system(self, kernel="6.0.0", ram_mb=16384, disk_gb=50.0):
        """Helper to create a SystemInfo mock object."""
        return SystemInfo(
            kernel_version=kernel,
            memory=MemoryInfo(total_mb=ram_mb),
            storage=[StorageInfo(mount_point="/", available_gb=disk_gb, total_gb=100.0)],
        )

    def _setup_mocks(
        self, mock_llm, mock_history, mock_detect, system=None, history=None, llm_content=None
    ):
        """Setup common mocks with default or specified values."""
        mock_detect.return_value = system or self._get_mock_system()
        mock_history.return_value = history if history is not None else []

        if llm_content is None:
            llm_content = '{"risk_level": "none", "reasons": [], "recommendations": [], "predicted_errors": []}'

        mock_llm_response = MagicMock()
        mock_llm_response.content = llm_content
        mock_llm.return_value = mock_llm_response
        return mock_llm

    def test_analyze_installation_high_risk(self, mock_llm, mock_history, mock_detect):
        # Temporarily enable LLM for this test
        self.manager.provider = "ollama"

        # Setup mock system info
        # Note: disk_gb=5.0 so it's not CRITICAL from static check initially
        system = self._get_mock_system(kernel="4.15.0-generic", ram_mb=2048, disk_gb=5.0)
        llm_content = '{"risk_level": "high", "reasons": ["LLM Reason"], "recommendations": ["LLM Rec"], "predicted_errors": ["LLM Error"]}'
        self._setup_mocks(
            mock_llm, mock_history, mock_detect, system=system, llm_content=llm_content
        )

        prediction = self.manager.analyze_installation("cuda-12.0", ["sudo apt install cuda-12.0"])

        # Risk should be HIGH because LLM returned high and static check (kernel < 5.4) is HIGH
        self.assertEqual(prediction.risk_level, RiskLevel.HIGH)
        self.assertTrue(any("LLM Reason" in r for r in prediction.reasons))
        self.assertTrue(any("Kernel version" in r for r in prediction.reasons))

    def test_static_compatibility_check(self, mock_llm, mock_history, mock_detect):
        # Mock LLM to return neutral result so only static checks apply
        system = self._get_mock_system(disk_gb=0.5)
        self._setup_mocks(mock_llm, mock_history, mock_detect, system=system)

        prediction = self.manager.analyze_installation("nginx", ["sudo apt install nginx"])

        self.assertEqual(prediction.risk_level, RiskLevel.CRITICAL)
        self.assertTrue(any("disk space" in r.lower() for r in prediction.reasons))

    def test_cuda_newer_kernel_risk(self, mock_llm, mock_history, mock_detect):
        """Test the specific risk warning for CUDA on newer kernels."""
        system = self._get_mock_system(kernel="6.5.0", disk_gb=50.0)
        self._setup_mocks(mock_llm, mock_history, mock_detect, system=system)

        prediction = self.manager.analyze_installation("cuda-12-4", ["apt install cuda"])

        self.assertEqual(prediction.risk_level, RiskLevel.LOW)
        self.assertTrue(any("driver-kernel mismatch" in r.lower() for r in prediction.reasons))
        self.assertTrue(any("perfectly synchronized" in r.lower() for r in prediction.reasons))

    def test_history_pattern_failure(self, mock_llm, mock_history, mock_detect):
        # Setup history with failure
        match_record = InstallationRecord(
            id="1",
            timestamp="now",
            operation_type=InstallationType.INSTALL,
            packages=["docker.io"],
            status=InstallationStatus.FAILED,
            before_snapshot=[],
            after_snapshot=[],
            commands_executed=[],
            error_message="Connection timeout",
        )
        self._setup_mocks(mock_llm, mock_history, mock_detect, history=[match_record])

        prediction = self.manager.analyze_installation("docker", ["sudo apt install docker.io"])

        # RiskLevel.MEDIUM for historical failure
        self.assertEqual(prediction.risk_level, RiskLevel.MEDIUM)
        self.assertTrue(any("failed 1 times" in r for r in prediction.reasons))

    def test_llm_malformed_json_fallback(self, mock_llm, mock_history, mock_detect):
        # Enable LLM for this test
        self.manager.provider = "ollama"

        # Mock LLM with non-JSON content starting with "Risk:" to trigger fallback
        self._setup_mocks(
            mock_llm, mock_history, mock_detect, llm_content="Risk: Malformed text response"
        )

        prediction = self.manager.analyze_installation("nginx", ["apt install nginx"])
        self.assertTrue(any("LLM detected risks" in r for r in prediction.reasons))

    def test_critical_risk_finalization(self, mock_llm, mock_history, mock_detect):
        self._setup_mocks(mock_llm, mock_history, mock_detect)

        prediction = self.manager.analyze_installation("test", ["test"])
        # Finalization should escalate to CRITICAL based on keyword
        prediction.reasons.append("This is a CRITICAL deficiency")
        self.manager._finalize_risk_level(prediction)
        self.assertEqual(prediction.risk_level, RiskLevel.CRITICAL)


if __name__ == "__main__":
    unittest.main()
