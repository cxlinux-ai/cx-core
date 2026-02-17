//! IPC request handlers for the daemon

use crate::alerts::{AlertDatabase, AlertSeverity, AlertStatus};
use crate::monitoring::MonitoringService;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};

/// Request types that the daemon can handle
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum DaemonRequest {
    /// Ping the daemon
    Ping,

    /// Get daemon version
    Version,

    /// Get daemon status
    Status,

    /// Get system health
    Health,

    /// List alerts with optional filters
    Alerts {
        status: Option<String>,
        severity: Option<String>,
    },

    /// Acknowledge an alert
    AcknowledgeAlert { id: String },

    /// Dismiss an alert
    DismissAlert { id: String },

    /// Acknowledge all active alerts
    AcknowledgeAllAlerts,

    /// Shutdown the daemon
    Shutdown,
}

/// Response types from the daemon
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum DaemonResponse {
    /// Success response
    Success { message: String },

    /// Error response
    Error { message: String },

    /// Pong response to ping
    Pong { version: String, uptime_secs: u64 },

    /// Version information
    Version { version: String },

    /// Daemon status
    Status {
        version: String,
        uptime_secs: u64,
        monitoring_enabled: bool,
        alert_count: usize,
    },

    /// System health information
    Health {
        memory_usage_percent: f64,
        disk_usage_percent: f64,
        failed_services: Vec<String>,
        uptime_secs: u64,
    },

    /// List of alerts
    Alerts { alerts: Vec<AlertInfo> },
}

/// Alert information for responses
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertInfo {
    pub id: String,
    pub severity: String,
    pub source: String,
    pub title: String,
    pub description: String,
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
}

impl DaemonRequest {
    /// Parse a request from JSON
    pub fn from_json(json: &str) -> Result<Self> {
        Ok(serde_json::from_str(json)?)
    }
}

impl DaemonResponse {
    /// Serialize response to JSON
    pub fn to_json(&self) -> Result<String> {
        Ok(serde_json::to_string(self)?)
    }
}

/// IPC request handler
pub struct RequestHandler {
    alert_db: Arc<Mutex<AlertDatabase>>,
    monitoring: Arc<MonitoringService>,
    start_time: std::time::Instant,
}

impl RequestHandler {
    pub fn new(alert_db: Arc<Mutex<AlertDatabase>>, monitoring: Arc<MonitoringService>) -> Self {
        Self {
            alert_db,
            monitoring,
            start_time: std::time::Instant::now(),
        }
    }

    /// Handle an incoming request
    pub fn handle(&self, request: DaemonRequest) -> DaemonResponse {
        match request {
            DaemonRequest::Ping => self.handle_ping(),
            DaemonRequest::Version => self.handle_version(),
            DaemonRequest::Status => self.handle_status(),
            DaemonRequest::Health => self.handle_health(),
            DaemonRequest::Alerts { status, severity } => self.handle_list_alerts(status, severity),
            DaemonRequest::AcknowledgeAlert { id } => self.handle_acknowledge_alert(id),
            DaemonRequest::DismissAlert { id } => self.handle_dismiss_alert(id),
            DaemonRequest::AcknowledgeAllAlerts => self.handle_acknowledge_all_alerts(),
            DaemonRequest::Shutdown => DaemonResponse::Success {
                message: "Shutdown requested".to_string(),
            },
        }
    }

    fn handle_ping(&self) -> DaemonResponse {
        DaemonResponse::Pong {
            version: env!("CARGO_PKG_VERSION").to_string(),
            uptime_secs: self.start_time.elapsed().as_secs(),
        }
    }

    fn handle_version(&self) -> DaemonResponse {
        DaemonResponse::Version {
            version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }

    fn handle_status(&self) -> DaemonResponse {
        let alert_count = match self
            .alert_db
            .lock()
            .unwrap()
            .list(Some(AlertStatus::Active), None)
        {
            Ok(alerts) => alerts.len(),
            Err(_) => 0,
        };

        DaemonResponse::Status {
            version: env!("CARGO_PKG_VERSION").to_string(),
            uptime_secs: self.start_time.elapsed().as_secs(),
            monitoring_enabled: true,
            alert_count,
        }
    }

    fn handle_health(&self) -> DaemonResponse {
        match self.monitoring.get_health() {
            Ok(health) => DaemonResponse::Health {
                memory_usage_percent: health.memory_usage_percent,
                disk_usage_percent: health.disk_usage_percent,
                failed_services: health.failed_services,
                uptime_secs: health.uptime_secs,
            },
            Err(e) => DaemonResponse::Error {
                message: format!("Failed to get health: {}", e),
            },
        }
    }

    fn handle_list_alerts(
        &self,
        status: Option<String>,
        severity: Option<String>,
    ) -> DaemonResponse {
        let status_filter = status.and_then(|s| AlertStatus::from_str(&s));
        let severity_filter = severity.and_then(|s| AlertSeverity::from_str(&s));

        match self
            .alert_db
            .lock()
            .unwrap()
            .list(status_filter, severity_filter)
        {
            Ok(alerts) => {
                let alert_infos: Vec<AlertInfo> = alerts
                    .into_iter()
                    .map(|a| AlertInfo {
                        id: a.id,
                        severity: a.severity.as_str().to_string(),
                        source: a.source,
                        title: a.title,
                        description: a.description,
                        status: a.status.as_str().to_string(),
                        created_at: a.created_at.to_rfc3339(),
                        updated_at: a.updated_at.to_rfc3339(),
                    })
                    .collect();

                DaemonResponse::Alerts {
                    alerts: alert_infos,
                }
            }
            Err(e) => DaemonResponse::Error {
                message: format!("Failed to list alerts: {}", e),
            },
        }
    }

    fn handle_acknowledge_alert(&self, id: String) -> DaemonResponse {
        match self.alert_db.lock().unwrap().acknowledge(&id) {
            Ok(true) => DaemonResponse::Success {
                message: format!("Alert {} acknowledged", id),
            },
            Ok(false) => DaemonResponse::Error {
                message: format!("Alert {} not found", id),
            },
            Err(e) => DaemonResponse::Error {
                message: format!("Failed to acknowledge alert: {}", e),
            },
        }
    }

    fn handle_dismiss_alert(&self, id: String) -> DaemonResponse {
        match self.alert_db.lock().unwrap().dismiss(&id) {
            Ok(true) => DaemonResponse::Success {
                message: format!("Alert {} dismissed", id),
            },
            Ok(false) => DaemonResponse::Error {
                message: format!("Alert {} not found", id),
            },
            Err(e) => DaemonResponse::Error {
                message: format!("Failed to dismiss alert: {}", e),
            },
        }
    }

    fn handle_acknowledge_all_alerts(&self) -> DaemonResponse {
        match self.alert_db.lock().unwrap().acknowledge_all() {
            Ok(count) => DaemonResponse::Success {
                message: format!("Acknowledged {} alert(s)", count),
            },
            Err(e) => DaemonResponse::Error {
                message: format!("Failed to acknowledge alerts: {}", e),
            },
        }
    }
}
