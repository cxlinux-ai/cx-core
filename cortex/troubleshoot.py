"""
Interactive Troubleshooting Assistant for Cortex.

This module provides the Troubleshooter class which:
1. Acts as a general-purpose AI assistant
2. Suggests shell commands to fix issues
3. Executes commands on behalf of the user (with confirmation)
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax

from cortex.api_key_detector import auto_detect_api_key
from cortex.ask import AskHandler
from cortex.logging_system import CortexLogger
from cortex.resolutions import ResolutionManager

console = Console()

# Dangerous command patterns that should never be executed
DANGEROUS_PATTERNS = [
    r"\brm\s+(-[^\s]*\s+)*-rf\b",  # rm -rf
    r"\brm\s+(-[^\s]*\s+)*-fr\b",  # rm -fr (same as above)
    r"\brm\b(?=.*\s-[-\w]*r)(?=.*\s-[-\w]*f)",  # rm with both -r and -f (any order)
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
    r"\|\s*(?:.*/)?(?:bash|sh|zsh)\b",  # Pipe to shell (matches bash, sh, zsh, /bin/bash, etc.)
    r"`[^`]*\b(rm|mkfs|dd|chmod|chown|shutdown|reboot)\b",  # Backtick with dangerous cmd
    r"\$\([^)]*\b(rm|mkfs|dd|chmod|chown|shutdown|reboot)\b",  # $() with dangerous cmd
]

# Number of recent messages to keep for context
MAX_HISTORY_CONTEXT = 5
MAX_INPUT_LENGTH = 10000


class Troubleshooter:
    """Interactive AI assistant for diagnosing and resolving system issues."""

    def __init__(self, no_execute: bool = False) -> None:
        self.logger = CortexLogger("troubleshooter")
        self.no_execute = no_execute
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
            if not self.api_key:
                if self.provider == "ollama":
                    self.api_key = "ollama"
                else:
                    raise ValueError(f"No API key found for provider '{self.provider}'")
            self.ai = AskHandler(self.api_key, self.provider)
            self.ai.cache = None  # Disable caching for conversational context
        except Exception as e:
            self.logger.warning(f"Failed to initialize AI: {e}")
            self.ai = None

        self.resolutions = ResolutionManager()

    def start(self) -> int:
        """Start the troubleshooting session."""
        console.print("[bold cyan]🤖 Cortex Troubleshooter[/bold cyan]")
        console.print(
            "[dim]Describe your issue, type 'doctor' to run health checks, or 'help' to escalate to human support.[/dim]"
        )

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
        redacted = re.sub(
            r"(?i)(--?(?:token|api[-_]?key|password|secret)\s+)(\S+)",
            r"\1***",
            cmd,
        )
        self.logger.info(f"Executing command: {redacted}")

        # Check if Firejail is available for sandboxing
        use_sandbox = shutil.which("firejail") is not None

        exec_cmd = cmd
        if use_sandbox:
            exec_cmd = f"firejail --quiet --private-tmp -- bash -c {shlex.quote(cmd)}"
            self.logger.info("Using Firejail sandbox for command execution")

        try:
            result = subprocess.run(
                exec_cmd, shell=True, capture_output=True, text=True, timeout=120
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

                if len(user_input) > MAX_INPUT_LENGTH:
                    console.print(
                        f"[yellow]⚠️  Input too long ({len(user_input)} chars). "
                        f"Please limit to {MAX_INPUT_LENGTH} characters.[/yellow]"
                    )
                    continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    # Learning Trigger
                    if Confirm.ask("Did we solve your problem?"):
                        with console.status("[cyan]Learning from success...[/cyan]"):
                            history_text = "\n".join(
                                [f"{m['role']}: {m['content']}" for m in self.messages]
                            )
                            try:
                                extraction = self.ai.ask(
                                    f"Analyze this troubleshooting session. Extract the core issue and the specific command that fixed it. Return ONLY a JSON object with keys 'issue' and 'fix'.\n\nSession:\n{history_text}",
                                    system_prompt="You are a knowledge extraction bot. Return only valid JSON.",
                                )

                                # Use regex to find the JSON block
                                match = re.search(r"\{.*\}", extraction, re.DOTALL)
                                if match:
                                    clean_json = match.group(0)
                                    data = json.loads(clean_json)

                                    if "issue" in data and "fix" in data:
                                        self.resolutions.save(data["issue"], data["fix"])
                                        console.print("[bold green]✓ Knowledge saved![/bold green]")
                                    else:
                                        self.logger.warning(f"Incomplete resolution data: {data}")
                                else:
                                    self.logger.warning(f"No JSON found in response: {extraction}")
                            except Exception as e:
                                self.logger.warning(f"Failed to learn resolution: {e}")

                    console.print("[dim]Exiting troubleshooter.[/dim]")
                    break

                # Special command to run doctor manually
                if user_input.lower() == "doctor":
                    from cortex.doctor import SystemDoctor

                    doc = SystemDoctor()
                    doc.run_checks()
                    continue

                # Help command for escalation
                if user_input.lower() == "help":
                    with console.status("[cyan]Generating support summary...[/cyan]"):
                        # Ask AI to summarize the issue
                        history_text = "\n".join(
                            [f"{m['role']}: {m['content']}" for m in self.messages]
                        )
                        summary = self.ai.ask(
                            f"Summarize the following troubleshooting session for a support ticket. Include the user's issue, commands tried, and errors encountered:\n\n{history_text}",
                            system_prompt="Create a concise summary of the issue with user's POV",
                        )

                    # Try to create log in ~/.cortex, fall back to tempdir if not writable
                    try:
                        log_file = os.path.expanduser("~/.cortex/cortex_support_log.txt")
                        os.makedirs(os.path.dirname(log_file), exist_ok=True)
                    except (PermissionError, OSError) as e:
                        self.logger.warning(f"Cannot write to ~/.cortex: {e}")
                        log_file = os.path.join(tempfile.gettempdir(), "cortex_support_log.txt")
                        console.print(f"[dim]Using fallback location: {log_file}[/dim]")

                    log_path = os.path.abspath(log_file)

                    try:
                        with open(log_file, "w", encoding="utf-8") as f:
                            f.write("Cortex Troubleshooting Log\n")
                            f.write("==========================\n\n")
                            f.write("Issue Summary:\n")
                            f.write(summary)

                        console.print(
                            f"\n[bold green]✓ Diagnostic log saved to {log_path}[/bold green]"
                        )
                        console.print(f"Please open a new issue and attach the {log_path} file.")
                    except (PermissionError, OSError) as e:
                        self.logger.error(f"Failed to write support log: {e}")
                        console.print(f"[red]Error: Could not write support log ({e})[/red]")
                    continue

                self.messages.append({"role": "user", "content": user_input})

                with console.status("[cyan]Thinking...[/cyan]"):
                    # Construct prompt with history
                    history_text = "\n".join(
                        [
                            f"{m['role']}: {m['content']}"
                            for m in self.messages[-MAX_HISTORY_CONTEXT:]
                        ]
                    )

                    # Dynamic Recall: Search for relevant past resolutions
                    relevant_fixes = self.resolutions.search(user_input)
                    current_system_prompt = self.messages[0]["content"]

                    if relevant_fixes:
                        fixes_text = "\n".join(
                            [f"- Issue: {r['issue']} -> Fix: {r['fix']}" for r in relevant_fixes]
                        )
                        current_system_prompt += f"\n\n[MEMORY] Here are past successful fixes for similar issues:\n{fixes_text}"

                    # We pass the system prompt explicitly to override AskHandler's default
                    response = self.ai.ask(
                        question=f"History:\n{history_text}\n\nUser: {user_input}",
                        system_prompt=current_system_prompt,  # The initial system prompt + memory
                    )

                console.print(Markdown(response))
                self.messages.append({"role": "assistant", "content": response})

                # Check for commands to execute
                while True:
                    commands = self._extract_code_blocks(response)
                    if not commands:
                        break

                    last_analysis = None
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

                        if self.no_execute:
                            console.print("\n[dim]Execution skipped (read-only mode)[/dim]")
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
                                {"role": "user", "content": f"[Command Output]\n{output}"}
                            )

                            # Ask AI for analysis of the output
                            with console.status("[cyan]Analyzing output...[/cyan]"):
                                analysis = self.ai.ask(
                                    f"Command '{cmd}' produced this output:\n{output}\n\nWhat is the next step?",
                                    system_prompt=self.messages[0]["content"],
                                )

                            console.print(Markdown(analysis))
                            self.messages.append({"role": "assistant", "content": analysis})
                            last_analysis = analysis

                    # If the last analysis contains new commands, loop back to execute them
                    if last_analysis and self._extract_code_blocks(last_analysis):
                        response = last_analysis
                        continue
                    else:
                        break

        except KeyboardInterrupt:
            console.print("\n[dim]Session cancelled.[/dim]")
            return 130
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            self.logger.error("Troubleshooting loop failed", exc_info=True)
            return 1

        return 0
