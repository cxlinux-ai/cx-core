import argparse
import os
import subprocess
import sys
import time
from typing import Optional

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus


class CortexCLI:
    """Command-line interface for Cortex AI-powered software installation."""

    def __init__(self) -> None:
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

    def _get_api_key(self) -> Optional[str]:
        """Return the configured API key or emit an error if missing."""
        api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            self._print_error("API key not found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
            return None
        return api_key

    def _get_provider(self) -> str:
        """Detect which LLM provider to use based on available credentials."""
        if os.environ.get('OPENAI_API_KEY'):
            return 'openai'
        if os.environ.get('ANTHROPIC_API_KEY'):
            return 'claude'
        return 'openai'

    def _print_status(self, label: str, message: str) -> None:
        print(f"{label} {message}")

    def _print_error(self, message: str) -> None:
        print(f"[ERROR] {message}", file=sys.stderr)

    def _print_success(self, message: str) -> None:
        print(f"[SUCCESS] {message}")

    def _animate_spinner(self, message: str) -> None:
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)

    def _clear_line(self) -> None:
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()

    def install(self, software: str, execute: bool = False, dry_run: bool = False) -> int:
        """Interpret a natural-language request and optionally execute the plan."""

        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()

        try:
            self._print_status("[INFO]", "Understanding request...")

            interpreter = CommandInterpreter(api_key=api_key, provider=provider)

            self._print_status("[PLAN]", "Planning installation...")

            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()

            commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error("No commands generated. Please try again with a different request.")
                return 1

            self._print_status("[EXEC]", f"Installing {software}...")
            print("\nGenerated commands:")
            for index, command in enumerate(commands, 1):
                print(f"  {index}. {command}")

            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                return 0

            if execute:
                def progress_callback(current: int, total: int, step) -> None:
                    status_label = "[PENDING]"
                    if step.status == StepStatus.SUCCESS:
                        status_label = "[OK]"
                    elif step.status == StepStatus.FAILED:
                        status_label = "[FAIL]"
                    print(f"\n[{current}/{total}] {status_label} {step.description}")
                    print(f"  Command: {step.command}")

                print("\nExecuting commands...")

                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                    timeout=300,
                    stop_on_error=True,
                    progress_callback=progress_callback,
                )

                result = coordinator.execute()

                if result.success:
                    self._print_success(f"{software} installed successfully!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")
                    return 0

                if result.failed_step is not None:
                    self._print_error(f"Installation failed at step {result.failed_step + 1}")
                else:
                    self._print_error("Installation failed")
                if result.error_message:
                    print(f"  Error: {result.error_message}", file=sys.stderr)
                return 1

            print("\nTo execute these commands, run with --execute flag")
            print("Example: cortex install docker --execute")
            return 0

        except ValueError as exc:
            self._print_error(str(exc))
            return 1
        except RuntimeError as exc:
            self._print_error(f"API call failed: {str(exc)}")
            return 1
        except Exception as exc:
            self._print_error(f"Unexpected error: {str(exc)}")
            return 1


def main() -> int:
    """Entry point for the cortex CLI command."""

    parser = argparse.ArgumentParser(
        prog='cortex',
        description='AI-powered Linux command interpreter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex install docker
  cortex install docker --execute
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run
  cortex --test

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
        """
    )

    parser.add_argument('--test', action='store_true', help='Run all test suites')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    install_parser = subparsers.add_parser('install', help='Install software using natural language')
    install_parser.add_argument('software', type=str, help='Software to install (natural language)')
    install_parser.add_argument('--execute', action='store_true', help='Execute the generated commands')
    install_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')

    args = parser.parse_args()

    if args.test:
        test_dir = os.path.join(os.path.dirname(__file__), '..', 'test')
        test_runner = os.path.join(test_dir, 'run_all_tests.py')

        if not os.path.exists(test_runner):
            print("[ERROR] Test runner not found", file=sys.stderr)
            return 1

        result = subprocess.run([sys.executable, test_runner])
        return result.returncode

    if not args.command:
        parser.print_help()
        return 1

    cli = CortexCLI()

    if args.command == 'install':
        return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)

    return 0


if __name__ == '__main__':
    sys.exit(main())
