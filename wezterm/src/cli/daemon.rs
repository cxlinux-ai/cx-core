//! CLI commands for interacting with the CX daemon

use anyhow::{Context, Result};
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;

/// Daemon management commands
#[derive(Debug, Parser, Clone)]
pub struct DaemonCommand {
    #[command(subcommand)]
    pub subcommand: DaemonSubCommand,
}

#[derive(Debug, Parser, Clone)]
pub enum DaemonSubCommand {
    /// Show daemon status
    Status {
        /// Show verbose status with health information
        #[arg(short, long)]
        verbose: bool,
    },

    /// Show system health
    Health,

    /// List and manage alerts
    Alerts {
        /// Filter by status (active, acknowledged, dismissed)
        #[arg(long)]
        status: Option<String>,

        /// Filter by severity (info, warning, error, critical)
        #[arg(long)]
        severity: Option<String>,

        /// Acknowledge all active alerts
        #[arg(long)]
        acknowledge_all: bool,

        /// Acknowledge specific alert by ID
        #[arg(long)]
        acknowledge: Option<String>,

        /// Dismiss specific alert by ID
        #[arg(long)]
        dismiss: Option<String>,
    },
}

#[derive(Debug, Serialize)]
#[serde(tag = "type", content = "data")]
enum Request {
    Status,
    Health,
    Alerts {
        status: Option<String>,
        severity: Option<String>,
    },
    AcknowledgeAlert {
        id: String,
    },
    DismissAlert {
        id: String,
    },
    AcknowledgeAllAlerts,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type", content = "data")]
enum Response {
    Status {
        version: String,
        uptime_secs: u64,
        monitoring_enabled: bool,
        alert_count: usize,
    },
    Health {
        memory_usage_percent: f64,
        disk_usage_percent: f64,
        failed_services: Vec<String>,
        uptime_secs: u64,
    },
    Alerts {
        alerts: Vec<AlertInfo>,
    },
    Success {
        message: String,
    },
    Error {
        message: String,
    },
}

#[derive(Debug, Deserialize)]
struct AlertInfo {
    id: String,
    severity: String,
    source: String,
    title: String,
    description: String,
    status: String,
    created_at: String,
    updated_at: String,
}

impl DaemonCommand {
    pub fn run(&self) -> Result<()> {
        match &self.subcommand {
            DaemonSubCommand::Status { verbose } => self.status(*verbose),
            DaemonSubCommand::Health => self.health(),
            DaemonSubCommand::Alerts {
                status,
                severity,
                acknowledge_all,
                acknowledge,
                dismiss,
            } => self.alerts(
                status.clone(),
                severity.clone(),
                *acknowledge_all,
                acknowledge.clone(),
                dismiss.clone(),
            ),
        }
    }

    fn status(&self, verbose: bool) -> Result<()> {
        let response = self.send_request(Request::Status)?;

        match response {
            Response::Status {
                version,
                uptime_secs,
                monitoring_enabled,
                alert_count,
            } => {
                println!("CX Daemon Status");
                println!("  Version: {}", version);
                println!("  Uptime: {} seconds", uptime_secs);
                println!(
                    "  Monitoring: {}",
                    if monitoring_enabled {
                        "enabled"
                    } else {
                        "disabled"
                    }
                );
                println!("  Active Alerts: {}", alert_count);

                if verbose {
                    println!();
                    let health_response = self.send_request(Request::Health)?;
                    if let Response::Health {
                        memory_usage_percent,
                        disk_usage_percent,
                        failed_services,
                        ..
                    } = health_response
                    {
                        println!("System Health:");
                        println!("  Memory Usage: {:.1}%", memory_usage_percent);
                        println!("  Disk Usage: {:.1}%", disk_usage_percent);
                        if !failed_services.is_empty() {
                            println!("  Failed Services: {}", failed_services.join(", "));
                        } else {
                            println!("  Failed Services: none");
                        }
                    }
                }

                Ok(())
            }
            Response::Error { message } => {
                anyhow::bail!("Daemon error: {}", message);
            }
            _ => {
                anyhow::bail!("Unexpected response from daemon");
            }
        }
    }

    fn health(&self) -> Result<()> {
        let response = self.send_request(Request::Health)?;

        match response {
            Response::Health {
                memory_usage_percent,
                disk_usage_percent,
                failed_services,
                uptime_secs,
            } => {
                println!("System Health");
                println!("  Memory Usage: {:.1}%", memory_usage_percent);
                println!("  Disk Usage: {:.1}%", disk_usage_percent);
                println!("  Uptime: {} seconds", uptime_secs);

                if !failed_services.is_empty() {
                    println!("  Failed Services:");
                    for service in failed_services {
                        println!("    - {}", service);
                    }
                } else {
                    println!("  Failed Services: none");
                }

                Ok(())
            }
            Response::Error { message } => {
                anyhow::bail!("Daemon error: {}", message);
            }
            _ => {
                anyhow::bail!("Unexpected response from daemon");
            }
        }
    }

    fn alerts(
        &self,
        status: Option<String>,
        severity: Option<String>,
        acknowledge_all: bool,
        acknowledge: Option<String>,
        dismiss: Option<String>,
    ) -> Result<()> {
        // Handle actions first
        if acknowledge_all {
            let response = self.send_request(Request::AcknowledgeAllAlerts)?;
            match response {
                Response::Success { message } => {
                    println!("{}", message);
                    return Ok(());
                }
                Response::Error { message } => {
                    anyhow::bail!("Failed to acknowledge alerts: {}", message);
                }
                _ => {
                    anyhow::bail!("Unexpected response from daemon");
                }
            }
        }

        if let Some(id) = acknowledge {
            let response = self.send_request(Request::AcknowledgeAlert { id })?;
            match response {
                Response::Success { message } => {
                    println!("{}", message);
                    return Ok(());
                }
                Response::Error { message } => {
                    anyhow::bail!("Failed to acknowledge alert: {}", message);
                }
                _ => {
                    anyhow::bail!("Unexpected response from daemon");
                }
            }
        }

        if let Some(id) = dismiss {
            let response = self.send_request(Request::DismissAlert { id })?;
            match response {
                Response::Success { message } => {
                    println!("{}", message);
                    return Ok(());
                }
                Response::Error { message } => {
                    anyhow::bail!("Failed to dismiss alert: {}", message);
                }
                _ => {
                    anyhow::bail!("Unexpected response from daemon");
                }
            }
        }

        // List alerts
        let response = self.send_request(Request::Alerts { status, severity })?;

        match response {
            Response::Alerts { alerts } => {
                if alerts.is_empty() {
                    println!("No alerts found");
                } else {
                    println!("Alerts ({})", alerts.len());
                    println!();
                    for alert in alerts {
                        println!("ID: {}", alert.id);
                        println!("  Severity: {}", alert.severity);
                        println!("  Source: {}", alert.source);
                        println!("  Title: {}", alert.title);
                        println!("  Description: {}", alert.description);
                        println!("  Status: {}", alert.status);
                        println!("  Created: {}", alert.created_at);
                        println!();
                    }
                }
                Ok(())
            }
            Response::Error { message } => {
                anyhow::bail!("Daemon error: {}", message);
            }
            _ => {
                anyhow::bail!("Unexpected response from daemon");
            }
        }
    }

    fn send_request(&self, request: Request) -> Result<Response> {
        let socket_path = get_socket_path();

        let mut stream = UnixStream::connect(&socket_path)
            .with_context(|| format!("Failed to connect to daemon at {}", socket_path.display()))?;

        // Send request
        let json = serde_json::to_string(&request)?;
        writeln!(stream, "{}", json)?;
        stream.flush()?;

        // Read response
        let mut reader = BufReader::new(stream);
        let mut response_line = String::new();
        reader.read_line(&mut response_line)?;

        let response: Response =
            serde_json::from_str(&response_line).context("Failed to parse daemon response")?;

        Ok(response)
    }
}

fn get_socket_path() -> PathBuf {
    // Use shared path logic from cx-daemon
    cx_daemon::get_daemon_socket_path()
}
