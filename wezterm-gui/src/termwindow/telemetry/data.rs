// CX Terminal: Telemetry Data Collection
// Collects CPU, RAM, Git status, and command history

use std::process::Command;
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// Telemetry data for the dashboard
#[derive(Debug, Clone)]
pub struct TelemetryData {
    /// CPU usage percentage (0-100)
    pub cpu_percent: f32,
    /// Memory usage percentage (0-100)
    pub mem_percent: f32,
    /// Total memory in GB
    pub mem_total_gb: f32,
    /// Used memory in GB
    pub mem_used_gb: f32,
    /// Git branch name (if in a repo)
    pub git_branch: Option<String>,
    /// Git status (clean, dirty, etc.)
    pub git_status: GitStatus,
    /// Number of uncommitted changes
    pub git_changes: usize,
    /// Last command exit code
    pub last_exit_code: Option<i32>,
    /// Last command that was run
    pub last_command: Option<String>,
    /// Current working directory
    pub cwd: Option<PathBuf>,
    /// Last update time
    pub last_update: Instant,
}

#[derive(Debug, Clone, PartialEq)]
pub enum GitStatus {
    /// Not in a git repository
    NotRepo,
    /// Clean working tree
    Clean,
    /// Has uncommitted changes
    Dirty,
    /// Has staged changes
    Staged,
    /// Has both staged and unstaged changes
    Mixed,
    /// Unknown status
    Unknown,
}

impl Default for TelemetryData {
    fn default() -> Self {
        Self {
            cpu_percent: 0.0,
            mem_percent: 0.0,
            mem_total_gb: 0.0,
            mem_used_gb: 0.0,
            git_branch: None,
            git_status: GitStatus::NotRepo,
            git_changes: 0,
            last_exit_code: None,
            last_command: None,
            cwd: None,
            last_update: Instant::now(),
        }
    }
}

impl TelemetryData {
    /// Create new telemetry data and collect current stats
    pub fn collect() -> Self {
        let mut data = Self::default();
        data.refresh();
        data
    }

    /// Refresh all telemetry data
    pub fn refresh(&mut self) {
        self.refresh_system_stats();
        self.refresh_git_status();
        self.last_update = Instant::now();
    }

    /// Check if data is stale (older than 2 seconds)
    pub fn is_stale(&self) -> bool {
        self.last_update.elapsed() > Duration::from_secs(2)
    }

    /// Refresh CPU and memory stats
    fn refresh_system_stats(&mut self) {
        // Use 'vm_stat' for memory on macOS
        #[cfg(target_os = "macos")]
        {
            // Get memory info
            if let Ok(output) = Command::new("vm_stat").output() {
                if let Ok(stdout) = String::from_utf8(output.stdout) {
                    self.parse_macos_memory(&stdout);
                }
            }

            // Get CPU info using 'top' in batch mode
            if let Ok(output) = Command::new("top")
                .args(["-l", "1", "-n", "0", "-stats", "cpu"])
                .output()
            {
                if let Ok(stdout) = String::from_utf8(output.stdout) {
                    self.parse_macos_cpu(&stdout);
                }
            }
        }

        #[cfg(target_os = "linux")]
        {
            // Parse /proc/meminfo for memory
            if let Ok(contents) = std::fs::read_to_string("/proc/meminfo") {
                self.parse_linux_memory(&contents);
            }

            // Parse /proc/stat for CPU
            if let Ok(contents) = std::fs::read_to_string("/proc/stat") {
                self.parse_linux_cpu(&contents);
            }
        }
    }

    #[cfg(target_os = "macos")]
    fn parse_macos_memory(&mut self, vm_stat: &str) {
        let page_size: u64 = 16384; // macOS page size (can vary, but 16KB on ARM)
        let mut pages_free: u64 = 0;
        let mut pages_active: u64 = 0;
        let mut pages_inactive: u64 = 0;
        let mut pages_wired: u64 = 0;
        let mut pages_compressed: u64 = 0;

        for line in vm_stat.lines() {
            let parts: Vec<&str> = line.split(':').collect();
            if parts.len() == 2 {
                let value = parts[1].trim().trim_end_matches('.').parse::<u64>().unwrap_or(0);
                match parts[0].trim() {
                    "Pages free" => pages_free = value,
                    "Pages active" => pages_active = value,
                    "Pages inactive" => pages_inactive = value,
                    "Pages wired down" => pages_wired = value,
                    "Pages occupied by compressor" => pages_compressed = value,
                    _ => {}
                }
            }
        }

        // Calculate memory usage
        let total_pages = pages_free + pages_active + pages_inactive + pages_wired + pages_compressed;
        let used_pages = pages_active + pages_wired + pages_compressed;

        if total_pages > 0 {
            self.mem_total_gb = (total_pages * page_size) as f32 / (1024.0 * 1024.0 * 1024.0);
            self.mem_used_gb = (used_pages * page_size) as f32 / (1024.0 * 1024.0 * 1024.0);
            self.mem_percent = (used_pages as f32 / total_pages as f32) * 100.0;
        }
    }

    #[cfg(target_os = "macos")]
    fn parse_macos_cpu(&mut self, top_output: &str) {
        // Look for "CPU usage: X.X% user, Y.Y% sys, Z.Z% idle"
        for line in top_output.lines() {
            if line.contains("CPU usage:") {
                let parts: Vec<&str> = line.split(',').collect();
                let mut user = 0.0f32;
                let mut sys = 0.0f32;

                for part in parts {
                    let part = part.trim();
                    if part.contains("user") {
                        if let Some(val) = part.split('%').next() {
                            user = val.split_whitespace().last()
                                .and_then(|s| s.parse().ok())
                                .unwrap_or(0.0);
                        }
                    } else if part.contains("sys") {
                        if let Some(val) = part.split('%').next() {
                            sys = val.split_whitespace().last()
                                .and_then(|s| s.parse().ok())
                                .unwrap_or(0.0);
                        }
                    }
                }

                self.cpu_percent = user + sys;
                break;
            }
        }
    }

    #[cfg(target_os = "linux")]
    fn parse_linux_memory(&mut self, meminfo: &str) {
        let mut total: u64 = 0;
        let mut available: u64 = 0;

        for line in meminfo.lines() {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                let value = parts[1].parse::<u64>().unwrap_or(0);
                match parts[0] {
                    "MemTotal:" => total = value,
                    "MemAvailable:" => available = value,
                    _ => {}
                }
            }
        }

        if total > 0 {
            let used = total.saturating_sub(available);
            self.mem_total_gb = total as f32 / (1024.0 * 1024.0);
            self.mem_used_gb = used as f32 / (1024.0 * 1024.0);
            self.mem_percent = (used as f32 / total as f32) * 100.0;
        }
    }

    #[cfg(target_os = "linux")]
    fn parse_linux_cpu(&mut self, _stat: &str) {
        // Simplified - would need to track deltas for accurate reading
        self.cpu_percent = 0.0;
    }

    /// Refresh Git status for current directory
    fn refresh_git_status(&mut self) {
        // Get current git branch
        if let Ok(output) = Command::new("git")
            .args(["branch", "--show-current"])
            .output()
        {
            if output.status.success() {
                let branch = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !branch.is_empty() {
                    self.git_branch = Some(branch);
                }
            }
        }

        // Get git status
        if let Ok(output) = Command::new("git")
            .args(["status", "--porcelain"])
            .output()
        {
            if output.status.success() {
                let status = String::from_utf8_lossy(&output.stdout);
                let lines: Vec<&str> = status.lines().collect();
                self.git_changes = lines.len();

                if lines.is_empty() {
                    self.git_status = GitStatus::Clean;
                } else {
                    let has_staged = lines.iter().any(|l| {
                        l.starts_with("M ") || l.starts_with("A ") || l.starts_with("D ")
                    });
                    let has_unstaged = lines.iter().any(|l| {
                        l.starts_with(" M") || l.starts_with(" D") || l.starts_with("??")
                    });

                    self.git_status = match (has_staged, has_unstaged) {
                        (true, true) => GitStatus::Mixed,
                        (true, false) => GitStatus::Staged,
                        (false, true) => GitStatus::Dirty,
                        (false, false) => GitStatus::Clean,
                    };
                }
            } else {
                self.git_status = GitStatus::NotRepo;
                self.git_branch = None;
            }
        }
    }

    /// Update the last command exit code
    pub fn set_last_exit_code(&mut self, code: i32, command: Option<String>) {
        self.last_exit_code = Some(code);
        self.last_command = command;
    }

    /// Check if last command failed
    pub fn last_command_failed(&self) -> bool {
        self.last_exit_code.map(|c| c != 0).unwrap_or(false)
    }

    /// Get status color for Git
    pub fn git_status_color(&self) -> (f32, f32, f32) {
        match self.git_status {
            GitStatus::Clean => (0.0, 1.0, 0.5),      // Green
            GitStatus::Dirty => (1.0, 0.8, 0.0),      // Yellow
            GitStatus::Staged => (0.0, 0.8, 1.0),     // Cyan
            GitStatus::Mixed => (1.0, 0.5, 0.0),      // Orange
            GitStatus::NotRepo => (0.5, 0.5, 0.5),    // Gray
            GitStatus::Unknown => (0.5, 0.5, 0.5),    // Gray
        }
    }

    /// Get formatted memory string
    pub fn mem_string(&self) -> String {
        format!("{:.1}/{:.1} GB ({:.0}%)", self.mem_used_gb, self.mem_total_gb, self.mem_percent)
    }

    /// Get formatted CPU string
    pub fn cpu_string(&self) -> String {
        format!("{:.1}%", self.cpu_percent)
    }

    /// Get Git status string
    pub fn git_string(&self) -> String {
        match (&self.git_branch, &self.git_status) {
            (Some(branch), GitStatus::Clean) => format!(" {}", branch),
            (Some(branch), GitStatus::Dirty) => format!(" {} *{}", branch, self.git_changes),
            (Some(branch), GitStatus::Staged) => format!(" {} +{}", branch, self.git_changes),
            (Some(branch), GitStatus::Mixed) => format!(" {} ±{}", branch, self.git_changes),
            (Some(branch), _) => format!(" {}", branch),
            (None, _) => "Not a git repo".to_string(),
        }
    }
}
