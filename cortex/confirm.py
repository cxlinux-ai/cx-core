def confirm_action(message: str) -> bool:
    try:
        response = input(f"{message} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}
