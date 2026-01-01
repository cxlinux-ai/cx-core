

def fetch_changelog(package: str) -> list[dict]:
    if package.lower() == "docker":
        return [
            {
                "version": "24.0.7",
                "date": "2023-11-15",
                "changes": [
                    "Security: CVE-2023-12345 fixed",
                    "Bug fixes: Container restart issues",
                    "New: BuildKit 0.12 support",
                ],
            },
            {
                "version": "24.0.6",
                "date": "2023-10-20",
                "changes": [
                    "Bug fixes: Network reliability improvements",
                ],
            },
        ]
    return []
