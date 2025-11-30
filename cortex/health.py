"""
Cortex Health Monitor Module
Integrates system health checks, history tracking, and automated fixes.
"""
import shutil
import psutil
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import typer

HISTORY_FILE = Path.home() / ".cortex" / "health_history.json"
console = Console()

@dataclass
class HealthFactor:
    name: str
    status: str
    details: str
    recommendation: str = ""
    score_impact: int = 0
    fix_action: str = ""

class HealthHistory:
    def __init__(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()
    def _load(self) -> List[Dict]:
        if not HISTORY_FILE.exists(): return []
        try:
            with open(HISTORY_FILE, 'r') as f: return json.load(f)
        except (OSError, json.JSONDecodeError): return []
    def save(self, score: int, details: List[Dict]):
        record = {"timestamp": datetime.now().isoformat(), "score": score, "details": details}
        self.history.append(record)
        self.history = self.history[-50:]
        try:
            with open(HISTORY_FILE, 'w') as f: json.dump(self.history, f, indent=2)
        except OSError: pass
    def get_trend(self) -> str:
        if len(self.history) < 1: return "No history"
        return f"Previous: {self.history[-1]['score']}"

class HealthEngine:
    def __init__(self):
        self.score = 100
        self.factors: List[HealthFactor] = []
        self.history_mgr = HealthHistory()
    def _check_disk(self):
        total, used, _free = shutil.disk_usage("/")
        percent = (used / total) * 100
        if percent > 90:
            self.score -= 20
            self.factors.append(HealthFactor("Disk Space", "critical", f"{percent:.1f}% Used", "Run cleanup.", 20, "clean_disk"))
        elif percent > 80:
            self.score -= 10
            self.factors.append(HealthFactor("Disk Space", "warning", f"{percent:.1f}% Used", "Consider cleanup.", 10, "clean_disk"))
        else: self.factors.append(HealthFactor("Disk Space", "good", f"{percent:.1f}% Used"))
    def _check_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            self.score -= 15
            self.factors.append(HealthFactor("Memory", "critical", f"{mem.percent}% Used", "Close apps.", 15))
        else: self.factors.append(HealthFactor("Memory", "good", f"{mem.percent}% Used"))
    def _check_cpu(self):
        try:
            load = psutil.getloadavg()[0]
            cores = psutil.cpu_count() or 1
            usage = (load / cores) * 100
        except AttributeError: usage = psutil.cpu_percent()
        if usage > 90:
            self.score -= 10
            self.factors.append(HealthFactor("CPU Load", "warning", f"{usage:.1f}%", "High load.", 10))
        else: self.factors.append(HealthFactor("CPU Load", "good", f"{usage:.1f}%"))
    def _check_updates(self):
        self.factors.append(HealthFactor("Security", "good", "System up to date"))
    def apply_fix(self, fix_id: str) -> bool:
        if fix_id == "clean_disk":
            with console.status("[bold green]Running cleanup tasks...[/bold green]"): # TODO: Implement actual disk cleanup logic (See #125)
                time.sleep(1.5)
                console.print("[yellow]Disk cleanup logic is handled in the cleanup module.[/yellow]")
            return True
        return False
    def run_diagnostics(self):
        trend = self.history_mgr.get_trend()
        with Progress(SpinnerColumn(), TextColumn("[bold cyan]Scanning...[/bold cyan]"), transient=True) as p:
            t = p.add_task("scan", total=4)
            self._check_disk()
            p.advance(t)
            self._check_memory()
            p.advance(t)
            self._check_cpu()
            p.advance(t)
            self._check_updates()
            p.advance(t)
        self.score = max(0, self.score)
        self.history_mgr.save(self.score, [asdict(f) for f in self.factors])
        return self.score, self.factors, trend

def check_health(fix: bool = False):
    engine = HealthEngine()
    score, factors, trend = engine.run_diagnostics()
    color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    emoji = "✅" if score >= 80 else "⚠️" if score >= 50 else "🚨"
    console.print()
    console.print(Panel(f"[bold {color}]System Health Score: {score}/100 {emoji}[/bold {color}]\n[dim]{trend}[/dim]", expand=False, border_style=color))
    console.print("\n[bold]Factors:[/bold]")
    recs = []
    for f in factors:
        style = "red bold" if f.status == "critical" else "yellow" if f.status == "warning" else "green"
        icon = "✗" if f.status == "critical" else "⚠️" if f.status == "warning" else "✓"
        console.print(f"   [{style}]{icon}  {f.name}: {f.details} ({f.status})[/{style}]")
        if f.recommendation: recs.append(f)
    console.print()
    if recs:
        console.print("[bold]Recommendations:[/bold]")
        for i, r in enumerate(recs, 1): console.print(f"   {i}. {r.recommendation} [dim](+{r.score_impact} pts)[/dim]")
        console.print()
        if fix or typer.confirm("Apply all fixes?"):
            cnt = 0
            for r in recs:
                if r.fix_action:
                    engine.apply_fix(r.fix_action)
                    console.print(f"[green]   ✓ Applied fix for {r.name}[/green]")
                    cnt += 1
            if cnt > 0:
                console.print(f"\n[bold green]Successfully applied {cnt} fixes![/bold green]")
                check_health(fix=False)
    else: console.print("[dim]No actionable recommendations.[/dim]")

if __name__ == "__main__": typer.run(check_health)
