import subprocess
from pathlib import Path

class GitManager:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)

    def init_repo(self):
        if (self.config_path / ".git").exists():
            return False

        subprocess.run(
            ["git", "init"],
            cwd=self.config_path,
            check=True
        )
        return True
    def commit_all(self, message: str) -> bool:
        subprocess.run(
            ["git", "add", "."],
            cwd=self.config_path,
            check=True
        )

        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.config_path,
            capture_output=True,
            text=True,
            check=False
        )

        if "nothing to commit" in result.stdout.lower():
            return False

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())

        return True
    def history(self) -> str:
        result = subprocess.run(
            ["git", "log", "--oneline", "--relative-date"],
            cwd=self.config_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            # No commits yet
            return ""

        return result.stdout.strip()

