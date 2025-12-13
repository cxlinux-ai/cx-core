// SPDX-License-Identifier: GPL-2.0
// Cortex Linux ML Workload Scheduler
// 
// This eBPF program detects and prioritizes ML inference workloads
// by monitoring process behavior patterns typical of LLM inference.
//
// Compile with:
//   clang -O2 -target bpf -c cortex_sched.bpf.c -o cortex_sched.bpf.o
//
// Load with cortex_sched_loader.py

#include <linux/bpf.h>
#include <linux/ptrace.h>
#include <linux/sched.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

// License required for eBPF
char LICENSE[] SEC("license") = "GPL";

// =============================================================================
// DATA STRUCTURES
// =============================================================================

// Process inference metrics
struct inference_metrics {
    __u64 gpu_wait_ns;          // Time spent waiting for GPU
    __u64 cpu_compute_ns;       // Time spent in CPU compute
    __u64 memory_alloc_bytes;   // Memory allocated
    __u64 context_switches;     // Number of context switches
    __u64 inference_count;      // Estimated inference calls
    __u64 last_update_ns;       // Last update timestamp
    __u32 priority_boost;       // Current priority boost level
    __u32 is_inference;         // Flag: detected as inference workload
};

// Global statistics
struct global_stats {
    __u64 total_inference_procs;
    __u64 total_boosted_ns;
    __u64 total_memory_saved;
    __u64 detection_count;
};

// =============================================================================
// BPF MAPS
// =============================================================================

// Per-process metrics (key: pid)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10240);
    __type(key, __u32);
    __type(value, struct inference_metrics);
} process_metrics SEC(".maps");

// Global statistics
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct global_stats);
} global_stats SEC(".maps");

// Ring buffer for events (userspace notification)
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 256 * 1024);
} events SEC(".maps");

// Known inference process names (for fast detection)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 64);
    __type(key, char[16]);
    __type(value, __u32);
} inference_procs SEC(".maps");

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

// Get or create metrics for a process
static __always_inline struct inference_metrics *get_metrics(__u32 pid) {
    struct inference_metrics *metrics;
    struct inference_metrics new_metrics = {};
    
    metrics = bpf_map_lookup_elem(&process_metrics, &pid);
    if (!metrics) {
        new_metrics.last_update_ns = bpf_ktime_get_ns();
        bpf_map_update_elem(&process_metrics, &pid, &new_metrics, BPF_NOEXIST);
        metrics = bpf_map_lookup_elem(&process_metrics, &pid);
    }
    
    return metrics;
}

// Check if process name matches known inference processes
static __always_inline int is_known_inference_proc(const char *comm) {
    char key[16] = {};
    __u32 *val;
    
    // Copy comm to key (max 15 chars + null)
    bpf_probe_read_kernel_str(key, sizeof(key), comm);
    
    val = bpf_map_lookup_elem(&inference_procs, key);
    return val != NULL;
}

// Detect inference workload by behavior patterns
static __always_inline int detect_inference_pattern(struct inference_metrics *metrics) {
    if (!metrics) return 0;
    
    // Pattern 1: High GPU wait ratio (typical of inference)
    // Inference workloads spend significant time waiting for GPU
    __u64 total_time = metrics->gpu_wait_ns + metrics->cpu_compute_ns;
    if (total_time > 0) {
        __u64 gpu_ratio = (metrics->gpu_wait_ns * 100) / total_time;
        if (gpu_ratio > 60) {  // >60% GPU wait suggests inference
            return 1;
        }
    }
    
    // Pattern 2: Large memory allocations (model weights)
    if (metrics->memory_alloc_bytes > 1024 * 1024 * 1024) {  // >1GB
        return 1;
    }
    
    // Pattern 3: Burst compute pattern (forward passes)
    // Low context switches during compute bursts
    if (metrics->inference_count > 0 && metrics->context_switches < metrics->inference_count * 2) {
        return 1;
    }
    
    return 0;
}

// =============================================================================
// TRACEPOINTS AND PROBES
// =============================================================================

// Track context switches (scheduler events)
SEC("tp/sched/sched_switch")
int handle_sched_switch(struct trace_event_raw_sched_switch *ctx) {
    __u32 prev_pid = ctx->prev_pid;
    __u32 next_pid = ctx->next_pid;
    __u64 now = bpf_ktime_get_ns();
    
    // Update metrics for process being switched out
    struct inference_metrics *prev_metrics = get_metrics(prev_pid);
    if (prev_metrics) {
        __sync_fetch_and_add(&prev_metrics->context_switches, 1);
        
        // Calculate CPU time since last update
        if (prev_metrics->last_update_ns > 0) {
            __u64 delta = now - prev_metrics->last_update_ns;
            __sync_fetch_and_add(&prev_metrics->cpu_compute_ns, delta);
        }
        prev_metrics->last_update_ns = now;
    }
    
    // Mark start time for process being switched in
    struct inference_metrics *next_metrics = get_metrics(next_pid);
    if (next_metrics) {
        next_metrics->last_update_ns = now;
    }
    
    return 0;
}

// Track memory allocations (mmap for model loading)
SEC("tp/syscalls/sys_enter_mmap")
int handle_mmap(struct trace_event_raw_sys_enter *ctx) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    __u64 len = ctx->args[1];  // mmap length
    
    // Only track large allocations (likely model weights)
    if (len > 100 * 1024 * 1024) {  // >100MB
        struct inference_metrics *metrics = get_metrics(pid);
        if (metrics) {
            __sync_fetch_and_add(&metrics->memory_alloc_bytes, len);
            
            // Large allocation is a strong signal for inference
            if (len > 1024 * 1024 * 1024) {  // >1GB
                metrics->is_inference = 1;
            }
        }
    }
    
    return 0;
}

// Track CUDA/GPU ioctl calls (NVIDIA driver)
SEC("tp/syscalls/sys_enter_ioctl")
int handle_ioctl(struct trace_event_raw_sys_enter *ctx) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    int fd = ctx->args[0];
    unsigned long cmd = ctx->args[1];
    
    // Check for NVIDIA ioctl command ranges
    // NVIDIA uses 0x46 ('F') as magic number
    if ((cmd >> 8) == 0x46) {
        struct inference_metrics *metrics = get_metrics(pid);
        if (metrics) {
            // Track GPU interaction
            __u64 now = bpf_ktime_get_ns();
            if (metrics->last_update_ns > 0) {
                __u64 delta = now - metrics->last_update_ns;
                __sync_fetch_and_add(&metrics->gpu_wait_ns, delta);
            }
            metrics->last_update_ns = now;
            
            // Increment inference counter for certain ioctls
            __sync_fetch_and_add(&metrics->inference_count, 1);
        }
    }
    
    return 0;
}

// Track process creation (detect inference process names)
SEC("tp/sched/sched_process_exec")
int handle_exec(struct trace_event_raw_sched_process_exec *ctx) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    char comm[16];
    
    bpf_get_current_comm(comm, sizeof(comm));
    
    // Check if this is a known inference process
    if (is_known_inference_proc(comm)) {
        struct inference_metrics *metrics = get_metrics(pid);
        if (metrics) {
            metrics->is_inference = 1;
            
            // Update global stats
            __u32 key = 0;
            struct global_stats *stats = bpf_map_lookup_elem(&global_stats, &key);
            if (stats) {
                __sync_fetch_and_add(&stats->total_inference_procs, 1);
                __sync_fetch_and_add(&stats->detection_count, 1);
            }
        }
    }
    
    return 0;
}

// Track process exit (cleanup)
SEC("tp/sched/sched_process_exit")
int handle_exit(struct trace_event_raw_sched_process_template *ctx) {
    __u32 pid = ctx->pid;
    
    // Remove from process metrics map
    bpf_map_delete_elem(&process_metrics, &pid);
    
    return 0;
}

// =============================================================================
// PERIODIC CHECK (called from userspace timer)
// =============================================================================

// This function is called periodically to check process patterns
// and update priority recommendations
SEC("tp/syscalls/sys_enter_nanosleep")  // Hook into a common syscall as trigger
int periodic_check(void *ctx) {
    __u32 pid = bpf_get_current_pid_tgid() >> 32;
    
    struct inference_metrics *metrics = bpf_map_lookup_elem(&process_metrics, &pid);
    if (!metrics) return 0;
    
    // Check if this process shows inference patterns
    if (!metrics->is_inference && detect_inference_pattern(metrics)) {
        metrics->is_inference = 1;
        
        // Update global stats
        __u32 key = 0;
        struct global_stats *stats = bpf_map_lookup_elem(&global_stats, &key);
        if (stats) {
            __sync_fetch_and_add(&stats->detection_count, 1);
        }
    }
    
    // Calculate priority boost for inference processes
    if (metrics->is_inference) {
        // Boost priority during active inference
        // Higher boost when GPU utilization is high
        __u64 total = metrics->gpu_wait_ns + metrics->cpu_compute_ns;
        if (total > 0) {
            metrics->priority_boost = (metrics->gpu_wait_ns * 10) / total;
        }
    }
    
    return 0;
}
