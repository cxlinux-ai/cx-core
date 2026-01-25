//! Agent runtime for managing and executing agents

use super::docker::DockerAgent;
use super::file::FileAgent;
use super::git::GitAgent;
use super::package::PackageAgent;
use super::system::SystemAgent;
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

    /// Create a runtime with all built-in agents registered and enabled
    pub fn with_builtin_agents() -> Self {
        let mut runtime = Self::new();
        runtime.register_builtin_agents();
        runtime.enable();
        runtime
    }

    /// Register all built-in agents
    pub fn register_builtin_agents(&mut self) {
        self.register(Arc::new(SystemAgent::new()));
        self.register(Arc::new(FileAgent::new()));
        self.register(Arc::new(PackageAgent::new()));
        self.register(Arc::new(GitAgent::new()));
        self.register(Arc::new(DockerAgent::new()));
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

    /// Get all registered agents with their descriptions
    pub fn list_agents(&self) -> Vec<(&str, &str)> {
        self.agents
            .values()
            .map(|a| (a.name(), a.description()))
            .collect()
    }

    /// Handle a request by routing to the appropriate agent
    pub fn handle(&self, request: AgentRequest) -> AgentResponse {
        if !self.enabled {
            return AgentResponse::error("Agent runtime is disabled".to_string());
        }

        // Try to find a specific agent by name
        if let Some(agent) = self.agents.get(&request.agent) {
            if agent.can_handle(&request) {
                return agent.handle(request);
            }
        }

        // Try to find any agent that can handle this request
        for agent in self.agents.values() {
            if agent.can_handle(&request) {
                return agent.handle(request.clone());
            }
        }

        // No agent found
        let available = self
            .agents
            .keys()
            .map(|s| s.as_str())
            .collect::<Vec<_>>()
            .join(", ");

        AgentResponse::error(format!(
            "No agent can handle: {}. Available agents: {}",
            request.command, available
        ))
        .with_suggestions(vec![
            "Try: @system show disk usage".to_string(),
            "Try: @git show status".to_string(),
            "Try: @docker list containers".to_string(),
        ])
    }

    /// Parse a natural language command and create an AgentRequest
    pub fn parse_command(&self, input: &str) -> Option<AgentRequest> {
        // Check for "@agent command" pattern
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

        // Check for explicit agent mentions
        for (name, _agent) in &self.agents {
            // Check if the input starts with the agent name
            if input_lower.starts_with(&name.to_lowercase()) {
                let command = input[name.len()..].trim();
                if !command.is_empty() {
                    return Some(AgentRequest::new(name, command));
                }
            }
        }

        // Try to infer agent from command keywords
        if let Some(agent_name) = self.infer_agent(&input_lower) {
            return Some(AgentRequest::new(&agent_name, input));
        }

        None
    }

    /// Infer which agent should handle a command based on keywords
    fn infer_agent(&self, input: &str) -> Option<String> {
        // System agent keywords
        if input.contains("system")
            || input.contains("disk")
            || input.contains("memory")
            || input.contains("service")
            || input.contains("uptime")
            || input.contains("cpu")
        {
            return Some("system".to_string());
        }

        // File agent keywords
        if input.contains("file")
            || input.contains("directory")
            || input.contains("folder")
            || input.starts_with("find ")
            || input.starts_with("search ")
            || input.starts_with("ls ")
            || input.starts_with("cat ")
        {
            return Some("file".to_string());
        }

        // Package agent keywords
        if input.contains("package")
            || input.contains("install")
            || input.contains("uninstall")
            || input.contains("apt ")
            || input.contains("brew ")
            || input.contains("pacman")
        {
            return Some("package".to_string());
        }

        // Git agent keywords
        if input.contains("git")
            || input.contains("commit")
            || input.contains("branch")
            || input.contains("merge")
            || input.contains("push")
            || input.contains("pull")
            || input.contains("checkout")
        {
            return Some("git".to_string());
        }

        // Docker agent keywords
        if input.contains("docker")
            || input.contains("container")
            || input.contains("image")
            || input.contains("podman")
            || input.contains("compose")
        {
            return Some("docker".to_string());
        }

        None
    }

    /// Execute a command directly (convenience method)
    pub fn execute(&self, input: &str) -> AgentResponse {
        if let Some(request) = self.parse_command(input) {
            self.handle(request)
        } else {
            AgentResponse::error(format!(
                "Could not parse command: {}. Try '@agent command' format.",
                input
            ))
            .with_suggestions(vec![
                "@system show disk usage".to_string(),
                "@file find *.log".to_string(),
                "@git show status".to_string(),
                "@docker list containers".to_string(),
                "@package search nodejs".to_string(),
            ])
        }
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
    fn test_parse_at_command() {
        let runtime = AgentRuntime::with_builtin_agents();

        // Test @agent format
        let req = runtime.parse_command("@git show status").unwrap();
        assert_eq!(req.agent, "git");
        assert_eq!(req.command, "show status");

        // Test agent-only format
        let req = runtime.parse_command("@system").unwrap();
        assert_eq!(req.agent, "system");
        assert_eq!(req.command, "help");
    }

    #[test]
    fn test_infer_agent() {
        let runtime = AgentRuntime::with_builtin_agents();

        // System keywords
        let req = runtime.parse_command("show disk usage").unwrap();
        assert_eq!(req.agent, "system");

        // Docker keywords
        let req = runtime.parse_command("list docker containers").unwrap();
        assert_eq!(req.agent, "docker");

        // Git keywords
        let req = runtime.parse_command("show git status").unwrap();
        assert_eq!(req.agent, "git");
    }

    #[test]
    fn test_handle_request() {
        let runtime = AgentRuntime::with_builtin_agents();

        // System request
        let response = runtime.execute("@system show uptime");
        // The response might succeed or fail depending on the system,
        // but it should not be "disabled" error
        assert!(!response.result.contains("disabled") || response.error.is_none());
    }

    #[test]
    fn test_disabled_runtime() {
        let runtime = AgentRuntime::new();

        let response = runtime.execute("@system show uptime");
        assert!(!response.success);
        assert!(response.error.as_ref().unwrap().contains("disabled"));
    }

    #[test]
    fn test_list_agents() {
        let runtime = AgentRuntime::with_builtin_agents();
        let agents = runtime.list_agents();

        // Should have at least the built-in agents
        assert!(agents.len() >= 5);

        // Check that agent names are present
        let names: Vec<_> = agents.iter().map(|(n, _)| *n).collect();
        assert!(names.contains(&"system"));
        assert!(names.contains(&"file"));
        assert!(names.contains(&"git"));
        assert!(names.contains(&"docker"));
        assert!(names.contains(&"package"));
    }
}
