//! CX Linux Daemon Client
//!
//! Communicates with the CX Linux daemon for:
//! - Agent orchestration
//! - System-wide AI context
//! - Fine-tuned LLM access
//! - Continuous learning pipeline

// CX Terminal: Scaffolded for future daemon integration
#![allow(dead_code)]
#![allow(unused_imports)]

mod agent_router;
mod client;
pub mod protocol;

pub use agent_router::DaemonAgentRouter;
pub use client::{
    AIResponse as DaemonAIResponse, AgentResponse as DaemonAgentResponse, AgentResult,
    CXDaemonClient, ConnectionState, ConnectionStateEvent, DaemonStatus, ReconnectConfig,
    SystemInfo,
};
pub use protocol::{
    AgentTask, ContextType, DaemonError, DaemonRequest, DaemonResponse, EnvironmentInfo, GitInfo,
    TerminalContext,
};

/// Default socket path for the CX daemon
pub const DEFAULT_SOCKET_PATH: &str = "/var/run/cx/daemon.sock";

/// Alternative socket path for user-level daemon
///
/// Returns the socket path in order of preference:
/// 1. $XDG_RUNTIME_DIR/cx/daemon.sock (most secure, session-scoped)
/// 2. ~/.cx/daemon.sock (user home directory)
///
/// Note: We intentionally do NOT fall back to /tmp as it is world-writable
/// and poses a security risk (socket hijacking, privilege escalation).
pub fn user_socket_path() -> std::path::PathBuf {
    if let Some(runtime_dir) = dirs_next::runtime_dir() {
        runtime_dir.join("cx/daemon.sock")
    } else if let Some(home) = dirs_next::home_dir() {
        home.join(".cx/daemon.sock")
    } else {
        // Last resort: use a path under home that we can create
        // This should rarely happen as home_dir almost always exists
        log::warn!("No home directory found, daemon socket path may not be writable");
        std::path::PathBuf::from("/var/run/user")
            .join(std::process::id().to_string())
            .join("cx/daemon.sock")
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
