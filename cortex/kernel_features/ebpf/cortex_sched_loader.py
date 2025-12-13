#!/usr/bin/env python3
"""
Cortex Linux eBPF ML Scheduler Loader

Loads and manages the eBPF program that detects and prioritizes ML inference workloads.

Requirements:
    - Linux 5.15+ with BTF support
    - bcc (BPF Compiler Collection) or libbpf
    - Root privileges

Usage:
    sudo python3 cortex_sched_loader.py start
    sudo python3 cortex_sched_loader.py status
    sudo python3 cortex_sched_loader.py stop
"""

import os
import sys
import time
import json
import signal
import argparse
import ctypes
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

# Check for root
if os.geteuid() != 0:
    print("ERROR: This script requires root privileges")
    print("Run with: sudo python3 cortex_sched_loader.py")
    sys.exit(1)

# Try to import BCC (BPF Compiler Collection)
try:
    from bcc import BPF, PerfType, PerfSWConfig
    HAS_BCC = True
except ImportError:
    HAS_BCC = False
    print("WARNING: bcc not installed. Install with:")
    print("  Ubuntu: sudo apt install python3-bcc bpfcc-tools")
    print("  Fedora: sudo dnf install python3-bcc bcc-tools")


# Known inference process names to detect
INFERENCE_PROCESSES = [
    "python",          # Most ML frameworks
    "python3",
    "ollama",          # Ollama server
    "ollama_llama_se", # Ollama server (truncated)
    "llama-server",    # llama.cpp server
    "vllm",            # vLLM
    "text-generation", # HuggingFace TGI
    "tritonserver",    # NVIDIA Triton
    "torchserve",      # PyTorch Serve
    "cortex-serve",    # Cortex model server
    "mlx_lm",          # Apple MLX
    "exllamav2",       # ExLlamaV2
    "koboldcpp",       # KoboldCpp
    "localai",         # LocalAI
]


@dataclass
class ProcessMetrics:
    """Metrics for a single process."""
    pid: int
    comm: str
    gpu_wait_ns: int
    cpu_compute_ns: int
    memory_alloc_mb: float
    context_switches: int
    inference_count: int
    is_inference: bool
    priority_boost: int
    
    @property
    def gpu_ratio(self) -> float:
        total = self.gpu_wait_ns + self.cpu_compute_ns
        if total == 0:
            return 0.0
        return (self.gpu_wait_ns / total) * 100


@dataclass
class GlobalStats:
    """Global scheduler statistics."""
    total_inference_procs: int
    total_boosted_ns: int
    detection_count: int
    uptime_seconds: float


class CortexScheduler:
    """
    Manages the eBPF-based ML workload scheduler.
    """
    
    # Inline eBPF program (used if compiled .o file not found)
    BPF_PROGRAM = """
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

// Process metrics structure
struct metrics_t {
    u64 gpu_wait_ns;
    u64 cpu_compute_ns;
    u64 memory_alloc_bytes;
    u64 context_switches;
    u64 inference_count;
    u64 last_update_ns;
    u32 priority_boost;
    u32 is_inference;
};

// Per-process metrics
BPF_HASH(process_metrics, u32, struct metrics_t);

// Known inference PIDs (populated from userspace)
BPF_HASH(inference_pids, u32, u32);

// Event for userspace notification
struct event_t {
    u32 pid;
    char comm[16];
    u32 event_type;  // 1=detected, 2=boosted, 3=released
};
BPF_PERF_OUTPUT(events);

// Track context switches
TRACEPOINT_PROBE(sched, sched_switch) {
    u32 prev_pid = args->prev_pid;
    u32 next_pid = args->next_pid;
    u64 now = bpf_ktime_get_ns();
    
    struct metrics_t *prev = process_metrics.lookup(&prev_pid);
    if (prev) {
        prev->context_switches++;
        if (prev->last_update_ns > 0) {
            prev->cpu_compute_ns += now - prev->last_update_ns;
        }
        prev->last_update_ns = now;
    }
    
    struct metrics_t *next = process_metrics.lookup(&next_pid);
    if (next) {
        next->last_update_ns = now;
    }
    
    return 0;
}

// Track large memory allocations
TRACEPOINT_PROBE(syscalls, sys_enter_mmap) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 len = args->len;
    
    if (len > 100 * 1024 * 1024) {  // >100MB
        struct metrics_t zero = {};
        struct metrics_t *m = process_metrics.lookup_or_try_init(&pid, &zero);
        if (m) {
            m->memory_alloc_bytes += len;
            if (len > 1024 * 1024 * 1024) {  // >1GB likely model
                m->is_inference = 1;
            }
        }
    }
    return 0;
}

// Track NVIDIA ioctl (GPU interaction)
TRACEPOINT_PROBE(syscalls, sys_enter_ioctl) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    unsigned long cmd = args->cmd;
    
    // NVIDIA uses 0x46 magic
    if ((cmd >> 8) == 0x46) {
        struct metrics_t zero = {};
        struct metrics_t *m = process_metrics.lookup_or_try_init(&pid, &zero);
        if (m) {
            u64 now = bpf_ktime_get_ns();
            if (m->last_update_ns > 0) {
                m->gpu_wait_ns += now - m->last_update_ns;
            }
            m->last_update_ns = now;
            m->inference_count++;
        }
    }
    return 0;
}

// Track process exec (detect inference by name)
TRACEPOINT_PROBE(sched, sched_process_exec) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    
    // Check if PID is in known inference list
    u32 *known = inference_pids.lookup(&pid);
    if (known) {
        struct metrics_t zero = {};
        struct metrics_t *m = process_metrics.lookup_or_try_init(&pid, &zero);
        if (m) {
            m->is_inference = 1;
            
            // Send event to userspace
            struct event_t evt = {};
            evt.pid = pid;
            evt.event_type = 1;
            bpf_get_current_comm(&evt.comm, sizeof(evt.comm));
            events.perf_submit(args, &evt, sizeof(evt));
        }
    }
    return 0;
}

// Cleanup on exit
TRACEPOINT_PROBE(sched, sched_process_exit) {
    u32 pid = args->pid;
    process_metrics.delete(&pid);
    inference_pids.delete(&pid);
    return 0;
}
"""
    
    def __init__(self):
        self.bpf: Optional[BPF] = None
        self.start_time: float = 0
        self.running = False
        
    def start(self) -> bool:
        """Load and start the eBPF program."""
        if not HAS_BCC:
            print("ERROR: BCC not installed")
            return False
            
        try:
            print("Loading eBPF program...")
            self.bpf = BPF(text=self.BPF_PROGRAM)
            self.start_time = time.time()
            self.running = True
            
            # Populate known inference PIDs
            self._populate_inference_pids()
            
            print("eBPF ML scheduler loaded successfully")
            return True
            
        except Exception as e:
            print(f"ERROR loading eBPF: {e}")
            return False
    
    def _populate_inference_pids(self):
        """Find and mark known inference processes."""
        if not self.bpf:
            return
            
        inference_pids = self.bpf["inference_pids"]
        
        # Scan /proc for matching processes
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
                
            try:
                comm_file = pid_dir / "comm"
                if comm_file.exists():
                    comm = comm_file.read_text().strip()
                    if any(proc in comm for proc in INFERENCE_PROCESSES):
                        pid = int(pid_dir.name)
                        inference_pids[ctypes.c_uint32(pid)] = ctypes.c_uint32(1)
                        print(f"  Marked inference process: {comm} (PID {pid})")
            except (PermissionError, FileNotFoundError):
                continue
    
    def stop(self):
        """Unload the eBPF program."""
        if self.bpf:
            self.bpf.cleanup()
            self.bpf = None
        self.running = False
        print("eBPF ML scheduler stopped")
    
    def get_process_metrics(self) -> List[ProcessMetrics]:
        """Get metrics for all tracked processes."""
        if not self.bpf:
            return []
            
        metrics_map = self.bpf["process_metrics"]
        results = []
        
        for pid, metrics in metrics_map.items():
            pid_val = pid.value
            
            # Get process name
            try:
                comm = Path(f"/proc/{pid_val}/comm").read_text().strip()
            except (FileNotFoundError, PermissionError):
                comm = "<unknown>"
            
            results.append(ProcessMetrics(
                pid=pid_val,
                comm=comm,
                gpu_wait_ns=metrics.gpu_wait_ns,
                cpu_compute_ns=metrics.cpu_compute_ns,
                memory_alloc_mb=metrics.memory_alloc_bytes / (1024 * 1024),
                context_switches=metrics.context_switches,
                inference_count=metrics.inference_count,
                is_inference=bool(metrics.is_inference),
                priority_boost=metrics.priority_boost
            ))
        
        return results
    
    def get_global_stats(self) -> GlobalStats:
        """Get global scheduler statistics."""
        metrics = self.get_process_metrics()
        inference_procs = sum(1 for m in metrics if m.is_inference)
        
        return GlobalStats(
            total_inference_procs=inference_procs,
            total_boosted_ns=sum(m.gpu_wait_ns for m in metrics if m.is_inference),
            detection_count=inference_procs,
            uptime_seconds=time.time() - self.start_time if self.running else 0
        )
    
    def print_status(self):
        """Print current scheduler status."""
        if not self.running:
            print("Scheduler not running")
            return
            
        stats = self.get_global_stats()
        metrics = self.get_process_metrics()
        
        print("=" * 70)
        print("CORTEX ML SCHEDULER STATUS")
        print("=" * 70)
        print(f"Uptime: {stats.uptime_seconds:.1f} seconds")
        print(f"Inference processes detected: {stats.total_inference_procs}")
        print(f"Total GPU time tracked: {stats.total_boosted_ns / 1e9:.2f} seconds")
        print()
        
        # Sort by inference flag and GPU time
        metrics.sort(key=lambda m: (m.is_inference, m.gpu_wait_ns), reverse=True)
        
        print(f"{'PID':<8} {'COMM':<20} {'INF':<4} {'GPU%':<6} {'MEM(MB)':<10} {'CTX':<8} {'BOOST':<6}")
        print("-" * 70)
        
        for m in metrics[:20]:  # Top 20
            inf_flag = "✓" if m.is_inference else ""
            print(f"{m.pid:<8} {m.comm[:19]:<20} {inf_flag:<4} {m.gpu_ratio:<6.1f} "
                  f"{m.memory_alloc_mb:<10.1f} {m.context_switches:<8} {m.priority_boost:<6}")
    
    def run_monitor(self, interval: float = 2.0):
        """Run continuous monitoring."""
        print("Starting monitor (Ctrl+C to stop)...")
        
        try:
            while self.running:
                os.system('clear')
                self.print_status()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopping monitor...")


def main():
    parser = argparse.ArgumentParser(
        description="Cortex Linux eBPF ML Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    sudo python3 cortex_sched_loader.py start
    sudo python3 cortex_sched_loader.py status
    sudo python3 cortex_sched_loader.py monitor
    sudo python3 cortex_sched_loader.py stop
        """
    )
    
    parser.add_argument("command", choices=["start", "stop", "status", "monitor", "json"],
                        help="Command to execute")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Monitor update interval (seconds)")
    
    args = parser.parse_args()
    
    scheduler = CortexScheduler()
    
    if args.command == "start":
        if scheduler.start():
            # Keep running and handle signals
            def signal_handler(sig, frame):
                scheduler.stop()
                sys.exit(0)
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            print("Scheduler running. Press Ctrl+C to stop.")
            while scheduler.running:
                time.sleep(1)
                scheduler._populate_inference_pids()  # Refresh known processes
                
    elif args.command == "stop":
        scheduler.stop()
        
    elif args.command == "status":
        if scheduler.start():
            time.sleep(0.5)  # Let it collect some data
            scheduler.print_status()
            scheduler.stop()
            
    elif args.command == "monitor":
        if scheduler.start():
            scheduler.run_monitor(args.interval)
            scheduler.stop()
            
    elif args.command == "json":
        if scheduler.start():
            time.sleep(0.5)
            metrics = scheduler.get_process_metrics()
            stats = scheduler.get_global_stats()
            output = {
                "stats": asdict(stats),
                "processes": [asdict(m) for m in metrics if m.is_inference]
            }
            print(json.dumps(output, indent=2))
            scheduler.stop()


if __name__ == "__main__":
    main()
