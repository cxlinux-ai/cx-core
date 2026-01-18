"""Natural language query interface for Cortex.

Handles user questions about installed packages, configurations,
and system state using LLM with semantic caching.
"""

import json
import os
import platform
import shutil
import sqlite3
import subprocess
from typing import Any

from cortex.config_utils import get_ollama_model


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
        return f"""You are a helpful Linux system assistant. Answer questions about the user's system clearly and concisely.

System Context:
{json.dumps(context, indent=2)}

Rules:
1. Provide direct, human-readable answers
2. Use the system context to give accurate information
3. Be concise but informative
4. If you don't have enough information, say so clearly
5. For package compatibility questions, consider the system's Python version and OS
6. Return ONLY the answer text, no JSON or markdown formatting"""

    def _call_openai(self, question: str, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=500,
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
            max_tokens=500,
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
                "options": {"temperature": 0.3},
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

        return answer
