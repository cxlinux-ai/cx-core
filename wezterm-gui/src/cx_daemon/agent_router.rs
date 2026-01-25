//! Daemon Agent Router
//!
//! Routes agent requests to the CX daemon if available,
//! falling back to local agents if the daemon is not running.

#![allow(dead_code)]

use super::client::{AgentResult, CXDaemonClient};
use super::protocol::DaemonError;
use crate::agents::{AgentRequest, AgentResponse, AgentRuntime};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Agent router that prefers daemon agents but falls back to local
pub struct DaemonAgentRouter {
    /// Daemon client (if available)
    daemon_client: Arc<RwLock<Option<CXDaemonClient>>>,
    /// Local agent runtime as fallback
    local_runtime: Arc<RwLock<AgentRuntime>>,
    /// Whether to prefer daemon over local agents
    prefer_daemon: bool,
    /// Whether to merge results from both sources
    merge_results: bool,
}

impl DaemonAgentRouter {
    /// Create a new agent router
    pub fn new(local_runtime: AgentRuntime) -> Self {
        Self {
            daemon_client: Arc::new(RwLock::new(None)),
            local_runtime: Arc::new(RwLock::new(local_runtime)),
            prefer_daemon: true,
            merge_results: false,
        }
    }

    /// Create a router with daemon client
    pub async fn with_daemon(local_runtime: AgentRuntime) -> Self {
        let mut router = Self::new(local_runtime);
        router.try_connect_daemon().await;
        router
    }

    /// Try to connect to the daemon
    pub async fn try_connect_daemon(&mut self) {
        if CXDaemonClient::is_available() {
            match CXDaemonClient::connect().await {
                Ok(client) => {
                    log::info!("Connected to CX daemon");
                    *self.daemon_client.write().await = Some(client);
                }
                Err(e) => {
                    log::warn!("Failed to connect to CX daemon: {}", e);
                }
            }
        } else {
            log::debug!("CX daemon not available");
        }
    }

    /// Check if daemon is available
    pub async fn is_daemon_available(&self) -> bool {
        self.daemon_client.read().await.is_some()
    }

    /// Set whether to prefer daemon over local agents
    pub fn set_prefer_daemon(&mut self, prefer: bool) {
        self.prefer_daemon = prefer;
    }

    /// Set whether to merge results from daemon and local agents
    pub fn set_merge_results(&mut self, merge: bool) {
        self.merge_results = merge;
    }

    /// Handle an agent request, routing to daemon or local as appropriate
    pub async fn handle(&self, request: AgentRequest) -> AgentResponse {
        let daemon_available = self.is_daemon_available().await;

        if self.prefer_daemon && daemon_available {
            // Try daemon first
            match self.handle_via_daemon(&request).await {
                Ok(result) => {
                    let response = self.agent_result_to_response(result);

                    if self.merge_results {
                        // Also get local result and merge
                        let local_response = self.handle_via_local(&request).await;
                        return self.merge_responses(response, local_response);
                    }

                    return response;
                }
                Err(e) => {
                    log::warn!("Daemon agent failed, falling back to local: {}", e);
                }
            }
        }

        // Fall back to local
        let response = self.handle_via_local(&request).await;

        // If daemon is available and we want merged results, try to get daemon result too
        if !self.prefer_daemon && daemon_available && self.merge_results {
            if let Ok(result) = self.handle_via_daemon(&request).await {
                let daemon_response = self.agent_result_to_response(result);
                return self.merge_responses(daemon_response, response);
            }
        }

        response
    }

    /// Handle request via daemon
    async fn handle_via_daemon(&self, request: &AgentRequest) -> Result<AgentResult, DaemonError> {
        let client_guard = self.daemon_client.read().await;
        let client = client_guard
            .as_ref()
            .ok_or_else(|| DaemonError::NotAvailable("Daemon not connected".to_string()))?;

        client
            .execute_agent(&request.agent, &request.command)
            .await
    }

    /// Handle request via local runtime
    async fn handle_via_local(&self, request: &AgentRequest) -> AgentResponse {
        let runtime = self.local_runtime.read().await;
        runtime.handle(request.clone())
    }

    /// Convert daemon AgentResult to local AgentResponse
    fn agent_result_to_response(&self, result: AgentResult) -> AgentResponse {
        if result.success {
            AgentResponse::success(result.result)
                .with_commands(result.commands_executed)
                .with_suggestions(result.suggestions)
        } else {
            AgentResponse::error(result.error.unwrap_or_else(|| "Unknown error".to_string()))
                .with_commands(result.commands_executed)
                .with_suggestions(result.suggestions)
        }
    }

    /// Merge two agent responses
    fn merge_responses(&self, primary: AgentResponse, secondary: AgentResponse) -> AgentResponse {
        let secondary_result = secondary.result.clone();
        let secondary_is_empty = secondary_result.is_empty();

        let mut result = if primary.success {
            primary.result.clone()
        } else {
            secondary_result.clone()
        };

        // If both have results, combine them
        if primary.success && secondary.success && !secondary_is_empty {
            result = format!(
                "{}\n\n---\n[Additional context]\n{}",
                primary.result, secondary.result
            );
        }

        let mut commands = primary.commands_executed;
        commands.extend(secondary.commands_executed);

        let mut suggestions = primary.suggestions;
        for suggestion in secondary.suggestions {
            if !suggestions.contains(&suggestion) {
                suggestions.push(suggestion);
            }
        }

        AgentResponse {
            success: primary.success || secondary.success,
            result,
            error: if primary.success { None } else { primary.error },
            commands_executed: commands,
            suggestions,
        }
    }

    /// Parse a command and route it appropriately
    pub async fn parse_and_handle(&self, input: &str) -> Option<AgentResponse> {
        // First try local parsing to create a request
        let request = {
            let runtime = self.local_runtime.read().await;
            runtime.parse_command(input)?
        };

        Some(self.handle(request).await)
    }

    /// List all available agents (from both daemon and local)
    pub async fn list_agents(&self) -> Vec<(String, String)> {
        let mut agents = Vec::new();

        // Get local agents
        {
            let runtime = self.local_runtime.read().await;
            for (name, desc) in runtime.list_agents() {
                agents.push((name.to_string(), format!("{} [local]", desc)));
            }
        }

        // Get daemon agents if available
        if let Some(client) = self.daemon_client.read().await.as_ref() {
            if let Ok(daemon_agents) = client.list_agents().await {
                for agent in daemon_agents {
                    // Check if we already have this agent
                    let name = agent.name.clone();
                    if !agents.iter().any(|(n, _)| n == &name) {
                        agents.push((name, format!("{} [daemon]", agent.description)));
                    }
                }
            }
        }

        agents
    }

    /// Get the daemon client for direct access
    pub async fn daemon_client(&self) -> Option<CXDaemonClient> {
        // Return a clone if we want to expose the client
        // For now, just return None as we don't want to expose internals
        None
    }

    /// Disconnect from daemon
    pub async fn disconnect(&self) {
        let mut client_guard = self.daemon_client.write().await;
        if let Some(client) = client_guard.take() {
            let _ = client.disconnect().await;
        }
    }
}

impl Default for DaemonAgentRouter {
    fn default() -> Self {
        Self::new(AgentRuntime::with_builtin_agents())
    }
}

/// Builder for DaemonAgentRouter
pub struct DaemonAgentRouterBuilder {
    local_runtime: Option<AgentRuntime>,
    prefer_daemon: bool,
    merge_results: bool,
    auto_connect: bool,
}

impl DaemonAgentRouterBuilder {
    pub fn new() -> Self {
        Self {
            local_runtime: None,
            prefer_daemon: true,
            merge_results: false,
            auto_connect: true,
        }
    }

    pub fn with_local_runtime(mut self, runtime: AgentRuntime) -> Self {
        self.local_runtime = Some(runtime);
        self
    }

    pub fn prefer_daemon(mut self, prefer: bool) -> Self {
        self.prefer_daemon = prefer;
        self
    }

    pub fn merge_results(mut self, merge: bool) -> Self {
        self.merge_results = merge;
        self
    }

    pub fn auto_connect(mut self, connect: bool) -> Self {
        self.auto_connect = connect;
        self
    }

    pub async fn build(self) -> DaemonAgentRouter {
        let runtime = self
            .local_runtime
            .unwrap_or_else(AgentRuntime::with_builtin_agents);

        let mut router = DaemonAgentRouter::new(runtime);
        router.set_prefer_daemon(self.prefer_daemon);
        router.set_merge_results(self.merge_results);

        if self.auto_connect {
            router.try_connect_daemon().await;
        }

        router
    }
}

impl Default for DaemonAgentRouterBuilder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_router_creation() {
        let router = DaemonAgentRouter::default();
        assert!(!router.is_daemon_available().await);
    }

    #[tokio::test]
    async fn test_local_fallback() {
        let router = DaemonAgentRouter::default();

        let request = AgentRequest::new("system", "show uptime");
        let response = router.handle(request).await;

        // Should get some response from local agent
        assert!(response.success || response.error.is_some());
    }

    #[tokio::test]
    async fn test_list_agents() {
        let router = DaemonAgentRouter::default();
        let agents = router.list_agents().await;

        // Should have local agents
        assert!(!agents.is_empty());

        // Check that known agents are present
        let names: Vec<_> = agents.iter().map(|(n, _)| n.as_str()).collect();
        assert!(names.contains(&"system"));
    }

    #[tokio::test]
    async fn test_builder() {
        let router = DaemonAgentRouterBuilder::new()
            .prefer_daemon(false)
            .merge_results(true)
            .auto_connect(false)
            .build()
            .await;

        assert!(!router.is_daemon_available().await);
    }
}
