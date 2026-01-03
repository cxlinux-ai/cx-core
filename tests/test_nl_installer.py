import os

from cortex.llm.interpreter import CommandInterpreter


def test_nl_ml_install_generates_commands():
    os.environ[
        "CORTEX_FAKE_COMMANDS"
    ] = """
    {
        "commands": ["pip install torch"]
    }
    """

    interpreter = CommandInterpreter(api_key="fake", provider="fake")

    commands = interpreter.parse("something for machine learning")

    assert isinstance(commands, list)
    assert len(commands) > 0
    assert "pip install" in commands[0]
