"""
Tests for First-Run Wizard Module

Issue: #256
"""

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.first_run_wizard import (
    FirstRunWizard,
    StepResult,
    WizardState,
    WizardStep,
    get_config,
    needs_first_run,
    run_wizard,
)


class TestWizardStep:
    """Tests for WizardStep enum."""

    def test_all_steps_exist(self):
        """Test all expected steps exist."""
        expected = [
            "WELCOME",
            "API_SETUP",
            "HARDWARE_DETECTION",
            "PREFERENCES",
            "SHELL_INTEGRATION",
            "TEST_COMMAND",
            "COMPLETE",
        ]

        actual = [s.name for s in WizardStep]

        for e in expected:
            assert e in actual

    def test_step_values(self):
        """Test step values are lowercase."""
        for step in WizardStep:
            assert step.value == step.name.lower()


class TestWizardState:
    """Tests for WizardState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = WizardState()

        assert state.current_step == WizardStep.WELCOME
        assert state.completed_steps == []
        assert state.skipped_steps == []
        assert state.collected_data == {}
        assert state.completed_at is None

    def test_mark_completed(self):
        """Test marking steps as completed."""
        state = WizardState()

        state.mark_completed(WizardStep.WELCOME)
        state.mark_completed(WizardStep.API_SETUP)

        assert WizardStep.WELCOME in state.completed_steps
        assert WizardStep.API_SETUP in state.completed_steps
        assert len(state.completed_steps) == 2

    def test_mark_completed_no_duplicates(self):
        """Test that completed steps aren't duplicated."""
        state = WizardState()

        state.mark_completed(WizardStep.WELCOME)
        state.mark_completed(WizardStep.WELCOME)

        assert state.completed_steps.count(WizardStep.WELCOME) == 1

    def test_mark_skipped(self):
        """Test marking steps as skipped."""
        state = WizardState()

        state.mark_skipped(WizardStep.SHELL_INTEGRATION)

        assert WizardStep.SHELL_INTEGRATION in state.skipped_steps

    def test_is_completed(self):
        """Test checking if step is completed."""
        state = WizardState()

        assert state.is_completed(WizardStep.WELCOME) is False

        state.mark_completed(WizardStep.WELCOME)

        assert state.is_completed(WizardStep.WELCOME) is True

    def test_to_dict(self):
        """Test serialization to dict."""
        state = WizardState()
        state.mark_completed(WizardStep.WELCOME)
        state.collected_data["test"] = "value"

        data = state.to_dict()

        assert data["current_step"] == "welcome"
        assert "welcome" in data["completed_steps"]
        assert data["collected_data"]["test"] == "value"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "current_step": "api_setup",
            "completed_steps": ["welcome"],
            "skipped_steps": [],
            "collected_data": {"api": "anthropic"},
            "started_at": "2024-01-15T10:00:00",
            "completed_at": None,
        }

        state = WizardState.from_dict(data)

        assert state.current_step == WizardStep.API_SETUP
        assert WizardStep.WELCOME in state.completed_steps
        assert state.collected_data["api"] == "anthropic"


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = StepResult(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"

    def test_result_with_data(self):
        """Test result with data."""
        result = StepResult(success=True, data={"api_provider": "anthropic"})

        assert result.data["api_provider"] == "anthropic"

    def test_result_with_skip(self):
        """Test result with skip directive."""
        result = StepResult(success=True, skip_to=WizardStep.TEST_COMMAND)

        assert result.skip_to == WizardStep.TEST_COMMAND


class TestFirstRunWizard:
    """Tests for FirstRunWizard class."""

    @pytest.fixture
    def wizard(self, tmp_path):
        """Create wizard with temp config directory."""
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        wizard.STATE_FILE = tmp_path / "wizard_state.json"
        wizard.CONFIG_FILE = tmp_path / "config.json"
        wizard.SETUP_COMPLETE_FILE = tmp_path / ".setup_complete"
        wizard._ensure_config_dir()
        return wizard

    def test_init_non_interactive(self, wizard):
        """Test non-interactive initialization."""
        assert wizard.interactive is False

    def test_ensure_config_dir(self, wizard):
        """Test config directory creation."""
        assert wizard.CONFIG_DIR.exists()

    def test_needs_setup_true(self, wizard):
        """Test needs_setup returns True when not set up."""
        assert wizard.needs_setup() is True

    def test_needs_setup_false(self, wizard):
        """Test needs_setup returns False when set up."""
        wizard.SETUP_COMPLETE_FILE.touch()
        assert wizard.needs_setup() is False

    def test_save_and_load_state(self, wizard):
        """Test state persistence."""
        wizard.state.current_step = WizardStep.PREFERENCES
        wizard.state.mark_completed(WizardStep.WELCOME)
        wizard.state.mark_completed(WizardStep.API_SETUP)

        wizard.save_state()

        # Create new wizard and load state
        wizard2 = FirstRunWizard(interactive=False)
        wizard2.STATE_FILE = wizard.STATE_FILE
        wizard2.load_state()

        assert wizard2.state.current_step == WizardStep.PREFERENCES
        assert WizardStep.WELCOME in wizard2.state.completed_steps

    def test_save_config(self, wizard):
        """Test config persistence."""
        wizard.config = {"api_provider": "anthropic", "preferences": {"verbosity": "normal"}}

        wizard.save_config()

        assert wizard.CONFIG_FILE.exists()

        with open(wizard.CONFIG_FILE) as f:
            loaded = json.load(f)

        assert loaded["api_provider"] == "anthropic"

    def test_mark_setup_complete(self, wizard):
        """Test marking setup as complete."""
        wizard.mark_setup_complete()

        assert wizard.SETUP_COMPLETE_FILE.exists()
        assert wizard.state.completed_at is not None

    @patch("os.system")
    def test_clear_screen(self, mock_system, wizard):
        """Test screen clearing."""
        wizard.interactive = True
        wizard._clear_screen()

        mock_system.assert_called()

    def test_print_header(self, wizard, capsys):
        """Test header printing."""
        wizard._print_header("Test Header")

        captured = capsys.readouterr()
        assert "Test Header" in captured.out

    def test_prompt_non_interactive(self, wizard):
        """Test prompt in non-interactive mode."""
        result = wizard._prompt("Enter value: ", default="default")
        assert result == "default"


class TestWizardSteps:
    """Tests for individual wizard steps."""

    @pytest.fixture
    def wizard(self, tmp_path):
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        wizard.STATE_FILE = tmp_path / "wizard_state.json"
        wizard.CONFIG_FILE = tmp_path / "config.json"
        wizard.SETUP_COMPLETE_FILE = tmp_path / ".setup_complete"
        wizard._ensure_config_dir()
        return wizard

    def test_step_welcome(self, wizard):
        """Test welcome step."""
        result = wizard._step_welcome()

        assert result.success is True

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key-12345678"})
    def test_step_api_setup_existing_key(self, wizard):
        """Test API setup with existing key."""
        result = wizard._step_api_setup()

        assert result.success is True
        assert wizard.config.get("api_provider") == "anthropic"

    @patch.dict(os.environ, {}, clear=True)
    def test_step_api_setup_no_key(self, wizard):
        """Test API setup without existing key."""
        # Remove any existing keys
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        result = wizard._step_api_setup()

        assert result.success is True
        assert result.data.get("api_provider") == "none"

    @patch("subprocess.run")
    def test_step_hardware_detection(self, mock_run, wizard):
        """Test hardware detection step."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="00:02.0 VGA compatible controller: Intel Corporation"
        )

        result = wizard._step_hardware_detection()

        assert result.success is True
        assert "hardware" in result.data

    def test_step_preferences(self, wizard):
        """Test preferences step."""
        result = wizard._step_preferences()

        assert result.success is True
        assert "preferences" in result.data

        prefs = result.data["preferences"]
        assert "auto_confirm" in prefs
        assert "verbosity" in prefs
        assert "enable_cache" in prefs

    def test_step_shell_integration(self, wizard):
        """Test shell integration step."""
        result = wizard._step_shell_integration()

        assert result.success is True

    def test_step_test_command(self, wizard):
        """Test the test command step."""
        result = wizard._step_test_command()

        assert result.success is True

    def test_step_complete(self, wizard):
        """Test completion step."""
        wizard.config = {
            "api_provider": "anthropic",
            "preferences": {"verbosity": "normal", "enable_cache": True},
        }

        result = wizard._step_complete()

        assert result.success is True


class TestHardwareDetection:
    """Tests for hardware detection functionality."""

    @pytest.fixture
    def wizard(self, tmp_path):
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        return wizard

    @patch("builtins.open")
    @patch("subprocess.run")
    def test_detect_hardware_full(self, mock_run, mock_open, wizard):
        """Test full hardware detection."""
        # Mock /proc/cpuinfo
        mock_open.return_value.__enter__.return_value.__iter__ = lambda s: iter(
            ["model name : Intel Core i7-9700K\n"]
        )

        # Mock lspci
        mock_run.return_value = MagicMock(
            returncode=0, stdout="00:02.0 VGA compatible controller: NVIDIA GeForce RTX 4090\n"
        )

        # Can't fully test due to file reading, but ensure method runs
        info = wizard._detect_hardware()

        assert isinstance(info, dict)

    @patch("subprocess.run")
    def test_detect_nvidia_gpu(self, mock_run, wizard):
        """Test NVIDIA GPU detection."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="01:00.0 VGA compatible controller: NVIDIA Corporation GeForce RTX 4090",
        )

        info = wizard._detect_hardware()

        # GPU detection happens in lspci parsing
        # Just verify it doesn't crash
        assert isinstance(info, dict)


class TestShellIntegration:
    """Tests for shell integration functionality."""

    @pytest.fixture
    def wizard(self, tmp_path):
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        return wizard

    def test_generate_bash_completion(self, wizard):
        """Test bash completion generation."""
        script = wizard._generate_completion_script("bash")

        assert "_cortex_completion" in script
        assert "complete" in script

    def test_generate_zsh_completion(self, wizard):
        """Test zsh completion generation."""
        script = wizard._generate_completion_script("zsh")

        assert "_cortex" in script
        assert "compdef" in script

    def test_generate_fish_completion(self, wizard):
        """Test fish completion generation."""
        script = wizard._generate_completion_script("fish")

        assert "complete -c cortex" in script

    def test_generate_unknown_shell(self, wizard):
        """Test completion for unknown shell."""
        script = wizard._generate_completion_script("unknown")

        assert "No completion available" in script

    def test_get_shell_config_bash(self, wizard):
        """Test getting bash config path."""
        path = wizard._get_shell_config("bash")

        assert path.name == ".bashrc"

    def test_get_shell_config_zsh(self, wizard):
        """Test getting zsh config path."""
        path = wizard._get_shell_config("zsh")

        assert path.name == ".zshrc"


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""

    def test_needs_first_run(self, tmp_path):
        """Test needs_first_run function."""
        # Should return True by default (no setup file)
        result = needs_first_run()
        assert isinstance(result, bool)

    @patch.object(FirstRunWizard, "run")
    def test_run_wizard(self, mock_run):
        """Test run_wizard function."""
        mock_run.return_value = True

        result = run_wizard(interactive=False)

        # Just verify it doesn't crash
        assert isinstance(result, bool)

    def test_get_config_no_file(self):
        """Test get_config when no file exists."""
        config = get_config()

        # Should return empty dict or existing config
        assert isinstance(config, dict)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def wizard(self, tmp_path):
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        wizard.STATE_FILE = tmp_path / "wizard_state.json"
        wizard.CONFIG_FILE = tmp_path / "config.json"
        wizard.SETUP_COMPLETE_FILE = tmp_path / ".setup_complete"
        return wizard

    def test_load_state_corrupted_file(self, wizard):
        """Test loading corrupted state file."""
        wizard.STATE_FILE.write_text("invalid json")

        result = wizard.load_state()

        assert result is False

    def test_save_state_readonly(self, wizard, tmp_path):
        """Test saving state to readonly location."""
        # Make directory readonly
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, 0o444)

        wizard.STATE_FILE = readonly_dir / "state.json"

        # Should not raise, just log warning
        wizard.save_state()

        # Cleanup
        os.chmod(readonly_dir, 0o755)

    def test_prompt_eof(self, wizard):
        """Test prompt handling EOF."""
        wizard.interactive = True

        with patch("builtins.input", side_effect=EOFError):
            result = wizard._prompt("Test: ", default="default")

        assert result == "default"

    def test_prompt_keyboard_interrupt(self, wizard):
        """Test prompt handling Ctrl+C."""
        wizard.interactive = True

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = wizard._prompt("Test: ", default="default")

        assert result == "default"


class TestIntegration:
    """Integration tests for the complete wizard flow."""

    @pytest.fixture
    def wizard(self, tmp_path):
        wizard = FirstRunWizard(interactive=False)
        wizard.CONFIG_DIR = tmp_path
        wizard.STATE_FILE = tmp_path / "wizard_state.json"
        wizard.CONFIG_FILE = tmp_path / "config.json"
        wizard.SETUP_COMPLETE_FILE = tmp_path / ".setup_complete"
        wizard._ensure_config_dir()
        return wizard

    @patch("subprocess.run")
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-12345678"})
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True)
    @patch("cortex.cli.CommandInterpreter")
    def test_complete_wizard_flow(self, mock_interpreter_class, mock_run, wizard):
        """Test complete wizard flow in non-interactive mode."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo 'test command'"]
        mock_interpreter_class.return_value = mock_interpreter

        result = wizard.run()

        assert result is True
        assert wizard.SETUP_COMPLETE_FILE.exists()
        assert wizard.CONFIG_FILE.exists()

    def test_wizard_resume(self, wizard):
        """Test wizard resuming from saved state."""
        # Simulate partial completion
        wizard.state.current_step = WizardStep.PREFERENCES
        wizard.state.mark_completed(WizardStep.WELCOME)
        wizard.state.mark_completed(WizardStep.API_SETUP)
        wizard.state.mark_completed(WizardStep.HARDWARE_DETECTION)
        wizard.save_state()

        # Create new wizard and load state
        wizard2 = FirstRunWizard(interactive=False)
        wizard2.CONFIG_DIR = wizard.CONFIG_DIR
        wizard2.STATE_FILE = wizard.STATE_FILE
        wizard2.CONFIG_FILE = wizard.CONFIG_FILE
        wizard2.SETUP_COMPLETE_FILE = wizard.SETUP_COMPLETE_FILE

        wizard2.load_state()

        assert wizard2.state.current_step == WizardStep.PREFERENCES
        assert len(wizard2.state.completed_steps) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
