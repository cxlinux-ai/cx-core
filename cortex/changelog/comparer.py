def compare_versions(old: dict, new: dict) -> str:
    lines = []
    lines.append(f"What's new in {new['version']}:")

    if new["security"]:
        lines.append(f"- {len(new['security'])} security fix(es)")
    if new["bugs"]:
        lines.append(f"- {len(new['bugs'])} bug fix(es)")
    if new["features"]:
        lines.append(f"- {len(new['features'])} new feature(s)")

    return "\n".join(lines)
