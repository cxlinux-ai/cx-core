//! Agent runtime for managing and executing agents

use super::traits::{Agent, AgentRequest, AgentResponse};
use std::collections::HashMap;
use std::sync::Arc;

/// Runtime for managing agents
pub struct AgentRuntime {
    /// Registered agents
    agents: HashMap<String, Arc<dyn Agent>>,
    /// Whether the runtime is enabled
    enabled: bool,
}

impl AgentRuntime {
    /// Create a new agent runtime
    pub fn new() -> Self {
        Self {
            agents: HashMap::new(),
            enabled: false,
        }
    }

    /// Enable the agent runtime
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable the agent runtime
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Check if the runtime is enabled
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Register an agent
    pub fn register(&mut self, agent: Arc<dyn Agent>) {
        self.agents.insert(agent.name().to_string(), agent);
    }

    /// Unregister an agent
    pub fn unregister(&mut self, name: &str) -> Option<Arc<dyn Agent>> {
        self.agents.remove(name)
    }

    /// Get an agent by name
    pub fn get(&self, name: &str) -> Option<&Arc<dyn Agent>> {
        self.agents.get(name)
    }

    /// List all registered agents
    pub fn list(&self) -> Vec<&str> {
        self.agents.keys().map(|s| s.as_str()).collect()
    }

    /// Handle a request by routing to the appropriate agent
    pub fn handle(&self, request: AgentRequest) -> AgentResponse {
        if !self.enabled {
            return AgentResponse::error("Agent runtime is disabled".to_string());
        }

        // Try to find a specific agent
        if let Some(agent) = self.agents.get(&request.agent) {
            if agent.can_handle(&request) {
                return agent.handle(request);
            }
        }

        // Try to find any agent that can handle this
        for agent in self.agents.values() {
            if agent.can_handle(&request) {
                return agent.handle(request.clone());
            }
        }

        AgentResponse::error(format!("No agent can handle: {}", request.command))
    }

    /// Parse a natural language command and create an AgentRequest
    pub fn parse_command(&self, input: &str) -> Option<AgentRequest> {
        // Simple parsing: look for "@agent command" pattern
        if input.starts_with('@') {
            let parts: Vec<&str> = input[1..].splitn(2, ' ').collect();
            if parts.len() >= 2 {
                return Some(AgentRequest::new(parts[0], parts[1]));
            } else if parts.len() == 1 {
                return Some(AgentRequest::new(parts[0], "help"));
            }
        }

        // Try to match against known agent keywords
        let input_lower = input.to_lowercase();
        for (name, agent) in &self.agents {
            // Check if the input starts with the agent name
            if input_lower.starts_with(&name.to_lowercase()) {
                let command = input[name.len()..].trim();
                if !command.is_empty() {
                    return Some(AgentRequest::new(name, command));
                }
            }
        }

        None
    }
}

impl Default for AgentRuntime {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_command() {
        let runtime = AgentRuntime::new();

        // Test @agent format
        let req = runtime.parse_command("@git show status").unwrap();
        assert_eq!(req.agent, "git");
        assert_eq!(req.command, "show status");

        // Test agent-only format
        let req = runtime.parse_command("@system").unwrap();
        assert_eq!(req.agent, "system");
        assert_eq!(req.command, "help");
    }
}
