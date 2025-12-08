import importlib.util
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def load_dashboard():
    """Load dashboard module"""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cortex", "dashboard.py")
    spec = importlib.util.spec_from_file_location("dashboard", path)
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load dashboard module")
    dashboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard)
    return dashboard


def test_system_monitor():
    """Test SystemMonitor"""
    print("[TEST] SystemMonitor")
    dashboard = load_dashboard()

    monitor = dashboard.SystemMonitor()
    monitor.update_metrics()
    metrics = monitor.get_metrics()

    assert metrics.cpu_percent >= 0, "CPU should be >= 0"
    assert metrics.ram_percent >= 0, "RAM should be >= 0"
    assert metrics.ram_used_gb > 0, "RAM used should be > 0"

    print(f" CPU: {metrics.cpu_percent:.1f}%")
    print(f" RAM: {metrics.ram_percent:.1f}% ({metrics.ram_used_gb:.1f}GB)")


def test_process_lister():
    """Test ProcessLister"""
    print("[TEST] ProcessLister")
    dashboard = load_dashboard()

    lister = dashboard.ProcessLister()
    lister.update_processes()
    processes = lister.get_processes()

    assert isinstance(processes, list), "Should return list"
    print(f" Found {len(processes)} processes")


def test_command_history():
    """Test CommandHistory"""
    print("[TEST] CommandHistory")
    dashboard = load_dashboard()

    history = dashboard.CommandHistory()
    cmds = history.get_history()

    assert isinstance(cmds, list), "Should return list"
    history.add_command("test")
    assert "test" in history.get_history(), "Should add command"
    print(f" History loaded with {len(cmds)} commands")


def test_ui_renderer():
    """Test UIRenderer"""
    print("[TEST] UIRenderer")
    dashboard = load_dashboard()

    monitor = dashboard.SystemMonitor()
    lister = dashboard.ProcessLister()
    history = dashboard.CommandHistory()

    ui = dashboard.UIRenderer(monitor, lister, history)

    monitor.update_metrics()
    lister.update_processes()

    # Test rendering
    header = ui._render_header()
    resources = ui._render_resources()
    processes = ui._render_processes()
    hist = ui._render_history()
    actions = ui._render_actions()
    footer = ui._render_footer()
    screen = ui._render_screen()

    assert all(
        [header, resources, processes, hist, actions, footer, screen]
    ), "All components should render"

    # Test new tab functionality
    assert hasattr(ui, "current_tab"), "UI should have current_tab"
    assert hasattr(ui, "installation_progress"), "UI should have installation_progress"
    assert hasattr(ui, "_render_progress_tab"), "UI should have progress tab renderer"

    print("✓ All components render")
    print("✓ Tab functionality working")
    print("✓ Installation progress tracking ready")


def test_dashboard_app():
    """Test DashboardApp"""
    print("[TEST] DashboardApp")
    dashboard = load_dashboard()

    app = dashboard.DashboardApp()

    assert app.monitor is not None, "Monitor should exist"
    assert app.lister is not None, "Lister should exist"
    assert app.history is not None, "History should exist"
    assert app.ui is not None, "UI should exist"

    print(" App initialized")


def main():
    """Run all tests"""
    print("=" * 60)
    print("CORTEX DASHBOARD TEST SUITE")
    print("=" * 60)
    print()

    tests = [
        test_system_monitor,
        test_process_lister,
        test_command_history,
        test_ui_renderer,
        test_dashboard_app,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
