/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! AI Panel for CX Terminal
//!
//! Provides AI-powered assistance including:
//! - Command explanation
//! - Error diagnosis
//! - Command suggestions
//! - Natural language to command conversion

mod chat;
mod claude;
mod llamacpp;
mod ollama;
mod panel;
mod provider;
mod widget;

pub use chat::{ChatHistory, ChatMessage, ChatRole};
pub use claude::ClaudeProvider;
pub use llamacpp::{LlamaCppProvider, CX_SYSTEM_PROMPT};
pub use ollama::{create_local_provider, OllamaProvider};
pub use panel::{AIPanel, AIPanelState, EnvironmentInfo, TerminalContext};
pub use provider::{AIError, AIProvider, AIProviderConfig};
pub use widget::{AIPanelUIItem, AIPanelWidget, RenderedLine};

/// AI Panel configuration
#[derive(Debug, Clone)]
pub struct AIConfig {
    /// Whether AI features are enabled
    pub enabled: bool,

    /// Selected AI provider
    pub provider: AIProviderType,

    /// API endpoint (for custom/local providers)
    pub api_endpoint: Option<String>,

    /// API key (for cloud providers)
    pub api_key: Option<String>,

    /// Model name
    pub model: String,

    /// Maximum tokens for responses
    pub max_tokens: u32,

    /// Temperature for generation
    pub temperature: f32,

    /// Whether to stream responses
    pub stream: bool,

    /// System prompt customization
    pub system_prompt: Option<String>,
}

impl Default for AIConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            provider: AIProviderType::None,
            api_endpoint: None,
            api_key: None,
            model: "".to_string(),
            max_tokens: 2048,
            temperature: 0.7,
            stream: true,
            system_prompt: None,
        }
    }
}

impl AIConfig {
    /// Create configuration with auto-detected best available provider
    pub fn auto_detect() -> Self {
        let provider = detect_best_provider();
        let mut config = Self::default();

        config.enabled = provider != AIProviderType::None;
        config.provider = provider;

        if let Some(endpoint) = provider.default_endpoint() {
            config.api_endpoint = Some(endpoint.to_string());
        }

        config.model = provider.default_model().to_string();

        // Set API key from environment if available
        match provider {
            AIProviderType::Claude => {
                config.api_key = std::env::var("ANTHROPIC_API_KEY").ok();
            }
            AIProviderType::OpenAI => {
                config.api_key = std::env::var("OPENAI_API_KEY").ok();
            }
            AIProviderType::CXLinux => {
                // No API key needed - native inference
            }
            _ => {}
        }

        // Set appropriate system prompt
        config.system_prompt = Some(match provider {
            AIProviderType::CXLinux => {
                // Use the unified system prompt from the fine-tuned model
                CX_SYSTEM_PROMPT.to_string()
            }
            _ => {
                "You are a helpful Linux terminal assistant. \
                 Provide concise, practical help with command-line tasks and system administration."
                    .to_string()
            }
        });

        config
    }

    /// Check if the configuration is ready to use
    pub fn is_ready(&self) -> bool {
        if !self.enabled || self.provider == AIProviderType::None {
            return false;
        }

        match self.provider {
            AIProviderType::None => false,
            AIProviderType::Claude | AIProviderType::OpenAI => {
                self.api_key.is_some() && !self.api_key.as_ref().unwrap().is_empty()
            }
            AIProviderType::CXLinux => {
                // Native inference - just check if model is available
                LlamaCppProvider::is_model_available()
            }
            AIProviderType::Local => self.api_endpoint.is_some(),
            AIProviderType::Custom => {
                self.api_endpoint.is_some() && !self.api_endpoint.as_ref().unwrap().is_empty()
            }
        }
    }

    /// Get current status for UI display
    pub fn get_status(&self) -> AIProviderStatus {
        AIProviderStatus {
            provider: self.provider,
            is_available: self.provider.is_available(),
            is_ready: self.is_ready(),
            model: if self.model.is_empty() {
                None
            } else {
                Some(self.model.clone())
            },
            error: if self.is_ready() {
                None
            } else {
                Some(match self.provider {
                    AIProviderType::None => "No AI provider configured".to_string(),
                    AIProviderType::Claude => "ANTHROPIC_API_KEY not set".to_string(),
                    AIProviderType::OpenAI => "OPENAI_API_KEY not set".to_string(),
                    AIProviderType::CXLinux => {
                        "CX Linux model not found. Run 'cx ai download' to install.".to_string()
                    }
                    AIProviderType::Local => "Ollama not running on localhost:11434".to_string(),
                    AIProviderType::Custom => "Custom endpoint not configured".to_string(),
                })
            },
        }
    }
}

/// AI provider status for UI display
#[derive(Debug, Clone)]
pub struct AIProviderStatus {
    pub provider: AIProviderType,
    pub is_available: bool,
    pub is_ready: bool,
    pub model: Option<String>,
    pub error: Option<String>,
}

impl AIProviderStatus {
    /// Get display text for status bar
    pub fn display_text(&self) -> String {
        if self.is_ready {
            format!("{} {}", self.provider.icon(), self.provider.display_name())
        } else {
            format!("{} No AI", AIProviderType::None.icon())
        }
    }

    /// Get color for status bar
    pub fn status_color(&self) -> &'static str {
        if self.is_ready {
            self.provider.status_color()
        } else {
            AIProviderType::None.status_color()
        }
    }
}

/// Detect the best available AI provider
pub fn detect_best_provider() -> AIProviderType {
    // Priority order: Claude > OpenAI > Local (Ollama) > CX Linux (native fallback) > None
    let providers = [
        AIProviderType::Claude,
        AIProviderType::OpenAI,
        AIProviderType::Local,
        AIProviderType::CXLinux,
    ];

    for &provider in &providers {
        if provider.is_available() {
            return provider;
        }
    }

    AIProviderType::None
}

/// Check all providers and their status
pub fn get_all_provider_status() -> Vec<AIProviderStatus> {
    let providers = [
        AIProviderType::Claude,
        AIProviderType::OpenAI,
        AIProviderType::Local,
        AIProviderType::CXLinux,
    ];

    providers
        .iter()
        .map(|&provider| {
            let config = AIConfig {
                enabled: true,
                provider,
                model: provider.default_model().to_string(),
                api_endpoint: provider.default_endpoint().map(|s| s.to_string()),
                ..Default::default()
            };
            config.get_status()
        })
        .collect()
}

/// Supported AI providers
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AIProviderType {
    /// No AI provider
    None,
    /// Anthropic Claude
    Claude,
    /// OpenAI GPT
    OpenAI,
    /// Local LLM (Ollama, llama.cpp, etc.)
    Local,
    /// CX Linux integrated AI
    CXLinux,
    /// Custom endpoint
    Custom,
}

impl AIProviderType {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "claude" | "anthropic" => Self::Claude,
            "openai" | "gpt" => Self::OpenAI,
            "local" | "ollama" | "llama" => Self::Local,
            "cxlinux" | "cx" => Self::CXLinux,
            "custom" => Self::Custom,
            _ => Self::None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Claude => "claude",
            Self::OpenAI => "openai",
            Self::Local => "local",
            Self::CXLinux => "cxlinux",
            Self::Custom => "custom",
        }
    }

    /// Get display name for UI
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::None => "No AI",
            Self::Claude => "Claude",
            Self::OpenAI => "OpenAI",
            Self::Local => "Ollama",
            Self::CXLinux => "CX AI",
            Self::Custom => "Custom",
        }
    }

    /// Get icon/emoji for status bar
    pub fn icon(&self) -> &'static str {
        match self {
            Self::None => "💤",
            Self::Claude => "🤖",
            Self::OpenAI => "🧠",
            Self::Local => "🏠",
            Self::CXLinux => "⚡",
            Self::Custom => "🔧",
        }
    }

    /// Get status color for UI
    pub fn status_color(&self) -> &'static str {
        match self {
            Self::None => "#6272A4",    // Muted gray
            Self::Claude => "#00D9FF",  // CX cyan
            Self::OpenAI => "#00D9FF",  // CX cyan
            Self::Local => "#FFB86C",   // Orange
            Self::CXLinux => "#00FFFF", // Bright cyan
            Self::Custom => "#F1FA8C",  // Yellow
        }
    }

    pub fn default_model(&self) -> &'static str {
        match self {
            Self::None => "",
            Self::Claude => "claude-3-5-sonnet-20241022",
            Self::OpenAI => "gpt-4-turbo-preview",
            Self::Local => "llama3",
            Self::CXLinux => "cortex-linux-7b-Q4_K_M",
            Self::Custom => "",
        }
    }

    pub fn default_endpoint(&self) -> Option<&'static str> {
        match self {
            Self::Claude => Some("https://api.anthropic.com/v1/messages"),
            Self::OpenAI => Some("https://api.openai.com/v1/chat/completions"),
            Self::Local => Some("http://localhost:11434/api/generate"),
            Self::CXLinux => None, // Native inference, no endpoint needed
            _ => None,
        }
    }

    /// Check if this provider is available in current environment
    pub fn is_available(&self) -> bool {
        match self {
            Self::None => false,
            Self::Claude => std::env::var("ANTHROPIC_API_KEY").is_ok(),
            Self::OpenAI => std::env::var("OPENAI_API_KEY").is_ok(),
            Self::Local => {
                // Check if Ollama is running
                std::process::Command::new("curl")
                    .args(["-s", "-m", "2", "http://localhost:11434/api/tags"])
                    .output()
                    .map(|output| output.status.success())
                    .unwrap_or(false)
            }
            Self::CXLinux => {
                // Check if model file exists in cache
                LlamaCppProvider::is_model_available()
            }
            Self::Custom => true, // Assume custom endpoint is configurable
        }
    }
}

/// Predefined AI actions
#[derive(Debug, Clone)]
pub enum AIAction {
    /// Explain a command or error
    Explain(String),
    /// Suggest commands for a task
    Suggest(String),
    /// Fix an error
    Fix(String),
    /// Convert natural language to command
    Generate(String),
    /// Custom query
    Query(String),
}

impl AIAction {
    /// Get the system prompt for this action
    pub fn system_prompt(&self) -> &'static str {
        match self {
            AIAction::Explain(_) => {
                "You are a Linux command expert. Explain commands, their options, and output clearly and concisely. Focus on practical understanding."
            }
            AIAction::Suggest(_) => {
                "You are a Linux command assistant. Suggest the most appropriate commands for the user's task. Provide brief explanations for each suggestion."
            }
            AIAction::Fix(_) => {
                "You are a Linux troubleshooting expert. Analyze errors and provide specific solutions. Include the exact commands to fix the issue."
            }
            AIAction::Generate(_) => {
                "You are a Linux command generator. Convert natural language descriptions into shell commands. Output only the command, no explanations."
            }
            AIAction::Query(_) => {
                "You are a helpful Linux terminal assistant. Answer questions accurately and concisely."
            }
        }
    }

    /// Get the user prompt
    pub fn user_prompt(&self) -> String {
        match self {
            AIAction::Explain(text) => format!("Explain this: {}", text),
            AIAction::Suggest(task) => format!("Suggest commands for: {}", task),
            AIAction::Fix(error) => format!("Fix this error: {}", error),
            AIAction::Generate(desc) => format!("Command for: {}", desc),
            AIAction::Query(query) => query.clone(),
        }
    }
}

/// Create an AI provider based on configuration
///
/// Returns a boxed provider trait object that can be used for AI requests.
/// Falls back to local provider if configured provider is unavailable.
pub fn create_provider(config: &AIConfig) -> Option<Box<dyn AIProvider>> {
    let provider_config = AIProviderConfig::from(config);

    match config.provider {
        AIProviderType::None => None,
        AIProviderType::Claude => {
            if provider_config.api_key.is_some() {
                Some(Box::new(ClaudeProvider::new(provider_config)))
            } else {
                log::warn!("Claude provider configured but no API key provided");
                None
            }
        }
        AIProviderType::OpenAI => {
            // OpenAI provider not yet implemented, fall back to Claude format
            log::warn!("OpenAI provider not yet implemented");
            None
        }
        AIProviderType::Local => Some(Box::new(OllamaProvider::new(provider_config))),
        AIProviderType::CXLinux => {
            // Native llama.cpp inference with the fine-tuned CX Linux model
            match LlamaCppProvider::new(provider_config) {
                Ok(provider) => Some(Box::new(provider)),
                Err(e) => {
                    log::warn!("Failed to create CX Linux provider: {}", e);
                    None
                }
            }
        }
        AIProviderType::Custom => {
            // Custom uses Ollama-compatible API
            Some(Box::new(OllamaProvider::new(provider_config)))
        }
    }
}

/// Manager for AI operations
///
/// Handles provider selection, request routing, and fallback logic.
pub struct AIManager {
    /// Primary provider
    primary: Option<Box<dyn AIProvider>>,
    /// Fallback provider (usually local)
    fallback: Option<Box<dyn AIProvider>>,
    /// Configuration
    config: AIConfig,
}

impl AIManager {
    /// Create a new AI manager
    pub fn new(config: AIConfig) -> Self {
        let primary = create_provider(&config);

        // Set up local fallback if primary is cloud-based
        let fallback = if matches!(
            config.provider,
            AIProviderType::Claude | AIProviderType::OpenAI
        ) {
            Some(Box::new(create_local_provider(None)) as Box<dyn AIProvider>)
        } else {
            None
        };

        Self {
            primary,
            fallback,
            config,
        }
    }

    /// Get the active provider
    pub fn provider(&self) -> Option<&dyn AIProvider> {
        self.primary.as_deref()
    }

    /// Get the fallback provider
    pub fn fallback_provider(&self) -> Option<&dyn AIProvider> {
        self.fallback.as_deref()
    }

    /// Check if any provider is available
    pub fn is_available(&self) -> bool {
        self.primary
            .as_ref()
            .map(|p| p.is_available())
            .unwrap_or(false)
            || self
                .fallback
                .as_ref()
                .map(|p| p.is_available())
                .unwrap_or(false)
    }

    /// Get provider name
    pub fn provider_name(&self) -> &str {
        self.primary
            .as_ref()
            .map(|p| p.name())
            .or_else(|| self.fallback.as_ref().map(|p| p.name()))
            .unwrap_or("None")
    }

    /// Update configuration
    pub fn update_config(&mut self, config: AIConfig) {
        self.config = config.clone();
        self.primary = create_provider(&config);

        if matches!(
            config.provider,
            AIProviderType::Claude | AIProviderType::OpenAI
        ) {
            self.fallback = Some(Box::new(create_local_provider(None)) as Box<dyn AIProvider>);
        } else {
            self.fallback = None;
        }
    }
}
