//! AI Provider abstraction

use super::{AIConfig, AIProviderType, ChatMessage, ChatRole};
use std::future::Future;
use std::pin::Pin;

/// Response from AI provider
#[derive(Debug, Clone)]
pub struct AIResponse {
    pub content: String,
    pub finish_reason: Option<String>,
    pub tokens_used: Option<u32>,
}

/// Configuration for AI provider
#[derive(Debug, Clone)]
pub struct AIProviderConfig {
    pub provider_type: AIProviderType,
    pub endpoint: String,
    pub api_key: Option<String>,
    pub model: String,
    pub max_tokens: u32,
    pub temperature: f32,
}

impl From<&AIConfig> for AIProviderConfig {
    fn from(config: &AIConfig) -> Self {
        Self {
            provider_type: config.provider,
            endpoint: config
                .api_endpoint
                .clone()
                .or_else(|| config.provider.default_endpoint().map(String::from))
                .unwrap_or_default(),
            api_key: config.api_key.clone(),
            model: if config.model.is_empty() {
                config.provider.default_model().to_string()
            } else {
                config.model.clone()
            },
            max_tokens: config.max_tokens,
            temperature: config.temperature,
        }
    }
}

/// Trait for AI providers
pub trait AIProvider: Send + Sync {
    /// Send a chat completion request
    fn chat_completion(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponse, AIError>> + Send + '_>>;

    /// Stream a chat completion (returns chunks)
    fn chat_completion_stream(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponseStream, AIError>> + Send + '_>>;

    /// Check if provider is available/configured
    fn is_available(&self) -> bool;

    /// Get provider name
    fn name(&self) -> &str;
}

/// Streaming response
pub struct AIResponseStream {
    // This would be implemented with async-stream or similar
    // For now, placeholder
    chunks: Vec<String>,
    position: usize,
}

impl AIResponseStream {
    pub fn new(chunks: Vec<String>) -> Self {
        Self { chunks, position: 0 }
    }

    pub fn next_chunk(&mut self) -> Option<String> {
        if self.position < self.chunks.len() {
            let chunk = self.chunks[self.position].clone();
            self.position += 1;
            Some(chunk)
        } else {
            None
        }
    }
}

/// AI provider errors
#[derive(Debug)]
pub enum AIError {
    /// Provider not configured
    NotConfigured,
    /// API error
    ApiError(String),
    /// Network error
    NetworkError(String),
    /// Rate limited
    RateLimited,
    /// Invalid response
    InvalidResponse(String),
    /// Authentication error
    AuthError,
    /// Model not found
    ModelNotFound,
    /// Context too long
    ContextTooLong,
}

impl std::fmt::Display for AIError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AIError::NotConfigured => write!(f, "AI provider not configured"),
            AIError::ApiError(msg) => write!(f, "API error: {}", msg),
            AIError::NetworkError(msg) => write!(f, "Network error: {}", msg),
            AIError::RateLimited => write!(f, "Rate limited, please try again later"),
            AIError::InvalidResponse(msg) => write!(f, "Invalid response: {}", msg),
            AIError::AuthError => write!(f, "Authentication failed"),
            AIError::ModelNotFound => write!(f, "Model not found"),
            AIError::ContextTooLong => write!(f, "Context too long, try a shorter input"),
        }
    }
}

impl std::error::Error for AIError {}

/// Format messages for Claude API
pub fn format_for_claude(messages: &[ChatMessage], system: Option<&str>) -> serde_json::Value {
    let msgs: Vec<serde_json::Value> = messages
        .iter()
        .filter(|m| m.role != ChatRole::System)
        .map(|m| {
            serde_json::json!({
                "role": match m.role {
                    ChatRole::User => "user",
                    ChatRole::Assistant => "assistant",
                    ChatRole::System => "user", // Shouldn't happen
                },
                "content": m.content
            })
        })
        .collect();

    let mut request = serde_json::json!({
        "messages": msgs,
    });

    if let Some(sys) = system {
        request["system"] = serde_json::Value::String(sys.to_string());
    }

    request
}

/// Format messages for OpenAI API
pub fn format_for_openai(messages: &[ChatMessage], system: Option<&str>) -> serde_json::Value {
    let mut msgs: Vec<serde_json::Value> = Vec::new();

    if let Some(sys) = system {
        msgs.push(serde_json::json!({
            "role": "system",
            "content": sys
        }));
    }

    for m in messages {
        msgs.push(serde_json::json!({
            "role": match m.role {
                ChatRole::User => "user",
                ChatRole::Assistant => "assistant",
                ChatRole::System => "system",
            },
            "content": m.content
        }));
    }

    serde_json::json!({
        "messages": msgs,
    })
}

/// Format for Ollama/local LLM
pub fn format_for_ollama(messages: &[ChatMessage], system: Option<&str>) -> serde_json::Value {
    // Ollama uses a simpler format
    let prompt = messages
        .iter()
        .map(|m| {
            let role = match m.role {
                ChatRole::User => "User",
                ChatRole::Assistant => "Assistant",
                ChatRole::System => "System",
            };
            format!("{}: {}", role, m.content)
        })
        .collect::<Vec<_>>()
        .join("\n\n");

    let mut request = serde_json::json!({
        "prompt": prompt,
        "stream": false,
    });

    if let Some(sys) = system {
        request["system"] = serde_json::Value::String(sys.to_string());
    }

    request
}
