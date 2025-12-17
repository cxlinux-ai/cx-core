from cortex.shell_integration import suggest_command


def test_suggest_command_empty():
    assert suggest_command("") is None


def test_suggest_command_text():
    # We only check that it does not crash
    result = suggest_command("install docker")
    assert result is None or isinstance(result, str)
