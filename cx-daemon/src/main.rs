//! CX Daemon - System monitoring and alert management daemon for CX Linux
//!
//! The daemon provides:
//! - System health monitoring (memory, disk, services)
//! - Persistent alert management with SQLite storage
//! - IPC interface via Unix socket for terminal integration

use anyhow::{Context, Result};
use clap::Parser;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

mod alerts;
mod ipc;
mod monitoring;
mod paths;

use alerts::AlertDatabase;
use ipc::{DaemonRequest, DaemonResponse, RequestHandler};
use monitoring::{MonitoringConfig, MonitoringService};

/// CX Daemon - Background service for system monitoring
#[derive(Parser, Debug)]
#[command(name = "cx-daemon", about = "CX Linux system monitoring daemon")]
struct Args {
    /// Unix socket path for IPC
    #[arg(long)]
    socket: Option<PathBuf>,

    /// Database path for alert storage
    #[arg(long)]
    database: Option<PathBuf>,

    /// Run in foreground (don't daemonize)
    #[arg(long)]
    foreground: bool,

    /// Memory warning threshold (percentage)
    #[arg(long, default_value = "80.0")]
    memory_warning: f64,

    /// Memory critical threshold (percentage)
    #[arg(long, default_value = "95.0")]
    memory_critical: f64,

    /// Disk warning threshold (percentage)
    #[arg(long, default_value = "85.0")]
    disk_warning: f64,

    /// Disk critical threshold (percentage)
    #[arg(long, default_value = "95.0")]
    disk_critical: f64,

    /// Monitoring check interval in seconds
    #[arg(long, default_value = "300")]
    check_interval: u64,

    /// Verbose logging
    #[arg(short, long)]
    verbose: bool,
}

fn get_default_socket_path() -> PathBuf {
    paths::get_daemon_socket_path()
}

fn get_default_db_path() -> PathBuf {
    paths::get_alert_db_path()
}

fn main() {
    if let Err(e) = run() {
        eprintln!("Error: {:#}", e);
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    env_bootstrap::bootstrap();

    let args = Args::parse();

    // env_bootstrap already initializes logging, just set level if verbose
    if args.verbose {
        log::set_max_level(log::LevelFilter::Debug);
    }

    log::info!("Starting CX Daemon v{}", env!("CARGO_PKG_VERSION"));

    // Get paths with defaults
    let socket_path = args.socket.unwrap_or_else(get_default_socket_path);
    let database_path = args.database.unwrap_or_else(get_default_db_path);

    // Initialize alert database
    let alert_db = Arc::new(Mutex::new(
        AlertDatabase::open(database_path.clone()).context("Failed to open alert database")?,
    ));

    log::info!("Alert database opened at {}", database_path.display());

    // Initialize monitoring service
    let monitoring_config = MonitoringConfig {
        memory_warning_threshold: args.memory_warning,
        memory_critical_threshold: args.memory_critical,
        disk_warning_threshold: args.disk_warning,
        disk_critical_threshold: args.disk_critical,
        check_interval_secs: args.check_interval,
    };

    let monitoring = Arc::new(MonitoringService::new(
        monitoring_config.clone(),
        alert_db.clone(),
    ));

    log::info!("Monitoring service initialized");

    // Start monitoring thread
    let monitoring_thread = {
        let monitoring = monitoring.clone();
        let interval = Duration::from_secs(monitoring_config.check_interval_secs);

        thread::spawn(move || {
            log::info!(
                "Monitoring thread started (interval: {} seconds)",
                monitoring_config.check_interval_secs
            );
            loop {
                if let Err(e) = monitoring.check_and_alert() {
                    log::error!("Monitoring check failed: {}", e);
                }
                thread::sleep(interval);
            }
        })
    };

    // Setup IPC handler
    let handler = Arc::new(RequestHandler::new(alert_db.clone(), monitoring.clone()));

    // Setup Unix socket

    // Remove existing socket if it exists
    if socket_path.exists() {
        std::fs::remove_file(&socket_path).context("Failed to remove existing socket")?;
    }

    // Create parent directory if needed
    if let Some(parent) = socket_path.parent() {
        std::fs::create_dir_all(parent).context("Failed to create socket directory")?;
    }

    let listener = UnixListener::bind(&socket_path).context("Failed to bind to Unix socket")?;

    log::info!("Daemon listening on {}", socket_path.display());

    // Main event loop
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let handler = handler.clone();
                thread::spawn(move || {
                    if let Err(e) = handle_client(stream, handler) {
                        log::error!("Error handling client: {}", e);
                    }
                });
            }
            Err(e) => {
                log::error!("Connection error: {}", e);
            }
        }
    }

    // Wait for monitoring thread (this will never exit normally)
    monitoring_thread.join().ok();

    Ok(())
}

fn handle_client(stream: UnixStream, handler: Arc<RequestHandler>) -> Result<()> {
    let mut reader = BufReader::new(&stream);
    let mut writer = stream.try_clone()?;

    loop {
        let mut line = String::new();
        let bytes_read = reader.read_line(&mut line)?;

        if bytes_read == 0 {
            // Client disconnected
            break;
        }

        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        log::debug!("Received request: {}", line);

        // Parse request
        let response = match DaemonRequest::from_json(line) {
            Ok(request) => {
                let resp = handler.handle(request.clone());

                // Check for shutdown request
                if matches!(request, DaemonRequest::Shutdown) {
                    log::info!("Shutdown requested, exiting...");
                    // Send response before exiting
                    let json = resp.to_json().unwrap_or_else(|_| "{}".to_string());
                    writeln!(writer, "{}", json)?;
                    writer.flush()?;
                    std::process::exit(0);
                }

                resp
            }
            Err(e) => DaemonResponse::Error {
                message: format!("Invalid request: {}", e),
            },
        };

        // Send response
        let json = response.to_json()?;
        writeln!(writer, "{}", json)?;
        writer.flush()?;

        log::debug!("Sent response: {}", json);
    }

    Ok(())
}
