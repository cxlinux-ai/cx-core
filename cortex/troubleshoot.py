"""
Interactive Troubleshooting Assistant for Cortex.

This module provides the Troubleshooter class which:
1. Acts as a general-purpose AI assistant
2. Suggests shell commands to fix issues
3. Executes commands on behalf of the user (with confirmation)
"""

import re
import shutil
import subprocess
import sys
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax

from cortex.api_key_detector import auto_detect_api_key
from cortex.ask import AskHandler
from cortex.logging_system import CortexLogger

console = Console()

# Dangerous command patterns that should never be executed
DANGEROUS_PATTERNS = [
    r"\brm\s+(-[^\s]*\s+)*-rf\b",  # rm -rf
    r"\brm\s+(-[^\s]*\s+)*-fr\b",  # rm -fr (same as above)
    r"\brm\s+(-[^\s]*\s+)*/\s*$",  # rm /
    r"\bmkfs\b",  # Format filesystem
    r"\bdd\s+.*of=/dev/",  # dd to device
    r">\s*/dev/sd[a-z]",  # Redirect to disk
    r"\bchmod\s+(-[^\s]*\s+)*777\s+/",  # chmod 777 on root
    r"\bchown\s+.*\s+/\s*$",  # chown on root
    r":\(\)\s*{\s*:\|:\s*&\s*}",  # Fork bomb
    r"\bshutdown\b",  # Shutdown
    r"\breboot\b",  # Reboot
    r"\binit\s+0\b",  # Halt
    r"\bpoweroff\b",  # Poweroff
    r"\|\s*bash",  # Pipe to bash
    r"\|\s*sh",  # Pipe to sh
]


class Troubleshooter:
    def __init__(self):
        self.logger = CortexLogger("troubleshooter")
        self.messages: list[dict[str, str]] = []

        # Initialize AI
        try:
            found, key, provider, _ = auto_detect_api_key()
            self.api_key = key or ""
            provider_name = provider or "openai"
            if provider_name == "anthropic":
                self.provider = "claude"
            else:
                self.provider = provider_name
            # Validate key presence (Ollama uses dummy key, so it's fine)
            if not self.api_key and self.provider != "ollama":
                raise ValueError(f"No API key found for provider '{self.provider}'")
            self.ai = AskHandler(self.api_key, self.provider)
            self.ai.cache = None  # Disable caching for conversational context
        except Exception as e:
            self.logger.warning(f"Failed to initialize AI: {e}")
            self.ai = None

    def _get_provider(self) -> str:
        """Determine which LLM provider to use."""
        found, _, provider, _ = auto_detect_api_key()
        if provider == "anthropic":
            return "claude"
        return provider or "openai"

    def _get_api_key(self) -> str:
        """Get the API key for the configured provider."""
        found, key, _, _ = auto_detect_api_key()
        return key or ""

    def start(self) -> int:
        """Start the troubleshooting session."""
        console.print("[bold cyan]🤖 Cortex Troubleshooter[/bold cyan]")
        console.print("[dim]Describe your issue, or type 'doctor' to run health checks.[/dim]")

        if not self.ai:
            console.print("\n[red]❌ AI Assistant unavailable (check API key).[/red]")
            return 1

        # Initial System Prompt
        system_prompt = (
            "You are Cortex, an AI-powered Cortex Linux troubleshooting assistant. "
            "Your goal is to diagnose and fix system issues. "
            "Do not answer general questions unrelated to system maintenance or troubleshooting. "
            "Rules:\n"
            "1. ALWAYS provide the specific shell command to run in a `bash` code block. Do not just tell the user to run it.\n"
            "2. Suggest one step at a time. Wait for the command output before proceeding.\n"
            "3. Analyze the command output and explain the findings step-by-step.\n"
            "4. Maintain your identity as Cortex."
        )
        self.messages.append({"role": "system", "content": system_prompt})

        return self._interactive_loop()

    def _extract_code_blocks(self, text: str) -> list[str]:
        """Extract content from markdown code blocks."""
        # Match ```bash ... ``` or ```sh ... ``` or just ``` ... ```
        pattern = r"```(?:bash|sh)?\n(.*?)```"
        return re.findall(pattern, text, re.DOTALL)

    def _is_command_safe(self, cmd: str) -> tuple[bool, str]:
        """Check if a command is safe to execute.

        Returns:
            Tuple of (is_safe, reason)
        """
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False, f"Command matches dangerous pattern: {pattern}"
        return True, ""

    def _execute_command(self, cmd: str) -> str:
        """Execute a shell command and return output.

        If Firejail is available, the command is executed in a sandbox
        for additional security since AI-suggested commands are untrusted.
        """
        # Log the command execution for audit
        self.logger.info(f"Executing command: {cmd}")

        # Check if Firejail is available for sandboxing
        use_sandbox = shutil.which("firejail") is not None

        exec_cmd = cmd
        if use_sandbox:
            exec_cmd = f"firejail --quiet --private-tmp {cmd}"
            self.logger.info("Using Firejail sandbox for command execution")

        try:
            result = subprocess.run(
                exec_cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            result_output = output.strip()
            self.logger.info(f"Command completed with exit code: {result.returncode}")
            return result_output
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return f"Error executing command: {e}"

    def _interactive_loop(self) -> int:
        """Main chat loop with command execution."""
        try:
            while True:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")

                if user_input.lower() in ["exit", "quit", "q"]:
                    console.print("[dim]Exiting troubleshooter.[/dim]")
                    break

                # Special command to run doctor manually
                if user_input.lower() == "doctor":
                    from cortex.doctor import SystemDoctor

                    doc = SystemDoctor()
                    doc.run_checks()
                    continue

                self.messages.append({"role": "user", "content": user_input})

                with console.status("[cyan]Thinking...[/cyan]"):
                    # Construct prompt with history
                    history_text = "\n".join(
                        [f"{m['role']}: {m['content']}" for m in self.messages[-5:]]
                    )

                    # We pass the system prompt explicitly to override AskHandler's default
                    response = self.ai.ask(
                        question=f"History:\n{history_text}\n\nUser: {user_input}",
                        system_prompt=self.messages[0]["content"],  # The initial system prompt
                    )

                console.print(Markdown(response))
                self.messages.append({"role": "assistant", "content": response})

                # Check for commands to execute
                commands = self._extract_code_blocks(response)
                if commands:
                    for cmd in commands:
                        cmd = cmd.strip()
                        if not cmd:
                            continue

                        console.print("\n[bold yellow]Suggested Command:[/bold yellow]")
                        console.print(Syntax(cmd, "bash", theme="monokai", line_numbers=False))

                        # Check if command is safe
                        is_safe, reason = self._is_command_safe(cmd)
                        if not is_safe:
                            console.print(
                                "\n[bold red]⚠️  BLOCKED: This command is potentially dangerous.[/bold red]"
                            )
                            console.print(f"[dim]Reason: {reason}[/dim]")
                            self.logger.warning(f"Blocked dangerous command: {cmd}")
                            continue

                        if Confirm.ask("Execute this command?"):
                            with console.status("[bold yellow]Executing...[/bold yellow]"):
                                output = self._execute_command(cmd)

                            # Show output to user
                            console.print(
                                Panel(
                                    output, title="Command Output", border_style="dim", expand=False
                                )
                            )

                            console.print("[dim]Output captured.[/dim]")
                            # Feed output back to AI
                            self.messages.append(
                                {"role": "system", "content": f"Command Output:\n{output}"}
                            )

                            # Ask AI for analysis of the output
                            with console.status("[cyan]Analyzing output...[/cyan]"):
                                analysis = self.ai.ask(
                                    f"Command '{cmd}' produced this output:\n{output}\n\nWhat is the next step?",
                                    system_prompt=self.messages[0]["content"],
                                )

                            console.print(Markdown(analysis))
                            self.messages.append({"role": "assistant", "content": analysis})

        except KeyboardInterrupt:
            console.print("\n[dim]Session cancelled.[/dim]")
            return 130
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            self.logger.error("Troubleshooting loop failed", exc_info=True)
            return 1

        return 0
