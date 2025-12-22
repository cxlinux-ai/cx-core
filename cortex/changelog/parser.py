from typing import Dict, List

def parse_changelog(entry: Dict) -> Dict:
    security = []
    bugs = []
    features = []

    for change in entry["changes"]:
        lower = change.lower()
        if "cve" in lower or "security" in lower:
            security.append(change)
        elif "bug" in lower or "fix" in lower:
            bugs.append(change)
        else:
            features.append(change)

    return {
        "version": entry["version"],
        "date": entry["date"],
        "security": security,
        "bugs": bugs,
        "features": features,
    }
