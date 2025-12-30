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
        cache: Optional["SemanticCache"] = None,
    ):
        """Initialize the command interpreter.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
            cache: Optional SemanticCache instance for response caching
        """
        self.api_key = api_key
        self.provider = APIProvider(provider.lower())

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
                # Try to load model from config or environment
                self.model = self._get_ollama_model()
            elif self.provider == APIProvider.FAKE:
                self.model = "fake"  # Fake provider doesn't use a real model

        self._initialize_client()

    def _get_ollama_model(self) -> str:
        """Get Ollama model from config file or environment."""
        # Try environment variable first
        env_model = os.environ.get("OLLAMA_MODEL")
        if env_model:
            return env_model

        # Try config file
        try:
            from pathlib import Path

            config_file = Path.home() / ".cortex" / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)
                    model = config.get("ollama_model")
                    if model:
                        return model
        except Exception:
            pass  # Ignore errors reading config

        # Default to llama3.2
        return "llama3.2"

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
            # Ollama uses OpenAI-compatible API
            try:
                from openai import OpenAI

                ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
                self.client = OpenAI(
                    api_key="ollama",
                    base_url=f"{ollama_base_url}/v1",  # Dummy key, not used
                )
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == APIProvider.FAKE:
            # Fake provider uses predefined commands from environment
            self.client = None  # No client needed for fake provider

    def _get_system_prompt(self, simplified: bool = False) -> str:
        """Get system prompt for command interpretation.

        Args:
            simplified: If True, return a shorter prompt optimized for local models
        """
        if simplified:
            return """You must respond with ONLY a JSON object. No explanations, no markdown, no code blocks.

Format: {"commands": ["command1", "command2"]}

Example input: install nginx
Example output: {"commands": ["sudo apt update", "sudo apt install -y nginx"]}

Rules:
- Use apt for Ubuntu packages
- Add sudo for system commands
- Return ONLY the JSON object"""

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
        """Call local Ollama instance using OpenAI-compatible API."""
        try:
            # For local models, be extremely explicit in the user message
            enhanced_input = f"""{user_input}

Respond with ONLY this JSON format (no explanations):
{{\"commands\": [\"command1\", \"command2\"]}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt(simplified=True)},
                    {"role": "user", "content": enhanced_input},
                ],
                temperature=0.1,  # Lower temperature for more focused responses
                max_tokens=300,  # Reduced tokens for faster response
            )

            content = response.choices[0].message.content.strip()
            return self._parse_commands(content)
        except Exception as e:
            # Provide helpful error message
            ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            raise RuntimeError(
                f"Ollama API call failed. Is Ollama running? (ollama serve)\n"
                f"URL: {ollama_base_url}, Model: {self.model}\n"
                f"Error: {str(e)}"
            )

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

    def _repair_json(self, content: str) -> str:
        """Attempt to repair common JSON formatting issues."""
        # Remove extra whitespace between braces and brackets
        import re

        content = re.sub(r"\{\s+", "{", content)
        content = re.sub(r"\s+\}", "}", content)
        content = re.sub(r"\[\s+", "[", content)
        content = re.sub(r"\s+\]", "]", content)
        content = re.sub(r",\s*([}\]])", r"\1", content)  # Remove trailing commas
        return content.strip()

    def _parse_commands(self, content: str) -> list[str]:
        try:
            # Strip markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                parts = content.split("```")
                if len(parts) >= 3:
                    content = parts[1].strip()

            # Try to find JSON object in the content
            import re

            # Look for {"commands": [...]} pattern
            json_match = re.search(
                r'\{\s*["\']commands["\']\s*:\s*\[.*?\]\s*\}', content, re.DOTALL
            )
            if json_match:
                content = json_match.group(0)

            # Try to repair common JSON issues
            content = self._repair_json(content)

            data = json.loads(content)
            commands = data.get("commands", [])

            if not isinstance(commands, list):
                raise ValueError("Commands must be a list")

            # Handle both formats:
            # 1. ["cmd1", "cmd2"] - direct string array
            # 2. [{"command": "cmd1"}, {"command": "cmd2"}] - object array
            result = []
            for cmd in commands:
                if isinstance(cmd, str):
                    # Direct string
                    if cmd:
                        result.append(cmd)
                elif isinstance(cmd, dict):
                    # Object with "command" key
                    cmd_str = cmd.get("command", "")
                    if cmd_str:
                        result.append(cmd_str)

            return result
        except (json.JSONDecodeError, ValueError) as e:
            # Log the problematic content for debugging
            import sys

            print(f"\nDebug: Failed to parse JSON. Raw content:\n{content[:500]}", file=sys.stderr)
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
