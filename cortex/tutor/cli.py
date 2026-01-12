"""
CLI for Intelligent Tutor.

Provides command-line interface for the AI-powered package tutor.

Usage:
    tutor <package>           Start interactive tutor for a package
    tutor --list              List packages you've studied
    tutor --progress          View learning progress
    tutor --reset [package]   Reset progress
"""

import argparse
import sys

from cortex.tutor import __version__
from cortex.tutor.branding import (
    console,
    get_user_input,
    print_banner,
    print_error_panel,
    print_progress_summary,
    print_success_panel,
    print_table,
    tutor_print,
)
from cortex.tutor.config import Config
from cortex.tutor.memory.sqlite_store import SQLiteStore
from cortex.tutor.tools.deterministic.validators import validate_package_name

# Default number of topics per package for progress tracking
DEFAULT_TUTOR_TOPICS = 5


def create_parser() -> argparse.ArgumentParser:
    """
    Create the argument parser for the CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="tutor",
        description="AI-Powered Installation Tutor for Cortex Linux",
        epilog="Example: tutor docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Version
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Verbose mode
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    # Package name (positional, optional)
    parser.add_argument(
        "package",
        nargs="?",
        help="Package name to learn about",
    )

    # List packages studied
    parser.add_argument(
        "--list",
        action="store_true",
        help="List packages you've studied",
    )

    # Progress
    parser.add_argument(
        "--progress",
        action="store_true",
        help="View learning progress",
    )

    # Reset progress
    parser.add_argument(
        "--reset",
        nargs="?",
        const="__all__",
        help="Reset progress (optionally for a specific package)",
    )

    # Force fresh (no cache)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Skip cache and generate fresh content",
    )

    # Quick question mode
    parser.add_argument(
        "-q",
        "--question",
        type=str,
        help="Ask a quick question about the package",
    )

    return parser


def cmd_teach(package: str, verbose: bool = False, fresh: bool = False) -> int:
    """
    Start an interactive tutoring session.

    Args:
        package: Package name to teach.
        verbose: Enable verbose output.
        fresh: Skip cache.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    # Validate package name
    is_valid, error = validate_package_name(package)
    if not is_valid:
        print_error_panel(f"Invalid package name: {error}")
        return 1

    try:
        # Lazy import - only load when needed (requires API key)
        from cortex.tutor.agents.tutor_agent import InteractiveTutor

        # Start interactive tutor
        interactive = InteractiveTutor(package, force_fresh=fresh)
        interactive.start()
        return 0

    except ValueError as e:
        print_error_panel(str(e))
        return 1
    except KeyboardInterrupt:
        console.print()
        tutor_print("Session ended", "info")
        return 0
    except Exception as e:
        print_error_panel(f"An error occurred: {e}")
        if verbose:
            import traceback

            console.print_exception()
        return 1


def cmd_question(package: str, question: str, verbose: bool = False) -> int:
    """
    Answer a quick question about a package.

    Args:
        package: Package context.
        question: The question.
        verbose: Enable verbose output.

    Returns:
        Exit code.
    """
    # Validate inputs
    is_valid, error = validate_package_name(package)
    if not is_valid:
        print_error_panel(f"Invalid package name: {error}")
        return 1

    try:
        # Lazy import - only load when needed (requires API key)
        from cortex.tutor.agents.tutor_agent import TutorAgent

        agent = TutorAgent(verbose=verbose)
        result = agent.ask(package, question)

        if result.get("validation_passed"):
            content = result.get("content", {})

            # Print answer
            console.print("\n[bold cyan]Answer:[/bold cyan]")
            console.print(content.get("answer", "No answer available"))

            # Print code example if available
            if content.get("code_example"):
                from cortex.tutor.branding import print_code_example

                ex = content["code_example"]
                print_code_example(
                    ex.get("code", ""),
                    ex.get("language", "bash"),
                    "Example",
                )

            # Print related topics
            related = content.get("related_topics", [])
            if related:
                console.print(f"\n[dim]Related topics: {', '.join(related)}[/dim]")

            return 0
        else:
            print_error_panel("Could not answer the question")
            return 1

    except Exception as e:
        print_error_panel(f"Error: {e}")
        return 1


def cmd_list_packages(_verbose: bool = False) -> int:
    """
    List packages that have been studied.

    Args:
        _verbose: Enable verbose output (reserved for future use).

    Returns:
        Exit code.
    """
    try:
        # Use SQLiteStore directly - no API key needed
        config = Config.from_env(require_api_key=False)
        store = SQLiteStore(config.get_db_path())
        packages = store.get_packages_studied()

        if not packages:
            tutor_print("You haven't studied any packages yet.", "info")
            tutor_print("Try: cortex tutor docker", "info")
            return 0

        console.print("\n[bold]Packages Studied:[/bold]")
        for pkg in packages:
            console.print(f"  \u2022 {pkg}")

        console.print(f"\n[dim]Total: {len(packages)} packages[/dim]")
        return 0

    except Exception as e:
        print_error_panel(f"Error: {e}")
        return 1


def _show_package_progress(store: SQLiteStore, package: str) -> None:
    """Display progress for a specific package."""
    stats = store.get_completion_stats(package)
    if stats:
        print_progress_summary(
            stats.get("completed", 0),
            stats.get("total", 0) or DEFAULT_TUTOR_TOPICS,
            package,
        )
        console.print(f"[dim]Average score: {stats.get('avg_score', 0):.0%}[/dim]")
        console.print(f"[dim]Total time: {stats.get('total_time_seconds', 0) // 60} minutes[/dim]")
    else:
        tutor_print(f"No progress found for {package}", "info")


def _show_all_progress(store: SQLiteStore) -> bool:
    """Display progress for all packages. Returns True if progress exists."""
    progress_list = store.get_all_progress()

    if not progress_list:
        tutor_print("No learning progress yet.", "info")
        return False

    # Group by package (progress_list contains Pydantic models)
    by_package: dict[str, list] = {}
    for p in progress_list:
        pkg = p.package_name
        if pkg not in by_package:
            by_package[pkg] = []
        by_package[pkg].append(p)

    # Build table rows
    rows = []
    for pkg, topics in by_package.items():
        completed = sum(1 for t in topics if t.completed)
        total = len(topics)
        avg_score = sum(t.score for t in topics) / total if total else 0
        rows.append([pkg, f"{completed}/{total}", f"{avg_score:.0%}"])

    print_table(["Package", "Progress", "Avg Score"], rows, "Learning Progress")
    return True


def cmd_progress(package: str | None = None, _verbose: bool = False) -> int:
    """
    Show learning progress.

    Args:
        package: Optional package filter.
        _verbose: Enable verbose output (reserved for future use).

    Returns:
        Exit code.
    """
    try:
        config = Config.from_env(require_api_key=False)
        store = SQLiteStore(config.get_db_path())

        if package:
            _show_package_progress(store, package)
        else:
            _show_all_progress(store)

        return 0

    except Exception as e:
        print_error_panel(f"Error: {e}")
        return 1


def cmd_reset(package: str | None = None, _verbose: bool = False) -> int:
    """
    Reset learning progress.

    Args:
        package: Optional package to reset. If None, resets all.
        _verbose: Enable verbose output (reserved for future use).

    Returns:
        Exit code.
    """
    try:
        # Confirm reset
        scope = package if package and package != "__all__" else "all packages"

        confirm = get_user_input(f"Reset progress for {scope}? (y/N)")
        if confirm.lower() != "y":
            tutor_print("Reset cancelled", "info")
            return 0

        # Use SQLiteStore directly - no API key needed
        config = Config.from_env(require_api_key=False)
        store = SQLiteStore(config.get_db_path())

        pkg = package if package != "__all__" else None
        count = store.reset_progress(pkg)

        print_success_panel(f"Reset {count} progress records")
        return 0

    except Exception as e:
        print_error_panel(f"Error: {e}")
        return 1


def main(args: list[str] | None = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        args: Command line arguments (uses sys.argv if None).

    Returns:
        Exit code.
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    # Print banner for interactive mode
    if parsed.package and not parsed.question:
        print_banner()

    # Handle commands
    if parsed.list:
        return cmd_list_packages(parsed.verbose)

    if parsed.progress:
        return cmd_progress(parsed.package, parsed.verbose)

    if parsed.reset:
        return cmd_reset(
            parsed.reset if parsed.reset != "__all__" else None,
            parsed.verbose,
        )

    if parsed.package and parsed.question:
        return cmd_question(parsed.package, parsed.question, parsed.verbose)

    if parsed.package:
        return cmd_teach(parsed.package, parsed.verbose, parsed.fresh)

    # No command specified - show help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
