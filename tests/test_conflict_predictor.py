"""
Unit tests for AI-Powered Dependency Conflict Predictor

Tests cover:
- Data classes (ConflictPrediction, ResolutionStrategy)
- LLM response parsing
- JSON extraction utilities
- Display formatting
- Basic strategy generation
- Security validations
"""

import json
import unittest
from unittest.mock import MagicMock, Mock, patch

from cortex.conflict_predictor import (
    ConflictPrediction,
    ConflictPredictor,
    ConflictType,
    ResolutionStrategy,
    StrategyType,
    escape_command_arg,
    extract_json_from_response,
    format_conflict_summary,
    get_pip_packages,
    validate_version_constraint,
)


class TestConflictPrediction(unittest.TestCase):
    """Test ConflictPrediction data class"""

    def test_conflict_prediction_creation(self):
        """Test creating a conflict prediction"""
        conflict = ConflictPrediction(
            package1="tensorflow",
            package2="numpy",
            conflict_type=ConflictType.VERSION,
            confidence=0.95,
            explanation="Version mismatch",
            severity="HIGH",
        )

        self.assertEqual(conflict.package1, "tensorflow")
        self.assertEqual(conflict.package2, "numpy")
        self.assertEqual(conflict.confidence, 0.95)
        self.assertEqual(conflict.severity, "HIGH")

    def test_conflict_to_dict(self):
        """Test converting conflict to dictionary"""
        conflict = ConflictPrediction(
            package1="mysql-server",
            package2="mariadb-server",
            conflict_type=ConflictType.MUTUAL_EXCLUSION,
            confidence=1.0,
            explanation="Cannot coexist",
        )

        conflict_dict = conflict.to_dict()
        self.assertEqual(conflict_dict["package1"], "mysql-server")
        self.assertEqual(conflict_dict["conflict_type"], "mutual_exclusion")

    def test_conflict_with_extended_fields(self):
        """Test conflict with installed_by and version fields"""
        conflict = ConflictPrediction(
            package1="tensorflow",
            package2="numpy",
            conflict_type=ConflictType.VERSION,
            confidence=0.95,
            explanation="Version mismatch",
            installed_by="pandas",
            current_version="2.1.0",
            required_constraint="< 2.0",
        )

        self.assertEqual(conflict.installed_by, "pandas")
        self.assertEqual(conflict.current_version, "2.1.0")
        self.assertEqual(conflict.required_constraint, "< 2.0")


class TestResolutionStrategy(unittest.TestCase):
    """Test ResolutionStrategy data class"""

    def test_resolution_strategy_creation(self):
        """Test creating a resolution strategy"""
        strategy = ResolutionStrategy(
            strategy_type=StrategyType.UPGRADE,
            description="Upgrade to version 2.16",
            safety_score=0.85,
            commands=["pip install tensorflow==2.16"],
            risks=["May break compatibility"],
            estimated_time_minutes=3.0,
        )

        self.assertEqual(strategy.strategy_type, StrategyType.UPGRADE)
        self.assertEqual(strategy.safety_score, 0.85)
        self.assertEqual(len(strategy.commands), 1)

    def test_strategy_to_dict(self):
        """Test converting strategy to dictionary"""
        strategy = ResolutionStrategy(
            strategy_type=StrategyType.VENV,
            description="Use virtual environment",
            safety_score=0.95,
            commands=["python3 -m venv myenv"],
        )

        strategy_dict = strategy.to_dict()
        self.assertEqual(strategy_dict["strategy_type"], "venv")
        self.assertEqual(strategy_dict["safety_score"], 0.95)


class TestConflictPredictor(unittest.TestCase):
    """Test ConflictPredictor class"""

    def setUp(self):
        """Set up test fixtures"""
        self.predictor = ConflictPredictor()

    def test_predictor_initialization(self):
        """Test predictor initializes correctly"""
        self.assertIsNone(self.predictor.llm_router)
        self.assertIsNotNone(self.predictor.history)

    def test_predictor_with_llm_router(self):
        """Test predictor with LLM router"""
        mock_router = MagicMock()
        predictor = ConflictPredictor(llm_router=mock_router)
        self.assertEqual(predictor.llm_router, mock_router)

    def test_predict_conflicts_no_llm(self):
        """Test prediction returns empty when no LLM router"""
        conflicts = self.predictor.predict_conflicts("tensorflow")
        self.assertEqual(conflicts, [])

    def test_predict_conflicts_with_resolutions_no_llm(self):
        """Test combined prediction returns empty when no LLM router"""
        conflicts, strategies = self.predictor.predict_conflicts_with_resolutions("tensorflow")
        self.assertEqual(conflicts, [])
        self.assertEqual(strategies, [])


class TestLLMResponseParsing(unittest.TestCase):
    """Test LLM response parsing"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_router = MagicMock()
        self.predictor = ConflictPredictor(llm_router=self.mock_router)

    def test_parse_combined_response_with_conflicts(self):
        """Test parsing LLM response with conflicts"""
        response = json.dumps(
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
                    }
                ],
                "strategies": [
                    {
                        "type": "VENV",
                        "description": "Use virtual environment",
                        "safety_score": 0.95,
                        "commands": ["python3 -m venv myenv"],
                        "benefits": ["Isolation"],
                        "risks": ["Must activate"],
                    }
                ],
            }
        )

        conflicts, strategies = self.predictor._parse_combined_response(response, "tensorflow")

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].package2, "numpy")
        self.assertEqual(conflicts[0].confidence, 0.95)
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0].strategy_type, StrategyType.VENV)

    def test_parse_combined_response_no_conflicts(self):
        """Test parsing LLM response with no conflicts"""
        response = json.dumps(
            {
                "has_conflicts": False,
                "conflicts": [],
                "strategies": [],
            }
        )

        conflicts, strategies = self.predictor._parse_combined_response(response, "requests")

        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(strategies), 0)

    def test_parse_combined_response_invalid_json(self):
        """Test parsing invalid JSON returns empty"""
        response = "This is not JSON"

        conflicts, strategies = self.predictor._parse_combined_response(response, "pkg")

        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(strategies), 0)

    def test_parse_combined_response_unknown_conflict_type(self):
        """Test parsing handles unknown conflict types"""
        response = json.dumps(
            {
                "conflicts": [
                    {
                        "conflicting_package": "pkg2",
                        "type": "UNKNOWN_TYPE",
                        "confidence": 0.8,
                        "explanation": "Some conflict",
                    }
                ],
            }
        )

        conflicts, _ = self.predictor._parse_combined_response(response, "pkg1")

        self.assertEqual(len(conflicts), 1)
        # Should default to VERSION
        self.assertEqual(conflicts[0].conflict_type, ConflictType.VERSION)


class TestExtractJsonFromResponse(unittest.TestCase):
    """Test JSON extraction utility"""

    def test_extract_simple_json(self):
        """Test extracting simple JSON"""
        response = '{"key": "value"}'
        result = extract_json_from_response(response)
        self.assertEqual(result, {"key": "value"})

    def test_extract_json_with_prefix(self):
        """Test extracting JSON with text prefix"""
        response = 'Here is the analysis: {"conflicts": []}'
        result = extract_json_from_response(response)
        self.assertEqual(result, {"conflicts": []})

    def test_extract_json_with_markdown(self):
        """Test extracting JSON wrapped in markdown"""
        response = '```json\n{"has_conflicts": true}\n```'
        result = extract_json_from_response(response)
        self.assertEqual(result, {"has_conflicts": True})

    def test_extract_nested_json(self):
        """Test extracting nested JSON"""
        response = '{"outer": {"inner": [1, 2, 3]}}'
        result = extract_json_from_response(response)
        self.assertEqual(result["outer"]["inner"], [1, 2, 3])

    def test_extract_no_json(self):
        """Test extracting from text without JSON"""
        response = "No JSON here"
        result = extract_json_from_response(response)
        self.assertIsNone(result)

    def test_extract_empty_response(self):
        """Test extracting from empty response"""
        result = extract_json_from_response("")
        self.assertIsNone(result)

    def test_extract_none_response(self):
        """Test extracting from None"""
        result = extract_json_from_response(None)
        self.assertIsNone(result)


class TestBasicStrategyGeneration(unittest.TestCase):
    """Test basic strategy generation (fallback when no LLM)"""

    def setUp(self):
        """Set up test fixtures"""
        self.predictor = ConflictPredictor()

    def test_generate_basic_strategies(self):
        """Test generating basic strategies"""
        conflicts = [
            ConflictPrediction(
                package1="tensorflow",
                package2="numpy",
                conflict_type=ConflictType.VERSION,
                confidence=0.95,
                explanation="Version conflict",
            )
        ]

        strategies = self.predictor._generate_basic_strategies(conflicts)

        self.assertGreater(len(strategies), 0)
        # Should include VENV as safest
        venv_strategies = [s for s in strategies if s.strategy_type == StrategyType.VENV]
        self.assertGreater(len(venv_strategies), 0)

    def test_strategies_sorted_by_safety(self):
        """Test strategies are sorted by safety score"""
        conflicts = [
            ConflictPrediction(
                package1="pkg1",
                package2="pkg2",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
            )
        ]

        strategies = self.predictor._generate_basic_strategies(conflicts)

        for i in range(len(strategies) - 1):
            self.assertGreaterEqual(strategies[i].safety_score, strategies[i + 1].safety_score)

    def test_strategies_limited_to_four(self):
        """Test strategies limited to 4 max"""
        conflicts = [
            ConflictPrediction(
                package1="pkg1",
                package2="pkg2",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
                required_constraint="< 2.0",
            )
        ]

        strategies = self.predictor._generate_basic_strategies(conflicts)

        self.assertLessEqual(len(strategies), 4)


class TestSecurityValidation(unittest.TestCase):
    """Test security validation functions"""

    def test_validate_version_constraint_valid(self):
        """Test valid version constraints"""
        # Note: constraints without spaces are valid (pip style)
        self.assertTrue(validate_version_constraint("<2.0"))
        self.assertTrue(validate_version_constraint(">=1.0"))
        self.assertTrue(validate_version_constraint("==1.2.3"))
        self.assertTrue(validate_version_constraint("!=2.0"))
        self.assertTrue(validate_version_constraint("~=1.4.2"))
        self.assertTrue(validate_version_constraint("1.0.0"))

    def test_validate_version_constraint_empty(self):
        """Test empty constraint is valid"""
        self.assertTrue(validate_version_constraint(""))
        self.assertTrue(validate_version_constraint(None))

    def test_validate_version_constraint_invalid(self):
        """Test invalid/malicious constraints are rejected"""
        # Command injection attempts
        self.assertFalse(validate_version_constraint("; rm -rf /"))
        self.assertFalse(validate_version_constraint("$(whoami)"))
        self.assertFalse(validate_version_constraint("`cat /etc/passwd`"))

    def test_escape_command_arg(self):
        """Test command argument escaping"""
        # Normal package name - shlex.quote only adds quotes when needed
        result = escape_command_arg("numpy")
        self.assertIn("numpy", result)
        # Package with special chars - should be quoted
        result = escape_command_arg("pkg; rm -rf /")
        self.assertIn("'", result)  # Should be quoted for safety


class TestDisplayFormatting(unittest.TestCase):
    """Test display/UI formatting functions"""

    def test_format_conflict_summary_empty(self):
        """Test formatting with no conflicts"""
        result = format_conflict_summary([], [])
        self.assertEqual(result, "")

    def test_format_conflict_summary_with_data(self):
        """Test formatting conflicts with data"""
        conflicts = [
            ConflictPrediction(
                package1="tensorflow",
                package2="numpy",
                conflict_type=ConflictType.VERSION,
                confidence=0.95,
                explanation="tensorflow 2.15 requires numpy < 2.0",
                severity="HIGH",
                installed_by="pandas",
                current_version="2.1.0",
            )
        ]
        strategies = [
            ResolutionStrategy(
                strategy_type=StrategyType.VENV,
                description="Use virtual environment",
                safety_score=0.95,
                commands=["python3 -m venv myenv"],
                benefits=["Isolation"],
                risks=["Must activate"],
            ),
        ]

        result = format_conflict_summary(conflicts, strategies)

        self.assertIn("tensorflow 2.15 requires numpy < 2.0", result)
        self.assertIn("pandas", result)
        self.assertIn("2.1.0", result)
        self.assertIn("[RECOMMENDED]", result)
        self.assertIn("Safety:", result)

    def test_format_conflict_summary_safety_bar(self):
        """Test safety bar is displayed"""
        conflicts = [
            ConflictPrediction(
                package1="pkg1",
                package2="pkg2",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test conflict",
            )
        ]
        strategies = [
            ResolutionStrategy(
                strategy_type=StrategyType.VENV,
                description="Test",
                safety_score=0.90,
                commands=["test"],
            ),
        ]

        result = format_conflict_summary(conflicts, strategies)

        self.assertIn("█", result)  # Should have filled blocks
        self.assertIn("90%", result)


class TestSystemParsing(unittest.TestCase):
    """Test system state parsing functions"""

    @patch("subprocess.run")
    def test_get_pip_packages_success(self, mock_run):
        """Test getting pip packages successfully"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {"name": "numpy", "version": "1.24.0"},
                    {"name": "pandas", "version": "2.0.0"},
                ]
            ),
        )

        packages = get_pip_packages()

        self.assertEqual(len(packages), 2)
        self.assertEqual(packages["numpy"], "1.24.0")
        self.assertEqual(packages["pandas"], "2.0.0")

    @patch("subprocess.run")
    def test_get_pip_packages_failure(self, mock_run):
        """Test handling pip failure gracefully"""
        mock_run.return_value = Mock(returncode=1, stdout="")

        packages = get_pip_packages()

        self.assertEqual(len(packages), 0)

    @patch("subprocess.run")
    def test_get_pip_packages_timeout(self, mock_run):
        """Test handling pip timeout"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("pip3", 5)

        packages = get_pip_packages()

        self.assertEqual(len(packages), 0)


class TestRecordResolution(unittest.TestCase):
    """Test recording conflict resolutions"""

    def setUp(self):
        """Set up test fixtures"""
        self.predictor = ConflictPredictor()

    def test_record_successful_resolution(self):
        """Test recording a successful resolution"""
        conflict = ConflictPrediction(
            package1="tensorflow",
            package2="numpy",
            conflict_type=ConflictType.VERSION,
            confidence=0.95,
            explanation="Test",
        )

        strategy = ResolutionStrategy(
            strategy_type=StrategyType.UPGRADE,
            description="Upgrade tensorflow",
            safety_score=0.85,
            commands=["pip install tensorflow==2.16"],
        )

        # Should not raise exception and return success rate
        result = self.predictor.record_resolution(conflict, strategy, success=True)
        # Default predictor has history, should return a success rate
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_record_failed_resolution(self):
        """Test recording a failed resolution"""
        conflict = ConflictPrediction(
            package1="pkg1",
            package2="pkg2",
            conflict_type=ConflictType.VERSION,
            confidence=0.8,
            explanation="Test",
        )

        strategy = ResolutionStrategy(
            strategy_type=StrategyType.DOWNGRADE,
            description="Downgrade pkg2",
            safety_score=0.6,
            commands=["pip install pkg2==1.0"],
        )

        # Should not raise exception and return success rate
        result = self.predictor.record_resolution(
            conflict, strategy, success=False, user_feedback="Did not work"
        )
        # Default predictor has history, should return a success rate
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)

    def test_record_resolution_with_mock_history(self):
        """Test that persistence call is made and success rate is queried"""
        mock_history = MagicMock()
        mock_history.record_conflict_resolution.return_value = "test-id"
        mock_history.get_conflict_resolution_success_rate.return_value = 0.75

        predictor = ConflictPredictor(history=mock_history)

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
        success_rate = predictor.record_resolution(conflict, strategy, success=True)

        # Assert persistence call was made with correct parameters
        mock_history.record_conflict_resolution.assert_called_once()
        call_kwargs = mock_history.record_conflict_resolution.call_args[1]
        self.assertEqual(call_kwargs["package1"], "tensorflow")
        self.assertEqual(call_kwargs["package2"], "numpy")
        self.assertEqual(call_kwargs["conflict_type"], "version")
        self.assertEqual(call_kwargs["strategy_type"], "venv")
        self.assertTrue(call_kwargs["success"])

        # Assert success rate was queried after recording
        mock_history.get_conflict_resolution_success_rate.assert_called_once_with(
            conflict_type="version",
            strategy_type="venv",
        )

        # Assert returned success rate
        self.assertEqual(success_rate, 0.75)

    def test_record_resolution_handles_db_error(self):
        """Test that DB/IO errors are handled gracefully"""
        mock_history = MagicMock()
        mock_history.record_conflict_resolution.side_effect = OSError("DB error")

        predictor = ConflictPredictor(history=mock_history)

        conflict = ConflictPrediction(
            package1="pkg1",
            package2="pkg2",
            conflict_type=ConflictType.VERSION,
            confidence=0.9,
            explanation="Test",
        )

        strategy = ResolutionStrategy(
            strategy_type=StrategyType.UPGRADE,
            description="Upgrade",
            safety_score=0.8,
            commands=["pip install --upgrade pkg1"],
        )

        # Should not raise exception, returns None on error
        result = predictor.record_resolution(conflict, strategy, success=True)
        self.assertIsNone(result)


class TestCommandInjectionProtection(unittest.TestCase):
    """Test command injection protection"""

    def test_malicious_package_name_in_strategy(self):
        """Test that malicious package names are escaped in generated commands"""
        predictor = ConflictPredictor()
        conflicts = [
            ConflictPrediction(
                package1="pkg; rm -rf /",
                package2="numpy",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
            )
        ]

        strategies = predictor._generate_basic_strategies(conflicts)

        # All commands should have the malicious package name properly quoted
        for strategy in strategies:
            for cmd in strategy.commands:
                if "pkg" in cmd:
                    # The malicious name should be quoted with single quotes
                    self.assertIn("'pkg; rm -rf /'", cmd)

    def test_malicious_constraint_rejected(self):
        """Test that malicious version constraints are rejected"""
        predictor = ConflictPredictor()
        conflicts = [
            ConflictPrediction(
                package1="pkg1",
                package2="pkg2",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
                required_constraint="; rm -rf /",  # Malicious constraint
            )
        ]

        strategies = predictor._generate_basic_strategies(conflicts)

        # Should not generate DOWNGRADE strategy with malicious constraint
        downgrade_strategies = [s for s in strategies if s.strategy_type == StrategyType.DOWNGRADE]
        self.assertEqual(len(downgrade_strategies), 0)


class TestJsonExtractionRobustness(unittest.TestCase):
    """Test JSON extraction edge cases"""

    def test_json_with_trailing_text(self):
        """Test JSON followed by additional text"""
        response = '{"key": "value"} and some more text here'
        result = extract_json_from_response(response)
        self.assertEqual(result, {"key": "value"})

    def test_multiple_json_objects(self):
        """Test only first JSON object is extracted"""
        response = '{"first": 1} {"second": 2}'
        result = extract_json_from_response(response)
        self.assertEqual(result, {"first": 1})

    def test_json_with_special_characters(self):
        """Test JSON with special characters in strings"""
        response = '{"explanation": "numpy < 2.0 && numpy >= 1.0"}'
        result = extract_json_from_response(response)
        self.assertEqual(result["explanation"], "numpy < 2.0 && numpy >= 1.0")

    def test_malformed_json_recovery(self):
        """Test recovery from malformed JSON at start"""
        response = '{bad json} {"valid": true}'
        result = extract_json_from_response(response)
        # Should find the valid JSON
        self.assertEqual(result, {"valid": True})

    def test_deeply_nested_json(self):
        """Test deeply nested JSON structures"""
        response = '{"a": {"b": {"c": {"d": [1, 2, {"e": "value"}]}}}}'
        result = extract_json_from_response(response)
        self.assertEqual(result["a"]["b"]["c"]["d"][2]["e"], "value")


class TestMalformedDpkgHandling(unittest.TestCase):
    """Test handling of malformed dpkg output"""

    @patch("subprocess.run")
    def test_malformed_dpkg_lines_skipped(self, mock_run):
        """Test that malformed dpkg lines are safely skipped"""
        from cortex.conflict_predictor import get_apt_packages_summary

        # Mix of valid and malformed lines
        mock_run.return_value = Mock(
            returncode=0,
            stdout="python3\tinstall\n\t\n\npython-dev\tinstall\nbadline\n",
        )

        packages = get_apt_packages_summary()

        # Should have extracted valid packages without error
        self.assertIn("python3", packages)
        self.assertIn("python-dev", packages)

    @patch("subprocess.run")
    def test_empty_dpkg_output(self, mock_run):
        """Test handling of empty dpkg output"""
        from cortex.conflict_predictor import get_apt_packages_summary

        mock_run.return_value = Mock(returncode=0, stdout="")

        packages = get_apt_packages_summary()

        self.assertEqual(packages, [])


class TestFullConflictPredictionFlow(unittest.TestCase):
    """Integration tests for full conflict prediction flow"""

    def test_full_flow_with_mock_llm(self):
        """Test complete prediction flow with mocked LLM"""
        mock_router = MagicMock()
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
                        "explanation": "tensorflow requires numpy < 2.0",
                        "current_version": "2.1.0",
                    }
                ],
                "strategies": [
                    {
                        "type": "VENV",
                        "description": "Use venv",
                        "safety_score": 0.95,
                        "commands": ["python3 -m venv tf_env"],
                    }
                ],
            }
        )
        mock_router.complete.return_value = mock_response

        predictor = ConflictPredictor(llm_router=mock_router)

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={"numpy": "2.1.0"}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = predictor.predict_conflicts_with_resolutions(
                    "tensorflow", "2.15.0"
                )

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].package2, "numpy")
        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0].strategy_type, StrategyType.VENV)

    def test_full_flow_llm_returns_no_conflicts(self):
        """Test flow when LLM returns no conflicts"""
        mock_router = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "has_conflicts": False,
                "conflicts": [],
                "strategies": [],
            }
        )
        mock_router.complete.return_value = mock_response

        predictor = ConflictPredictor(llm_router=mock_router)

        with patch("cortex.conflict_predictor.get_pip_packages", return_value={}):
            with patch("cortex.conflict_predictor.get_apt_packages_summary", return_value=[]):
                conflicts, strategies = predictor.predict_conflicts_with_resolutions("requests")

        self.assertEqual(len(conflicts), 0)
        self.assertEqual(len(strategies), 0)


class TestStrategyExecutionOrder(unittest.TestCase):
    """Test strategy execution order and command structure"""

    def test_venv_commands_order(self):
        """Test venv strategy has commands in correct order"""
        predictor = ConflictPredictor()
        conflicts = [
            ConflictPrediction(
                package1="tensorflow",
                package2="numpy",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
            )
        ]

        strategies = predictor._generate_basic_strategies(conflicts)
        venv_strategy = next(s for s in strategies if s.strategy_type == StrategyType.VENV)

        # Commands should be: create venv, activate, install
        self.assertEqual(len(venv_strategy.commands), 3)
        self.assertIn("venv", venv_strategy.commands[0])
        self.assertIn("source", venv_strategy.commands[1])
        self.assertIn("pip install", venv_strategy.commands[2])

    def test_remove_conflict_commands_order(self):
        """Test remove strategy has commands in correct order"""
        predictor = ConflictPredictor()
        conflicts = [
            ConflictPrediction(
                package1="pkg1",
                package2="pkg2",
                conflict_type=ConflictType.VERSION,
                confidence=0.9,
                explanation="Test",
            )
        ]

        strategies = predictor._generate_basic_strategies(conflicts)
        remove_strategy = next(
            s for s in strategies if s.strategy_type == StrategyType.REMOVE_CONFLICT
        )

        # Commands should be: uninstall conflicting, install new
        self.assertEqual(len(remove_strategy.commands), 2)
        self.assertIn("uninstall", remove_strategy.commands[0])
        self.assertIn("install", remove_strategy.commands[1])


class TestTimeoutProtection(unittest.TestCase):
    """Test timeout protection in system calls"""

    @patch("subprocess.run")
    def test_pip_timeout_handled(self, mock_run):
        """Test pip command timeout is handled gracefully"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("pip3", 5)

        packages = get_pip_packages()

        self.assertEqual(packages, {})
        # Should not raise exception

    @patch("subprocess.run")
    def test_dpkg_timeout_handled(self, mock_run):
        """Test dpkg command timeout is handled gracefully"""
        import subprocess

        from cortex.conflict_predictor import get_apt_packages_summary

        mock_run.side_effect = subprocess.TimeoutExpired("dpkg", 5)

        packages = get_apt_packages_summary()

        self.assertEqual(packages, [])
        # Should not raise exception


class TestMemoryUsageWithLargePackages(unittest.TestCase):
    """Test handling of large package lists"""

    @patch("subprocess.run")
    def test_pip_packages_limited(self, mock_run):
        """Test that pip packages are limited in prompt"""
        # Create a large list of packages
        large_package_list = [{"name": f"package{i}", "version": "1.0.0"} for i in range(200)]
        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(large_package_list))

        packages = get_pip_packages()

        # Should return all packages (limiting happens in prompt building)
        self.assertEqual(len(packages), 200)

    def test_prompt_limits_packages(self):
        """Test that prompt building limits package count"""
        predictor = ConflictPredictor()

        # Create large package dicts
        pip_packages = {f"pkg{i}": "1.0.0" for i in range(100)}
        apt_packages = [f"lib{i}" for i in range(50)]

        prompt = predictor._build_combined_prompt(
            "tensorflow", "2.15.0", pip_packages, apt_packages
        )

        # Should limit pip to 50 and apt to 30
        pip_count = prompt.count("==1.0.0")
        apt_count = prompt.count("lib")

        self.assertLessEqual(pip_count, 50)
        self.assertLessEqual(apt_count, 30)


if __name__ == "__main__":
    unittest.main()
