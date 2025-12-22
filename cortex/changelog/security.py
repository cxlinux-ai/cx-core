def has_security_fixes(parsed: dict) -> bool:
    return len(parsed.get("security", [])) > 0
