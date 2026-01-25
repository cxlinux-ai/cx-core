//! Ollama Provider for CX Terminal
//!
//! Implements the AIProvider trait for local Ollama LLM server.
//! Provides privacy-first, offline-capable AI assistance.

use super::{
    provider::{AIError, AIProvider, AIProviderConfig, AIResponse, AIResponseStream},
    ChatMessage, ChatRole,
};
use std::future::Future;
use std::pin::Pin;

// CX Terminal: Ollama (local LLM) implementation

/// Default Ollama endpoint
pub const DEFAULT_OLLAMA_ENDPOINT: &str = "http://localhost:11434";

/// Ollama API Provider (local LLM)
pub struct OllamaProvider {
    config: AIProviderConfig,
    client: reqwest::Client,
}

impl OllamaProvider {
    /// Create a new Ollama provider
    pub fn new(config: AIProviderConfig) -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(300)) // Longer timeout for local inference
            .build()
            .expect("Failed to create HTTP client");

        Self { config, client }
    }

    /// Build the request body for Ollama's /api/chat endpoint
    fn build_chat_request_body(
        &self,
        messages: &[ChatMessage],
        system_prompt: Option<&str>,
        stream: bool,
    ) -> serde_json::Value {
        let api_messages: Vec<serde_json::Value> = messages
            .iter()
            .map(|m| {
                serde_json::json!({
                    "role": match m.role {
                        ChatRole::User => "user",
                        ChatRole::Assistant => "assistant",
                        ChatRole::System => "system",
                    },
                    "content": m.content
                })
            })
            .collect();

        let mut body = serde_json::json!({
            "model": self.config.model,
            "messages": api_messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        });

        // Add system prompt as first message if provided
        if let Some(sys) = system_prompt {
            if let Some(messages) = body["messages"].as_array_mut() {
                messages.insert(
                    0,
                    serde_json::json!({
                        "role": "system",
                        "content": sys
                    }),
                );
            }
        }

        body
    }

    /// Build the request body for Ollama's /api/generate endpoint (simpler)
    fn build_generate_request_body(
        &self,
        messages: &[ChatMessage],
        system_prompt: Option<&str>,
        stream: bool,
    ) -> serde_json::Value {
        // Combine messages into a single prompt
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

        let mut body = serde_json::json!({
            "model": self.config.model,
            "prompt": format!("{}\n\nAssistant:", prompt),
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        });

        if let Some(sys) = system_prompt {
            body["system"] = serde_json::Value::String(sys.to_string());
        }

        body
    }

    /// Get the chat endpoint URL
    fn chat_endpoint(&self) -> String {
        let base = self.config.endpoint.trim_end_matches('/');
        format!("{}/api/chat", base)
    }

    /// Get the generate endpoint URL
    fn generate_endpoint(&self) -> String {
        let base = self.config.endpoint.trim_end_matches('/');
        format!("{}/api/generate", base)
    }

    /// Get the tags endpoint URL (for listing models)
    fn tags_endpoint(&self) -> String {
        let base = self.config.endpoint.trim_end_matches('/');
        format!("{}/api/tags", base)
    }

    /// Parse a non-streaming response from /api/chat
    fn parse_chat_response(&self, json: serde_json::Value) -> Result<AIResponse, AIError> {
        // Ollama chat response format:
        // {
        //   "message": { "role": "assistant", "content": "..." },
        //   "done": true,
        //   "eval_count": N
        // }

        let content = json["message"]["content"]
            .as_str()
            .ok_or_else(|| AIError::InvalidResponse("Missing message content".to_string()))?;

        let tokens_used = json["eval_count"].as_u64().map(|n| n as u32);

        let finish_reason = if json["done"].as_bool() == Some(true) {
            Some("stop".to_string())
        } else {
            None
        };

        Ok(AIResponse {
            content: content.to_string(),
            finish_reason,
            tokens_used,
        })
    }

    /// Parse a non-streaming response from /api/generate
    fn parse_generate_response(&self, json: serde_json::Value) -> Result<AIResponse, AIError> {
        // Ollama generate response format:
        // {
        //   "response": "...",
        //   "done": true,
        //   "eval_count": N
        // }

        let content = json["response"]
            .as_str()
            .ok_or_else(|| AIError::InvalidResponse("Missing response field".to_string()))?;

        let tokens_used = json["eval_count"].as_u64().map(|n| n as u32);

        let finish_reason = if json["done"].as_bool() == Some(true) {
            Some("stop".to_string())
        } else {
            None
        };

        Ok(AIResponse {
            content: content.to_string(),
            finish_reason,
            tokens_used,
        })
    }

    /// Check if Ollama server is running
    pub async fn check_health(&self) -> Result<bool, AIError> {
        let response = self
            .client
            .get(&self.tags_endpoint())
            .send()
            .await
            .map_err(|e| AIError::NetworkError(e.to_string()))?;

        Ok(response.status().is_success())
    }

    /// List available models
    pub async fn list_models(&self) -> Result<Vec<OllamaModel>, AIError> {
        let response = self
            .client
            .get(&self.tags_endpoint())
            .send()
            .await
            .map_err(|e| AIError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            return Err(AIError::NetworkError(format!(
                "Failed to list models: {}",
                response.status()
            )));
        }

        let json: serde_json::Value = response
            .json()
            .await
            .map_err(|e| AIError::InvalidResponse(e.to_string()))?;

        let models = json["models"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|m| {
                        Some(OllamaModel {
                            name: m["name"].as_str()?.to_string(),
                            size: m["size"].as_u64().unwrap_or(0),
                            modified_at: m["modified_at"].as_str().unwrap_or("").to_string(),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        Ok(models)
    }
}

/// Ollama model info
#[derive(Debug, Clone)]
pub struct OllamaModel {
    pub name: String,
    pub size: u64,
    pub modified_at: String,
}

impl AIProvider for OllamaProvider {
    fn chat_completion(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponse, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            // Try /api/chat first (better for multi-turn)
            let body = self.build_chat_request_body(&messages, system.as_deref(), false);

            let response = self
                .client
                .post(&self.chat_endpoint())
                .header("content-type", "application/json")
                .json(&body)
                .send()
                .await
                .map_err(|e| {
                    if e.is_connect() {
                        AIError::NetworkError(
                            "Cannot connect to Ollama. Is it running?".to_string(),
                        )
                    } else {
                        AIError::NetworkError(e.to_string())
                    }
                })?;

            let status = response.status().as_u16();

            // If /api/chat returns 404, try /api/generate
            if status == 404 {
                return self.fallback_to_generate(messages, system).await;
            }

            let json: serde_json::Value = response
                .json()
                .await
                .map_err(|e| AIError::InvalidResponse(e.to_string()))?;

            if status >= 400 {
                let error_msg = json["error"]
                    .as_str()
                    .unwrap_or("Unknown error")
                    .to_string();

                return match status {
                    404 => Err(AIError::ModelNotFound),
                    _ => Err(AIError::ApiError(error_msg)),
                };
            }

            self.parse_chat_response(json)
        })
    }

    fn chat_completion_stream(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponseStream, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            let body = self.build_chat_request_body(&messages, system.as_deref(), true);

            let response = self
                .client
                .post(&self.chat_endpoint())
                .header("content-type", "application/json")
                .json(&body)
                .send()
                .await
                .map_err(|e| {
                    if e.is_connect() {
                        AIError::NetworkError(
                            "Cannot connect to Ollama. Is it running?".to_string(),
                        )
                    } else {
                        AIError::NetworkError(e.to_string())
                    }
                })?;

            let status = response.status().as_u16();

            if status >= 400 {
                let json: serde_json::Value = response
                    .json()
                    .await
                    .map_err(|e| AIError::InvalidResponse(e.to_string()))?;

                let error_msg = json["error"]
                    .as_str()
                    .unwrap_or("Unknown error")
                    .to_string();

                return Err(AIError::ApiError(error_msg));
            }

            // Ollama streams newline-delimited JSON
            let text = response
                .text()
                .await
                .map_err(|e| AIError::NetworkError(e.to_string()))?;

            let chunks = parse_ollama_stream(&text);
            Ok(AIResponseStream::new(chunks))
        })
    }

    fn is_available(&self) -> bool {
        !self.config.endpoint.is_empty() && !self.config.model.is_empty()
    }

    fn name(&self) -> &str {
        "Ollama"
    }
}

impl OllamaProvider {
    /// Fallback to /api/generate for older Ollama versions
    async fn fallback_to_generate(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Result<AIResponse, AIError> {
        let body = self.build_generate_request_body(&messages, system_prompt.as_deref(), false);

        let response = self
            .client
            .post(&self.generate_endpoint())
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
            let error_msg = json["error"]
                .as_str()
                .unwrap_or("Unknown error")
                .to_string();

            return match status {
                404 => Err(AIError::ModelNotFound),
                _ => Err(AIError::ApiError(error_msg)),
            };
        }

        self.parse_generate_response(json)
    }
}

/// Parse Ollama's streaming response (newline-delimited JSON)
fn parse_ollama_stream(data: &str) -> Vec<String> {
    let mut chunks = Vec::new();

    for line in data.lines() {
        if line.is_empty() {
            continue;
        }

        if let Ok(json) = serde_json::from_str::<serde_json::Value>(line) {
            // /api/chat format
            if let Some(content) = json["message"]["content"].as_str() {
                if !content.is_empty() {
                    chunks.push(content.to_string());
                }
            }
            // /api/generate format
            else if let Some(response) = json["response"].as_str() {
                if !response.is_empty() {
                    chunks.push(response.to_string());
                }
            }

            // Check if done
            if json["done"].as_bool() == Some(true) {
                break;
            }
        }
    }

    chunks
}

/// Create a provider configured for local Ollama with sensible defaults
pub fn create_local_provider(model: Option<&str>) -> OllamaProvider {
    let config = AIProviderConfig {
        provider_type: super::AIProviderType::Local,
        endpoint: DEFAULT_OLLAMA_ENDPOINT.to_string(),
        api_key: None, // Not needed for local
        model: model.unwrap_or("llama3").to_string(),
        max_tokens: 4096,
        temperature: 0.7,
    };

    OllamaProvider::new(config)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai::AIProviderType;

    fn test_config() -> AIProviderConfig {
        AIProviderConfig {
            provider_type: AIProviderType::Local,
            endpoint: DEFAULT_OLLAMA_ENDPOINT.to_string(),
            api_key: None,
            model: "llama3".to_string(),
            max_tokens: 2048,
            temperature: 0.7,
        }
    }

    #[test]
    fn test_build_chat_request() {
        let provider = OllamaProvider::new(test_config());
        let messages = vec![ChatMessage::user("Hello")];

        let body = provider.build_chat_request_body(&messages, Some("Be helpful"), false);

        assert_eq!(body["model"], "llama3");
        assert_eq!(body["stream"], false);
        assert!(body["messages"].is_array());

        // System message should be first
        let msgs = body["messages"].as_array().unwrap();
        assert_eq!(msgs[0]["role"], "system");
        assert_eq!(msgs[0]["content"], "Be helpful");
    }

    #[test]
    fn test_build_generate_request() {
        let provider = OllamaProvider::new(test_config());
        let messages = vec![ChatMessage::user("Hello")];

        let body = provider.build_generate_request_body(&messages, Some("Be helpful"), false);

        assert_eq!(body["model"], "llama3");
        assert_eq!(body["system"], "Be helpful");
        assert!(body["prompt"].as_str().unwrap().contains("User: Hello"));
    }

    #[test]
    fn test_parse_chat_response() {
        let provider = OllamaProvider::new(test_config());

        let json = serde_json::json!({
            "message": {
                "role": "assistant",
                "content": "Hello there!"
            },
            "done": true,
            "eval_count": 15
        });

        let response = provider.parse_chat_response(json).unwrap();
        assert_eq!(response.content, "Hello there!");
        assert_eq!(response.finish_reason, Some("stop".to_string()));
        assert_eq!(response.tokens_used, Some(15));
    }

    #[test]
    fn test_parse_generate_response() {
        let provider = OllamaProvider::new(test_config());

        let json = serde_json::json!({
            "response": "Hello there!",
            "done": true,
            "eval_count": 15
        });

        let response = provider.parse_generate_response(json).unwrap();
        assert_eq!(response.content, "Hello there!");
    }

    #[test]
    fn test_parse_ollama_stream() {
        let data = r#"{"message":{"role":"assistant","content":"Hello"},"done":false}
{"message":{"role":"assistant","content":" world"},"done":false}
{"message":{"role":"assistant","content":"!"},"done":true}"#;

        let chunks = parse_ollama_stream(data);
        assert_eq!(chunks, vec!["Hello", " world", "!"]);
    }

    #[test]
    fn test_endpoints() {
        let provider = OllamaProvider::new(test_config());

        assert_eq!(
            provider.chat_endpoint(),
            "http://localhost:11434/api/chat"
        );
        assert_eq!(
            provider.generate_endpoint(),
            "http://localhost:11434/api/generate"
        );
        assert_eq!(provider.tags_endpoint(), "http://localhost:11434/api/tags");
    }

    #[test]
    fn test_is_available() {
        let mut config = test_config();
        let provider = OllamaProvider::new(config.clone());
        assert!(provider.is_available());

        config.model = "".to_string();
        let provider = OllamaProvider::new(config);
        assert!(!provider.is_available());
    }
}
