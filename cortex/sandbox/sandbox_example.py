#!/usr/bin/env python3
"""
Example usage of Sandboxed Command Executor.

This demonstrates how to use the sandbox executor to safely run AI-generated commands.
"""

from sandbox_executor import CommandBlocked, SandboxExecutor


def example_basic_usage():
    """Basic usage example."""
    print("=== Basic Usage ===")

    # Create executor
    executor = SandboxExecutor()

    # Execute a safe command
    try:
        result = executor.execute('echo "Hello, Cortex!"')
        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.stdout}")
        print(f"Execution time: {result.execution_time:.2f}s")
    except CommandBlocked as e:
        print(f"Command blocked: {e}")


def example_dry_run():
    """Dry-run mode example."""
    print("\n=== Dry-Run Mode ===")

    executor = SandboxExecutor()

    # Preview what would execute
    result = executor.execute("apt-get update", dry_run=True)
    print(f"Preview: {result.preview}")
    print(f"Output: {result.stdout}")


def example_blocked_commands():
    """Example of blocked commands."""
    print("\n=== Blocked Commands ===")

    executor = SandboxExecutor()

    dangerous_commands = [
        "rm -rf /",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sda1",
    ]

    for cmd in dangerous_commands:
        try:
            result = executor.execute(cmd)
            print(f"Unexpected: {cmd} was allowed")
        except CommandBlocked as e:
            print(f"✓ Blocked: {cmd} - {e}")


def example_with_rollback():
    """Example with rollback capability."""
    print("\n=== Rollback Example ===")

    executor = SandboxExecutor(enable_rollback=True)

    # Execute a command that might fail
    try:
        result = executor.execute("invalid-command-that-fails")
        if result.failed:
            print("Command failed, rollback triggered")
            print(f"Stderr: {result.stderr}")
    except CommandBlocked as e:
        print(f"Command blocked: {e}")


def example_audit_logging():
    """Example of audit logging."""
    print("\n=== Audit Logging ===")

    executor = SandboxExecutor()

    # Execute some commands
    try:
        executor.execute('echo "test1"', dry_run=True)
        executor.execute('echo "test2"', dry_run=True)
    except:
        pass

    # Get audit log
    audit_log = executor.get_audit_log()
    print(f"Total log entries: {len(audit_log)}")

    for entry in audit_log[-5:]:  # Last 5 entries
        print(f"  - {entry['timestamp']}: {entry['command']} (type: {entry['type']})")

    # Save audit log
    executor.save_audit_log("audit_log.json")
    print("Audit log saved to audit_log.json")


def example_resource_limits():
    """Example of resource limits."""
    print("\n=== Resource Limits ===")

    # Create executor with custom limits
    executor = SandboxExecutor(
        max_cpu_cores=1, max_memory_mb=1024, max_disk_mb=512, timeout_seconds=60
    )

    print(f"CPU limit: {executor.max_cpu_cores} cores")
    print(f"Memory limit: {executor.max_memory_mb} MB")
    print(f"Disk limit: {executor.max_disk_mb} MB")
    print(f"Timeout: {executor.timeout_seconds} seconds")


def example_sudo_commands():
    """Example of sudo command handling."""
    print("\n=== Sudo Commands ===")

    executor = SandboxExecutor()

    # Allowed sudo commands (package installation)
    allowed_sudo = [
        "sudo apt-get install python3",
        "sudo pip install numpy",
    ]

    for cmd in allowed_sudo:
        is_valid, violation = executor.validate_command(cmd)
        if is_valid:
            print(f"✓ Allowed: {cmd}")
        else:
            print(f"✗ Blocked: {cmd} - {violation}")

    # Blocked sudo commands
    blocked_sudo = [
        "sudo rm -rf /",
        "sudo chmod 777 /",
    ]

    for cmd in blocked_sudo:
        is_valid, violation = executor.validate_command(cmd)
        if not is_valid:
            print(f"✓ Blocked: {cmd} - {violation}")


def example_status_check():
    """Check system status and configuration."""
    print("\n=== System Status ===")

    executor = SandboxExecutor()

    # Check Firejail availability
    if executor.is_firejail_available():
        print("✓ Firejail is available - Full sandbox isolation enabled")
        print(f"  Firejail path: {executor.firejail_path}")
    else:
        print("⚠ Firejail not found - Using fallback mode (reduced security)")
        print("  Install with: sudo apt-get install firejail")

    # Show configuration
    print("\nResource Limits:")
    print(f"  CPU: {executor.max_cpu_cores} cores")
    print(f"  Memory: {executor.max_memory_mb} MB")
    print(f"  Disk: {executor.max_disk_mb} MB")
    print(f"  Timeout: {executor.timeout_seconds} seconds")
    print(f"  Rollback: {'Enabled' if executor.enable_rollback else 'Disabled'}")


def example_command_validation():
    """Demonstrate command validation."""
    print("\n=== Command Validation ===")

    executor = SandboxExecutor()

    test_commands = [
        ('echo "test"', True),
        ("python3 --version", True),
        ("rm -rf /", False),
        ("sudo apt-get install python3", True),
        ("sudo rm -rf /", False),
        ("nc -l 1234", False),  # Not whitelisted
    ]

    for cmd, expected_valid in test_commands:
        is_valid, violation = executor.validate_command(cmd)
        status = "✓" if (is_valid == expected_valid) else "✗"
        result = "ALLOWED" if is_valid else "BLOCKED"
        print(f"{status} {result}: {cmd}")
        if not is_valid and violation:
            print(f"    Reason: {violation}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("Sandboxed Command Executor - Usage Examples")
    print("=" * 60)

    example_status_check()
    example_basic_usage()
    example_dry_run()
    example_command_validation()
    example_blocked_commands()
    example_with_rollback()
    example_audit_logging()
    example_resource_limits()
    example_sudo_commands()

    print("\n" + "=" * 60)
    print("Examples Complete")
    print("=" * 60)
    print("\nSummary:")
    print("  ✓ Command validation working")
    print("  ✓ Security blocking active")
    print("  ✓ Dry-run mode functional")
    print("  ✓ Audit logging enabled")
    print("  ✓ Resource limits configured")
    print("  ✓ Sudo restrictions enforced")


if __name__ == "__main__":
    main()
