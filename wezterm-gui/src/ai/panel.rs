//! AI Panel UI state and logic

use super::{AIAction, AIConfig, ChatHistory, ChatMessage, ChatRole};

/// State of the AI panel
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AIPanelState {
    /// Panel is hidden
    Hidden,
    /// Panel is visible - chat mode
    Chat,
    /// Panel is visible - suggestions mode
    Suggestions,
    /// Panel is visible - explain mode
    Explain,
    /// Panel is minimized (shows status only)
    Minimized,
}

/// The AI Panel component
pub struct AIPanel {
    /// Current state
    pub state: AIPanelState,

    /// Chat history
    pub history: ChatHistory,

    /// Current input text
    pub input: String,

    /// Whether a request is in progress
    pub loading: bool,

    /// Current streaming response (if any)
    pub streaming_response: Option<String>,

    /// Error message (if any)
    pub error: Option<String>,

    /// Panel width (percentage of terminal width)
    pub width_percent: u8,

    /// Configuration
    pub config: AIConfig,

    /// Quick suggestions
    pub suggestions: Vec<String>,

    /// Context from terminal (recent commands, errors)
    pub context: TerminalContext,
}

impl AIPanel {
    pub fn new(config: AIConfig) -> Self {
        Self {
            state: AIPanelState::Hidden,
            history: ChatHistory::new(),
            input: String::new(),
            loading: false,
            streaming_response: None,
            error: None,
            width_percent: 30,
            config,
            suggestions: Vec::new(),
            context: TerminalContext::default(),
        }
    }

    /// Toggle panel visibility
    pub fn toggle(&mut self) {
        self.state = match self.state {
            AIPanelState::Hidden => AIPanelState::Chat,
            _ => AIPanelState::Hidden,
        };
    }

    /// Show panel in specific mode
    pub fn show(&mut self, mode: AIPanelState) {
        self.state = mode;
    }

    /// Hide panel
    pub fn hide(&mut self) {
        self.state = AIPanelState::Hidden;
    }

    /// Minimize panel
    pub fn minimize(&mut self) {
        if self.state != AIPanelState::Hidden {
            self.state = AIPanelState::Minimized;
        }
    }

    /// Check if panel is visible
    pub fn is_visible(&self) -> bool {
        self.state != AIPanelState::Hidden
    }

    /// Check if panel is expanded (not minimized)
    pub fn is_expanded(&self) -> bool {
        matches!(
            self.state,
            AIPanelState::Chat | AIPanelState::Suggestions | AIPanelState::Explain
        )
    }

    /// Submit current input
    pub fn submit(&mut self) -> Option<AIAction> {
        if self.input.is_empty() || self.loading {
            return None;
        }

        let text = std::mem::take(&mut self.input);

        // Add user message to history
        self.history.add(ChatMessage {
            role: ChatRole::User,
            content: text.clone(),
            timestamp: chrono::Utc::now(),
        });

        // Determine action based on mode
        let action = match self.state {
            AIPanelState::Explain => AIAction::Explain(text),
            AIPanelState::Suggestions => AIAction::Suggest(text),
            _ => AIAction::Query(text),
        };

        self.loading = true;
        self.error = None;

        Some(action)
    }

    /// Handle streaming response chunk
    pub fn append_response(&mut self, chunk: &str) {
        match &mut self.streaming_response {
            Some(response) => response.push_str(chunk),
            None => self.streaming_response = Some(chunk.to_string()),
        }
    }

    /// Finalize response
    pub fn complete_response(&mut self) {
        self.loading = false;

        if let Some(response) = self.streaming_response.take() {
            self.history.add(ChatMessage {
                role: ChatRole::Assistant,
                content: response,
                timestamp: chrono::Utc::now(),
            });
        }
    }

    /// Handle error
    pub fn set_error(&mut self, error: String) {
        self.loading = false;
        self.streaming_response = None;
        self.error = Some(error);
    }

    /// Clear error
    pub fn clear_error(&mut self) {
        self.error = None;
    }

    /// Clear chat history
    pub fn clear_history(&mut self) {
        self.history.clear();
        self.suggestions.clear();
    }

    /// Explain something (from block action)
    pub fn explain(&mut self, text: String) -> AIAction {
        self.state = AIPanelState::Explain;
        self.input = text.clone();
        self.submit().unwrap_or(AIAction::Explain(text))
    }

    /// Update context from terminal
    pub fn update_context(&mut self, context: TerminalContext) {
        self.context = context;
    }

    /// Get width in pixels (given total width)
    pub fn width(&self, total_width: u32) -> u32 {
        if self.is_expanded() {
            (total_width * self.width_percent as u32) / 100
        } else if self.state == AIPanelState::Minimized {
            48 // Icon width
        } else {
            0
        }
    }

    /// Adjust width
    pub fn set_width_percent(&mut self, percent: u8) {
        self.width_percent = percent.clamp(20, 60);
    }
}

/// Context from the terminal for AI assistance
#[derive(Debug, Clone, Default)]
pub struct TerminalContext {
    /// Recent commands
    pub recent_commands: Vec<String>,

    /// Current working directory
    pub cwd: String,

    /// Last error output
    pub last_error: Option<String>,

    /// Environment hints (OS, shell, etc.)
    pub environment: EnvironmentInfo,
}

/// Environment information
#[derive(Debug, Clone, Default)]
pub struct EnvironmentInfo {
    pub os: String,
    pub shell: String,
    pub user: String,
    pub hostname: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_panel_toggle() {
        let mut panel = AIPanel::new(AIConfig::default());
        assert_eq!(panel.state, AIPanelState::Hidden);

        panel.toggle();
        assert_eq!(panel.state, AIPanelState::Chat);

        panel.toggle();
        assert_eq!(panel.state, AIPanelState::Hidden);
    }

    #[test]
    fn test_panel_submit() {
        let mut panel = AIPanel::new(AIConfig::default());
        panel.state = AIPanelState::Chat;
        panel.input = "test query".to_string();

        let action = panel.submit();
        assert!(action.is_some());
        assert!(panel.loading);
        assert!(panel.input.is_empty());
    }
}
