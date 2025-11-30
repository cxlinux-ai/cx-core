import sys
import os
import argparse
import time
from typing import List, Optional
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter
from installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus
)
from cortex.user_preferences import (
    PreferencesManager,
    print_all_preferences,
    format_preference_value
)
    PreferencesManager,
    print_all_preferences,
    format_preference_value
)


class CortexCLI:
    def __init__(self):
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        self.prefs_manager = None  # Lazy initialization
    
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

    def history(self, limit: int = 20, status: Optional[str] = None, show_id: Optional[str] = None):
        """Show installation history"""
        history = InstallationHistory()
        
        try:
            if show_id:
                # Show specific installation
                record = history.get_installation(show_id)
                
                if not record:
                    self._print_error(f"Installation {show_id} not found")
                    return 1
                
                print(f"\nInstallation Details: {record.id}")
                print("=" * 60)
                print(f"Timestamp: {record.timestamp}")
                print(f"Operation: {record.operation_type.value}")
                print(f"Status: {record.status.value}")
                if record.duration_seconds:
                    print(f"Duration: {record.duration_seconds:.2f}s")
                else:
                    print("Duration: N/A")
                print(f"\nPackages: {', '.join(record.packages)}")
                
                if record.error_message:
                    print(f"\nError: {record.error_message}")
                
                if record.commands_executed:
                    print(f"\nCommands executed:")
                    for cmd in record.commands_executed:
                        print(f"  {cmd}")
                
                print(f"\nRollback available: {record.rollback_available}")
                return 0
            else:
                # List history
                status_filter = InstallationStatus(status) if status else None
                records = history.get_history(limit, status_filter)
                
                if not records:
                    print("No installation records found.")
                    return 0
                
                print(f"\n{'ID':<18} {'Date':<20} {'Operation':<12} {'Packages':<30} {'Status':<15}")
                print("=" * 100)
                
                for r in records:
                    date = r.timestamp[:19].replace('T', ' ')
                    packages = ', '.join(r.packages[:2])
                    if len(r.packages) > 2:
                        packages += f" +{len(r.packages)-2}"
                    
                    print(f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}")
                
                return 0
        except Exception as e:
            self._print_error(f"Failed to retrieve history: {str(e)}")
            return 1

    def rollback(self, install_id: str, dry_run: bool = False):
        """Rollback an installation"""
        history = InstallationHistory()
        
        try:
            success, message = history.rollback(install_id, dry_run)
            
            if dry_run:
                print("\nRollback actions (dry run):")
                print(message)
                return 0
            elif success:
                self._print_success(message)
                return 0
            else:
                self._print_error(message)
                return 1
        except Exception as e:
            self._print_error(f"Rollback failed: {str(e)}")
            return 1

    def _get_prefs_manager(self):
        """Lazy initialize preferences manager"""
        if self.prefs_manager is None:
            self.prefs_manager = PreferencesManager()
        return self.prefs_manager

    def check_pref(self, key: Optional[str] = None):
        """Check/display user preferences"""
        manager = self._get_prefs_manager()
        
        try:
            if key:
                # Show specific preference
                value = manager.get(key)
                if value is None:
                    self._print_error(f"Preference key '{key}' not found")
                    print("\nAvailable preference keys:")
                    print("  - verbosity")
                    print("  - theme")
                    print("  - language")
                    print("  - timezone")
                    print("  - confirmations.before_install")
                    print("  - confirmations.before_remove")
                    print("  - confirmations.before_upgrade")
                    print("  - confirmations.before_system_changes")
                    print("  - auto_update.check_on_start")
                    print("  - auto_update.auto_install")
                    print("  - auto_update.frequency_hours")
                    print("  - ai.model")
                    print("  - ai.creativity")
                    print("  - ai.explain_steps")
                    print("  - ai.suggest_alternatives")
                    print("  - ai.learn_from_history")
                    print("  - ai.max_suggestions")
                    print("  - packages.default_sources")
                    print("  - packages.prefer_latest")
                    print("  - packages.auto_cleanup")
                    print("  - packages.backup_before_changes")
                    return 1
                
                print(f"\n{key} = {format_preference_value(value)}")
                return 0
            else:
                # Show all preferences
                print_all_preferences(manager)
                
                # Show validation status
                print("\nValidation Status:")
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    print("✅ Configuration is valid")
                
                # Show config info
                info = manager.get_config_info()
                print(f"\nConfiguration file: {info['config_path']}")
                print(f"File size: {info['config_size_bytes']} bytes")
                if info['last_modified']:
                    print(f"Last modified: {info['last_modified']}")
                
                return 0
                
        except Exception as e:
            self._print_error(f"Failed to read preferences: {str(e)}")
            return 1

    def edit_pref(self, action: str, key: Optional[str] = None, value: Optional[str] = None):
        """Edit user preferences (add/set, delete/remove, list)"""
        manager = self._get_prefs_manager()
        
        try:
            if action in ['add', 'set', 'update']:
                # Set/update a preference
                if not key:
                    self._print_error("Key is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    print("Example: cortex edit-pref set ai.model gpt-4")
                    return 1
                
                if not value:
                    self._print_error("Value is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    return 1
                
                # Get current value for comparison
                old_value = manager.get(key)
                
                # Set new value
                manager.set(key, value)
                
                self._print_success(f"Updated {key}")
                if old_value is not None:
                    print(f"  Old value: {format_preference_value(old_value)}")
                print(f"  New value: {format_preference_value(manager.get(key))}")
                
                # Validate after change
                errors = manager.validate()
                if errors:
                    print("\n⚠️  Warning: Configuration has validation errors:")
                    for error in errors:
                        print(f"  - {error}")
                    print("\nYou may want to fix these issues.")
                
                return 0
                
            elif action in ['delete', 'remove', 'reset-key']:
                # Reset a specific key to default
                if not key:
                    self._print_error("Key is required for delete/remove/reset-key action")
                    print("Usage: cortex edit-pref delete <key>")
                    print("Example: cortex edit-pref delete ai.model")
                    return 1
                
                # To "delete" a key, we reset entire config and reload (since we can't delete individual keys)
                # Instead, we'll reset to the default value for that key
                print(f"Resetting {key} to default value...")
                
                # Create a new manager with defaults
                defaults = UserPreferences()
                
                # Get the default value
                parts = key.split('.')
                obj = defaults
                for part in parts:
                    obj = getattr(obj, part)
                default_value = obj
                
                # Set to default
                manager.set(key, format_preference_value(default_value))
                
                self._print_success(f"Reset {key} to default")
                print(f"  Value: {format_preference_value(manager.get(key))}")
                
                return 0
                
            elif action in ['list', 'show', 'display']:
                # List all preferences (same as check-pref)
                return self.check_pref()
                
            elif action == 'reset-all':
                # Reset all preferences to defaults
                confirm = input("⚠️  This will reset ALL preferences to defaults. Continue? (yes/no): ")
                if confirm.lower() not in ['yes', 'y']:
                    print("Operation cancelled.")
                    return 0
                
                manager.reset()
                self._print_success("All preferences reset to defaults")
                return 0
                
            elif action == 'validate':
                # Validate configuration
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    self._print_success("Configuration is valid")
                    return 0
                    
            elif action == 'export':
                # Export preferences to file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for export action")
                    print("Usage: cortex edit-pref export <filepath>")
                    print("Example: cortex edit-pref export ~/cortex-prefs.json")
                    return 1
                
                from pathlib import Path
                manager.export_json(Path(key))
                return 0
                
            elif action == 'import':
                # Import preferences from file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for import action")
                    print("Usage: cortex edit-pref import <filepath>")
                    print("Example: cortex edit-pref import ~/cortex-prefs.json")
                    return 1
                
                from pathlib import Path
                filepath = Path(key)
                if not filepath.exists():
                    self._print_error(f"File not found: {filepath}")
                    return 1
                
                manager.import_json(filepath)
                return 0
                
            else:
                self._print_error(f"Unknown action: {action}")
                print("\nAvailable actions:")
                print("  set/add/update <key> <value>  - Set a preference value")
                print("  delete/remove <key>           - Reset a preference to default")
                print("  list/show/display             - Display all preferences")
                print("  reset-all                     - Reset all preferences to defaults")
                print("  validate                      - Validate configuration")
                print("  export <filepath>             - Export preferences to JSON")
                print("  import <filepath>             - Import preferences from JSON")
                return 1
                
        except AttributeError as e:
            self._print_error(f"Invalid preference key: {key}")
            print("Use 'cortex check-pref' to see available keys")
            return 1
        except Exception as e:
            self._print_error(f"Failed to edit preferences: {str(e)}")
            import traceback
            traceback.print_exc()
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
  cortex history
  cortex history show <id>
  cortex rollback <id>
  cortex check-pref
  cortex check-pref ai.model
  cortex edit-pref set ai.model gpt-4
  cortex edit-pref delete theme
  cortex edit-pref reset-all

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
    
    # History command
    history_parser = subparsers.add_parser('history', help='View installation history')
    history_parser.add_argument('--limit', type=int, default=20, help='Number of records to show')
    history_parser.add_argument('--status', choices=['success', 'failed', 'rolled_back', 'in_progress'], 
                               help='Filter by status')
    history_parser.add_argument('show_id', nargs='?', help='Show details for specific installation ID')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback an installation')
    rollback_parser.add_argument('id', help='Installation ID to rollback')
    rollback_parser.add_argument('--dry-run', action='store_true', help='Show rollback actions without executing')
    
    # Check preferences command
    check_pref_parser = subparsers.add_parser('check-pref', help='Check/display user preferences')
    check_pref_parser.add_argument('key', nargs='?', help='Specific preference key to check (optional)')
    
    # Edit preferences command
    edit_pref_parser = subparsers.add_parser('edit-pref', help='Edit user preferences')
    edit_pref_parser.add_argument('action', 
                                  choices=['set', 'add', 'update', 'delete', 'remove', 'reset-key', 
                                          'list', 'show', 'display', 'reset-all', 'validate', 'export', 'import'],
                                  help='Action to perform')
    edit_pref_parser.add_argument('key', nargs='?', help='Preference key or filepath (for export/import)')
    edit_pref_parser.add_argument('value', nargs='?', help='Preference value (for set/add/update)')
    health_parser = subparsers.add_parser('health', help='System health')
    health_parser.add_argument('--fix', action='store_true')
    # Health command

    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = CortexCLI()
    
    try:
        if args.command == 'install':
            return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
        elif args.command == 'history':
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == 'rollback':
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == 'check-pref':
            return cli.check_pref(key=args.key)
        elif args.command == 'edit-pref':
            return cli.edit_pref(action=args.action, key=args.key, value=args.value)
        elif args.command == 'health':
            from cortex.health import check_health
            check_health(fix=args.fix)
            return 0
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())