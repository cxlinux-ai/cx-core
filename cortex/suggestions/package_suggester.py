from rapidfuzz import process

from cortex.branding import console, cx_print

# Temporary known package data (can be expanded later)
KNOWN_PACKAGES = [
    {
        "name": "apache2",
        "description": "Popular HTTP web server",
        "downloads": 50000000,
        "rating": 4.7,
        "tags": ["web server", "http", "apache"],
    },
    {
        "name": "nginx",
        "description": "High-performance event-driven web server",
        "downloads": 70000000,
        "rating": 4.9,
        "tags": ["web server", "reverse proxy"],
    },
    {
        "name": "docker",
        "description": "Container runtime",
        "downloads": 100000000,
        "rating": 4.8,
        "tags": ["containers", "devops"],
    },
]


def suggest_alternatives(query: str, limit: int = 3):
    names = [pkg["name"] for pkg in KNOWN_PACKAGES]
    matches = process.extract(query, names, limit=limit)

    results = []
    for name, score, _ in matches:
        pkg = next(p for p in KNOWN_PACKAGES if p["name"] == name)
        results.append(pkg)

    return results


def show_suggestions(packages):
    cx_print("💡 Did you mean:", "info")

    for i, pkg in enumerate(packages, 1):
        console.print(
            f"\n{i}. [bold]{pkg['name']}[/bold] (recommended)\n"
            f"   - {pkg['description']}\n"
            f"   - {pkg['downloads']:,} downloads\n"
            f"   - Rating: {pkg['rating']}/5"
        )
