"""Natural language query interface for Cortex.

Handles user questions about installed packages, configurations,
and system state using LLM with semantic caching. Also provides
educational content and tracks learning progress.
"""

import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortex.config_utils import get_ollama_model

# Module logger for debug diagnostics
logger = logging.getLogger(__name__)

# Maximum number of tokens to request from LLM
MAX_TOKENS = 2000


class SystemInfoGatherer:
    """Gathers local system information for context-aware responses."""

    @staticmethod
    def get_python_version() -> str:
        """Get installed Python version."""
        return platform.python_version()

    @staticmethod
    def get_python_path() -> str:
        """Get Python executable path."""
        import sys

        return sys.executable

    @staticmethod
    def get_os_info() -> dict[str, str]:
        """Get OS information."""
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        }

    @staticmethod
    def get_installed_package(package: str) -> str | None:
        """Check if a package is installed via apt and return version."""
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", package],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            # If dpkg-query is unavailable or fails, return None silently.
            # We avoid user-visible logs to keep CLI output clean.
            pass
        return None

    @staticmethod
    def get_pip_package(package: str) -> str | None:
        """Check if a Python package is installed via pip."""
        try:
            result = subprocess.run(
                ["pip3", "show", package],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            # If pip is unavailable or the command fails, return None silently.
            pass
        return None

    @staticmethod
    def check_command_exists(cmd: str) -> bool:
        """Check if a command exists in PATH."""
        return shutil.which(cmd) is not None

    @staticmethod
    def get_gpu_info() -> dict[str, Any]:
        """Get GPU information if available."""
        gpu_info: dict[str, Any] = {"available": False, "nvidia": False, "cuda": None}

        # Check for nvidia-smi
        if shutil.which("nvidia-smi"):
            gpu_info["nvidia"] = True
            gpu_info["available"] = True
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    gpu_info["model"] = result.stdout.strip().split(",")[0]
            except (subprocess.SubprocessError, FileNotFoundError):
                # If nvidia-smi is unavailable or fails, keep defaults.
                pass

            # Check CUDA version
            try:
                result = subprocess.run(
                    ["nvcc", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "release" in line.lower():
                            parts = line.split("release")
                            if len(parts) > 1:
                                gpu_info["cuda"] = parts[1].split(",")[0].strip()
            except (subprocess.SubprocessError, FileNotFoundError):
                # If nvcc is unavailable or fails, leave CUDA info unset.
                pass

        return gpu_info

    def gather_context(self) -> dict[str, Any]:
        """Gather relevant system context for LLM."""
        return {
            "python_version": self.get_python_version(),
            "python_path": self.get_python_path(),
            "os": self.get_os_info(),
            "gpu": self.get_gpu_info(),
        }


class LearningTracker:
    """Tracks educational topics the user has explored."""

    _progress_file: Path | None = None

    # Patterns that indicate educational questions
    EDUCATIONAL_PATTERNS = [
        r"^explain\b",
        r"^teach\s+me\b",
        r"^what\s+is\b",
        r"^what\s+are\b",
        r"^how\s+does\b",
        r"^how\s+do\b",
        r"^how\s+to\b",
        r"\bbest\s+practices?\b",
        r"^tutorial\b",
        r"^guide\s+to\b",
        r"^learn\s+about\b",
        r"^introduction\s+to\b",
        r"^basics\s+of\b",
    ]

    # Compiled patterns shared across all instances for efficiency
    _compiled_patterns: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE) for p in EDUCATIONAL_PATTERNS
    ]

    def __init__(self) -> None:
        """Initialize the learning tracker.

        Uses pre-compiled educational patterns for efficient matching
        across multiple queries. Patterns are shared as class variables
        to avoid recompilation overhead.
        """

    @property
    def progress_file(self) -> Path:
        """Lazily compute the progress file path to avoid import-time errors."""
        if self._progress_file is None:
            try:
                self._progress_file = Path.home() / ".cortex" / "learning_history.json"
            except RuntimeError:
                # Fallback for restricted environments where home is inaccessible
                import tempfile

                self._progress_file = (
                    Path(tempfile.gettempdir()) / ".cortex" / "learning_history.json"
                )
        return self._progress_file

    def is_educational_query(self, question: str) -> bool:
        """Determine if a question is educational in nature."""
        return any(pattern.search(question) for pattern in self._compiled_patterns)

    def extract_topic(self, question: str) -> str:
        """Extract the main topic from an educational question."""
        # Remove common prefixes
        topic = question.lower()
        prefixes_to_remove = [
            r"^explain\s+",
            r"^teach\s+me\s+about\s+",
            r"^teach\s+me\s+",
            r"^what\s+is\s+",
            r"^what\s+are\s+",
            r"^how\s+does\s+",
            r"^how\s+do\s+",
            r"^how\s+to\s+",
            r"^tutorial\s+on\s+",
            r"^guide\s+to\s+",
            r"^learn\s+about\s+",
            r"^introduction\s+to\s+",
            r"^basics\s+of\s+",
            r"^best\s+practices\s+for\s+",
        ]
        for prefix in prefixes_to_remove:
            topic = re.sub(prefix, "", topic, flags=re.IGNORECASE)

        # Clean up and truncate
        topic = topic.strip("? ").strip()

        # Truncate at word boundaries to keep topic identifier meaningful
        # If topic exceeds 50 chars, truncate at the last space within those 50 chars
        # to preserve whole words. If the first 50 chars contain no spaces,
        # keep the full 50-char prefix.
        if len(topic) > 50:
            truncated = topic[:50]
            # Try to split at word boundary; keep full 50 chars if no spaces found
            words = truncated.rsplit(" ", 1)
            # Handle case where topic starts with space after prefix removal
            topic = words[0] if words[0] else truncated

        return topic

    def record_topic(self, question: str) -> None:
        """Record that the user explored an educational topic.

        Note: This method performs a read-modify-write cycle on the history file
        without file locking. If multiple cortex ask processes run concurrently,
        concurrent updates could theoretically be lost. This is acceptable for a
        single-user CLI tool where concurrent invocations are rare and learning
        history is non-critical, but worth noting for future enhancements.
        """
        if not self.is_educational_query(question):
            return

        topic = self.extract_topic(question)
        if not topic:
            return

        history = self._load_history()
        if not isinstance(history, dict):
            history = {"topics": {}, "total_queries": 0}

        # Ensure history has expected structure (defensive defaults for malformed data)
        history.setdefault("topics", {})
        history.setdefault("total_queries", 0)
        if not isinstance(history.get("topics"), dict):
            history["topics"] = {}

        # Ensure total_queries is an integer
        if not isinstance(history.get("total_queries"), int):
            try:
                history["total_queries"] = int(history["total_queries"])
            except (ValueError, TypeError):
                history["total_queries"] = 0

        # Use UTC timestamps for consistency and accurate sorting
        utc_now = datetime.now(timezone.utc).isoformat()

        # Update or add topic
        if topic in history["topics"]:
            # Check if the topic data is actually a dict before accessing it
            if not isinstance(history["topics"][topic], dict):
                # If topic data is malformed, reinitialize it
                history["topics"][topic] = {
                    "count": 1,
                    "first_accessed": utc_now,
                    "last_accessed": utc_now,
                }
            else:
                try:
                    # Safely increment count, handle missing key
                    history["topics"][topic]["count"] = history["topics"][topic].get("count", 0) + 1
                    history["topics"][topic]["last_accessed"] = utc_now
                except (KeyError, TypeError, AttributeError):
                    # If topic data is malformed, reinitialize it
                    history["topics"][topic] = {
                        "count": 1,
                        "first_accessed": utc_now,
                        "last_accessed": utc_now,
                    }
        else:
            history["topics"][topic] = {
                "count": 1,
                "first_accessed": utc_now,
                "last_accessed": utc_now,
            }

        history["total_queries"] = history.get("total_queries", 0) + 1
        self._save_history(history)

    def get_history(self) -> dict[str, Any]:
        """Get the learning history."""
        return self._load_history()

    def get_recent_topics(self, limit: int = 5) -> list[str]:
        """Get recently explored topics."""
        history = self._load_history()
        topics = history.get("topics", {})

        # Filter out malformed entries and sort by last_accessed
        valid_topics = [
            (name, data)
            for name, data in topics.items()
            if isinstance(data, dict) and "last_accessed" in data
        ]
        sorted_topics = sorted(
            valid_topics,
            key=lambda x: x[1].get("last_accessed", ""),
            reverse=True,
        )
        return [t[0] for t in sorted_topics[:limit]]

    def _load_history(self) -> dict[str, Any]:
        """Load learning history from file."""
        if not self.progress_file.exists():
            return {"topics": {}, "total_queries": 0}

        try:
            with open(self.progress_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"topics": {}, "total_queries": 0}

    def _save_history(self, history: dict[str, Any]) -> None:
        """Save learning history to file.

        Silently handles save failures to keep CLI clean, but logs at debug level
        for diagnostics. Failures may occur due to permission issues or disk space.
        """
        try:
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except OSError as e:
            # Log at debug level to help diagnose permission/disk issues
            # without breaking CLI output or crashing the application
            logger.debug(
                f"Failed to save learning history to {self.progress_file}: {e}",
                exc_info=False,
            )


class AskHandler:
    """Handles natural language questions about the system."""

    def __init__(
        self,
        api_key: str,
        provider: str = "claude",
        model: str | None = None,
    ):
        """Initialize the ask handler.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
        """
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.info_gatherer = SystemInfoGatherer()
        self.learning_tracker = LearningTracker()

        # Initialize cache
        try:
            from cortex.semantic_cache import SemanticCache

            self.cache: SemanticCache | None = SemanticCache()
        except (ImportError, OSError):
            self.cache = None

        self._initialize_client()

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4"
        elif self.provider == "claude":
            return "claude-sonnet-4-20250514"
        elif self.provider == "ollama":
            return self._get_ollama_model()
        elif self.provider == "fake":
            return "fake"
        return "gpt-4"

    def _get_ollama_model(self) -> str:
        """Determine which Ollama model to use.

        Delegates to the shared ``get_ollama_model()`` utility function.
        """
        return get_ollama_model()

    def _initialize_client(self):
        if self.provider == "openai":
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == "claude":
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        elif self.provider == "ollama":
            self.ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.client = None
        elif self.provider == "fake":
            self.client = None
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _get_system_prompt(self, context: dict[str, Any]) -> str:
        return f"""You are a helpful Linux system assistant and tutor. You help users with both system-specific questions AND educational queries about Linux, packages, and best practices.

System Context:
{json.dumps(context, indent=2)}

**Query Type Detection**

Automatically detect the type of question and respond appropriately:

**Educational Questions (tutorials, explanations, learning)**

Triggered by questions like: "explain...", "teach me...", "how does X work", "what is...", "best practices for...", "tutorial on...", "learn about...", "guide to..."

For educational questions:
1. Provide structured, tutorial-style explanations
2. Include practical code examples with proper formatting
3. Highlight best practices and common pitfalls to avoid
4. Break complex topics into digestible sections
5. Use clear section labels and bullet points for readability
6. Mention related topics the user might want to explore next
7. Tailor examples to the user's system when relevant (e.g., use apt for Debian-based systems)

**Diagnostic Questions (system-specific, troubleshooting)**

Triggered by questions about: current system state, "why is my...", "what packages...", "check my...", specific errors, system status

For diagnostic questions:
1. Analyze the provided system context
2. Give specific, actionable answers
3. Be concise but informative
4. If you don't have enough information, say so clearly

**Output Formatting Rules (CRITICAL - Follow exactly)**

1. NEVER use markdown headings (# or ##) - they render poorly in terminals
2. For section titles, use **Bold Text** on its own line instead
3. Use bullet points (-) for lists
4. Use numbered lists (1. 2. 3.) for sequential steps
5. Use triple backticks with language name for code blocks (```bash)
6. Use *italic* sparingly for emphasis
7. Keep lines under 100 characters when possible
8. Add blank lines between sections for readability
9. For tables, use simple text formatting, not markdown tables

Example of good formatting:
**Installation Steps**

1. Update your package list:
```bash
sudo apt update
```

2. Install the package:
```bash
sudo apt install nginx
```

**Key Points**
- Point one here
- Point two here"""

    def _call_openai(self, question: str, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )
        # Defensive: content may be None or choices could be empty in edge cases
        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError):
            content = ""
        return content.strip()

    def _call_claude(self, question: str, system_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
        # Defensive: content list or text may be missing/None
        try:
            text = getattr(response.content[0], "text", None) or ""
        except (IndexError, AttributeError):
            text = ""
        return text.strip()

    def _call_ollama(self, question: str, system_prompt: str) -> str:
        import urllib.error
        import urllib.request

        url = f"{self.ollama_url}/api/generate"
        prompt = f"{system_prompt}\n\nQuestion: {question}"

        data = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": MAX_TOKENS},
            }
        ).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "").strip()

    def _call_fake(self, question: str, system_prompt: str) -> str:
        """Return predefined fake response for testing."""
        fake_response = os.environ.get("CORTEX_FAKE_RESPONSE", "")
        if fake_response:
            return fake_response
        # Default fake responses for common questions
        q_lower = question.lower()
        if "python" in q_lower and "version" in q_lower:
            return f"You have Python {platform.python_version()} installed."
        return "I cannot answer that question in test mode."

    def ask(self, question: str, system_prompt: str | None = None) -> str:
        """Ask a natural language question about the system.

        Args:
            question: Natural language question
            system_prompt: Optional override for the system prompt

        Returns:
            Human-readable answer string

        Raises:
            ValueError: If question is empty
            RuntimeError: If offline and no cached response exists
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        question = question.strip()

        # Use provided system prompt or generate default
        if system_prompt is None:
            context = self.info_gatherer.gather_context()
            system_prompt = self._get_system_prompt(context)

        # Cache lookup uses both question and system context (via system_prompt) for system-specific answers
        cache_key = f"ask:{question}"

        # Try cache first
        if self.cache is not None:
            cached = self.cache.get_commands(
                prompt=cache_key,
                provider=self.provider,
                model=self.model,
                system_prompt=system_prompt,
            )
            if cached is not None and len(cached) > 0:
                # Track topic access even for cached responses
                self.learning_tracker.record_topic(question)
                return cached[0]

        # Call LLM
        try:
            if self.provider == "openai":
                answer = self._call_openai(question, system_prompt)
            elif self.provider == "claude":
                answer = self._call_claude(question, system_prompt)
            elif self.provider == "ollama":
                answer = self._call_ollama(question, system_prompt)
            elif self.provider == "fake":
                answer = self._call_fake(question, system_prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {str(e)}")

        # Cache the response silently
        if self.cache is not None and answer:
            try:
                self.cache.put_commands(
                    prompt=cache_key,
                    provider=self.provider,
                    model=self.model,
                    system_prompt=system_prompt,
                    commands=[answer],
                )
            except (OSError, sqlite3.Error):
                pass  # Silently fail cache writes

        # Track educational topics for learning history
        self.learning_tracker.record_topic(question)

        return answer

    def get_learning_history(self) -> dict[str, Any]:
        """Get the user's learning history.

        Returns:
            Dictionary with topics explored and statistics
        """
        return self.learning_tracker.get_history()

    def get_recent_topics(self, limit: int = 5) -> list[str]:
        """Get recently explored educational topics.

        Args:
            limit: Maximum number of topics to return

        Returns:
            List of topic strings
        """
        return self.learning_tracker.get_recent_topics(limit)
