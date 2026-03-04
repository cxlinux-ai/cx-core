"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1

CLI Entry point for CX Dependency Guardian.
"""

import sys
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .guardian import DependencyGuardian
from .resolver import ConflictResolver

console = Console()

def run_cli(package_name: str):
    guardian = DependencyGuardian()
    resolver = ConflictResolver()
    
    with console.status(f"[bold green]Analyzing system state for '{package_name}'...[/bold green]"):
        report = guardian.simulate_install(package_name)
    
    if not report:
        console.print(f"[bold red]Error:[/bold red] Could not simulate installation for '{package_name}'. Check package name.")
        return

    if report.status == "SAFE":
        console.print(Panel(f"✅ [bold green]No conflicts detected.[/bold green] '{package_name}' is safe to install.", title="System Health"))
        return

    # Handle conflicts
    analysis = resolver.resolve(report)
    
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("Usage: python3 -m cx.dependency_guardian.cli <package_name>")
    else:
        run_cli(sys.argv[1])
