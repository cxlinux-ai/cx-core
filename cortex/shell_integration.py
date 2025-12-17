"""
Shell integration helpers for Cortex.

This module is used by Bash/Zsh hotkey bindings to convert
natural language input into a suggested shell command.
"""


def suggest_command(user_input: str) -> str | None:
    """
    Generate a shell command suggestion from free-form user input.

    Args:
        user_input (str): Text currently typed in the shell.

    Returns:a
        Optional[str]: Suggested shell command or None if no suggestion.
    """
    user_input = user_input.strip()
    if not user_input:
        return None

    # Import here to keep shell integration lightweight
    try:
        from cortex.interpreter import interpret
    except Exception:
        return None

    try:
        result = interpret(user_input)
    except Exception:
        return None

    if not result:
        return None

    # Expected result structure:
    # {
    #   "command": "sudo apt install docker",
    #   ...
    # }
    command = result.get("command")
    if not isinstance(command, str):
        return None

    return command.strip()
