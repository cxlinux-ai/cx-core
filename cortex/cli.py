import sys
import os
import argparse
import time
from typing import List, Optional
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus


class CortexCLI:
    def __init__(self):
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
    
    def _get_api_key(self) -> Optional[str]:
        api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            self._print_error("API key not found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
            return None
        return api_key
    
    def _get_provider(self) -> str:
        if os.environ.get('OPENAI_API_KEY'):
            return 'openai'
        elif os.environ.get('ANTHROPIC_API_KEY'):
            return 'claude'
        return 'openai'
    
    def _print_status(self, emoji: str, message: str):
        print(f"{emoji} {message}")
    
    def _print_error(self, message: str):
        print(f"❌ Error: {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        print(f"✅ {message}")
    
    def _animate_spinner(self, message: str):
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)
    
    def _clear_line(self):
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
    
    def install(self, software: str, execute: bool = False, dry_run: bool = False):
        api_key = self._get_api_key()
        if not api_key:
            return 1
        
        provider = self._get_provider()
        
        try:
            self._print_status("🧠", "Understanding request...")
            
            interpreter = CommandInterpreter(api_key=api_key, provider=provider)
            
            self._print_status("📦", "Planning installation...")
            
            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()
            
            commands = interpreter.parse(f"install {software}")
            
            if not commands:
                self._print_error("No commands generated. Please try again with a different request.")
                return 1
            
            self._print_status("⚙️", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")
            
            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                return 0
            
            if execute:
                def progress_callback(current, total, step):
                    status_emoji = "⏳"
                    if step.status == StepStatus.SUCCESS:
                        status_emoji = "✅"
                    elif step.status == StepStatus.FAILED:
                        status_emoji = "❌"
                    print(f"\n[{current}/{total}] {status_emoji} {step.description}")
                    print(f"  Command: {step.command}")
                
                print("\nExecuting commands...")
                
                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i+1}" for i in range(len(commands))],
                    timeout=300,
                    stop_on_error=True,
                    progress_callback=progress_callback
                )
                
                result = coordinator.execute()
                
                if result.success:
                    self._print_success(f"{software} installed successfully!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")
                    return 0
                else:
                    if result.failed_step is not None:
                        self._print_error(f"Installation failed at step {result.failed_step + 1}")
                    else:
                        self._print_error("Installation failed")
                    if result.error_message:
                        print(f"  Error: {result.error_message}", file=sys.stderr)
                    return 1
            else:
                print("\nTo execute these commands, run with --execute flag")
                print("Example: cortex install docker --execute")
            
            return 0
            
        except ValueError as e:
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            self._print_error(f"API call failed: {str(e)}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error: {str(e)}")
            return 1


def main():
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

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    install_parser = subparsers.add_parser('install', help='Install software using natural language')
    install_parser.add_argument('software', type=str, help='Software to install (natural language)')
    install_parser.add_argument('--execute', action='store_true', help='Execute the generated commands')
    install_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = CortexCLI()
    
    if args.command == 'install':
        return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
