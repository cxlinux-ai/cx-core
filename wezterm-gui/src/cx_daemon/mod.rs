//! CX Linux Daemon Client
//!
//! Communicates with the CX Linux daemon for:
//! - Agent orchestration
//! - System-wide AI context
//! - Fine-tuned LLM access
//! - Continuous learning pipeline

#![allow(dead_code)]

mod agent_router;
mod client;
mod protocol;

pub use agent_router::DaemonAgentRouter;
pub use client::CXDaemonClient;
pub use protocol::{AgentTask, DaemonError, DaemonRequest, DaemonResponse};

/// Default socket path for the CX daemon
pub const DEFAULT_SOCKET_PATH: &str = "/var/run/cx/daemon.sock";

/// Alternative socket path for user-level daemon
pub fn user_socket_path() -> std::path::PathBuf {
    if let Some(runtime_dir) = dirs_next::runtime_dir() {
        runtime_dir.join("cx/daemon.sock")
    } else if let Some(home) = dirs_next::home_dir() {
        home.join(".cx/daemon.sock")
    } else {
        std::path::PathBuf::from("/tmp/cx-daemon.sock")
    }
}

/// Check if the CX daemon is available
pub fn is_daemon_available() -> bool {
    CXDaemonClient::is_available()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_user_socket_path() {
        let path = user_socket_path();
        // Should have some path, even if daemon doesn't exist
        assert!(!path.to_string_lossy().is_empty());
    }

    #[test]
    fn test_is_daemon_available() {
        // This will typically be false in test environment
        let _ = is_daemon_available();
    }
}
