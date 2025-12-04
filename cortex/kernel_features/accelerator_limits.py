#!/usr/bin/env python3
"""
Cortex Accelerator-Aware Resource Limits

cgroups v2 wrapper for AI workloads with preset profiles for inference,
training, batch, and interactive workloads.

Features:
- cgroups v2 unified hierarchy support
- Workload presets with sensible defaults
- NVIDIA GPU isolation via environment variables
- OOM score adjustment for priority
- CPU quota, weight, and affinity
- Memory hard and soft limits
- User mode delegation support
"""

import os
import json
import sqlite3
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
import logging

# Configuration
CORTEX_DB = Path.home() / ".cortex/limits.db"
CGROUP_ROOT = Path("/sys/fs/cgroup")
CORTEX_CGROUP = "cortex.slice"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class WorkloadPreset(Enum):
    """Predefined workload configurations optimized for AI tasks."""
    INFERENCE = "inference"
    TRAINING = "training"
    BATCH = "batch"
    INTERACTIVE = "interactive"


# Preset configurations
# CPU values are in percentage (100 = 1 core)
PRESETS = {
    "inference": {
        "cpu_quota": 400,       # 4 cores
        "cpu_weight": 100,      # normal priority
        "memory_gb": 32,
        "memory_high_gb": 28,   # soft limit
        "oom_score_adj": -500,
        "gpu_percent": 100,
        "description": "Low-latency serving"
    },
    "training": {
        "cpu_quota": 1600,      # 16 cores
        "cpu_weight": 150,      # higher priority
        "memory_gb": 128,
        "memory_high_gb": 120,
        "oom_score_adj": -800,
        "gpu_percent": 100,
        "description": "Long training jobs"
    },
    "batch": {
        "cpu_quota": 800,       # 8 cores
        "cpu_weight": 50,       # lower priority
        "memory_gb": 64,
        "memory_high_gb": 56,
        "oom_score_adj": 0,
        "gpu_percent": 80,
        "description": "Background processing"
    },
    "interactive": {
        "cpu_quota": 200,       # 2 cores
        "cpu_weight": 120,      # slightly higher for responsiveness
        "memory_gb": 16,
        "memory_high_gb": 14,
        "oom_score_adj": -200,
        "gpu_percent": 50,
        "description": "Development"
    },
}


@dataclass
class ResourceLimits:
    """Resource limit configuration for a workload profile."""
    name: str
    preset: str = "inference"
    cpu_quota: float = 400.0       # percentage (100 = 1 core)
    cpu_weight: int = 100          # 1-10000, default 100
    memory_max: int = 32 * 1024**3 # hard limit in bytes
    memory_high: int = 28 * 1024**3 # soft limit in bytes
    gpu_ids: List[int] = field(default_factory=list)
    gpu_percent: int = 100
    oom_score_adj: int = 0         # -1000 to 1000
    cpu_affinity: List[int] = field(default_factory=list)  # specific CPUs
    cgroup_path: str = ""

    def __post_init__(self):
        if self.gpu_ids is None:
            self.gpu_ids = []
        if self.cpu_affinity is None:
            self.cpu_affinity = []
        if not self.cgroup_path:
            self.cgroup_path = f"{CORTEX_CGROUP}/{self.name}"

    @classmethod
    def from_preset(cls, name: str, preset: str, gpus: int = 0) -> 'ResourceLimits':
        """Create ResourceLimits from a preset configuration."""
        p = PRESETS.get(preset, PRESETS["inference"])
        return cls(
            name=name,
            preset=preset,
            cpu_quota=p["cpu_quota"],
            cpu_weight=p["cpu_weight"],
            memory_max=int(p["memory_gb"] * 1024**3),
            memory_high=int(p["memory_high_gb"] * 1024**3),
            gpu_ids=list(range(gpus)) if gpus > 0 else [],
            gpu_percent=p["gpu_percent"],
            oom_score_adj=p["oom_score_adj"]
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ResourceLimits':
        """Create from dictionary."""
        return cls(**data)


class LimitsDatabase:
    """SQLite-based storage for resource limit profiles."""

    def __init__(self, db_path: Path = CORTEX_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applied_pids (
                    pid INTEGER,
                    profile_name TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (pid, profile_name)
                )
            """)

    def save(self, limits: ResourceLimits) -> bool:
        """Save or update a profile."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (name, config, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (limits.name, json.dumps(limits.to_dict()))
            )
        return True

    def get(self, name: str) -> Optional[ResourceLimits]:
        """Retrieve a profile by name."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return ResourceLimits.from_dict(json.loads(row[0]))
        return None

    def delete(self, name: str) -> bool:
        """Delete a profile."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM profiles WHERE name = ?", (name,))
            conn.execute("DELETE FROM applied_pids WHERE profile_name = ?", (name,))
        return True

    def list_all(self) -> List[ResourceLimits]:
        """List all profiles."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT config FROM profiles").fetchall()
            return [ResourceLimits.from_dict(json.loads(r[0])) for r in rows]

    def record_pid(self, pid: int, profile_name: str):
        """Record that a PID has been assigned to a profile."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO applied_pids (pid, profile_name) VALUES (?, ?)",
                (pid, profile_name)
            )

    def get_pids(self, profile_name: str) -> List[int]:
        """Get PIDs assigned to a profile."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT pid FROM applied_pids WHERE profile_name = ?",
                (profile_name,)
            ).fetchall()
            return [r[0] for r in rows]


class CgroupsV2Controller:
    """Interface to cgroups v2 filesystem."""

    def __init__(self, root: Path = CGROUP_ROOT):
        self.root = root
        self.cortex_root = root / CORTEX_CGROUP

    def is_available(self) -> bool:
        """Check if cgroups v2 is available."""
        return (self.root / "cgroup.controllers").exists()

    def is_user_delegated(self) -> bool:
        """Check if user delegation is enabled."""
        user_slice = self.root / f"user.slice/user-{os.getuid()}.slice"
        if user_slice.exists():
            subtree = user_slice / "cgroup.subtree_control"
            if subtree.exists():
                return True
        return os.getuid() == 0

    def get_available_controllers(self) -> List[str]:
        """Get list of available controllers."""
        controllers_file = self.root / "cgroup.controllers"
        if controllers_file.exists():
            return controllers_file.read_text().strip().split()
        return []

    def create_cgroup(self, path: str) -> Tuple[bool, str]:
        """Create a cgroup hierarchy."""
        cgroup_path = self.root / path
        try:
            cgroup_path.mkdir(parents=True, exist_ok=True)

            # Enable controllers on parent
            parent = cgroup_path.parent
            if parent != self.root:
                subtree_control = parent / "cgroup.subtree_control"
                if subtree_control.exists():
                    controllers = self.get_available_controllers()
                    for ctrl in ['cpu', 'memory', 'io']:
                        if ctrl in controllers:
                            try:
                                subtree_control.write_text(f"+{ctrl}")
                            except PermissionError:
                                pass

            return True, str(cgroup_path)
        except PermissionError as e:
            return False, f"Permission denied: {e}"
        except Exception as e:
            return False, str(e)

    def apply_cpu_limits(self, path: str, quota: float, weight: int = 100) -> bool:
        """
        Apply CPU limits to a cgroup.

        Args:
            path: cgroup path relative to root
            quota: CPU percentage (100 = 1 core)
            weight: CPU weight (1-10000, default 100)
        """
        cgroup_path = self.root / path

        # cpu.max format: MAX PERIOD (microseconds)
        # quota of 400% = 400000us per 100000us period = 4 cores
        period = 100000
        max_quota = int(quota * 1000)  # convert percentage to microseconds

        try:
            cpu_max = cgroup_path / "cpu.max"
            if cpu_max.exists():
                cpu_max.write_text(f"{max_quota} {period}")

            cpu_weight = cgroup_path / "cpu.weight"
            if cpu_weight.exists():
                # weight must be 1-10000
                cpu_weight.write_text(str(max(1, min(10000, weight))))

            return True
        except PermissionError:
            logger.warning(f"Permission denied setting CPU limits for {path}")
            return False
        except Exception as e:
            logger.error(f"Failed to set CPU limits: {e}")
            return False

    def apply_memory_limits(self, path: str, max_bytes: int, high_bytes: int = 0) -> bool:
        """
        Apply memory limits to a cgroup.

        Args:
            path: cgroup path relative to root
            max_bytes: hard memory limit
            high_bytes: soft memory limit (triggers reclaim)
        """
        cgroup_path = self.root / path

        try:
            memory_max = cgroup_path / "memory.max"
            if memory_max.exists():
                memory_max.write_text(str(max_bytes))

            if high_bytes > 0:
                memory_high = cgroup_path / "memory.high"
                if memory_high.exists():
                    memory_high.write_text(str(high_bytes))

            return True
        except PermissionError:
            logger.warning(f"Permission denied setting memory limits for {path}")
            return False
        except Exception as e:
            logger.error(f"Failed to set memory limits: {e}")
            return False

    def add_pid(self, path: str, pid: int) -> bool:
        """Add a process to a cgroup."""
        cgroup_path = self.root / path
        procs_file = cgroup_path / "cgroup.procs"

        try:
            if procs_file.exists():
                procs_file.write_text(str(pid))
                return True
        except PermissionError:
            logger.warning(f"Permission denied adding PID {pid} to {path}")
        except Exception as e:
            logger.error(f"Failed to add PID: {e}")
        return False

    def get_pids(self, path: str) -> List[int]:
        """Get PIDs in a cgroup."""
        cgroup_path = self.root / path
        procs_file = cgroup_path / "cgroup.procs"

        try:
            if procs_file.exists():
                content = procs_file.read_text().strip()
                if content:
                    return [int(p) for p in content.split('\n')]
        except Exception:
            pass
        return []

    def delete_cgroup(self, path: str) -> bool:
        """Delete a cgroup (must be empty)."""
        cgroup_path = self.root / path
        try:
            if cgroup_path.exists():
                cgroup_path.rmdir()
            return True
        except OSError:
            return False


class OOMScoreManager:
    """Manage OOM score adjustments for processes."""

    @staticmethod
    def set_oom_score_adj(pid: int, score: int) -> bool:
        """
        Set OOM score adjustment for a process.

        Args:
            pid: Process ID
            score: -1000 (never kill) to 1000 (always kill first)
        """
        score = max(-1000, min(1000, score))
        oom_file = Path(f"/proc/{pid}/oom_score_adj")

        try:
            if oom_file.exists():
                oom_file.write_text(str(score))
                return True
        except PermissionError:
            logger.warning(f"Permission denied setting OOM score for PID {pid}")
        except Exception as e:
            logger.error(f"Failed to set OOM score: {e}")
        return False

    @staticmethod
    def get_oom_score_adj(pid: int) -> Optional[int]:
        """Get current OOM score adjustment."""
        oom_file = Path(f"/proc/{pid}/oom_score_adj")
        try:
            if oom_file.exists():
                return int(oom_file.read_text().strip())
        except Exception:
            pass
        return None


class AcceleratorLimitsManager:
    """Main manager for accelerator-aware resource limits."""

    def __init__(self):
        self.db = LimitsDatabase()
        self.cgroups = CgroupsV2Controller()
        self.oom = OOMScoreManager()

    def create(self, limits: ResourceLimits) -> bool:
        """Create a new resource limit profile."""
        # Save to database
        self.db.save(limits)

        # Create cgroup
        success, msg = self.cgroups.create_cgroup(limits.cgroup_path)
        if success:
            # Apply limits to cgroup
            self.cgroups.apply_cpu_limits(
                limits.cgroup_path,
                limits.cpu_quota,
                limits.cpu_weight
            )
            self.cgroups.apply_memory_limits(
                limits.cgroup_path,
                limits.memory_max,
                limits.memory_high
            )
            print(f"Created profile '{limits.name}' (preset: {limits.preset})")
            print(f"   CPU: {limits.cpu_quota/100:.0f} cores, Memory: {limits.memory_max/1e9:.0f}GB")
            if limits.gpu_ids:
                print(f"   GPUs: {','.join(map(str, limits.gpu_ids))}")
        else:
            print(f"Created profile '{limits.name}' (cgroup creation failed: {msg})")
            print("   Profile saved, but system limits not applied.")

        return True

    def apply(self, profile_name: str, pid: int) -> bool:
        """Apply a profile's limits to a running process."""
        limits = self.db.get(profile_name)
        if not limits:
            print(f"Profile '{profile_name}' not found")
            return False

        # Verify process exists
        if not Path(f"/proc/{pid}").exists():
            print(f"Process {pid} not found")
            return False

        success = True

        # Add to cgroup
        if self.cgroups.add_pid(limits.cgroup_path, pid):
            print(f"Added PID {pid} to cgroup {limits.cgroup_path}")
        else:
            print(f"Could not add PID {pid} to cgroup (may need root)")
            success = False

        # Set OOM score
        if self.oom.set_oom_score_adj(pid, limits.oom_score_adj):
            print(f"Set OOM score adjustment to {limits.oom_score_adj}")
        else:
            print(f"Could not set OOM score (may need root)")
            success = False

        # Record in database
        self.db.record_pid(pid, profile_name)

        return success

    def get_env(self, profile_name: str) -> Dict[str, str]:
        """Get environment variables for a profile."""
        limits = self.db.get(profile_name)
        if not limits:
            return {}

        env = {}

        # GPU isolation
        if limits.gpu_ids:
            env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, limits.gpu_ids))
            # Also set for AMD ROCm
            env["HIP_VISIBLE_DEVICES"] = env["CUDA_VISIBLE_DEVICES"]
            # Intel oneAPI
            env["ONEAPI_DEVICE_SELECTOR"] = f"level_zero:{','.join(map(str, limits.gpu_ids))}"

        # Memory hints for ML frameworks
        if limits.memory_max > 0:
            mem_gb = limits.memory_max // (1024**3)
            env["TF_MEMORY_ALLOCATION"] = str(mem_gb * 1024)  # MB for TensorFlow
            env["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{mem_gb * 512}"

        # CPU hints
        if limits.cpu_quota > 0:
            cores = int(limits.cpu_quota / 100)
            env["OMP_NUM_THREADS"] = str(cores)
            env["MKL_NUM_THREADS"] = str(cores)
            env["OPENBLAS_NUM_THREADS"] = str(cores)

        return env

    def print_env(self, profile_name: str):
        """Print environment variables as shell exports."""
        env = self.get_env(profile_name)
        if not env:
            print(f"# Profile '{profile_name}' not found or has no env vars", file=__import__('sys').stderr)
            return

        for key, value in env.items():
            print(f"export {key}={value}")

    def status(self, profile_name: Optional[str] = None):
        """Show status of profiles."""
        if profile_name:
            limits = self.db.get(profile_name)
            if not limits:
                print(f"Profile '{profile_name}' not found")
                return
            self._print_profile_detail(limits)
        else:
            self._print_profiles_table()

    def _print_profiles_table(self):
        """Print summary table of all profiles."""
        profiles = self.db.list_all()

        if not profiles:
            print("No profiles configured. Create one with:")
            print("  cortex limits create <name> --preset inference --gpus 2")
            return

        print(f"\n{'NAME':<20} {'PRESET':<12} {'CPU':<8} {'MEMORY':<10} {'GPUS':<10} {'OOM':<8}")
        print("-" * 75)

        for p in profiles:
            gpus = ",".join(map(str, p.gpu_ids)) if p.gpu_ids else "-"
            cpu_cores = f"{p.cpu_quota/100:.0f}"
            memory = f"{p.memory_max/1e9:.0f}G"
            print(f"{p.name:<20} {p.preset:<12} {cpu_cores:<8} {memory:<10} {gpus:<10} {p.oom_score_adj:<8}")
        print()

    def _print_profile_detail(self, limits: ResourceLimits):
        """Print detailed information about a profile."""
        print(f"\n=== Profile: {limits.name} ===")
        print(f"Preset: {limits.preset}")
        print(f"cgroup path: {limits.cgroup_path}")
        print()
        print("CPU Limits:")
        print(f"  Quota: {limits.cpu_quota/100:.1f} cores ({limits.cpu_quota}%)")
        print(f"  Weight: {limits.cpu_weight}")
        if limits.cpu_affinity:
            print(f"  Affinity: CPUs {','.join(map(str, limits.cpu_affinity))}")
        print()
        print("Memory Limits:")
        print(f"  Hard limit (max): {limits.memory_max/1e9:.1f} GB")
        print(f"  Soft limit (high): {limits.memory_high/1e9:.1f} GB")
        print()
        print("GPU Configuration:")
        if limits.gpu_ids:
            print(f"  Visible GPUs: {','.join(map(str, limits.gpu_ids))}")
        else:
            print("  No GPU restrictions")
        print(f"  GPU allocation: {limits.gpu_percent}%")
        print()
        print(f"OOM Score Adjustment: {limits.oom_score_adj}")
        print()

        # Show applied PIDs
        pids = self.db.get_pids(limits.name)
        active_pids = [p for p in pids if Path(f"/proc/{p}").exists()]
        if active_pids:
            print(f"Active processes: {', '.join(map(str, active_pids))}")

        # Show cgroup PIDs
        cgroup_pids = self.cgroups.get_pids(limits.cgroup_path)
        if cgroup_pids:
            print(f"Processes in cgroup: {', '.join(map(str, cgroup_pids))}")
        print()

    def delete(self, profile_name: str) -> bool:
        """Delete a profile."""
        limits = self.db.get(profile_name)
        if not limits:
            print(f"Profile '{profile_name}' not found")
            return False

        # Try to delete cgroup
        self.cgroups.delete_cgroup(limits.cgroup_path)

        # Delete from database
        self.db.delete(profile_name)
        print(f"Deleted profile '{profile_name}'")
        return True

    def list_presets(self):
        """List available presets."""
        print("\nAvailable Presets:")
        print("-" * 70)
        print(f"{'PRESET':<15} {'CPU':<8} {'MEMORY':<10} {'OOM':<8} {'DESCRIPTION':<25}")
        print("-" * 70)

        for name, config in PRESETS.items():
            print(f"{name:<15} {config['cpu_quota']/100:.0f}{'':<5} "
                  f"{config['memory_gb']}G{'':<6} {config['oom_score_adj']:<8} "
                  f"{config['description']:<25}")
        print()


def main():
    """CLI entry point."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Cortex Accelerator-Aware Resource Limits",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex limits create inference-job --preset inference --gpus 2
  cortex limits apply inference-job --pid 12345
  eval $(cortex limits env inference-job)
  cortex limits status inference-job
  cortex limits list
  cortex limits presets
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # create command
    create_parser = subparsers.add_parser("create", help="Create a new profile")
    create_parser.add_argument("name", help="Profile name")
    create_parser.add_argument("--preset", default="inference",
                               choices=list(PRESETS.keys()),
                               help="Workload preset (default: inference)")
    create_parser.add_argument("--gpus", type=int, default=0,
                               help="Number of GPUs to allocate")
    create_parser.add_argument("--cpu", type=float,
                               help="CPU quota percentage (100 = 1 core)")
    create_parser.add_argument("--memory", type=int,
                               help="Memory limit in GB")
    create_parser.add_argument("--oom-adj", type=int,
                               help="OOM score adjustment (-1000 to 1000)")

    # apply command
    apply_parser = subparsers.add_parser("apply", help="Apply profile to a process")
    apply_parser.add_argument("name", help="Profile name")
    apply_parser.add_argument("--pid", type=int, required=True,
                              help="Process ID to apply limits to")

    # env command
    env_parser = subparsers.add_parser("env", help="Print environment variables")
    env_parser.add_argument("name", help="Profile name")

    # status command
    status_parser = subparsers.add_parser("status", help="Show profile status")
    status_parser.add_argument("name", nargs="?", help="Profile name (optional)")

    # list command
    subparsers.add_parser("list", help="List all profiles")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a profile")
    delete_parser.add_argument("name", help="Profile name")

    # presets command
    subparsers.add_parser("presets", help="List available presets")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    mgr = AcceleratorLimitsManager()

    if args.command == "create":
        limits = ResourceLimits.from_preset(args.name, args.preset, args.gpus)

        # Override with explicit arguments
        if args.cpu is not None:
            limits.cpu_quota = args.cpu
        if args.memory is not None:
            limits.memory_max = args.memory * 1024**3
            limits.memory_high = int(limits.memory_max * 0.875)
        if args.oom_adj is not None:
            limits.oom_score_adj = args.oom_adj

        mgr.create(limits)

    elif args.command == "apply":
        mgr.apply(args.name, args.pid)

    elif args.command == "env":
        mgr.print_env(args.name)

    elif args.command == "status":
        mgr.status(args.name)

    elif args.command == "list":
        mgr.status()

    elif args.command == "delete":
        mgr.delete(args.name)

    elif args.command == "presets":
        mgr.list_presets()


if __name__ == "__main__":
    main()
