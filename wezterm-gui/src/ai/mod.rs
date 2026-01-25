//! AI Panel for CX Terminal
//!
//! Provides AI-powered assistance including:
//! - Command explanation
//! - Error diagnosis
//! - Command suggestions
//! - Natural language to command conversion

mod panel;
mod provider;
mod chat;
mod claude;
mod ollama;
mod widget;

pub use panel::{AIPanel, AIPanelState, TerminalContext, EnvironmentInfo};
pub use provider::{AIProvider, AIProviderConfig, AIError};
pub use chat::{ChatMessage, ChatRole, ChatHistory};
pub use claude::ClaudeProvider;
pub use ollama::{OllamaProvider, create_local_provider};
pub use widget::{AIPanelWidget, RenderedLine, AIPanelUIItem};

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

    pub fn default_model(&self) -> &'static str {
        match self {
            Self::None => "",
            Self::Claude => "claude-3-5-sonnet-20241022",
            Self::OpenAI => "gpt-4-turbo-preview",
            Self::Local => "llama3",
            Self::CXLinux => "cx-assistant",
            Self::Custom => "",
        }
    }

    pub fn default_endpoint(&self) -> Option<&'static str> {
        match self {
            Self::Claude => Some("https://api.anthropic.com/v1/messages"),
            Self::OpenAI => Some("https://api.openai.com/v1/chat/completions"),
            Self::Local => Some("http://localhost:11434/api/generate"),
            Self::CXLinux => Some("unix:///var/run/cx/ai.sock"),
            _ => None,
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
            // CX Linux provider would communicate with local daemon
            log::warn!("CX Linux provider not yet implemented");
            None
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
