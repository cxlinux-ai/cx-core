//! Claude API Provider for CX Terminal
//!
//! Implements the AIProvider trait for Anthropic's Claude API.
//! Supports both streaming and non-streaming completions.

use super::{
    provider::{AIError, AIProvider, AIProviderConfig, AIResponse, AIResponseStream},
    ChatMessage, ChatRole,
};
use std::future::Future;
use std::pin::Pin;

// CX Terminal: Claude API implementation

/// Claude API Provider
pub struct ClaudeProvider {
    config: AIProviderConfig,
    client: reqwest::Client,
}

impl ClaudeProvider {
    /// Create a new Claude provider
    pub fn new(config: AIProviderConfig) -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .expect("Failed to create HTTP client");

        Self { config, client }
    }

    /// Build the request body for Claude API
    fn build_request_body(
        &self,
        messages: &[ChatMessage],
        system_prompt: Option<&str>,
        stream: bool,
    ) -> serde_json::Value {
        let api_messages: Vec<serde_json::Value> = messages
            .iter()
            .filter(|m| m.role != ChatRole::System)
            .map(|m| {
                serde_json::json!({
                    "role": match m.role {
                        ChatRole::User => "user",
                        ChatRole::Assistant => "assistant",
                        ChatRole::System => "user", // Filtered above
                    },
                    "content": m.content
                })
            })
            .collect();

        let mut body = serde_json::json!({
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": api_messages,
            "stream": stream,
        });

        if let Some(sys) = system_prompt {
            body["system"] = serde_json::Value::String(sys.to_string());
        }

        body
    }

    /// Parse a non-streaming response
    fn parse_response(&self, json: serde_json::Value) -> Result<AIResponse, AIError> {
        // Claude API response format:
        // {
        //   "content": [{ "type": "text", "text": "..." }],
        //   "stop_reason": "end_turn",
        //   "usage": { "input_tokens": N, "output_tokens": M }
        // }

        let content = json["content"]
            .as_array()
            .and_then(|arr| arr.first())
            .and_then(|c| c["text"].as_str())
            .ok_or_else(|| AIError::InvalidResponse("Missing content in response".to_string()))?;

        let finish_reason = json["stop_reason"].as_str().map(String::from);
        let tokens_used = json["usage"]["output_tokens"].as_u64().map(|n| n as u32);

        Ok(AIResponse {
            content: content.to_string(),
            finish_reason,
            tokens_used,
        })
    }

    /// Parse error response
    fn parse_error(&self, status: u16, json: serde_json::Value) -> AIError {
        let error_msg = json["error"]["message"]
            .as_str()
            .or_else(|| json["error"]["type"].as_str())
            .unwrap_or("Unknown error")
            .to_string();

        match status {
            401 => AIError::AuthError,
            429 => AIError::RateLimited,
            400 if error_msg.contains("context") || error_msg.contains("tokens") => {
                AIError::ContextTooLong
            }
            404 => AIError::ModelNotFound,
            _ => AIError::ApiError(error_msg),
        }
    }
}

impl AIProvider for ClaudeProvider {
    fn chat_completion(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponse, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            let api_key = self
                .config
                .api_key
                .as_ref()
                .ok_or(AIError::NotConfigured)?;

            let body = self.build_request_body(&messages, system.as_deref(), false);

            let response = self
                .client
                .post(&self.config.endpoint)
                .header("x-api-key", api_key)
                .header("anthropic-version", "2023-06-01")
                .header("content-type", "application/json")
                .json(&body)
                .send()
                .await
                .map_err(|e| AIError::NetworkError(e.to_string()))?;

            let status = response.status().as_u16();

            let json: serde_json::Value = response
                .json()
                .await
                .map_err(|e| AIError::InvalidResponse(e.to_string()))?;

            if status >= 400 {
                return Err(self.parse_error(status, json));
            }

            self.parse_response(json)
        })
    }

    fn chat_completion_stream(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponseStream, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            let api_key = self
                .config
                .api_key
                .as_ref()
                .ok_or(AIError::NotConfigured)?;

            let body = self.build_request_body(&messages, system.as_deref(), true);

            let response = self
                .client
                .post(&self.config.endpoint)
                .header("x-api-key", api_key)
                .header("anthropic-version", "2023-06-01")
                .header("content-type", "application/json")
                .json(&body)
                .send()
                .await
                .map_err(|e| AIError::NetworkError(e.to_string()))?;

            let status = response.status().as_u16();

            if status >= 400 {
                let json: serde_json::Value = response
                    .json()
                    .await
                    .map_err(|e| AIError::InvalidResponse(e.to_string()))?;
                return Err(self.parse_error(status, json));
            }

            // Parse SSE stream
            // Claude sends: data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
            let text = response
                .text()
                .await
                .map_err(|e| AIError::NetworkError(e.to_string()))?;

            let chunks = parse_sse_stream(&text);
            Ok(AIResponseStream::new(chunks))
        })
    }

    fn is_available(&self) -> bool {
        self.config.api_key.is_some() && !self.config.endpoint.is_empty()
    }

    fn name(&self) -> &str {
        "Claude"
    }
}

/// Parse Server-Sent Events stream from Claude
fn parse_sse_stream(data: &str) -> Vec<String> {
    let mut chunks = Vec::new();

    for line in data.lines() {
        if let Some(json_str) = line.strip_prefix("data: ") {
            if json_str == "[DONE]" {
                break;
            }

            if let Ok(json) = serde_json::from_str::<serde_json::Value>(json_str) {
                // Handle content_block_delta events
                if json["type"].as_str() == Some("content_block_delta") {
                    if let Some(text) = json["delta"]["text"].as_str() {
                        chunks.push(text.to_string());
                    }
                }
            }
        }
    }

    chunks
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai::AIProviderType;

    #[test]
    fn test_build_request_body() {
        let config = AIProviderConfig {
            provider_type: AIProviderType::Claude,
            endpoint: "https://api.anthropic.com/v1/messages".to_string(),
            api_key: Some("test-key".to_string()),
            model: "claude-3-5-sonnet-20241022".to_string(),
            max_tokens: 1024,
            temperature: 0.7,
        };

        let provider = ClaudeProvider::new(config);

        let messages = vec![ChatMessage::user("Hello")];

        let body = provider.build_request_body(&messages, Some("Be helpful"), false);

        assert_eq!(body["model"], "claude-3-5-sonnet-20241022");
        assert_eq!(body["max_tokens"], 1024);
        assert_eq!(body["system"], "Be helpful");
        assert_eq!(body["stream"], false);
        assert!(body["messages"].is_array());
    }

    #[test]
    fn test_parse_response() {
        let config = AIProviderConfig {
            provider_type: AIProviderType::Claude,
            endpoint: "test".to_string(),
            api_key: Some("test".to_string()),
            model: "test".to_string(),
            max_tokens: 1024,
            temperature: 0.7,
        };

        let provider = ClaudeProvider::new(config);

        let json = serde_json::json!({
            "content": [{ "type": "text", "text": "Hello there!" }],
            "stop_reason": "end_turn",
            "usage": { "input_tokens": 10, "output_tokens": 5 }
        });

        let response = provider.parse_response(json).unwrap();
        assert_eq!(response.content, "Hello there!");
        assert_eq!(response.finish_reason, Some("end_turn".to_string()));
        assert_eq!(response.tokens_used, Some(5));
    }

    #[test]
    fn test_is_available() {
        let mut config = AIProviderConfig {
            provider_type: AIProviderType::Claude,
            endpoint: "https://api.anthropic.com/v1/messages".to_string(),
            api_key: None,
            model: "test".to_string(),
            max_tokens: 1024,
            temperature: 0.7,
        };

        let provider = ClaudeProvider::new(config.clone());
        assert!(!provider.is_available());

        config.api_key = Some("test-key".to_string());
        let provider = ClaudeProvider::new(config);
        assert!(provider.is_available());
    }

    #[test]
    fn test_parse_sse_stream() {
        let data = r#"event: message_start
data: {"type":"message_start"}

event: content_block_delta
data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}

event: content_block_delta
data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}

event: message_stop
data: {"type":"message_stop"}
"#;

        let chunks = parse_sse_stream(data);
        assert_eq!(chunks, vec!["Hello", " world"]);
    }
}
