//! CX Daemon Protocol
//!
//! Defines the protocol for communication with the CX Linux daemon
//! over Unix sockets using JSON serialization.

#![allow(dead_code)]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;

/// Errors that can occur when communicating with the daemon
#[derive(Error, Debug, Clone)]
pub enum DaemonError {
    #[error("Daemon not available at {0}")]
    NotAvailable(String),

    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("Request timeout")]
    Timeout,

    #[error("Protocol error: {0}")]
    Protocol(String),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Agent error: {0}")]
    AgentError(String),

    #[error("AI error: {0}")]
    AIError(String),

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("Resource not found: {0}")]
    NotFound(String),
}

/// Requests that can be sent to the CX daemon
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum DaemonRequest {
    /// Execute an agent command
    AgentExecute {
        agent: String,
        command: String,
        params: HashMap<String, String>,
        require_confirmation: bool,
    },

    /// Query the AI with terminal context
    AIQuery {
        query: String,
        context: TerminalContext,
        system_prompt: Option<String>,
        stream: bool,
    },

    /// Send command history for learning
    LearnFromHistory {
        command: String,
        output: String,
        exit_code: i32,
        duration_ms: u64,
        cwd: String,
        environment: HashMap<String, String>,
    },

    /// Get shared context from daemon
    GetContext {
        context_type: ContextType,
    },

    /// Register a terminal instance
    RegisterTerminal {
        terminal_id: String,
        pid: u32,
        tty: Option<String>,
    },

    /// Unregister a terminal instance
    UnregisterTerminal {
        terminal_id: String,
    },

    /// Ping the daemon
    Ping,

    /// Get daemon status
    Status,

    /// List available agents from daemon
    ListAgents,

    /// Get agent details
    GetAgent {
        name: String,
    },
}

/// Responses from the CX daemon
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum DaemonResponse {
    /// Operation succeeded
    Success {
        message: String,
    },

    /// Operation failed
    Error {
        code: String,
        message: String,
    },

    /// Result from agent execution
    AgentResult {
        success: bool,
        result: String,
        commands_executed: Vec<String>,
        suggestions: Vec<String>,
        error: Option<String>,
    },

    /// Response from AI query
    AIResponse {
        content: String,
        model: String,
        tokens_used: Option<u32>,
        cached: bool,
    },

    /// Streaming AI response chunk
    AIStreamChunk {
        content: String,
        done: bool,
    },

    /// Context data from daemon
    Context {
        context_type: ContextType,
        data: serde_json::Value,
    },

    /// Pong response
    Pong {
        version: String,
        uptime_secs: u64,
    },

    /// Daemon status
    Status {
        version: String,
        uptime_secs: u64,
        connected_terminals: u32,
        ai_provider: String,
        learning_enabled: bool,
        agents_available: Vec<String>,
    },

    /// List of available agents
    AgentList {
        agents: Vec<AgentInfo>,
    },

    /// Details of a specific agent
    AgentDetails {
        info: AgentInfo,
        examples: Vec<String>,
        capabilities: Vec<String>,
    },
}

/// Information about an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentInfo {
    pub name: String,
    pub description: String,
    pub icon: Option<String>,
    pub enabled: bool,
    pub source: AgentSource,
}

/// Source of an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AgentSource {
    /// Built into the daemon
    Builtin,
    /// Loaded from plugin
    Plugin(String),
    /// Custom user agent
    Custom,
}

/// Types of context that can be requested
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ContextType {
    /// Full system context
    System,
    /// Recent command history across all terminals
    CommandHistory,
    /// Learned patterns and preferences
    UserPatterns,
    /// Custom context by name
    Custom(String),
}

/// Terminal context sent with AI queries
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TerminalContext {
    /// Recent commands from this terminal
    pub recent_commands: Vec<String>,
    /// Current working directory
    pub cwd: String,
    /// Last error if any
    pub last_error: Option<String>,
    /// Environment information
    pub environment: EnvironmentInfo,
    /// Terminal ID for cross-session context
    pub terminal_id: Option<String>,
    /// Currently selected text
    pub selection: Option<String>,
}

/// Environment information
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EnvironmentInfo {
    /// Operating system
    pub os: String,
    /// Shell being used
    pub shell: String,
    /// User name
    pub user: String,
    /// Hostname
    pub hostname: String,
    /// Git repository info if in one
    pub git_info: Option<GitInfo>,
}

/// Git repository information
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GitInfo {
    /// Current branch
    pub branch: String,
    /// Repository root path
    pub root: String,
    /// Whether there are uncommitted changes
    pub dirty: bool,
    /// Remote URL
    pub remote: Option<String>,
}

/// A task that an agent can perform
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTask {
    /// Unique task ID
    pub id: String,
    /// Agent that will handle this task
    pub agent: String,
    /// Task description
    pub description: String,
    /// Commands to execute
    pub commands: Vec<String>,
    /// Whether confirmation is required
    pub requires_confirmation: bool,
    /// Task priority
    pub priority: TaskPriority,
    /// Task status
    pub status: TaskStatus,
}

/// Task priority levels
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskPriority {
    Low,
    Normal,
    High,
    Critical,
}

/// Task status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskStatus {
    Pending,
    Running,
    Completed,
    Failed(String),
    Cancelled,
}

impl DaemonRequest {
    /// Create a new agent execute request
    pub fn agent_execute(agent: &str, command: &str) -> Self {
        Self::AgentExecute {
            agent: agent.to_string(),
            command: command.to_string(),
            params: HashMap::new(),
            require_confirmation: true,
        }
    }

    /// Create a new AI query request
    pub fn ai_query(query: &str, context: TerminalContext) -> Self {
        Self::AIQuery {
            query: query.to_string(),
            context,
            system_prompt: None,
            stream: true,
        }
    }

    /// Create a learn from history request
    pub fn learn(
        command: &str,
        output: &str,
        exit_code: i32,
        duration_ms: u64,
        cwd: &str,
    ) -> Self {
        Self::LearnFromHistory {
            command: command.to_string(),
            output: output.to_string(),
            exit_code,
            duration_ms,
            cwd: cwd.to_string(),
            environment: HashMap::new(),
        }
    }

    /// Serialize the request to JSON
    pub fn to_json(&self) -> Result<String, DaemonError> {
        serde_json::to_string(self).map_err(|e| DaemonError::Serialization(e.to_string()))
    }

    /// Serialize the request to JSON with newline
    pub fn to_json_line(&self) -> Result<String, DaemonError> {
        let mut json = self.to_json()?;
        json.push('\n');
        Ok(json)
    }
}

impl DaemonResponse {
    /// Deserialize a response from JSON
    pub fn from_json(json: &str) -> Result<Self, DaemonError> {
        serde_json::from_str(json).map_err(|e| DaemonError::Serialization(e.to_string()))
    }

    /// Check if this is an error response
    pub fn is_error(&self) -> bool {
        matches!(self, DaemonResponse::Error { .. })
    }

    /// Get error message if this is an error response
    pub fn error_message(&self) -> Option<&str> {
        if let DaemonResponse::Error { message, .. } = self {
            Some(message)
        } else {
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_serialize_agent_request() {
        let req = DaemonRequest::agent_execute("git", "show status");
        let json = req.to_json().unwrap();
        assert!(json.contains("AgentExecute"));
        assert!(json.contains("git"));
        assert!(json.contains("show status"));
    }

    #[test]
    fn test_serialize_ai_query() {
        let ctx = TerminalContext {
            cwd: "/home/user".to_string(),
            ..Default::default()
        };
        let req = DaemonRequest::ai_query("explain this error", ctx);
        let json = req.to_json().unwrap();
        assert!(json.contains("AIQuery"));
        assert!(json.contains("explain this error"));
    }

    #[test]
    fn test_deserialize_response() {
        let json = r#"{"type":"Success","data":{"message":"OK"}}"#;
        let resp = DaemonResponse::from_json(json).unwrap();
        assert!(matches!(resp, DaemonResponse::Success { .. }));
    }

    #[test]
    fn test_error_response() {
        let resp = DaemonResponse::Error {
            code: "NOT_FOUND".to_string(),
            message: "Agent not found".to_string(),
        };
        assert!(resp.is_error());
        assert_eq!(resp.error_message(), Some("Agent not found"));
    }
}
