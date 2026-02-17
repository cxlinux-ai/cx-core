//! System monitoring service
//!
//! Monitors system health metrics and generates alerts when thresholds are exceeded

use crate::alerts::{Alert, AlertDatabase, AlertSeverity};
use anyhow::Result;
use std::path::Path;
use std::sync::{Arc, Mutex};

/// System health metrics
#[derive(Debug, Clone, serde::Serialize)]
pub struct SystemHealth {
    pub memory_usage_percent: f64,
    pub disk_usage_percent: f64,
    pub failed_services: Vec<String>,
    pub uptime_secs: u64,
}

/// Monitoring thresholds
#[derive(Debug, Clone)]
pub struct MonitoringConfig {
    pub memory_warning_threshold: f64,
    pub memory_critical_threshold: f64,
    pub disk_warning_threshold: f64,
    pub disk_critical_threshold: f64,
    pub check_interval_secs: u64,
}

impl Default for MonitoringConfig {
    fn default() -> Self {
        Self {
            memory_warning_threshold: 80.0,
            memory_critical_threshold: 95.0,
            disk_warning_threshold: 85.0,
            disk_critical_threshold: 95.0,
            check_interval_secs: 300, // 5 minutes
        }
    }
}

/// System monitoring service
pub struct MonitoringService {
    config: MonitoringConfig,
    alert_db: Arc<Mutex<AlertDatabase>>,
    start_time: std::time::Instant,
}

impl MonitoringService {
    pub fn new(config: MonitoringConfig, alert_db: Arc<Mutex<AlertDatabase>>) -> Self {
        Self {
            config,
            alert_db,
            start_time: std::time::Instant::now(),
        }
    }

    /// Get current system health
    pub fn get_health(&self) -> Result<SystemHealth> {
        Ok(SystemHealth {
            memory_usage_percent: self.get_memory_usage()?,
            disk_usage_percent: self.get_disk_usage("/")?,
            failed_services: self.get_failed_services()?,
            uptime_secs: self.start_time.elapsed().as_secs(),
        })
    }

    /// Run monitoring checks and generate alerts
    pub fn check_and_alert(&self) -> Result<()> {
        let health = self.get_health()?;

        // Check memory usage
        if health.memory_usage_percent >= self.config.memory_critical_threshold {
            self.create_alert(
                AlertSeverity::Critical,
                "memory_monitor",
                "Critical Memory Usage",
                &format!(
                    "Memory usage is at {:.1}% (critical threshold: {:.1}%)",
                    health.memory_usage_percent, self.config.memory_critical_threshold
                ),
            )?;
        } else if health.memory_usage_percent >= self.config.memory_warning_threshold {
            self.create_alert(
                AlertSeverity::Warning,
                "memory_monitor",
                "High Memory Usage",
                &format!(
                    "Memory usage is at {:.1}% (warning threshold: {:.1}%)",
                    health.memory_usage_percent, self.config.memory_warning_threshold
                ),
            )?;
        }

        // Check disk usage
        if health.disk_usage_percent >= self.config.disk_critical_threshold {
            self.create_alert(
                AlertSeverity::Critical,
                "disk_monitor",
                "Critical Disk Space",
                &format!(
                    "Disk usage is at {:.1}% (critical threshold: {:.1}%)",
                    health.disk_usage_percent, self.config.disk_critical_threshold
                ),
            )?;
        } else if health.disk_usage_percent >= self.config.disk_warning_threshold {
            self.create_alert(
                AlertSeverity::Warning,
                "disk_monitor",
                "Low Disk Space",
                &format!(
                    "Disk usage is at {:.1}% (warning threshold: {:.1}%)",
                    health.disk_usage_percent, self.config.disk_warning_threshold
                ),
            )?;
        }

        // Check for failed services
        if !health.failed_services.is_empty() {
            self.create_alert(
                AlertSeverity::Error,
                "service_monitor",
                "Failed Services Detected",
                &format!(
                    "The following services have failed: {}",
                    health.failed_services.join(", ")
                ),
            )?;
        }

        Ok(())
    }

    /// Create and store an alert
    fn create_alert(
        &self,
        severity: AlertSeverity,
        source: &str,
        title: &str,
        description: &str,
    ) -> Result<()> {
        let alert = Alert::new(severity, source, title, description);
        let db = self.alert_db.lock().unwrap();
        db.insert(&alert)?;
        log::info!("Generated alert: {} - {}", title, description);
        Ok(())
    }

    /// Get memory usage percentage
    fn get_memory_usage(&self) -> Result<f64> {
        #[cfg(target_os = "linux")]
        {
            let meminfo = std::fs::read_to_string("/proc/meminfo")?;
            let mut mem_total = 0u64;
            let mut mem_available = 0u64;

            for line in meminfo.lines() {
                if let Some(value) = line.strip_prefix("MemTotal:") {
                    mem_total = value
                        .trim()
                        .split_whitespace()
                        .next()
                        .and_then(|v| v.parse().ok())
                        .unwrap_or(0);
                } else if let Some(value) = line.strip_prefix("MemAvailable:") {
                    mem_available = value
                        .trim()
                        .split_whitespace()
                        .next()
                        .and_then(|v| v.parse().ok())
                        .unwrap_or(0);
                }
            }

            if mem_total > 0 {
                let used = mem_total.saturating_sub(mem_available);
                Ok((used as f64 / mem_total as f64) * 100.0)
            } else {
                Ok(0.0)
            }
        }

        #[cfg(not(target_os = "linux"))]
        {
            // Fallback for non-Linux systems
            Ok(0.0)
        }
    }

    /// Get disk usage percentage for a path
    fn get_disk_usage(&self, path: &str) -> Result<f64> {
        #[cfg(unix)]
        {
            use std::ffi::CString;
            use std::mem;

            let path_c = CString::new(path)?;
            let mut stat: libc::statvfs = unsafe { mem::zeroed() };

            let result = unsafe { libc::statvfs(path_c.as_ptr(), &mut stat) };
            if result == 0 {
                // Use u64 for calculations to prevent overflow
                let total = stat.f_blocks as u64 * stat.f_frsize as u64;
                let available = stat.f_bavail as u64 * stat.f_frsize as u64;
                let used = total.saturating_sub(available);

                if total > 0 {
                    Ok((used as f64 / total as f64) * 100.0)
                } else {
                    Ok(0.0)
                }
            } else {
                Ok(0.0)
            }
        }

        #[cfg(not(unix))]
        {
            let _ = path;
            Ok(0.0)
        }
    }

    /// Get list of failed systemd services
    fn get_failed_services(&self) -> Result<Vec<String>> {
        #[cfg(target_os = "linux")]
        {
            // Check if systemctl is available
            if !Path::new("/usr/bin/systemctl").exists() && !Path::new("/bin/systemctl").exists() {
                return Ok(Vec::new());
            }

            let output = std::process::Command::new("systemctl")
                .args(&["--failed", "--no-pager", "--no-legend"])
                .output();

            match output {
                Ok(output) if output.status.success() => {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    let failed: Vec<String> = stdout
                        .lines()
                        .filter_map(|line| line.split_whitespace().next().map(|s| s.to_string()))
                        .collect();
                    Ok(failed)
                }
                _ => Ok(Vec::new()),
            }
        }

        #[cfg(not(target_os = "linux"))]
        {
            Ok(Vec::new())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::alerts::AlertDatabase;

    #[test]
    fn test_system_health() {
        let temp_dir = std::env::temp_dir();
        let db_path = temp_dir.join("test_monitoring.db");
        let _ = std::fs::remove_file(&db_path);

        let db = Arc::new(Mutex::new(AlertDatabase::open(db_path.clone()).unwrap()));
        let config = MonitoringConfig::default();
        let service = MonitoringService::new(config, db);

        let health = service.get_health().unwrap();
        assert!(health.memory_usage_percent >= 0.0);
        assert!(health.memory_usage_percent <= 100.0);

        let _ = std::fs::remove_file(db_path);
    }
}
