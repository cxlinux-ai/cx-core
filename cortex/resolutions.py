"""
Resolution Manager for Cortex Troubleshooter.

This module handles the storage and retrieval of successful troubleshooting resolutions.
It uses a simple JSON file for storage and keyword matching for retrieval.
"""

import fcntl
import json
import os
import time
from pathlib import Path
from typing import TypedDict

MAX_RESOLUTIONS = 50
DEFAULT_SEARCH_LIMIT = 3


class Resolution(TypedDict):
    issue: str
    fix: str
    timestamp: float


class ResolutionManager:
    def __init__(self, storage_path: str = "~/.cortex/resolutions.json"):
        self.storage_path = Path(os.path.expanduser(storage_path))
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure the storage file exists."""
        if not self.storage_path.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump([], f)

    def save(self, issue: str, fix: str) -> None:
        """Save a new resolution."""

        resolution: Resolution = {
            "issue": issue,
            "fix": fix,
            "timestamp": time.time(),
        }

        # Use r+ to allow reading and writing with a lock
        with open(self.storage_path, "r+") as f:
            # Acquire an exclusive lock to prevent race conditions
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                try:
                    resolutions = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError):
                    resolutions = []

                resolutions.append(resolution)

                # Keep only the last N resolutions to prevent unlimited growth
                if len(resolutions) > MAX_RESOLUTIONS:
                    resolutions = resolutions[-MAX_RESOLUTIONS:]

                # Rewind to the beginning of the file to overwrite
                f.seek(0)
                f.truncate()
                json.dump(resolutions, f, indent=2)
            finally:
                # Always release the lock
                fcntl.flock(f, fcntl.LOCK_UN)

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Resolution]:
        """
        Search for resolutions relevant to the query.

        Uses simple keyword matching: finds resolutions where the issue description
        shares words with the query.
        """
        try:
            with open(self.storage_path) as f:
                resolutions: list[Resolution] = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        if not resolutions:
            return []

        query_words = set(query.lower().split())
        scored_resolutions = []

        for res in resolutions:
            if "issue" not in res or "fix" not in res:
                continue
            issue_words = set(res["issue"].lower().split())
            # Calculate overlap score
            score = len(query_words.intersection(issue_words))
            if score > 0:
                scored_resolutions.append((score, res))

        # Sort by score (descending) and take top N
        scored_resolutions.sort(key=lambda x: x[0], reverse=True)
        return [res for _, res in scored_resolutions[:limit]]
