import json

def export_changelog(data: dict, filename: str):
    if filename.endswith(".json"):
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
    else:
        with open(filename, "w") as f:
            f.write(str(data))
