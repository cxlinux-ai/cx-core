"""
System Information Command Generator for Cortex.

Generates read-only commands using LLM to retrieve system and application information.
All commands are validated against the CommandValidator to ensure they only read the system.

Usage:
    generator = SystemInfoGenerator(api_key="...", provider="claude")

    # Simple info queries
    result = generator.get_info("What version of Python is installed?")

    # Application-specific queries
    result = generator.get_app_info("nginx", "What's the current nginx configuration?")

    # Structured info retrieval
    info = generator.get_structured_info("hardware", ["cpu", "memory", "disk"])
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cortex.ask import CommandValidator

console = Console()


class InfoCategory(str, Enum):
    """Categories of system information."""

    HARDWARE = "hardware"
    SOFTWARE = "software"
    NETWORK = "network"
    SECURITY = "security"
    SERVICES = "services"
    PACKAGES = "packages"
    PROCESSES = "processes"
    STORAGE = "storage"
    PERFORMANCE = "performance"
    CONFIGURATION = "configuration"
    LOGS = "logs"
    USERS = "users"
    APPLICATION = "application"
    CUSTOM = "custom"


@dataclass
class InfoCommand:
    """A single read-only command for gathering information."""

    command: str
    purpose: str
    category: InfoCategory = InfoCategory.CUSTOM
    timeout: int = 30


@dataclass
class InfoResult:
    """Result of executing an info command."""

    command: str
    success: bool
    output: str
    error: str = ""
    execution_time: float = 0.0


@dataclass
class SystemInfoResult:
    """Complete result of a system info query."""

    query: str
    answer: str
    commands_executed: list[InfoResult] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    category: InfoCategory = InfoCategory.CUSTOM


# Common info command templates for quick lookups
# Note: Commands are simplified to avoid || patterns which are blocked by CommandValidator
COMMON_INFO_COMMANDS: dict[str, list[InfoCommand]] = {
    # Hardware Information
    "cpu": [
        InfoCommand("lscpu", "Get CPU architecture and details", InfoCategory.HARDWARE),
        InfoCommand("head -30 /proc/cpuinfo", "Get CPU model and cores", InfoCategory.HARDWARE),
        InfoCommand("nproc", "Get number of processing units", InfoCategory.HARDWARE),
    ],
    "memory": [
        InfoCommand("free -h", "Get memory usage in human-readable format", InfoCategory.HARDWARE),
        InfoCommand(
            "head -20 /proc/meminfo", "Get detailed memory information", InfoCategory.HARDWARE
        ),
    ],
    "disk": [
        InfoCommand("df -h", "Get disk space usage", InfoCategory.STORAGE),
        InfoCommand("lsblk", "List block devices", InfoCategory.STORAGE),
    ],
    "gpu": [
        InfoCommand(
            "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
            "Get NVIDIA GPU info",
            InfoCategory.HARDWARE,
        ),
        InfoCommand("lspci", "List PCI devices including VGA", InfoCategory.HARDWARE),
    ],
    # OS Information
    "os": [
        InfoCommand("cat /etc/os-release", "Get OS release information", InfoCategory.SOFTWARE),
        InfoCommand("uname -a", "Get kernel and system info", InfoCategory.SOFTWARE),
        InfoCommand("lsb_release -a", "Get LSB release info", InfoCategory.SOFTWARE),
    ],
    "kernel": [
        InfoCommand("uname -r", "Get kernel version", InfoCategory.SOFTWARE),
        InfoCommand("cat /proc/version", "Get detailed kernel version", InfoCategory.SOFTWARE),
    ],
    # Network Information
    "network": [
        InfoCommand("ip addr show", "List network interfaces", InfoCategory.NETWORK),
        InfoCommand("ip route show", "Show routing table", InfoCategory.NETWORK),
        InfoCommand("ss -tuln", "List listening ports", InfoCategory.NETWORK),
    ],
    "dns": [
        InfoCommand("cat /etc/resolv.conf", "Get DNS configuration", InfoCategory.NETWORK),
        InfoCommand("host google.com", "Test DNS resolution", InfoCategory.NETWORK),
    ],
    # Services
    "services": [
        InfoCommand(
            "systemctl list-units --type=service --state=running --no-pager",
            "List running services",
            InfoCategory.SERVICES,
        ),
        InfoCommand(
            "systemctl list-units --type=service --state=failed --no-pager",
            "List failed services",
            InfoCategory.SERVICES,
        ),
    ],
    # Security
    "security": [
        InfoCommand("ufw status", "Check firewall status", InfoCategory.SECURITY),
        InfoCommand("aa-status", "Check AppArmor status", InfoCategory.SECURITY),
        InfoCommand("wc -l /etc/passwd", "Count system users", InfoCategory.SECURITY),
    ],
    # Processes
    "processes": [
        InfoCommand(
            "ps aux --sort=-%mem", "Top memory-consuming processes", InfoCategory.PROCESSES
        ),
        InfoCommand("ps aux --sort=-%cpu", "Top CPU-consuming processes", InfoCategory.PROCESSES),
    ],
    # Environment
    "environment": [
        InfoCommand("env", "List environment variables", InfoCategory.CONFIGURATION),
        InfoCommand("echo $PATH", "Show PATH", InfoCategory.CONFIGURATION),
        InfoCommand("echo $SHELL", "Show current shell", InfoCategory.CONFIGURATION),
    ],
}

# Application-specific info templates
# Note: Commands are simplified to avoid || patterns which are blocked by CommandValidator
APP_INFO_TEMPLATES: dict[str, dict[str, list[InfoCommand]]] = {
    "nginx": {
        "status": [
            InfoCommand(
                "systemctl status nginx --no-pager",
                "Check nginx service status",
                InfoCategory.SERVICES,
            ),
            InfoCommand("nginx -v", "Get nginx version", InfoCategory.SOFTWARE),
        ],
        "config": [
            InfoCommand(
                "cat /etc/nginx/nginx.conf", "Get nginx configuration", InfoCategory.CONFIGURATION
            ),
            InfoCommand(
                "ls -la /etc/nginx/sites-enabled/", "List enabled sites", InfoCategory.CONFIGURATION
            ),
        ],
        "logs": [
            InfoCommand(
                "tail -50 /var/log/nginx/access.log", "Recent access logs", InfoCategory.LOGS
            ),
            InfoCommand(
                "tail -50 /var/log/nginx/error.log", "Recent error logs", InfoCategory.LOGS
            ),
        ],
    },
    "docker": {
        "status": [
            InfoCommand("docker --version", "Get Docker version", InfoCategory.SOFTWARE),
            InfoCommand("docker info", "Get Docker info", InfoCategory.SOFTWARE),
        ],
        "containers": [
            InfoCommand("docker ps -a", "List containers", InfoCategory.APPLICATION),
            InfoCommand("docker images", "List images", InfoCategory.APPLICATION),
        ],
        "resources": [
            InfoCommand(
                "docker stats --no-stream", "Container resource usage", InfoCategory.PERFORMANCE
            ),
        ],
    },
    "postgresql": {
        "status": [
            InfoCommand(
                "systemctl status postgresql --no-pager",
                "Check PostgreSQL service",
                InfoCategory.SERVICES,
            ),
            InfoCommand("psql --version", "Get PostgreSQL version", InfoCategory.SOFTWARE),
        ],
        "config": [
            InfoCommand(
                "head -50 /etc/postgresql/14/main/postgresql.conf",
                "PostgreSQL config",
                InfoCategory.CONFIGURATION,
            ),
        ],
    },
    "mysql": {
        "status": [
            InfoCommand(
                "systemctl status mysql --no-pager", "Check MySQL status", InfoCategory.SERVICES
            ),
            InfoCommand("mysql --version", "Get MySQL version", InfoCategory.SOFTWARE),
        ],
    },
    "redis": {
        "status": [
            InfoCommand(
                "systemctl status redis-server --no-pager",
                "Check Redis status",
                InfoCategory.SERVICES,
            ),
            InfoCommand("redis-cli --version", "Get Redis version", InfoCategory.SOFTWARE),
        ],
        "info": [
            InfoCommand("redis-cli info", "Redis server info", InfoCategory.APPLICATION),
        ],
    },
    "python": {
        "version": [
            InfoCommand("python3 --version", "Get Python version", InfoCategory.SOFTWARE),
            InfoCommand("which python3", "Find Python executable", InfoCategory.SOFTWARE),
        ],
        "packages": [
            InfoCommand(
                "pip3 list --format=freeze", "List installed packages", InfoCategory.PACKAGES
            ),
        ],
        "venv": [
            InfoCommand(
                "echo $VIRTUAL_ENV", "Check active virtual environment", InfoCategory.CONFIGURATION
            ),
        ],
    },
    "nodejs": {
        "version": [
            InfoCommand("node --version", "Get Node.js version", InfoCategory.SOFTWARE),
            InfoCommand("npm --version", "Get npm version", InfoCategory.SOFTWARE),
        ],
        "packages": [
            InfoCommand("npm list -g --depth=0", "List global npm packages", InfoCategory.PACKAGES),
        ],
    },
    "git": {
        "version": [
            InfoCommand("git --version", "Get Git version", InfoCategory.SOFTWARE),
        ],
        "config": [
            InfoCommand(
                "git config --global --list", "Git global config", InfoCategory.CONFIGURATION
            ),
        ],
    },
    "ssh": {
        "status": [
            InfoCommand(
                "systemctl status ssh --no-pager", "Check SSH service", InfoCategory.SERVICES
            ),
        ],
        "config": [
            InfoCommand(
                "head -50 /etc/ssh/sshd_config", "SSH server config", InfoCategory.CONFIGURATION
            ),
        ],
    },
    "systemd": {
        "status": [
            InfoCommand("systemctl --version", "Get systemd version", InfoCategory.SOFTWARE),
            InfoCommand(
                "systemctl list-units --state=failed --no-pager",
                "Failed units",
                InfoCategory.SERVICES,
            ),
        ],
        "timers": [
            InfoCommand(
                "systemctl list-timers --no-pager", "List active timers", InfoCategory.SERVICES
            ),
        ],
    },
}


class SystemInfoGenerator:
    """
    Generates read-only commands to retrieve system and application information.

    Uses LLM to generate appropriate commands based on natural language queries,
    while enforcing read-only access through CommandValidator.
    """

    MAX_ITERATIONS = 5
    MAX_OUTPUT_CHARS = 4000

    def __init__(
        self,
        api_key: str | None = None,
        provider: str = "claude",
        model: str | None = None,
        debug: bool = False,
    ):
        """
        Initialize the system info generator.

        Args:
            api_key: API key for LLM provider (defaults to env var)
            provider: LLM provider ("claude", "openai", "ollama")
            model: Optional model override
            debug: Enable debug output
        """
        self.api_key = (
            api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        )
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.debug = debug

        self._initialize_client()

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4o"
        elif self.provider == "claude":
            return "claude-sonnet-4-20250514"
        elif self.provider == "ollama":
            return "llama3.2"
        return "gpt-4o"

    def _initialize_client(self):
        """Initialize the LLM client."""
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
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _get_system_prompt(self, context: str = "") -> str:
        """Get the system prompt for info command generation."""
        app_list = ", ".join(sorted(APP_INFO_TEMPLATES.keys()))
        category_list = ", ".join([c.value for c in InfoCategory])

        prompt = f"""You are a Linux system information assistant that generates READ-ONLY shell commands.

Your task is to generate shell commands that gather system information to answer the user's query.
You can ONLY generate commands that READ information - no modifications allowed.

IMPORTANT RULES:
- Generate ONLY read-only commands (cat, ls, grep, find, ps, etc.)
- NEVER generate commands that modify the system (rm, mv, cp, apt install, etc.)
- NEVER use sudo (commands must work as regular user where possible)
- NEVER use output redirection (>, >>)
- NEVER use dangerous command chaining (;, &&, ||) except for fallback patterns
- Commands should handle missing files/tools gracefully using || echo fallbacks

ALLOWED COMMAND PATTERNS:
- Reading files: cat, head, tail, less (without writing)
- Listing: ls, find, locate, which, whereis, type
- System info: uname, hostname, uptime, whoami, id, lscpu, lsmem, lsblk
- Process info: ps, top, pgrep, pidof, pstree, free, vmstat
- Package queries: dpkg-query, dpkg -l, apt-cache, pip list/show/freeze
- Network info: ip addr, ip route, ss, netstat (read operations)
- Service status: systemctl status (NOT start/stop/restart)
- Text processing: grep, awk, sed (for filtering, NOT modifying files)

BLOCKED PATTERNS (NEVER USE):
- sudo, su
- apt install/remove, pip install/uninstall
- rm, mv, cp, mkdir, touch, chmod, chown
- Output redirection: > or >>
- systemctl start/stop/restart/enable/disable

RESPONSE FORMAT:
You must respond with a JSON object in one of these formats:

For generating a command to gather info:
{{
    "response_type": "command",
    "command": "<shell command>",
    "category": "<{category_list}>",
    "reasoning": "<why this command>"
}}

For providing the final answer:
{{
    "response_type": "answer",
    "answer": "<comprehensive answer based on gathered data>",
    "reasoning": "<summary of findings>"
}}

KNOWN APPLICATIONS with pre-defined info commands: {app_list}

{context}"""
        return prompt

    def _truncate_output(self, output: str) -> str:
        """Truncate output to avoid context overflow."""
        if len(output) <= self.MAX_OUTPUT_CHARS:
            return output
        half = self.MAX_OUTPUT_CHARS // 2
        return f"{output[:half]}\n\n... [truncated {len(output) - self.MAX_OUTPUT_CHARS} chars] ...\n\n{output[-half:]}"

    def _execute_command(self, command: str, timeout: int = 30) -> InfoResult:
        """Execute a validated read-only command."""
        import time

        start_time = time.time()

        # Validate command first
        is_valid, error = CommandValidator.validate_command(command)
        if not is_valid:
            return InfoResult(
                command=command,
                success=False,
                output="",
                error=f"Command blocked: {error}",
                execution_time=time.time() - start_time,
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return InfoResult(
                command=command,
                success=result.returncode == 0,
                output=result.stdout.strip(),
                error=result.stderr.strip() if result.returncode != 0 else "",
                execution_time=time.time() - start_time,
            )
        except subprocess.TimeoutExpired:
            return InfoResult(
                command=command,
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
                execution_time=timeout,
            )
        except Exception as e:
            return InfoResult(
                command=command,
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
            )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Call the LLM and parse the response."""
        try:
            if self.provider == "claude":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = response.content[0].text
            elif self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=2048,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content
            elif self.provider == "ollama":
                import httpx

                response = httpx.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            # Parse JSON from response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No JSON found in response")

        except json.JSONDecodeError as e:
            if self.debug:
                console.print(f"[red]JSON parse error: {e}[/red]")
            return {
                "response_type": "answer",
                "answer": f"Error parsing LLM response: {e}",
                "reasoning": "",
            }
        except Exception as e:
            if self.debug:
                console.print(f"[red]LLM error: {e}[/red]")
            return {"response_type": "answer", "answer": f"Error calling LLM: {e}", "reasoning": ""}

    def get_info(self, query: str, context: str = "") -> SystemInfoResult:
        """
        Get system information based on a natural language query.

        Uses an agentic loop to:
        1. Generate commands to gather information
        2. Execute commands (read-only only)
        3. Analyze results
        4. Either generate more commands or provide final answer

        Args:
            query: Natural language question about the system
            context: Optional additional context for the LLM

        Returns:
            SystemInfoResult with answer and command execution details
        """
        system_prompt = self._get_system_prompt(context)
        commands_executed: list[InfoResult] = []
        history: list[dict[str, str]] = []

        user_prompt = f"Query: {query}"

        for iteration in range(self.MAX_ITERATIONS):
            if self.debug:
                console.print(f"[dim]Iteration {iteration + 1}/{self.MAX_ITERATIONS}[/dim]")

            # Build prompt with history
            full_prompt = user_prompt
            if history:
                full_prompt += "\n\nPrevious commands and results:\n"
                for i, entry in enumerate(history, 1):
                    full_prompt += f"\n--- Command {i} ---\n"
                    full_prompt += f"Command: {entry['command']}\n"
                    if entry["success"]:
                        full_prompt += f"Output:\n{self._truncate_output(entry['output'])}\n"
                    else:
                        full_prompt += f"Error: {entry['error']}\n"
                full_prompt += "\nBased on these results, either run another command or provide the final answer.\n"

            # Call LLM
            response = self._call_llm(system_prompt, full_prompt)

            if response.get("response_type") == "answer":
                # Final answer
                return SystemInfoResult(
                    query=query,
                    answer=response.get("answer", "No answer provided"),
                    commands_executed=commands_executed,
                    raw_data={h["command"]: h["output"] for h in history if h.get("success")},
                )

            elif response.get("response_type") == "command":
                command = response.get("command", "")
                if not command:
                    continue

                if self.debug:
                    console.print(f"[cyan]Executing:[/cyan] {command}")

                result = self._execute_command(command)
                commands_executed.append(result)

                history.append(
                    {
                        "command": command,
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                    }
                )

                if self.debug:
                    if result.success:
                        console.print("[green]✓ Success[/green]")
                    else:
                        console.print(f"[red]✗ Failed: {result.error}[/red]")

        # Max iterations reached
        return SystemInfoResult(
            query=query,
            answer="Could not complete the query within iteration limit.",
            commands_executed=commands_executed,
            raw_data={h["command"]: h["output"] for h in history if h.get("success")},
        )

    def get_app_info(
        self,
        app_name: str,
        query: str | None = None,
        aspects: list[str] | None = None,
    ) -> SystemInfoResult:
        """
        Get information about a specific application.

        Args:
            app_name: Application name (nginx, docker, postgresql, etc.)
            query: Optional natural language query about the app
            aspects: Optional list of aspects to check (status, config, logs, etc.)

        Returns:
            SystemInfoResult with application information
        """
        app_lower = app_name.lower()
        commands_executed: list[InfoResult] = []
        raw_data: dict[str, Any] = {}

        # Check if we have predefined commands for this app
        if app_lower in APP_INFO_TEMPLATES:
            templates = APP_INFO_TEMPLATES[app_lower]
            aspects_to_check = aspects or list(templates.keys())

            for aspect in aspects_to_check:
                if aspect in templates:
                    for cmd_info in templates[aspect]:
                        result = self._execute_command(cmd_info.command, cmd_info.timeout)
                        commands_executed.append(result)
                        if result.success and result.output:
                            raw_data[f"{aspect}:{cmd_info.purpose}"] = result.output

        # If there's a specific query, use LLM to analyze
        if query:
            context = f"""Application: {app_name}
Already gathered data:
{json.dumps(raw_data, indent=2)[:2000]}

Now answer the specific question about this application."""

            result = self.get_info(query, context)
            result.commands_executed = commands_executed + result.commands_executed
            result.raw_data.update(raw_data)
            return result

        # Generate summary answer from raw data
        answer_parts = [f"**{app_name.title()} Information**\n"]
        for key, value in raw_data.items():
            aspect, desc = key.split(":", 1)
            answer_parts.append(
                f"\n**{aspect.title()}** ({desc}):\n```\n{value[:500]}{'...' if len(value) > 500 else ''}\n```"
            )

        return SystemInfoResult(
            query=query or f"Get information about {app_name}",
            answer="\n".join(answer_parts) if raw_data else f"No information found for {app_name}",
            commands_executed=commands_executed,
            raw_data=raw_data,
            category=InfoCategory.APPLICATION,
        )

    def get_structured_info(
        self,
        category: str | InfoCategory,
        aspects: list[str] | None = None,
    ) -> SystemInfoResult:
        """
        Get structured system information for a category.

        Args:
            category: Info category (hardware, network, services, etc.)
            aspects: Optional specific aspects (cpu, memory, disk for hardware, etc.)

        Returns:
            SystemInfoResult with structured information
        """
        if isinstance(category, str):
            category = category.lower()
        else:
            category = category.value

        commands_executed: list[InfoResult] = []
        raw_data: dict[str, Any] = {}

        # Map categories to common commands
        category_mapping = {
            "hardware": ["cpu", "memory", "disk", "gpu"],
            "software": ["os", "kernel"],
            "network": ["network", "dns"],
            "services": ["services"],
            "security": ["security"],
            "processes": ["processes"],
            "storage": ["disk"],
            "performance": ["cpu", "memory", "processes"],
            "configuration": ["environment"],
        }

        aspects_to_check = aspects or category_mapping.get(category, [])

        for aspect in aspects_to_check:
            if aspect in COMMON_INFO_COMMANDS:
                for cmd_info in COMMON_INFO_COMMANDS[aspect]:
                    result = self._execute_command(cmd_info.command, cmd_info.timeout)
                    commands_executed.append(result)
                    if result.success and result.output:
                        raw_data[f"{aspect}:{cmd_info.purpose}"] = result.output

        # Generate structured answer
        answer_parts = [f"**{category.title()} Information**\n"]
        for key, value in raw_data.items():
            aspect, desc = key.split(":", 1)
            answer_parts.append(
                f"\n**{aspect.upper()}** ({desc}):\n```\n{value[:800]}{'...' if len(value) > 800 else ''}\n```"
            )

        return SystemInfoResult(
            query=f"Get {category} information",
            answer="\n".join(answer_parts) if raw_data else f"No {category} information found",
            commands_executed=commands_executed,
            raw_data=raw_data,
            category=(
                InfoCategory(category)
                if category in [c.value for c in InfoCategory]
                else InfoCategory.CUSTOM
            ),
        )

    def quick_info(self, info_type: str) -> str:
        """
        Quick lookup for common system information.

        Args:
            info_type: Type of info (cpu, memory, disk, os, network, etc.)

        Returns:
            String with the requested information
        """
        info_lower = info_type.lower()

        if info_lower in COMMON_INFO_COMMANDS:
            outputs = []
            for cmd_info in COMMON_INFO_COMMANDS[info_lower]:
                result = self._execute_command(cmd_info.command)
                if result.success and result.output:
                    outputs.append(result.output)
            return "\n\n".join(outputs) if outputs else f"No {info_type} information available"

        # Try as app info
        if info_lower in APP_INFO_TEMPLATES:
            result = self.get_app_info(info_lower, aspects=["status", "version"])
            return result.answer

        return (
            f"Unknown info type: {info_type}. Available: {', '.join(COMMON_INFO_COMMANDS.keys())}"
        )

    def list_available_info(self) -> dict[str, list[str]]:
        """List all available pre-defined info types and applications."""
        return {
            "system_info": list(COMMON_INFO_COMMANDS.keys()),
            "applications": list(APP_INFO_TEMPLATES.keys()),
            "categories": [c.value for c in InfoCategory],
        }


def get_system_info_generator(
    provider: str = "claude",
    debug: bool = False,
) -> SystemInfoGenerator:
    """
    Factory function to create a SystemInfoGenerator with default configuration.

    Args:
        provider: LLM provider to use
        debug: Enable debug output

    Returns:
        Configured SystemInfoGenerator instance
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    return SystemInfoGenerator(api_key=api_key, provider=provider, debug=debug)


# CLI helper for quick testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python system_info_generator.py <query>")
        print("       python system_info_generator.py --quick <info_type>")
        print("       python system_info_generator.py --app <app_name> [query]")
        print("       python system_info_generator.py --list")
        sys.exit(1)

    try:
        generator = get_system_info_generator(debug=True)

        if sys.argv[1] == "--list":
            available = generator.list_available_info()
            console.print("\n[bold]Available Information Types:[/bold]")
            console.print(f"System: {', '.join(available['system_info'])}")
            console.print(f"Apps: {', '.join(available['applications'])}")
            console.print(f"Categories: {', '.join(available['categories'])}")

        elif sys.argv[1] == "--quick" and len(sys.argv) > 2:
            info = generator.quick_info(sys.argv[2])
            console.print(Panel(info, title=f"{sys.argv[2].title()} Info"))

        elif sys.argv[1] == "--app" and len(sys.argv) > 2:
            app_name = sys.argv[2]
            query = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
            result = generator.get_app_info(app_name, query)
            console.print(Panel(result.answer, title=f"{app_name.title()} Info"))

        else:
            query = " ".join(sys.argv[1:])
            result = generator.get_info(query)
            console.print(Panel(result.answer, title="System Info"))

            if result.commands_executed:
                table = Table(title="Commands Executed")
                table.add_column("Command", style="cyan")
                table.add_column("Status", style="green")
                table.add_column("Time", style="dim")
                for cmd in result.commands_executed:
                    status = "✓" if cmd.success else "✗"
                    table.add_row(cmd.command[:60], status, f"{cmd.execution_time:.2f}s")
                console.print(table)

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
