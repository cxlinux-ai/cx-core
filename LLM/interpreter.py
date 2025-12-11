import os
import json
from typing import List, Optional, Dict, Any
from enum import Enum


class APIProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"


class CommandInterpreter:
    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: Optional[str] = None
    ):
        self.api_key = api_key
        self.provider = APIProvider(provider.lower())
        
        if model:
            self.model = model
        else:
            if self.provider == APIProvider.OPENAI:
                self.model = "gpt-4"
            elif self.provider == APIProvider.CLAUDE:
                self.model = "claude-sonnet-4-20250514"
            elif self.provider == APIProvider.OLLAMA:
                self.model = "llama3.2"  # Default Ollama model

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
            self.ollama_url = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
            self.client = None  # Will use requests
    
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
    
    def _call_openai(self, user_input: str) -> List[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}")
    
    def _call_claude(self, user_input: str) -> List[str]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=self._get_system_prompt(),
                messages=[
                    {"role": "user", "content": user_input}
                ]
            )

            content = response.content[0].text.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"Claude API call failed: {str(e)}")

    def _call_ollama(self, user_input: str) -> List[str]:
        """Call local Ollama instance for offline/local inference"""
        import urllib.request
        import urllib.error

        try:
            url = f"{self.ollama_url}/api/generate"
            prompt = f"{self._get_system_prompt()}\n\nUser request: {user_input}"

            data = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3
                }
            }).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result.get('response', '').strip()
                return self._parse_commands(content)

        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama not available at {self.ollama_url}: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Ollama API call failed: {str(e)}")
    
    def _parse_commands(self, content: str) -> List[str]:
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
    
    def _validate_commands(self, commands: List[str]) -> List[str]:
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
    
    def parse(self, user_input: str, validate: bool = True) -> List[str]:
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")
        
        if self.provider == APIProvider.OPENAI:
            commands = self._call_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            commands = self._call_claude(user_input)
        elif self.provider == APIProvider.OLLAMA:
            commands = self._call_ollama(user_input)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
        if validate:
            commands = self._validate_commands(commands)
        
        return commands
    
    def parse_with_context(
        self,
        user_input: str,
        system_info: Optional[Dict[str, Any]] = None,
        validate: bool = True
    ) -> List[str]:
        context = ""
        if system_info:
            context = f"\n\nSystem context: {json.dumps(system_info)}"
        
        enriched_input = user_input + context
        return self.parse(enriched_input, validate=validate)
