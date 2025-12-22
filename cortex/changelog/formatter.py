def format_changelog(parsed: dict) -> str:
    lines = []
    header = f"{parsed['version']} ({parsed['date']})"
    lines.append(header)

    for sec in parsed["security"]:
        lines.append(f"   🔐 {sec}")

    for bug in parsed["bugs"]:
        lines.append(f"   🐛 {bug}")

    for feat in parsed["features"]:
        lines.append(f"   ✨ {feat}")

    return "\n".join(lines)
