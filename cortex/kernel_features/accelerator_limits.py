#!/usr/bin/env python3
"""
Cortex Accelerator-Aware Resource Limits

cgroups v2 wrapper for AI workloads.
"""

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from cortex.utils.db_pool import get_connection_pool

CORTEX_DB = Path.home() / ".cortex/limits.db"
CGROUP_ROOT = Path("/sys/fs/cgroup")


class WorkloadPreset(Enum):
    INFERENCE = "inference"
    TRAINING = "training"
    BATCH = "batch"
    INTERACTIVE = "interactive"


PRESETS = {
    "inference": {"cpu": 400, "memory_gb": 32, "oom_adj": -500, "gpu_pct": 100},
    "training": {"cpu": 1600, "memory_gb": 128, "oom_adj": -800, "gpu_pct": 100},
    "batch": {"cpu": 800, "memory_gb": 64, "oom_adj": 0, "gpu_pct": 80},
    "interactive": {"cpu": 200, "memory_gb": 16, "oom_adj": -200, "gpu_pct": 50},
}


@dataclass
class ResourceLimits:
    name: str
    preset: str = "inference"
    cpu_quota: float = 400.0
    memory_max: int = 32 * 1024**3
    gpu_ids: list[int] = None
    oom_score_adj: int = 0

    def __post_init__(self):
        self.gpu_ids = self.gpu_ids or []

    @classmethod
    def from_preset(cls, name: str, preset: str, gpus: int = 0):
        p = PRESETS.get(preset, PRESETS["inference"])
        return cls(
            name, preset, p["cpu"], int(p["memory_gb"] * 1e9), list(range(gpus)), p["oom_adj"]
        )


class LimitsDatabase:
    def __init__(self):
        CORTEX_DB.parent.mkdir(parents=True, exist_ok=True)
        self._pool = get_connection_pool(str(CORTEX_DB), pool_size=5)
        with self._pool.get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, config TEXT)")

    def save(self, limits: ResourceLimits):
        with self._pool.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?,?)",
                (limits.name, json.dumps(asdict(limits))),
            )

    def get(self, name: str) -> ResourceLimits | None:
        with self._pool.get_connection() as conn:
            row = conn.execute("SELECT config FROM profiles WHERE name=?", (name,)).fetchone()
            return ResourceLimits(**json.loads(row[0])) if row else None

    def list_all(self):
        with self._pool.get_connection() as conn:
            return [
                ResourceLimits(**json.loads(r[0]))
                for r in conn.execute("SELECT config FROM profiles")
            ]


class AcceleratorLimitsManager:
    def __init__(self):
        self.db = LimitsDatabase()

    def create(self, limits: ResourceLimits) -> bool:
        self.db.save(limits)
        print(f"✅ Created profile '{limits.name}' (preset: {limits.preset})")
        return True

    def get_env(self, name: str) -> dict[str, str]:
        limits = self.db.get(name)
        if not limits:
            return {}
        return {"CUDA_VISIBLE_DEVICES": ",".join(map(str, limits.gpu_ids))}

    def status(self):
        profiles = self.db.list_all()
        print(f"\n{'NAME':<20} {'PRESET':<12} {'CPU':<8} {'MEMORY':<10} {'GPUS':<10}")
        print("-" * 65)
        for p in profiles:
            gpus = ",".join(map(str, p.gpu_ids)) or "-"
            print(
                f"{p.name:<20} {p.preset:<12} {p.cpu_quota / 100:.0f}{'':<5} {p.memory_max / 1e9:.0f}G{'':<5} {gpus:<10}"
            )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Accelerator Limits")
    sub = parser.add_subparsers(dest="cmd")

    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--preset", default="inference")
    c.add_argument("--gpus", type=int, default=0)

    sub.add_parser("env").add_argument("name")
    sub.add_parser("status")
    sub.add_parser("list")

    args = parser.parse_args()
    mgr = AcceleratorLimitsManager()

    if args.cmd == "create":
        mgr.create(ResourceLimits.from_preset(args.name, args.preset, args.gpus))
    elif args.cmd == "env":
        for k, v in mgr.get_env(args.name).items():
            print(f"export {k}={v}")
    elif args.cmd in ("status", "list"):
        mgr.status()


if __name__ == "__main__":
    main()
