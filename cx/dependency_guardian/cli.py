"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1

CLI Entry point for CX Dependency Guardian.
"""

import sys
import asyncio
import logging
import argparse
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .guardian import DependencyGuardian
from .resolver import ConflictResolver

console = Console()
logger = logging.getLogger("cx.dependency_guardian.cli")

async def run_cli(package_name: str) -> int:
    """
    Main execution flow for the SDG CLI.
    AUDIT: Emits structured events for system operation tracking.
    """
    logger.info("AUDIT: CLI Invocation for package '%s'", package_name)
    
    guardian = DependencyGuardian()
    resolver = ConflictResolver()
    
    try:
        with console.status(f"[bold green]Initializing system state...[/bold green]"):
            await guardian.initialize()

        with console.status(f"[bold green]Analyzing dependencies for '{package_name}'...[/bold green]"):
            report = await guardian.simulate_install(package_name)
    except Exception as e:
        logger.exception("AUDIT: Critical failure during CLI execution for '%s'", package_name)
        console.print(f"[bold red]Internal Error:[/bold red] {str(e)}")
        return 1
    
    if not report:
        logger.warning("AUDIT: Simulation failed (Invalid package or environment): %s", package_name)
        console.print(f"[bold red]Error:[/bold red] Could not simulate installation for '{package_name}'. Check package name or system permissions.")
        return 1

    logger.info("AUDIT: Simulation result: %s", report.status)

    if report.status == "SAFE":
        console.print(Panel(f"✅ [bold green]No conflicts detected.[/bold green] '{package_name}' is safe to install.", title="System Health"))
        return 0

    if report.status == "UNKNOWN_STATE":
        console.print(Panel(f"❓ [bold yellow]Unknown System State.[/bold yellow] Could not verify safety for '{package_name}'.", title="Warning"))
        return 1

    # Handle conflicts
    analysis = resolver.resolve(report)
    
    logger.info("AUDIT: Resolution summary: Score=%s, Status=%s, Suggestions=%d", 
                analysis["overall_safety_score"], analysis["status"], len(analysis["suggestions"]))
    
    console.print(Panel(f"🚨 [bold red]CRITICAL:[/bold red] Potential conflicts detected for '{package_name}'", title="Dependency Alert", border_style="red"))
    
    table = Table(title="AI Resolution Suggestions")
    table.add_column("Action", style="cyan")
    table.add_column("Confidence", style="magenta")
    table.add_column("Risk", style="yellow")
    table.add_column("Rationale", style="white")

    for sugg in analysis["suggestions"]:
        table.add_row(sugg["action"], f"{sugg['confidence']*100}%", sugg["risk"], sugg["rationale"])

    console.print(table)
    console.print(f"\n[bold white]Overall Safety Score:[/bold white] {analysis['overall_safety_score']}")
    
    return 0

def main():
    """CLI entry point with argparse support."""
    parser = argparse.ArgumentParser(
        description="CX Dependency Guardian: Predict dependency conflicts before installation."
    )
    parser.add_argument("package_name", help="The name of the Debian package to analyze.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging.")
    
    args = parser.parse_args()
    
    # Configure logging based on flag
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    
    try:
        sys.exit(asyncio.run(run_cli(args.package_name)))
    except KeyboardInterrupt:
        sys.exit(1)

if __name__ == "__main__":
    main()
