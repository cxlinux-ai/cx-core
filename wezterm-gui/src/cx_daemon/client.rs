//! CX Daemon Client
//!
//! Handles communication with the CX Linux daemon over Unix sockets.

#![allow(dead_code)]

use super::protocol::{
    AgentInfo, ContextType, DaemonError, DaemonRequest, DaemonResponse, TerminalContext,
};
use super::{user_socket_path, DEFAULT_SOCKET_PATH};
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

/// Client for communicating with the CX Linux daemon
pub struct CXDaemonClient {
    /// Path to the daemon socket
    socket_path: PathBuf,
    /// Whether currently connected
    connected: Arc<AtomicBool>,
    /// Terminal ID for this instance
    terminal_id: String,
    /// Connection timeout
    timeout: Duration,
}

impl CXDaemonClient {
    /// Create a new daemon client with default socket path
    pub fn new() -> Self {
        Self::with_socket_path(Self::find_socket_path())
    }

    /// Create a new daemon client with a specific socket path
    pub fn with_socket_path(socket_path: PathBuf) -> Self {
        Self {
            socket_path,
            connected: Arc::new(AtomicBool::new(false)),
            terminal_id: uuid::Uuid::new_v4().to_string(),
            timeout: Duration::from_secs(5),
        }
    }

    /// Find the best socket path to use
    fn find_socket_path() -> PathBuf {
        // Check system socket first
        let system_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        if system_path.exists() {
            return system_path;
        }

        // Fall back to user socket
        let user_path = user_socket_path();
        if user_path.exists() {
            return user_path;
        }

        // Return system path even if it doesn't exist (for error messages)
        system_path
    }

    /// Check if the daemon is available
    pub fn is_available() -> bool {
        let system_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        if system_path.exists() {
            return Self::test_connection(&system_path);
        }

        let user_path = user_socket_path();
        if user_path.exists() {
            return Self::test_connection(&user_path);
        }

        false
    }

    /// Test if a socket is responsive
    fn test_connection(path: &PathBuf) -> bool {
        if let Ok(stream) = UnixStream::connect(path) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));

            // Try to send a ping
            let mut stream = stream;
            let request = DaemonRequest::Ping;
            if let Ok(json) = request.to_json_line() {
                if stream.write_all(json.as_bytes()).is_ok() {
                    let mut reader = BufReader::new(&stream);
                    let mut response = String::new();
                    if reader.read_line(&mut response).is_ok() {
                        return DaemonResponse::from_json(&response)
                            .map(|r| matches!(r, DaemonResponse::Pong { .. }))
                            .unwrap_or(false);
                    }
                }
            }
        }
        false
    }

    /// Connect to the daemon
    pub async fn connect() -> Result<Self, DaemonError> {
        let client = Self::new();
        client.register_terminal().await?;
        Ok(client)
    }

    /// Register this terminal with the daemon
    async fn register_terminal(&self) -> Result<(), DaemonError> {
        let request = DaemonRequest::RegisterTerminal {
            terminal_id: self.terminal_id.clone(),
            pid: std::process::id(),
            tty: std::env::var("TTY").ok(),
        };

        match self.send_request(&request).await {
            Ok(DaemonResponse::Success { .. }) => {
                self.connected.store(true, Ordering::SeqCst);
                Ok(())
            }
            Ok(DaemonResponse::Error { message, .. }) => {
                Err(DaemonError::ConnectionFailed(message))
            }
            Ok(_) => Err(DaemonError::Protocol("Unexpected response".to_string())),
            Err(e) => Err(e),
        }
    }

    /// Unregister this terminal from the daemon
    pub async fn disconnect(&self) -> Result<(), DaemonError> {
        if !self.connected.load(Ordering::SeqCst) {
            return Ok(());
        }

        let request = DaemonRequest::UnregisterTerminal {
            terminal_id: self.terminal_id.clone(),
        };

        let _ = self.send_request(&request).await;
        self.connected.store(false, Ordering::SeqCst);
        Ok(())
    }

    /// Check if connected to the daemon
    pub fn is_connected(&self) -> bool {
        self.connected.load(Ordering::SeqCst)
    }

    /// Execute an agent command through the daemon
    pub async fn execute_agent(
        &self,
        agent: &str,
        command: &str,
    ) -> Result<AgentResult, DaemonError> {
        let request = DaemonRequest::agent_execute(agent, command);

        match self.send_request(&request).await? {
            DaemonResponse::AgentResult {
                success,
                result,
                commands_executed,
                suggestions,
                error,
            } => Ok(AgentResult {
                success,
                result,
                commands_executed,
                suggestions,
                error,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::AgentError(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Query AI through the daemon (uses fine-tuned CX model)
    pub async fn query_ai(
        &self,
        query: &str,
        context: &TerminalContext,
    ) -> Result<AIResponse, DaemonError> {
        let mut ctx = context.clone();
        ctx.terminal_id = Some(self.terminal_id.clone());

        let request = DaemonRequest::AIQuery {
            query: query.to_string(),
            context: ctx,
            system_prompt: None,
            stream: false,
        };

        match self.send_request(&request).await? {
            DaemonResponse::AIResponse {
                content,
                model,
                tokens_used,
                cached,
            } => Ok(AIResponse {
                content,
                model,
                tokens_used,
                cached,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::AIError(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Query AI with streaming response
    pub async fn query_ai_stream(
        &self,
        query: &str,
        context: &TerminalContext,
        mut on_chunk: impl FnMut(String),
    ) -> Result<(), DaemonError> {
        let mut ctx = context.clone();
        ctx.terminal_id = Some(self.terminal_id.clone());

        let request = DaemonRequest::AIQuery {
            query: query.to_string(),
            context: ctx,
            system_prompt: None,
            stream: true,
        };

        let stream = self.connect_stream()?;
        let mut stream_writer = stream.try_clone().map_err(|e| {
            DaemonError::ConnectionFailed(format!("Failed to clone stream: {}", e))
        })?;

        // Send request
        let json = request.to_json_line()?;
        stream_writer
            .write_all(json.as_bytes())
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

        // Read streaming response
        let reader = BufReader::new(&stream);
        for line in reader.lines() {
            let line = line.map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

            match DaemonResponse::from_json(&line)? {
                DaemonResponse::AIStreamChunk { content, done } => {
                    on_chunk(content);
                    if done {
                        break;
                    }
                }
                DaemonResponse::Error { message, .. } => {
                    return Err(DaemonError::AIError(message));
                }
                _ => {}
            }
        }

        Ok(())
    }

    /// Send command history for learning
    pub async fn learn_from_command(
        &self,
        command: &str,
        output: &str,
        exit_code: i32,
        duration_ms: u64,
        cwd: &str,
    ) -> Result<(), DaemonError> {
        // Truncate output if too long
        let max_output_len = 10000;
        let truncated_output = if output.len() > max_output_len {
            format!("{}...[truncated]", &output[..max_output_len])
        } else {
            output.to_string()
        };

        let request = DaemonRequest::learn(command, &truncated_output, exit_code, duration_ms, cwd);

        // Fire and forget - don't wait for response
        let _ = self.send_request_no_wait(&request);
        Ok(())
    }

    /// Get context from daemon
    pub async fn get_context(
        &self,
        context_type: ContextType,
    ) -> Result<serde_json::Value, DaemonError> {
        let request = DaemonRequest::GetContext { context_type };

        match self.send_request(&request).await? {
            DaemonResponse::Context { data, .. } => Ok(data),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotFound(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// List available agents from daemon
    pub async fn list_agents(&self) -> Result<Vec<AgentInfo>, DaemonError> {
        let request = DaemonRequest::ListAgents;

        match self.send_request(&request).await? {
            DaemonResponse::AgentList { agents } => Ok(agents),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotFound(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Get daemon status
    pub async fn status(&self) -> Result<DaemonStatus, DaemonError> {
        let request = DaemonRequest::Status;

        match self.send_request(&request).await? {
            DaemonResponse::Status {
                version,
                uptime_secs,
                connected_terminals,
                ai_provider,
                learning_enabled,
                agents_available,
            } => Ok(DaemonStatus {
                version,
                uptime_secs,
                connected_terminals,
                ai_provider,
                learning_enabled,
                agents_available,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotAvailable(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Send a request and wait for response
    async fn send_request(&self, request: &DaemonRequest) -> Result<DaemonResponse, DaemonError> {
        // Use synchronous IO wrapped in spawn_blocking for async
        let socket_path = self.socket_path.clone();
        let timeout = self.timeout;
        let json = request.to_json_line()?;

        let response = tokio::task::spawn_blocking(move || {
            let stream = UnixStream::connect(&socket_path).map_err(|e| {
                DaemonError::NotAvailable(format!("{}: {}", socket_path.display(), e))
            })?;

            stream
                .set_read_timeout(Some(timeout))
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;
            stream
                .set_write_timeout(Some(timeout))
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

            let mut stream = stream;
            stream
                .write_all(json.as_bytes())
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

            let mut reader = BufReader::new(&stream);
            let mut response = String::new();
            reader
                .read_line(&mut response)
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

            DaemonResponse::from_json(&response)
        })
        .await
        .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))??;

        Ok(response)
    }

    /// Send a request without waiting for response
    fn send_request_no_wait(&self, request: &DaemonRequest) -> Result<(), DaemonError> {
        let json = request.to_json_line()?;
        let socket_path = self.socket_path.clone();

        // Spawn a background task to send
        std::thread::spawn(move || {
            if let Ok(mut stream) = UnixStream::connect(&socket_path) {
                let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
                let _ = stream.write_all(json.as_bytes());
            }
        });

        Ok(())
    }

    /// Connect to daemon and return the stream
    fn connect_stream(&self) -> Result<UnixStream, DaemonError> {
        let stream = UnixStream::connect(&self.socket_path).map_err(|e| {
            DaemonError::NotAvailable(format!("{}: {}", self.socket_path.display(), e))
        })?;

        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;
        stream
            .set_write_timeout(Some(self.timeout))
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

        Ok(stream)
    }

    /// Get terminal ID
    pub fn terminal_id(&self) -> &str {
        &self.terminal_id
    }
}

impl Default for CXDaemonClient {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for CXDaemonClient {
    fn drop(&mut self) {
        if self.connected.load(Ordering::SeqCst) {
            // Try to unregister on drop
            let request = DaemonRequest::UnregisterTerminal {
                terminal_id: self.terminal_id.clone(),
            };
            let _ = self.send_request_no_wait(&request);
        }
    }
}

/// Result from agent execution
#[derive(Debug, Clone)]
pub struct AgentResult {
    pub success: bool,
    pub result: String,
    pub commands_executed: Vec<String>,
    pub suggestions: Vec<String>,
    pub error: Option<String>,
}

/// Response from AI query
#[derive(Debug, Clone)]
pub struct AIResponse {
    pub content: String,
    pub model: String,
    pub tokens_used: Option<u32>,
    pub cached: bool,
}

/// Daemon status information
#[derive(Debug, Clone)]
pub struct DaemonStatus {
    pub version: String,
    pub uptime_secs: u64,
    pub connected_terminals: u32,
    pub ai_provider: String,
    pub learning_enabled: bool,
    pub agents_available: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let client = CXDaemonClient::new();
        assert!(!client.terminal_id.is_empty());
    }

    #[test]
    fn test_find_socket_path() {
        let path = CXDaemonClient::find_socket_path();
        // Should always return some path
        assert!(!path.to_string_lossy().is_empty());
    }

    #[tokio::test]
    async fn test_is_available() {
        // This will typically be false in test environment
        let _ = CXDaemonClient::is_available();
    }
}
