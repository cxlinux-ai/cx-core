"""
Tests for the Cortex Dashboard module.

Tests verify:
- System monitoring with explicit-intent pattern
- Process listing with privacy protections
- Model listing (Ollama integration)
- Command history
- UI rendering
- Dashboard app initialization
"""

import io
import json
import os
import sys
import time
import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cortex.dashboard as dashboard
from cortex.dashboard import (
    ACTION_MAP,
    BAR_WIDTH,
    BYTES_PER_GB,
    CRITICAL_THRESHOLD,
    CommandHistory,
    DashboardApp,
    DashboardTab,
    InstallationProgress,
    InstallationState,
    ModelLister,
    ProcessLister,
    SystemMetrics,
    SystemMonitor,
    UIRenderer,
)


class TestSystemMonitor(unittest.TestCase):
    """Test SystemMonitor class with explicit-intent pattern."""

    def test_init_no_auto_collection(self):
        """Metrics should be zero before enabling - no auto-collection."""
        monitor = SystemMonitor()
        metrics = monitor.get_metrics()
        self.assertEqual(metrics.cpu_percent, 0.0)
        self.assertEqual(metrics.ram_percent, 0.0)
        self.assertFalse(monitor._monitoring_enabled)

    def test_enable_monitoring(self):
        """Enabling monitoring should set the flag."""
        monitor = SystemMonitor()
        monitor.enable_monitoring()
        self.assertTrue(monitor._monitoring_enabled)

    def test_update_metrics_when_enabled(self):
        """Metrics should be populated after enabling and updating with deterministic mocked values."""
        from unittest.mock import MagicMock, patch

        monitor = SystemMonitor()
        monitor.enable_monitoring()

        # Mock psutil to return deterministic values
        mock_vm = MagicMock()
        mock_vm.used = 8589934592  # 8 GB in bytes
        mock_vm.total = 17179869184  # 16 GB in bytes
        mock_vm.percent = 50.0

        with patch("cortex.dashboard.psutil.cpu_percent", return_value=42.5):
            with patch("cortex.dashboard.psutil.virtual_memory", return_value=mock_vm):
                monitor.update_metrics()
                metrics = monitor.get_metrics()

        # Verify metrics match mocked values
        self.assertEqual(metrics.cpu_percent, 42.5)
        self.assertEqual(metrics.ram_percent, 50.0)
        self.assertAlmostEqual(metrics.ram_used_gb, 8.0, places=1)
        self.assertAlmostEqual(metrics.ram_total_gb, 16.0, places=1)

    def test_update_metrics_when_disabled(self):
        """Metrics should not update when monitoring is disabled."""
        monitor = SystemMonitor()
        # Don't enable
        monitor.update_metrics()
        metrics = monitor.get_metrics()
        self.assertEqual(metrics.cpu_percent, 0.0)


class TestProcessLister(unittest.TestCase):
    """Test ProcessLister class with explicit-intent pattern."""

    def test_init_no_auto_collection(self):
        """Process list should be empty before enabling."""
        lister = ProcessLister()
        processes = lister.get_processes()
        self.assertEqual(len(processes), 0)
        self.assertFalse(lister._enabled)

    def test_enable_process_listing(self):
        """Enabling should set the flag."""
        lister = ProcessLister()
        lister.enable()
        self.assertTrue(lister._enabled)

    def test_update_processes_when_enabled(self):
        """Should return list of processes when enabled."""
        lister = ProcessLister()
        lister.enable()
        lister.update_processes()
        processes = lister.get_processes()
        self.assertIsInstance(processes, list)

    def test_no_cmdline_collected(self):
        """Privacy: cmdline should NOT be collected."""
        lister = ProcessLister()
        lister.enable()
        lister.update_processes()
        for proc in lister.get_processes():
            self.assertNotIn("cmdline", proc)

    def test_keywords_defined(self):
        """Should have AI/ML related keywords defined."""
        self.assertIn("python", ProcessLister.KEYWORDS)
        self.assertIn("ollama", ProcessLister.KEYWORDS)
        self.assertIn("pytorch", ProcessLister.KEYWORDS)


class TestModelLister(unittest.TestCase):
    """Test ModelLister class for Ollama integration."""

    def test_init_no_auto_collection(self):
        """Model list should be empty before enabling."""
        lister = ModelLister()
        models = lister.get_models()
        self.assertEqual(len(models), 0)
        self.assertFalse(lister._enabled)

    def test_enable_model_listing(self):
        """Enabling should set the flag."""
        lister = ModelLister()
        lister.enable()
        self.assertTrue(lister._enabled)

    @patch("cortex.dashboard.requests.get")
    def test_check_ollama_available(self, mock_get):
        """Should detect when Ollama is running."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        lister = ModelLister()
        result = lister.check_ollama()
        self.assertTrue(result)
        self.assertTrue(lister.ollama_available)

    @patch("cortex.dashboard.requests.get")
    def test_check_ollama_not_available(self, mock_get):
        """Should handle Ollama not running."""
        mock_get.side_effect = Exception("Connection refused")

        lister = ModelLister()
        result = lister.check_ollama()
        self.assertFalse(result)
        self.assertFalse(lister.ollama_available)

    @patch("cortex.dashboard.requests.get")
    def test_update_models_success(self, mock_get):
        """Should parse Ollama API response correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama2:7b", "size": 4000000000, "digest": "abc12345xyz"},
                {"name": "codellama:13b", "size": 8000000000, "digest": "def67890uvw"},
            ]
        }
        mock_get.return_value = mock_response

        lister = ModelLister()
        lister.enable()
        lister.update_models()
        models = lister.get_models()

        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["name"], "llama2:7b")
        self.assertEqual(models[1]["name"], "codellama:13b")


class TestCommandHistory(unittest.TestCase):
    """Test CommandHistory class with explicit-intent pattern."""

    def test_init_no_auto_loading(self):
        """History should be empty before loading."""
        history = CommandHistory()
        cmds = history.get_history()
        self.assertEqual(len(cmds), 0)
        self.assertFalse(history._loaded)

    def test_add_command_without_loading(self):
        """Can add commands manually without loading shell history."""
        history = CommandHistory()
        history.add_command("test command")
        cmds = history.get_history()
        self.assertIn("test command", cmds)

    def test_add_empty_command_ignored(self):
        """Empty commands should be ignored."""
        history = CommandHistory()
        history.add_command("")
        history.add_command("   ")
        cmds = history.get_history()
        self.assertEqual(len(cmds), 0)


class TestUIRenderer(unittest.TestCase):
    """Test UIRenderer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = SystemMonitor()
        self.lister = ProcessLister()
        self.history = CommandHistory()
        self.model_lister = ModelLister()
        self.ui = UIRenderer(
            self.monitor,
            self.lister,
            self.history,
            self.model_lister,
        )

    def test_init_state(self):
        """UI should have correct initial state."""
        self.assertFalse(self.ui.running)
        self.assertFalse(self.ui.should_quit)
        self.assertEqual(self.ui.current_tab, DashboardTab.HOME)
        self.assertFalse(self.ui._user_started_monitoring)

    def test_render_header(self):
        """Header should render without error."""
        header = self.ui._render_header()
        self.assertIsNotNone(header)

    def test_render_resources_before_monitoring(self):
        """Resources should show placeholder before monitoring enabled."""
        panel = self.ui._render_resources()
        self.assertIsNotNone(panel)

    def test_render_processes_before_monitoring(self):
        """Processes should show placeholder before monitoring enabled."""
        panel = self.ui._render_processes()
        self.assertIsNotNone(panel)

    def test_render_models_before_monitoring(self):
        """Models should show placeholder before monitoring enabled."""
        panel = self.ui._render_models()
        self.assertIsNotNone(panel)

    def test_render_history(self):
        """History should render without error."""
        panel = self.ui._render_history()
        self.assertIsNotNone(panel)

    def test_render_actions(self):
        """Actions should render without error."""
        panel = self.ui._render_actions()
        self.assertIsNotNone(panel)

    def test_render_footer(self):
        """Footer should render without error."""
        panel = self.ui._render_footer()
        self.assertIsNotNone(panel)

    def test_render_screen(self):
        """Full screen should render without error."""
        screen = self.ui._render_screen()
        self.assertIsNotNone(screen)

    def test_render_progress_tab(self):
        """Progress tab should render without error."""
        self.ui.current_tab = DashboardTab.PROGRESS
        tab = self.ui._render_progress_tab()
        self.assertIsNotNone(tab)


class TestDashboardApp(unittest.TestCase):
    """Test DashboardApp class."""

    def test_init_components(self):
        """App should initialize all components."""
        app = DashboardApp()

        self.assertIsNotNone(app.monitor)
        self.assertIsNotNone(app.lister)
        self.assertIsNotNone(app.history)
        self.assertIsNotNone(app.model_lister)
        self.assertIsNotNone(app.ui)

    def test_no_auto_collection_on_init(self):
        """No auto-collection should happen on app initialization."""
        app = DashboardApp()

        self.assertFalse(app.monitor._monitoring_enabled)
        self.assertFalse(app.lister._enabled)
        self.assertFalse(app.history._loaded)
        self.assertFalse(app.model_lister._enabled)


class TestDataClasses(unittest.TestCase):
    """Test data classes."""

    def test_system_metrics_defaults(self):
        """SystemMetrics should have sensible defaults."""
        metrics = SystemMetrics(
            cpu_percent=50.0,
            ram_percent=60.0,
            ram_used_gb=8.0,
            ram_total_gb=16.0,
        )
        self.assertEqual(metrics.cpu_percent, 50.0)
        self.assertIsNone(metrics.gpu_percent)
        self.assertIsNotNone(metrics.timestamp)

    def test_installation_progress_defaults(self):
        """InstallationProgress should have sensible defaults."""
        progress = InstallationProgress()
        self.assertEqual(progress.state, InstallationState.IDLE)
        self.assertEqual(progress.package, "")
        self.assertEqual(progress.current_step, 0)

    def test_installation_progress_update_elapsed(self):
        """Elapsed time should update when start_time is set."""
        progress = InstallationProgress()
        progress.start_time = time.time() - 5.0  # 5 seconds ago
        progress.update_elapsed()
        self.assertGreaterEqual(progress.elapsed_time, 4.9)


class TestConstants(unittest.TestCase):
    """Test that constants are properly defined."""

    def test_action_map_defined(self):
        """ACTION_MAP should have all required actions."""
        self.assertIn("1", ACTION_MAP)
        self.assertIn("2", ACTION_MAP)
        self.assertIn("3", ACTION_MAP)
        self.assertIn("4", ACTION_MAP)

    def test_action_map_structure(self):
        """ACTION_MAP entries should have correct structure."""
        for key, value in ACTION_MAP.items():
            self.assertEqual(len(value), 3)  # (label, action_type, handler_name)
            label, action_type, handler_name = value
            self.assertIsInstance(label, str)
            self.assertTrue(handler_name.startswith("_"))

    def test_bytes_per_gb(self):
        """BYTES_PER_GB should be correct."""
        self.assertEqual(BYTES_PER_GB, 1024**3)

    def test_bar_width(self):
        """BAR_WIDTH should be defined."""
        self.assertIsInstance(BAR_WIDTH, int)
        self.assertGreater(BAR_WIDTH, 0)

    def test_critical_threshold(self):
        """CRITICAL_THRESHOLD should be defined."""
        self.assertIsInstance(CRITICAL_THRESHOLD, int)
        self.assertGreater(CRITICAL_THRESHOLD, 0)
        self.assertLessEqual(CRITICAL_THRESHOLD, 100)


class TestOllamaConfig(unittest.TestCase):
    """Test Ollama endpoint configuration resolution."""

    def test_env_overrides_default(self):
        """Environment variable should take precedence and strip trailing slash."""
        with patch.dict(os.environ, {"OLLAMA_API_BASE": "https://example.com:9999/"}, clear=True):
            base = dashboard._get_ollama_api_base()
        self.assertEqual(base, "https://example.com:9999")

    def test_config_file_used_when_env_missing(self):
        """preferences.yaml should be read when env is absent."""
        mock_prefs = "ollama_api_base: https://config.example.com:7777"
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=mock_prefs)):
                    base = dashboard._get_ollama_api_base()
        self.assertEqual(base, "https://config.example.com:7777")

    def test_default_used_when_no_sources(self):
        """Fallback to default when env and config are unavailable."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.exists", return_value=False):
                base = dashboard._get_ollama_api_base()
        self.assertEqual(base, dashboard.DEFAULT_OLLAMA_API_BASE)


class TestInstallFlows(unittest.TestCase):
    """Test installation flow behaviors."""

    def setUp(self):
        self.ui = DashboardApp().ui
        self.ui.installation_progress.package = "nginx"

    def test_run_dry_run_and_confirm_starts_thread(self):
        """Dry-run and confirm should spawn background execution."""
        finished = Event()

        def _mark_done():
            finished.set()

        with patch.object(self.ui, "_execute_dry_run", side_effect=_mark_done):
            self.ui._run_dry_run_and_confirm()
            self.assertTrue(finished.wait(timeout=1.0))

    def test_execute_dry_run_failure_sets_error(self):
        """Dry-run errors should surface in progress state."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "token"}, clear=True):
            with patch("cortex.cli.CortexCLI") as mock_cli:
                instance = mock_cli.return_value

                def raise_error(*_, **__):
                    raise RuntimeError("cli failure")

                instance.install.side_effect = raise_error
                self.ui._execute_dry_run()

        self.assertEqual(self.ui.installation_progress.state, InstallationState.FAILED)
        self.assertIn("failure", self.ui.installation_progress.error_message.lower())

    def test_execute_dry_run_bad_json_sets_parse_error(self):
        """Non-JSON output should yield parse failure message."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "token"}, clear=True):
            with patch("cortex.cli.CortexCLI") as mock_cli:
                instance = mock_cli.return_value

                def write_bad_json(*_, **__):
                    print("not-json")
                    return 0

                instance.install.side_effect = write_bad_json
                self.ui._execute_dry_run()

        self.assertEqual(self.ui.installation_progress.state, InstallationState.FAILED)
        self.assertEqual(
            self.ui.installation_progress.error_message, "Failed to parse installation plan"
        )

    def test_execute_confirmed_install_success(self):
        """Confirmed install should mark completion when sandbox commands succeed."""

        class FakeSandbox:
            def execute(self, cmd, stdin=None):
                return SimpleNamespace(success=True, stdout=f"ran {cmd}")

        # Set up pending commands as they would be stored from dry-run
        self.ui._pending_commands = ["echo hi"]

        with patch("cortex.sandbox.sandbox_executor.SandboxExecutor", FakeSandbox):
            self.ui._execute_confirmed_install()

        self.assertEqual(self.ui.installation_progress.state, InstallationState.COMPLETED)
        self.assertIn("nginx", self.ui.installation_progress.success_message)


class TestKeyboardInput(unittest.TestCase):
    """Test keyboard input handling including ANSI sequences."""

    def setUp(self):
        self.ui = DashboardApp().ui

    def test_simple_character(self):
        """Single character input should be returned directly."""
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = "q"

        with patch("cortex.dashboard.sys.stdin", mock_stdin):
            with patch("cortex.dashboard.select.select", return_value=([mock_stdin], [], [])):
                key = self.ui._check_keyboard_input()

        self.assertEqual(key, "q")

    def test_arrow_key_sequence(self):
        """CSI escape sequence should map to arrow token."""
        mock_stdin = MagicMock()
        mock_stdin.read.side_effect = ["\x1b", "[", "A"]

        with patch("cortex.dashboard.sys.stdin", mock_stdin):
            with patch(
                "cortex.dashboard.select.select",
                side_effect=[
                    ([mock_stdin], [], []),
                    ([mock_stdin], [], []),
                    ([mock_stdin], [], []),
                ],
            ):
                key = self.ui._check_keyboard_input()

        self.assertEqual(key, "<UP>")


if __name__ == "__main__":
    unittest.main()
