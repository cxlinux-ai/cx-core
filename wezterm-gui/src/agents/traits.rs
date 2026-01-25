//! Agent trait definitions

use std::collections::HashMap;

/// Capabilities that an agent can provide
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum AgentCapability {
    /// Can execute shell commands
    Execute,
    /// Can read files
    ReadFile,
    /// Can write files
    WriteFile,
    /// Can manage packages
    PackageManage,
    /// Can manage services
    ServiceManage,
    /// Can manage network
    NetworkManage,
    /// Custom capability
    Custom(String),
}

/// A request to an agent
#[derive(Debug, Clone)]
pub struct AgentRequest {
    /// The agent to handle this request
    pub agent: String,
    /// The command or query
    pub command: String,
    /// Additional parameters
    pub params: HashMap<String, String>,
    /// Whether to require confirmation before execution
    pub require_confirmation: bool,
}

impl AgentRequest {
    pub fn new(agent: &str, command: &str) -> Self {
        Self {
            agent: agent.to_string(),
            command: command.to_string(),
            params: HashMap::new(),
            require_confirmation: true,
        }
    }

    pub fn with_param(mut self, key: &str, value: &str) -> Self {
        self.params.insert(key.to_string(), value.to_string());
        self
    }

    pub fn auto_execute(mut self) -> Self {
        self.require_confirmation = false;
        self
    }
}

/// A response from an agent
#[derive(Debug, Clone)]
pub struct AgentResponse {
    /// Whether the operation succeeded
    pub success: bool,
    /// The result or output
    pub result: String,
    /// Any error message
    pub error: Option<String>,
    /// Commands that were executed
    pub commands_executed: Vec<String>,
    /// Suggested follow-up actions
    pub suggestions: Vec<String>,
}

impl AgentResponse {
    pub fn success(result: String) -> Self {
        Self {
            success: true,
            result,
            error: None,
            commands_executed: Vec::new(),
            suggestions: Vec::new(),
        }
    }

    pub fn error(error: String) -> Self {
        Self {
            success: false,
            result: String::new(),
            error: Some(error),
            commands_executed: Vec::new(),
            suggestions: Vec::new(),
        }
    }

    pub fn with_commands(mut self, commands: Vec<String>) -> Self {
        self.commands_executed = commands;
        self
    }

    pub fn with_suggestions(mut self, suggestions: Vec<String>) -> Self {
        self.suggestions = suggestions;
        self
    }
}

/// Trait for implementing agents
pub trait Agent: Send + Sync {
    /// Get the agent's name
    fn name(&self) -> &str;

    /// Get the agent's description
    fn description(&self) -> &str;

    /// Get the capabilities this agent provides
    fn capabilities(&self) -> &[AgentCapability];

    /// Check if this agent can handle the given request
    fn can_handle(&self, request: &AgentRequest) -> bool;

    /// Handle a request
    fn handle(&self, request: AgentRequest) -> AgentResponse;

    /// Get example commands for this agent
    fn examples(&self) -> &[&str] {
        &[]
    }
}
