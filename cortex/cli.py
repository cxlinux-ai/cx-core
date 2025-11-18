import sys
import os
import argparse
import time
from typing import List, Optional
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus
from cortex.update_manifest import UpdateChannel
from cortex.updater import ChecksumMismatch, InstallError, UpdateError, UpdateService


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
        self._notify_update_if_available()
        api_key = self._get_api_key()
        if not api_key:
            return 1
        
        provider = self._get_provider()
        
        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()
        
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
            
            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)
            
            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL,
                    packages,
                    commands,
                    start_time
                )
            
            self._print_status("⚙️", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")
            
            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
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
                    
                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n📝 Installation recorded (ID: {install_id})")
                        print(f"   To rollback: cortex rollback {install_id}")
                    
                    return 0
                else:
                    # Record failed installation
                    if install_id:
                        error_msg = result.error_message or "Installation failed"
                        history.update_installation(
                            install_id,
                            InstallationStatus.FAILED,
                            error_msg
                        )
                    
                    if result.failed_step is not None:
                        self._print_error(f"Installation failed at step {result.failed_step + 1}")
                    else:
                        self._print_error("Installation failed")
                    if result.error_message:
                        print(f"  Error: {result.error_message}", file=sys.stderr)
                    if install_id:
                        print(f"\n📝 Installation recorded (ID: {install_id})")
                        print(f"   View details: cortex history show {install_id}")
                    return 1
            else:
                print("\nTo execute these commands, run with --execute flag")
                print("Example: cortex install docker --execute")
            
            return 0
            
        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"API call failed: {str(e)}")
            return 1
        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            return 1

    def update(self, channel: Optional[str] = None, force: bool = False, dry_run: bool = False):
        try:
            channel_enum = UpdateChannel.from_string(channel) if channel else self.update_service.get_channel()
        except ValueError as exc:
            self._print_error(str(exc))
            return 1

        try:
            result = self.update_service.perform_update(force=force, channel=channel_enum, dry_run=dry_run)
        except ChecksumMismatch as exc:
            self._print_error(f"Security check failed: {exc}")
            return 1
        except InstallError as exc:
            self._print_error(f"Installer error: {exc}")
            return 1
        except UpdateError as exc:
            self._print_error(f"Update failed: {exc}")
            return 1
        except Exception as exc:
            self._print_error(f"Unexpected update failure: {exc}")
            return 1

        if not result.release:
            self._print_status("ℹ️", result.message or "Cortex is already up to date.")
            return 0

        release = result.release

        if not result.updated:
            self._print_status("🔔", f"Update available: {release.version.raw} ({release.channel.value})")
            if release.release_notes:
                self._print_status("🆕", "What's new:")
                for line in release.release_notes.strip().splitlines():
                    print(f"   {line}")
            self._print_status("ℹ️", result.message or "Dry run complete.")
            return 0

        self._print_success(f"Update complete! {result.previous_version.raw} → {release.version.raw}")
        self._print_status("🗂️", f"Log saved to {result.log_path}")
        if release.release_notes:
            self._print_status("🆕", "What's new:")
            for line in release.release_notes.strip().splitlines():
                print(f"   {line}")

        return 0

    def _notify_update_if_available(self):
        if os.environ.get("CORTEX_UPDATE_CHECK", "1") in ("0", "false", "False"):
            return

        try:
            result = self.update_service.check_for_updates()
        except Exception:
            return

        if result.update_available and result.release:
            release = result.release
            print(
                f"\n🔔 Cortex update available: {release.version.raw} "
                f"({result.channel.value} channel)\n"
                "   Run 'cortex update' to learn more.\n"
            )

    def show_channel(self):
        channel = self.update_service.get_channel()
        self._print_status("ℹ️", f"Current update channel: {channel.value}")
        return 0

    def set_channel(self, channel: str):
        try:
            channel_enum = UpdateChannel.from_string(channel)
        except ValueError as exc:
            self._print_error(str(exc))
            return 1

        self.update_service.set_channel(channel_enum)
        self._print_success(f"Update channel set to '{channel_enum.value}'")
        return 0


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
    
    # Install command
    install_parser = subparsers.add_parser('install', help='Install software using natural language')
    install_parser.add_argument('software', type=str, help='Software to install (natural language)')
    install_parser.add_argument('--execute', action='store_true', help='Execute the generated commands')
    install_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')
    
    update_parser = subparsers.add_parser('update', help='Check for Cortex updates or upgrade')
    update_parser.add_argument('--channel', choices=[c.value for c in UpdateChannel], help='Update channel to use')
    update_parser.add_argument('--force', action='store_true', help='Force network check')
    update_parser.add_argument('--dry-run', action='store_true', help='Show details without installing')

    channel_parser = subparsers.add_parser('channel', help='Manage Cortex update channel')
    channel_sub = channel_parser.add_subparsers(dest='channel_command', required=True)
    channel_sub.add_parser('show', help='Display current update channel')
    channel_set_parser = channel_sub.add_parser('set', help='Set update channel')
    channel_set_parser.add_argument('channel', choices=[c.value for c in UpdateChannel], help='Channel to use')

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = CortexCLI()
    
    if args.command == 'install':
        return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
    if args.command == 'update':
        return cli.update(channel=args.channel, force=args.force, dry_run=args.dry_run)
    if args.command == 'channel':
        if args.channel_command == 'show':
            return cli.show_channel()
        if args.channel_command == 'set':
            return cli.set_channel(args.channel)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
