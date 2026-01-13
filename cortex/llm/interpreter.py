import json
import os
import sqlite3
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from cortex.config_utils import get_ollama_model

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
        # ✅ Defensive Ollama base URL initialization
        if self.provider == APIProvider.OLLAMA:
            self.ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

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
        """Get Ollama model from config file or environment.

        Delegates to the shared ``get_ollama_model()`` utility function.
        """
        return get_ollama_model()

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

    def _get_system_prompt(
        self, simplified: bool = False, domain: str | None = None, install_mode: str | None = None
    ) -> str:
        """Get system prompt for command interpretation.

        Args:
            simplified: If True, return a shorter prompt optimized for local models
            domain: Optional domain context to guide command generation
            install_mode: Type of installation ('system', 'python', 'mixed')
        """
        domain_context = ""
        if domain and domain != "unknown":
            domain_context = (
                f"\n\nDomain: {domain}\n"
                f"Generate commands specific to this domain only. "
                f"Avoid installing unrelated packages."
            )

        # Add install mode constraint
        install_mode_constraint = ""
        if install_mode == "python":
            install_mode_constraint = "\n⚠️ CONSTRAINT: This is a Python package installation. ALWAYS use 'pip install' or 'pip3 install'. NEVER use 'apt install'."
        elif install_mode == "mixed":
            install_mode_constraint = "\n⚠️ CONSTRAINT: Use 'pip install' for Python packages and 'apt install' for system-level tools only."

        common_rules = """
    Execution environment:
    - Target OS: Linux (Ubuntu/Debian family)
    - Commands will be executed by a non-interactive POSIX-compatible shell

    Rules:
    - Respond with ONLY valid JSON
    - The response MUST be a JSON array wrapped in an object under the "commands" key
    - No explanations, no markdown, no code blocks
    - Commands must be POSIX-compliant (portable across Linux shells)
    - Do NOT assume interactive shells
    - Avoid shell-specific features that are not POSIX-compliant
    - Commands should be safe, atomic, and sequential
    - Avoid destructive operations unless explicitly requested
    - Use apt for system packages on Debian/Ubuntu
    - Add sudo only for system-level commands
    ⚠️ CRITICAL RULE - PYTHON PACKAGES MUST USE PIP:
    - When the request involves Python libraries, packages, or tools (e.g., numpy, pandas,
    Flask, Django, TensorFlow, or anything installed via PyPI): use "pip install" or "pip3 install"
    - NEVER use "apt install python3-*" for any Python package or library
    - Use apt ONLY for system-level tools (like git, curl, build-essential, etc.)
    - If unsure whether something is a Python package: use pip
    """

        if simplified:
            return f"""{common_rules}

    Format:
    {{"commands": ["command1", "command2"]}}

    Example input: install nginx
    Example output:
    {{"commands": ["sudo apt update", "sudo apt install -y nginx"]}}
    {domain_context}{install_mode_constraint}
    """

        return f"""You are a Linux system command expert.
    Convert natural language requests into safe, executable bash commands.

    {common_rules}

    Additional guidance:
    - If virtual environments are needed, prefer invoking tools directly
    (e.g., venv/bin/pip install ...) instead of relying on shell activation.
    - Validate command syntax before returning.

    Format:
    {{"commands": ["command1", "command2", ...]}}

    Example request:
    "install docker with nvidia support"

    Example response:
    {{"commands": [
    "sudo apt update",
    "sudo apt install -y docker.io",
    "sudo apt install -y nvidia-docker2",
    "sudo systemctl restart docker"
    ]}}
    {domain_context}{install_mode_constraint}
    """

    def _extract_intent_ollama(self, user_input: str) -> dict:
        import urllib.error
        import urllib.request

        prompt = f"""
    {self._get_intent_prompt()}

    User request:
    {user_input}
    """

        data = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 300,
                },  # num_predict is max_tokens equivalent for Ollama
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
                text = raw.get("response", "")
                return self._parse_intent_from_text(text)

        except Exception:
            # True failure → unknown intent
            return {
                "action": "unknown",
                "domain": "unknown",
                "description": "Failed to extract intent",
                "ambiguous": True,
                "confidence": 0.0,
                "install_mode": "system",
            }

    def _get_intent_prompt(self) -> str:
        return """You are an intent extraction engine for a Linux package manager.

Extract the user's intent as JSON. Score confidence based on whether the domain (not specific package names) can be identified.

Key principle: If the domain is identifiable, confidence should be >= 0.5 even if specific details are vague.

Confidence scoring:
- HIGH (0.8-1.0): Domain is clearly mentioned or obvious from context
- MEDIUM (0.5-0.8): Domain is recognizable but specifics are vague or need clarification
- LOW (0.0-0.5): Domain cannot be identified or request is completely unclear

Rules:
- Do NOT suggest commands or list packages
- Focus on domain identification, not package specificity
- If a domain keyword appears, confidence should be at least 0.6+
- Set ambiguous=true if specifics need clarification but domain is recognized
- Respond ONLY in valid JSON

Install mode: system (apt/system packages), python (pip/virtualenv), mixed (both)

Response format (JSON only):
{
  "action": "install",
  "domain": "...",
  "install_mode": "...",
  "description": "brief explanation",
  "ambiguous": true/false,
  "confidence": 0.0
}
"""

    def _call_openai(
        self, user_input: str, domain: str | None = None, install_mode: str | None = None
    ) -> list[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(
                            domain=domain, install_mode=install_mode
                        ),
                    },
                    {"role": "user", "content": user_input},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            if not response.choices:
                raise RuntimeError("OpenAI returned empty response")
            content = (response.choices[0].message.content or "").strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}")

    def _extract_intent_openai(self, user_input: str) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_intent_prompt()},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.2,
                max_tokens=300,
            )

            if not response.choices:
                raise RuntimeError("OpenAI returned empty response")
            content = (response.choices[0].message.content or "").strip()
            return self._parse_intent_from_text(content)
        except Exception as e:
            return {
                "action": "unknown",
                "domain": "unknown",
                "description": f"Failed to extract intent: {str(e)}",
                "ambiguous": True,
                "confidence": 0.0,
                "install_mode": "system",
            }

    def _parse_intent_from_text(self, text: str) -> dict:
        """
        Extract intent JSON from loose LLM output.
        No semantic assumptions.
        """
        # Try to locate JSON block
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(text[start : end + 1])

                # Minimal validation (structure only)
                for key in ["action", "domain", "install_mode", "ambiguous", "confidence"]:
                    if key not in parsed:
                        raise ValueError("Missing intent field")

                # Ensure description has a default if missing
                if "description" not in parsed:
                    parsed["description"] = ""

                return parsed
        except Exception:
            pass

        # If parsing fails, do NOT guess meaning
        return {
            "action": "unknown",
            "domain": "unknown",
            "description": "Unstructured intent output",
            "ambiguous": True,
            "confidence": 0.0,
            "install_mode": "system",
        }

    def _call_claude(
        self, user_input: str, domain: str | None = None, install_mode: str | None = None
    ) -> list[str]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=self._get_system_prompt(domain=domain, install_mode=install_mode),
                messages=[{"role": "user", "content": user_input}],
            )

            if not response.content:
                raise RuntimeError("Claude returned empty response")
            content = (response.content[0].text or "").strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"Claude API call failed: {str(e)}")

    def _call_ollama(
        self, user_input: str, domain: str | None = None, install_mode: str | None = None
    ) -> list[str]:
        """Call local Ollama instance using OpenAI-compatible API."""
        try:
            # For local models, be extremely explicit in the user message
            enhanced_input = f"""{user_input}

Respond with ONLY this JSON format (no explanations):
{{\"commands\": [\"command1\", \"command2\"]}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(
                            simplified=True, domain=domain, install_mode=install_mode
                        ),
                    },
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
        """
        Robust command parser.
        Handles strict JSON (OpenAI/Claude) and loose output (Ollama).
        """
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

            # Attempt to isolate JSON
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                json_blob = content[start : end + 1]
            else:
                # No braces found - content is not valid JSON
                raise ValueError("No JSON object found in response")

            # First attempt: strict JSON
            data = json.loads(json_blob)
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
                    if cmd.strip():
                        result.append(cmd.strip())
                elif isinstance(cmd, dict):
                    # Object with "command" key
                    cmd_str = cmd.get("command", "")
                    if cmd_str and isinstance(cmd_str, str) and cmd_str.strip():
                        result.append(cmd_str.strip())

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

    def parse(self, user_input: str, validate: bool = True, domain: str | None = None) -> list[str]:
        """Parse natural language input into shell commands.

        Args:
            user_input: Natural language description of desired action
            validate: If True, validate commands for dangerous patterns
            domain: Optional domain context (e.g., 'database', 'web_server') to guide command generation

        Returns:
            List of shell commands to execute

        Raises:
            ValueError: If input is empty
            RuntimeError: If offline mode is enabled and no cached response exists
        """
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        # Extract intent first to determine install_mode constraint
        try:
            intent = self.extract_intent(user_input)
            install_mode = intent.get("install_mode", "system")
            if not domain:
                domain = intent.get("domain", "unknown")
                if domain == "unknown":
                    domain = None
        except Exception:
            install_mode = "system"

        cache_system_prompt = (
            self._get_system_prompt(domain=domain, install_mode=install_mode)
            + f"\n\n[cortex-cache-validate={bool(validate)}]"
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
            commands = self._call_openai(user_input, domain=domain, install_mode=install_mode)
        elif self.provider == APIProvider.CLAUDE:
            commands = self._call_claude(user_input, domain=domain, install_mode=install_mode)
        elif self.provider == APIProvider.OLLAMA:
            commands = self._call_ollama(user_input, domain=domain, install_mode=install_mode)
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

    def _extract_intent_claude(self, user_input: str) -> dict:
        """Extract intent from user input using Claude API.

        Args:
            user_input: Natural language description of desired action

        Returns:
            Dict with keys: action, domain, install_mode, description, ambiguous, confidence
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=0.2,
                system=self._get_intent_prompt(),
                messages=[{"role": "user", "content": user_input}],
            )

            if not response.content:
                raise RuntimeError("Claude returned empty response")
            content = (response.content[0].text or "").strip()
            return self._parse_intent_from_text(content)
        except Exception as e:
            return {
                "action": "unknown",
                "domain": "unknown",
                "description": f"Failed to extract intent: {str(e)}",
                "ambiguous": True,
                "confidence": 0.0,
                "install_mode": "system",
            }

    def extract_intent(self, user_input: str) -> dict:
        """Extract intent from natural language input.

        Analyzes the user's request to determine:
        - action: Type of operation (install, remove, etc.)
        - domain: Category of request (machine learning, web development, etc.)
        - install_mode: Installation type (system, python, or mixed)
        - confidence: Confidence level (0.0-1.0)
        - ambiguous: Whether clarification is needed

        Args:
            user_input: Natural language description of desired action

        Returns:
            Dict with keys: action, domain, install_mode, description, ambiguous, confidence

        Raises:
            ValueError: If input is empty
        """
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        if self.provider == APIProvider.OPENAI:
            return self._extract_intent_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            return self._extract_intent_claude(user_input)
        elif self.provider == APIProvider.OLLAMA:
            return self._extract_intent_ollama(user_input)
        elif self.provider == APIProvider.FAKE:
            # Check for configurable fake intent from environment
            fake_intent_env = os.environ.get("CORTEX_FAKE_INTENT")
            if fake_intent_env:
                try:
                    return json.loads(fake_intent_env)
                except json.JSONDecodeError:
                    pass  # Fall back to default

            # Return realistic intent for testing (not ambiguous)
            return {
                "action": "install",
                "domain": "general",
                "install_mode": "system",
                "description": user_input,
                "ambiguous": False,
                "confidence": 0.8,
            }
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
