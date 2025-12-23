import json
import os
import sqlite3
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from cortex.semantic_cache import SemanticCache


class APIProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    FAKE = "fake"


class CommandInterpreter:
    """Interprets natural language commands into executable shell commands using LLM APIs.

    Supports multiple providers (OpenAI, Claude, Ollama) with optional semantic caching
    and offline mode for cached responses.
    """

    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: str | None = None,
        offline: bool = False,
        cache: Optional["SemanticCache"] = None,
    ):
        """Initialize the command interpreter.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
            offline: If True, only use cached responses
            cache: Optional SemanticCache instance for response caching
        """
        self.api_key = api_key
        self.provider = APIProvider(provider.lower())
        self.offline = offline

        if cache is None:
            try:
                from cortex.semantic_cache import SemanticCache

                self.cache: SemanticCache | None = SemanticCache()
            except (ImportError, OSError):
                # Cache initialization can fail due to missing dependencies or permissions
                self.cache = None
        else:
            self.cache = cache

        if model:
            self.model = model
        else:
            if self.provider == APIProvider.OPENAI:
                self.model = "gpt-4"
            elif self.provider == APIProvider.CLAUDE:
                self.model = "claude-sonnet-4-20250514"
            elif self.provider == APIProvider.OLLAMA:
                self.model = "llama3.2"  # Default Ollama model
            elif self.provider == APIProvider.FAKE:
                self.model = "fake"  # Fake provider doesn't use a real model

        self._initialize_client()

    def _initialize_client(self):
        if self.provider == APIProvider.OPENAI:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == APIProvider.CLAUDE:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        elif self.provider == APIProvider.OLLAMA:
            # Ollama uses local HTTP API, no special client needed
            self.ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.client = None  # Will use requests
        elif self.provider == APIProvider.FAKE:
            # Fake provider uses predefined commands from environment
            self.client = None  # No client needed for fake provider

    def _get_system_prompt(self) -> str:
        return """You are a Linux system command expert. Convert natural language requests into safe, validated bash commands.

Rules:
1. Return ONLY a JSON array of commands
2. Each command must be a safe, executable bash command
3. Commands should be atomic and sequential
4. Avoid destructive operations without explicit user confirmation
5. Use package managers appropriate for Debian/Ubuntu systems (apt)
6. Include necessary privilege escalation (sudo) when required
7. Validate command syntax before returning

Format:
{"commands": ["command1", "command2", ...]}

Example request: "install docker with nvidia support"
Example response: {"commands": ["sudo apt update", "sudo apt install -y docker.io", "sudo apt install -y nvidia-docker2", "sudo systemctl restart docker"]}"""

    def _call_openai(self, user_input: str) -> list[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            content = response.choices[0].message.content.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}")

    def _call_claude(self, user_input: str) -> list[str]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": user_input}],
            )

            content = response.content[0].text.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"Claude API call failed: {str(e)}")

    def _call_ollama(self, user_input: str) -> list[str]:
        """Call local Ollama instance for offline/local inference"""
        import urllib.error
        import urllib.request

        try:
            url = f"{self.ollama_url}/api/generate"
            prompt = f"{self._get_system_prompt()}\n\nUser request: {user_input}"

            data = json.dumps(
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result.get("response", "").strip()
                return self._parse_commands(content)

        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama not available at {self.ollama_url}: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Ollama API call failed: {str(e)}")

    def _call_fake(self, user_input: str) -> list[str]:
        """Return predefined fake commands from environment for testing."""
        fake_commands_env = os.environ.get("CORTEX_FAKE_COMMANDS")
        if not fake_commands_env:
            raise RuntimeError("CORTEX_FAKE_COMMANDS environment variable not set")

        try:
            data = json.loads(fake_commands_env)
            commands = data.get("commands", [])
            if not isinstance(commands, list):
                raise ValueError("Commands must be a list in CORTEX_FAKE_COMMANDS")
            return [cmd for cmd in commands if cmd and isinstance(cmd, str)]
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse CORTEX_FAKE_COMMANDS: {str(e)}")

    def _parse_commands(self, content: str) -> list[str]:
        try:
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            commands = data.get("commands", [])

            if not isinstance(commands, list):
                raise ValueError("Commands must be a list")

            return [cmd for cmd in commands if cmd and isinstance(cmd, str)]
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse LLM response: {str(e)}")

    def _validate_commands(self, commands: list[str]) -> list[str]:
        dangerous_patterns = [
            "rm -rf /",
            "dd if=",
            "mkfs.",
            "> /dev/sda",
            "fork bomb",
            ":(){ :|:& };:",
        ]

        validated = []
        for cmd in commands:
            cmd_lower = cmd.lower()
            if any(pattern in cmd_lower for pattern in dangerous_patterns):
                continue
            validated.append(cmd)

        return validated

    def parse(self, user_input: str, validate: bool = True) -> list[str]:
        """Parse natural language input into shell commands.

        Args:
            user_input: Natural language description of desired action
            validate: If True, validate commands for dangerous patterns

        Returns:
            List of shell commands to execute

        Raises:
            ValueError: If input is empty
            RuntimeError: If offline mode is enabled and no cached response exists
        """
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        cache_system_prompt = (
            self._get_system_prompt() + f"\n\n[cortex-cache-validate={bool(validate)}]"
        )

        if self.cache is not None:
            cached = self.cache.get_commands(
                prompt=user_input,
                provider=self.provider.value,
                model=self.model,
                system_prompt=cache_system_prompt,
            )
            if cached is not None:
                return cached

        if self.offline:
            raise RuntimeError("Offline mode: no cached response available for this request")

        if self.provider == APIProvider.OPENAI:
            commands = self._call_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            commands = self._call_claude(user_input)
        elif self.provider == APIProvider.OLLAMA:
            commands = self._call_ollama(user_input)
        elif self.provider == APIProvider.FAKE:
            commands = self._call_fake(user_input)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if validate:
            commands = self._validate_commands(commands)

        if self.cache is not None and commands:
            try:
                self.cache.put_commands(
                    prompt=user_input,
                    provider=self.provider.value,
                    model=self.model,
                    system_prompt=cache_system_prompt,
                    commands=commands,
                )
            except (OSError, sqlite3.Error):
                # Silently fail cache writes - not critical for operation
                pass

        return commands

    def parse_with_context(
        self, user_input: str, system_info: dict[str, Any] | None = None, validate: bool = True
    ) -> list[str]:
        context = ""
        if system_info:
            context = f"\n\nSystem context: {json.dumps(system_info)}"

        enriched_input = user_input + context
        return self.parse(enriched_input, validate=validate)
