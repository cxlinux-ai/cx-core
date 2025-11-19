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
from cortex.templates import TemplateManager, Template, TemplateFormat, InstallationStep
from installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus
)


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
    
    def install(self, software: str, execute: bool = False, dry_run: bool = False, template: Optional[str] = None):
        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()
        
        try:
            # If template is specified, use template system
            if template:
                return self._install_from_template(template, execute, dry_run)
            
            # Otherwise, use LLM-based installation
            api_key = self._get_api_key()
            if not api_key:
                return 1
            
            provider = self._get_provider()
            
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
    
    def _install_from_template(self, template_name: str, execute: bool, dry_run: bool):
        """Install from a template."""
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()
        
        try:
            template_manager = TemplateManager()
            
            self._print_status("[*]", f"Loading template: {template_name}...")
            template = template_manager.load_template(template_name)
            
            if not template:
                self._print_error(f"Template '{template_name}' not found")
                self._print_status("[*]", "Available templates:")
                templates = template_manager.list_templates()
                for name, info in templates.items():
                    print(f"  - {name}: {info['description']}")
                return 1
            
            # Display template info
            print(f"\n{template.name} Template:")
            print(f"   {template.description}")
            print(f"\n   Packages:")
            for pkg in template.packages:
                print(f"   - {pkg}")
            
            # Check hardware compatibility
            is_compatible, warnings = template_manager.check_hardware_compatibility(template)
            if warnings:
                print("\n[WARNING] Hardware Compatibility Warnings:")
                for warning in warnings:
                    print(f"   - {warning}")
                if not is_compatible and not dry_run:
                    try:
                        response = input("\n[WARNING] Hardware requirements not met. Continue anyway? (y/N): ")
                        if response.lower() != 'y':
                            print("\n[INFO] Installation aborted by user")
                            return 1
                    except (EOFError, KeyboardInterrupt):
                        # Non-interactive environment or user cancelled
                        print("\n[ERROR] Aborting install: cannot prompt for hardware confirmation in non-interactive mode")
                        print("        Use --dry-run to preview commands, or ensure hardware requirements are met")
                        return 1
            
            # Generate commands
            self._print_status("[*]", "Generating installation commands...")
            commands = template_manager.generate_commands(template)
            
            if not commands:
                self._print_error("No commands generated from template")
                return 1
            
            # Extract packages for tracking
            packages = template.packages if template.packages else history._extract_packages_from_commands(commands)
            
            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL,
                    packages,
                    commands,
                    start_time
                )
            
            print(f"\n[*] Installing {len(packages)} packages...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")
            
            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0
            
            if execute:
                # Convert template steps to coordinator format if available
                if template.steps:
                    plan = [
                        {
                            "command": step.command,
                            "description": step.description,
                            "rollback": step.rollback
                        }
                        for step in template.steps
                    ]
                    coordinator = InstallationCoordinator.from_plan(
                        plan,
                        timeout=300,
                        stop_on_error=True
                    )
                else:
                    def progress_callback(current, total, step):
                        status_emoji = "⏳"
                        if step.status == StepStatus.SUCCESS:
                            status_emoji = "✅"
                        elif step.status == StepStatus.FAILED:
                            status_emoji = "❌"
                        print(f"\n[{current}/{total}] {status_emoji} {step.description}")
                        print(f"  Command: {step.command}")
                    
                    coordinator = InstallationCoordinator(
                        commands=commands,
                        descriptions=[f"Step {i+1}" for i in range(len(commands))],
                        timeout=300,
                        stop_on_error=True,
                        progress_callback=progress_callback
                    )
                
                print("\nExecuting commands...")
                result = coordinator.execute()
                
                if result.success:
                    # Run verification commands if available
                    if template.verification_commands:
                        self._print_status("[*]", "Verifying installation...")
                        verify_results = coordinator.verify_installation(template.verification_commands)
                        all_passed = all(verify_results.values())
                        if not all_passed:
                            print("\n[WARNING] Some verification checks failed:")
                            for cmd, passed in verify_results.items():
                                status = "[OK]" if passed else "[FAIL]"
                                print(f"  {status} {cmd}")
                    
                    # Run post-install commands once
                    if template.post_install:
                        self._print_status("[*]", "Running post-installation steps...")
                        print("\n[*] Post-installation information:")
                        for cmd in template.post_install:
                            subprocess.run(cmd, shell=True)
                    
                    self._print_success(f"{template.name} stack ready!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")
                    
                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n[*] Installation recorded (ID: {install_id})")
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
                print(f"Example: cortex install --template {template_name} --execute")
            
            return 0
            
        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            return 1
    
    def template_list(self):
        """List all available templates."""
        try:
            template_manager = TemplateManager()
            templates = template_manager.list_templates()
            
            if not templates:
                print("No templates found.")
                return 0
            
            print("\nAvailable Templates:")
            print("=" * 80)
            print(f"{'Name':<20} {'Version':<12} {'Type':<12} {'Description':<35}")
            print("=" * 80)
            
            for name, info in sorted(templates.items()):
                desc = info['description'][:33] + "..." if len(info['description']) > 35 else info['description']
                print(f"{name:<20} {info['version']:<12} {info['type']:<12} {desc:<35}")
            
            print(f"\nTotal: {len(templates)} templates")
            return 0
        except Exception as e:
            self._print_error(f"Failed to list templates: {str(e)}")
            return 1
    
    def template_create(self, name: str, interactive: bool = True):
        """Create a new template interactively."""
        try:
            print(f"\n[*] Creating template: {name}")
            
            if interactive:
                description = input("Description: ").strip()
                if not description:
                    self._print_error("Description is required")
                    return 1
                
                version = input("Version (default: 1.0.0): ").strip() or "1.0.0"
                author = input("Author (optional): ").strip() or None
                
                print("\nEnter packages (one per line, empty line to finish):")
                packages = []
                while True:
                    pkg = input("  Package: ").strip()
                    if not pkg:
                        break
                    packages.append(pkg)
                
                # Create template
                from cortex.templates import Template, HardwareRequirements
                template = Template(
                    name=name,
                    description=description,
                    version=version,
                    author=author,
                    packages=packages
                )
                
                # Ask about hardware requirements
                print("\nHardware Requirements (optional):")
                min_ram = input("  Minimum RAM (MB, optional): ").strip()
                min_cores = input("  Minimum CPU cores (optional): ").strip()
                min_storage = input("  Minimum storage (MB, optional): ").strip()
                
                if min_ram or min_cores or min_storage:
                    hw_req = HardwareRequirements(
                        min_ram_mb=int(min_ram) if min_ram else None,
                        min_cores=int(min_cores) if min_cores else None,
                        min_storage_mb=int(min_storage) if min_storage else None
                    )
                    template.hardware_requirements = hw_req
                
                # Save template
                template_manager = TemplateManager()
                template_path = template_manager.save_template(template, name)
                
                self._print_success(f"Template '{name}' created successfully!")
                print(f"  Saved to: {template_path}")
                return 0
            else:
                self._print_error("Non-interactive template creation not yet supported")
                return 1
                
        except Exception as e:
            self._print_error(f"Failed to create template: {str(e)}")
            return 1
    
    def template_import(self, file_path: str, name: Optional[str] = None):
        """Import a template from a file."""
        try:
            template_manager = TemplateManager()
            template = template_manager.import_template(file_path, name)
            
            # Save to user templates
            save_name = name or template.name
            template_path = template_manager.save_template(template, save_name)
            
            self._print_success(f"Template '{save_name}' imported successfully!")
            print(f"  Saved to: {template_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to import template: {str(e)}")
            return 1
    
    def template_export(self, name: str, file_path: str, format: str = "yaml"):
        """Export a template to a file."""
        try:
            template_manager = TemplateManager()
            template_format = TemplateFormat.YAML if format.lower() == "yaml" else TemplateFormat.JSON
            export_path = template_manager.export_template(name, file_path, template_format)
            
            self._print_success(f"Template '{name}' exported successfully!")
            print(f"  Saved to: {export_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to export template: {str(e)}")
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
  cortex install --template lamp --execute
  cortex template list
  cortex template create my-stack
  cortex template import template.yaml
  cortex template export lamp my-template.yaml
  cortex history
  cortex history show <id>
  cortex rollback <id>

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Install command
    install_parser = subparsers.add_parser('install', help='Install software using natural language or template')
    install_parser.add_argument('software', type=str, nargs='?', help='Software to install (natural language)')
    install_parser.add_argument('--template', type=str, help='Install from template (e.g., lamp, mean, mern)')
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
    
    # Template command
    template_parser = subparsers.add_parser('template', help='Manage installation templates')
    template_subparsers = template_parser.add_subparsers(dest='template_action', help='Template actions')
    
    # Template list
    template_list_parser = template_subparsers.add_parser('list', help='List all available templates')
    
    # Template create
    template_create_parser = template_subparsers.add_parser('create', help='Create a new template')
    template_create_parser.add_argument('name', type=str, help='Template name')
    
    # Template import
    template_import_parser = template_subparsers.add_parser('import', help='Import a template from file')
    template_import_parser.add_argument('file_path', type=str, help='Path to template file')
    template_import_parser.add_argument('--name', type=str, help='Optional new name for the template')
    
    # Template export
    template_export_parser = template_subparsers.add_parser('export', help='Export a template to file')
    template_export_parser.add_argument('name', type=str, help='Template name to export')
    template_export_parser.add_argument('file_path', type=str, help='Destination file path')
    template_export_parser.add_argument('--format', choices=['yaml', 'json'], default='yaml', help='Export format')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = CortexCLI()
    
    try:
        if args.command == 'install':
            if args.template:
                return cli.install("", execute=args.execute, dry_run=args.dry_run, template=args.template)
            elif args.software:
                return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
            else:
                install_parser.print_help()
                return 1
        elif args.command == 'history':
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == 'rollback':
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == 'template':
            if args.template_action == 'list':
                return cli.template_list()
            elif args.template_action == 'create':
                return cli.template_create(args.name)
            elif args.template_action == 'import':
                return cli.template_import(args.file_path, args.name)
            elif args.template_action == 'export':
                return cli.template_export(args.name, args.file_path, args.format)
            else:
                template_parser.print_help()
                return 1
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
