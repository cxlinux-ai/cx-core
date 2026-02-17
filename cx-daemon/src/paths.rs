//! Shared utilities for CX daemon

use std::path::PathBuf;

/// Get the daemon socket path using consistent logic
///
/// Priority order:
/// 1. $XDG_RUNTIME_DIR/cx/daemon.sock (most secure, session-scoped)
/// 2. ~/.cx/daemon.sock (user home directory)
/// 3. /var/run/cx/daemon.sock (system-wide fallback)
pub fn get_daemon_socket_path() -> PathBuf {
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        PathBuf::from(runtime_dir).join("cx/daemon.sock")
    } else if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".cx/daemon.sock")
    } else {
        PathBuf::from("/var/run/cx/daemon.sock")
    }
}

/// Get the alert database path
///
/// Priority order:
/// 1. ~/.cx/alerts.db (user home directory)
/// 2. /var/lib/cx/alerts.db (system-wide fallback)
pub fn get_alert_db_path() -> PathBuf {
    if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".cx/alerts.db")
    } else {
        PathBuf::from("/var/lib/cx/alerts.db")
    }
}
