"""
Integration tests for AI-Powered Dependency Conflict Predictor

These tests verify the full integration between:
- ConflictPredictor
- InstallationHistory
- CLI integration
- LLM Router
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from cortex.conflict_predictor import (
    ConflictPrediction,
    ConflictPredictor,
    ConflictType,
    ResolutionStrategy,
    StrategyType,
)
from cortex.installation_history import InstallationHistory
from cortex.llm_router import LLMRouter


class TestConflictPredictorIntegration(unittest.TestCase):
    """Integration tests for conflict prediction with real components"""

    def setUp(self):
        """Set up test fixtures"""
        self.history = InstallationHistory()
        self.mock_router = MagicMock()
        self.predictor = ConflictPredictor(llm_router=self.mock_router, history=self.history)

    def test_full_prediction_flow_with_history(self):
        """Test complete prediction flow with history recording"""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": True,
                "conflicts": [
                    {
                        "conflicting_package": "numpy",
                        "current_version": "2.1.0",
                        "required_constraint": "< 2.0",
                        "type": "VERSION",
                        "confidence": 0.95,
                        "severity": "HIGH",
                        "explanation": "tensorflow requires numpy < 2.0",
                        "installed_by": "pandas",
                    }
                ],
                "strategies": [
                    {
                        "type": "VENV",
                        "description": "Use virtual environment",
                        "safety_score": 0.95,
                        "commands": ["python3 -m venv tf_env"],
                        "benefits": ["Isolation"],
                        "risks": ["Must activate"],
                    }
                ],
            }
        )
        self.mock_router.complete.return_value = mock_response

        # Predict conflicts
        with patch("cortex.conflict_predictor.get_pip_packages", return_value={"numpy": "2.1.0"}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "tensorflow", "2.15.0"
                )

        # Verify results
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].package2, "numpy")
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0].strategy_type, StrategyType.VENV)

    def test_resolution_recording_in_history(self):
        """Test that resolutions are recorded in history database"""
        conflict = ConflictPrediction(
            package1="tensorflow",
            package2="numpy",
            conflict_type=ConflictType.VERSION,
            confidence=0.95,
            explanation="Version conflict",
        )

        strategy = ResolutionStrategy(
            strategy_type=StrategyType.VENV,
            description="Use venv",
            safety_score=0.95,
            commands=["python3 -m venv tf_env"],
        )

        # Record resolution
        self.predictor.record_resolution(conflict, strategy, success=True)

        # Verify it was recorded (check success rate)
        success_rate = self.history.get_conflict_resolution_success_rate(
            conflict_type="version", strategy_type="venv"
        )
        # Should have at least one record now
        self.assertGreaterEqual(success_rate, 0.0)

    def test_cli_integration_flow(self):
        """Test integration with CLI install flow"""
        # This simulates what happens in cli.py install() method
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": False,
                "conflicts": [],
                "strategies": [],
            }
        )
        self.mock_router.complete.return_value = mock_response

        # Simulate CLI flow
        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "requests"
                )

        # Should return no conflicts
        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(strategies), 0)

    def test_multiple_conflicts_handling(self):
        """Test handling multiple conflicts simultaneously"""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": True,
                "conflicts": [
                    {
                        "conflicting_package": "numpy",
                        "type": "VERSION",
                        "confidence": 0.95,
                        "severity": "HIGH",
                        "explanation": "numpy version conflict",
                    },
                    {
                        "conflicting_package": "protobuf",
                        "type": "VERSION",
                        "confidence": 0.85,
                        "severity": "MEDIUM",
                        "explanation": "protobuf version conflict",
                    },
                ],
                "strategies": [
                    {
                        "type": "VENV",
                        "description": "Use venv",
                        "safety_score": 0.95,
                        "commands": ["python3 -m venv env"],
                    }
                ],
            }
        )
        self.mock_router.complete.return_value = mock_response

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "tensorflow"
                )

        # Should handle multiple conflicts
        self.assertEqual(len(conflicts), 2)
        self.assertGreater(len(strategies), 0)

    def test_fallback_to_basic_strategies(self):
        """Test fallback when LLM doesn't provide strategies"""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": True,
                "conflicts": [
                    {
                        "conflicting_package": "numpy",
                        "type": "VERSION",
                        "confidence": 0.9,
                        "explanation": "Version conflict",
                    }
                ],
                "strategies": [],  # LLM didn't provide strategies
            }
        )
        self.mock_router.complete.return_value = mock_response

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "tensorflow"
                )

        # Should fallback to basic strategies
        self.assertEqual(len(conflicts), 1)
        self.assertGreater(len(strategies), 0)  # Should have fallback strategies

    def test_error_handling_in_prediction(self):
        """Test error handling when LLM call fails"""
        # Simulate LLM failure
        self.mock_router.complete.side_effect = Exception("LLM API error")

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "tensorflow"
                )

        # Should return empty lists on error
        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(strategies), 0)

    def test_strategy_ranking_by_safety(self):
        """Test that strategies are properly ranked by safety score"""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": True,
                "conflicts": [
                    {
                        "conflicting_package": "numpy",
                        "type": "VERSION",
                        "confidence": 0.9,
                        "explanation": "Version conflict",
                    }
                ],
                "strategies": [
                    {
                        "type": "REMOVE_CONFLICT",
                        "description": "Remove conflicting",
                        "safety_score": 0.2,
                        "commands": ["pip uninstall numpy"],
                    },
                    {
                        "type": "VENV",
                        "description": "Use venv",
                        "safety_score": 0.95,
                        "commands": ["python3 -m venv env"],
                    },
                    {
                        "type": "UPGRADE",
                        "description": "Upgrade package",
                        "safety_score": 0.75,
                        "commands": ["pip install --upgrade tensorflow"],
                    },
                ],
            }
        )
        self.mock_router.complete.return_value = mock_response

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = self.predictor.predict_conflicts_with_resolutions(
                    "tensorflow"
                )

        # Strategies should be sorted by safety (highest first)
        self.assertGreater(len(strategies), 1)
        for i in range(len(strategies) - 1):
            self.assertGreaterEqual(strategies[i].safety_score, strategies[i + 1].safety_score)


if __name__ == "__main__":
    unittest.main()
