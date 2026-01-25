//! AI Panel methods for TermWindow
//!
//! This module adds AI panel handling to the terminal window,
//! including panel toggle, input routing, and AI request handling.

use crate::ai::{
    AIAction, AIConfig, AIManager, AIPanel, AIPanelState, AIPanelWidget, ChatMessage,
};
use mux::pane::PaneId;
use mux::Mux;
use ::window::WindowOps;

// CX Terminal: AI Panel implementation for TermWindow

impl crate::TermWindow {
    /// Toggle the AI panel visibility
    pub fn toggle_ai_panel(&mut self) {
        self.ai_panel.borrow_mut().toggle();
        if let Some(w) = self.window.as_ref() { w.invalidate(); }
        log::debug!("AI panel toggled, visible: {}", self.ai_panel.borrow().is_visible());
    }

    /// Show the AI panel in a specific mode
    pub fn show_ai_panel(&mut self, mode: AIPanelState) {
        self.ai_panel.borrow_mut().show(mode);
        if let Some(w) = self.window.as_ref() { w.invalidate(); }
    }

    /// Hide the AI panel
    pub fn hide_ai_panel(&mut self) {
        self.ai_panel.borrow_mut().hide();
        if let Some(w) = self.window.as_ref() { w.invalidate(); }
    }

    /// Check if AI panel is visible
    pub fn is_ai_panel_visible(&self) -> bool {
        self.ai_panel.borrow().is_visible()
    }

    /// Get AI panel width in pixels
    pub fn ai_panel_width(&self) -> u32 {
        let panel = self.ai_panel.borrow();
        panel.width(self.dimensions.pixel_width as u32)
    }

    /// Get the terminal width minus AI panel
    pub fn terminal_width_with_ai_panel(&self) -> usize {
        let panel_width = self.ai_panel_width();
        self.dimensions.pixel_width.saturating_sub(panel_width as usize)
    }

    /// Handle AI panel input (when panel has focus)
    pub fn handle_ai_panel_key(&mut self, key: &str, modifiers: window::Modifiers) -> bool {
        if !self.is_ai_panel_visible() {
            return false;
        }

        let mut panel = self.ai_panel.borrow_mut();

        match (modifiers, key) {
            // Escape closes the panel
            (window::Modifiers::NONE, "Escape") => {
                drop(panel);
                self.hide_ai_panel();
                return true;
            }

            // Enter submits the input
            (window::Modifiers::NONE, "Return") => {
                if let Some(action) = panel.submit() {
                    drop(panel);
                    self.execute_ai_action(action);
                }
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }

            // Backspace deletes character
            (window::Modifiers::NONE, "Backspace") => {
                if !panel.input.is_empty() {
                    panel.input.pop();
                    if let Some(w) = self.window.as_ref() { w.invalidate(); }
                }
                return true;
            }

            // Ctrl+C clears input or hides panel
            (window::Modifiers::CTRL, "c") => {
                if panel.input.is_empty() {
                    drop(panel);
                    self.hide_ai_panel();
                } else {
                    panel.input.clear();
                    if let Some(w) = self.window.as_ref() { w.invalidate(); }
                }
                return true;
            }

            // Ctrl+L clears chat history
            (window::Modifiers::CTRL, "l") => {
                panel.clear_history();
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }

            // Arrow keys for scrolling
            (window::Modifiers::NONE, "Up") => {
                drop(panel);
                self.ai_widget.borrow_mut().scroll_up(1);
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }
            (window::Modifiers::NONE, "Down") => {
                drop(panel);
                self.ai_widget.borrow_mut().scroll_down(1);
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }
            (window::Modifiers::NONE, "PageUp") => {
                drop(panel);
                self.ai_widget.borrow_mut().scroll_up(10);
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }
            (window::Modifiers::NONE, "PageDown") => {
                drop(panel);
                self.ai_widget.borrow_mut().scroll_down(10);
                if let Some(w) = self.window.as_ref() { w.invalidate(); }
                return true;
            }

            _ => {}
        }

        false
    }

    /// Handle character input for AI panel
    pub fn handle_ai_panel_char(&mut self, c: char) -> bool {
        if !self.is_ai_panel_visible() {
            return false;
        }

        // Filter control characters
        if c.is_control() {
            return false;
        }

        self.ai_panel.borrow_mut().input.push(c);
        if let Some(w) = self.window.as_ref() { w.invalidate(); }
        true
    }

    /// Execute an AI action
    pub fn execute_ai_action(&mut self, action: AIAction) {
        log::debug!("Executing AI action: {:?}", action);

        let manager = self.ai_manager.borrow();
        let provider = match manager.provider() {
            Some(p) => p,
            None => {
                self.ai_panel.borrow_mut().set_error(
                    "No AI provider configured. Set config.ai in your wezterm config.".to_string(),
                );
                return;
            }
        };

        // Build messages from history
        let panel = self.ai_panel.borrow();
        let messages: Vec<ChatMessage> = panel
            .history
            .messages()
            .iter()
            .cloned()
            .collect();
        let system_prompt = Some(action.system_prompt().to_string());
        drop(panel);

        // For now, we'll need to spawn this async
        // This is a placeholder - actual async integration needs work
        log::info!(
            "Would send to {}: {} messages with system prompt",
            provider.name(),
            messages.len()
        );

        // TODO: Spawn async task to call provider.chat_completion()
        // For now, show a placeholder response
        self.ai_panel.borrow_mut().append_response(
            "AI response would appear here. Async integration pending.\n\n\
             Configure AI in your wezterm.lua:\n\
             config.ai = {\n\
               enabled = true,\n\
               provider = 'claude',\n\
               api_key = os.getenv('ANTHROPIC_API_KEY'),\n\
             }",
        );
        self.ai_panel.borrow_mut().complete_response();
        if let Some(w) = self.window.as_ref() { w.invalidate(); }
    }

    /// Explain selected text using AI
    pub fn ai_explain_selection(&mut self, pane_id: PaneId) {
        let mux = match Mux::try_get() {
            Some(m) => m,
            None => return,
        };

        let pane = match mux.get_pane(pane_id) {
            Some(p) => p,
            None => return,
        };

        // Get selection from pane
        let selection_text = self.selection_text(&pane);

        if selection_text.is_empty() {
            log::debug!("No text selected for AI explain");
            return;
        }

        // Show AI panel and set up explain action
        self.show_ai_panel(AIPanelState::Explain);

        let action = self.ai_panel.borrow_mut().explain(selection_text);
        self.execute_ai_action(action);
    }

    /// Open AI panel for command generation
    pub fn ai_generate_command(&mut self) {
        self.show_ai_panel(AIPanelState::Suggestions);
        // Focus will be on input, user types what they want
    }

    /// Update AI panel with terminal context
    pub fn update_ai_context(&mut self, pane_id: PaneId) {
        let mux = match Mux::try_get() {
            Some(m) => m,
            None => return,
        };

        let pane = match mux.get_pane(pane_id) {
            Some(p) => p,
            None => return,
        };

        // Build context from terminal state
        let cwd = self.get_pane_cwd(pane_id).unwrap_or_default();

        // Get recent commands from block manager
        let recent_commands: Vec<String> = {
            let managers = self.block_managers.borrow();
            managers
                .get(&pane_id)
                .map(|m| {
                    m.recent_blocks(5)
                        .iter()
                        .map(|b| b.command.clone())
                        .collect()
                })
                .unwrap_or_default()
        };

        // Get last error if any
        let last_error = {
            let managers = self.block_managers.borrow();
            managers.get(&pane_id).and_then(|m| {
                m.recent_blocks(1)
                    .first()
                    .filter(|b| b.exit_code.map(|c| c != 0).unwrap_or(false))
                    .map(|b| format!("Command '{}' failed with exit code {:?}", b.command, b.exit_code))
            })
        };

        let context = crate::ai::TerminalContext {
            recent_commands,
            cwd,
            last_error,
            environment: crate::ai::EnvironmentInfo::default(),
        };

        self.ai_panel.borrow_mut().update_context(context);
    }

    /// Update AI configuration from Lua config
    pub fn update_ai_config(&mut self, config: &config::ConfigHandle) {
        // TODO: Read AI config from Lua config
        // For now, use defaults or environment
        let api_key = std::env::var("ANTHROPIC_API_KEY").ok();

        if api_key.is_some() {
            let ai_config = AIConfig {
                enabled: true,
                provider: crate::ai::AIProviderType::Claude,
                api_key,
                model: "claude-3-5-sonnet-20241022".to_string(),
                ..AIConfig::default()
            };

            *self.ai_panel.borrow_mut() = AIPanel::new(ai_config.clone());
            self.ai_manager.borrow_mut().update_config(ai_config);

            log::info!("AI panel configured with Claude provider");
        } else if let Ok(_) = std::env::var("OLLAMA_HOST") {
            // Check for Ollama
            let ai_config = AIConfig {
                enabled: true,
                provider: crate::ai::AIProviderType::Local,
                model: "llama3".to_string(),
                ..AIConfig::default()
            };

            *self.ai_panel.borrow_mut() = AIPanel::new(ai_config.clone());
            self.ai_manager.borrow_mut().update_config(ai_config);

            log::info!("AI panel configured with Ollama provider");
        }
    }

    /// Render the AI panel (returns lines to draw)
    pub fn render_ai_panel(&self) -> Vec<crate::ai::RenderedLine> {
        let panel = self.ai_panel.borrow();
        if !panel.is_visible() {
            return Vec::new();
        }

        let width = panel.width(self.dimensions.pixel_width as u32) as usize;
        let height = self.dimensions.pixel_height / self.render_metrics.cell_size.height as usize;

        drop(panel);

        let panel = self.ai_panel.borrow();
        let mut widget = self.ai_widget.borrow_mut();
        widget.render(&panel, width, height)
    }

    /// Handle mouse click in AI panel area
    pub fn handle_ai_panel_click(&mut self, x: usize, y: usize) -> bool {
        if !self.is_ai_panel_visible() {
            return false;
        }

        let panel_width = self.ai_panel_width() as usize;
        let panel_x = self.dimensions.pixel_width.saturating_sub(panel_width);

        // Check if click is in panel area
        if x < panel_x {
            return false;
        }

        let panel = self.ai_panel.borrow();
        let widget = self.ai_widget.borrow();

        if let Some(hit) = widget.hit_test(
            &panel,
            panel_x,
            0,
            panel_width,
            self.dimensions.pixel_height,
            x,
            y,
        ) {
            drop(widget);
            drop(panel);

            match hit.item {
                crate::ai::AIPanelUIItem::CloseButton => {
                    self.hide_ai_panel();
                }
                crate::ai::AIPanelUIItem::SendButton => {
                    let action = self.ai_panel.borrow_mut().submit();
                    if let Some(action) = action {
                        self.execute_ai_action(action);
                    }
                }
                crate::ai::AIPanelUIItem::InputField => {
                    // Focus input - already focused by default
                }
                _ => {}
            }

            if let Some(w) = self.window.as_ref() { w.invalidate(); }
            return true;
        }

        false
    }

    /// Access the AI panel state
    pub fn ai_panel(&self) -> std::cell::Ref<'_, AIPanel> {
        self.ai_panel.borrow()
    }

    /// Access the AI panel state mutably
    pub fn ai_panel_mut(&self) -> std::cell::RefMut<'_, AIPanel> {
        self.ai_panel.borrow_mut()
    }

    /// Access the AI widget
    pub fn ai_widget(&self) -> std::cell::Ref<'_, AIPanelWidget> {
        self.ai_widget.borrow()
    }

    /// Access the AI widget mutably
    pub fn ai_widget_mut(&self) -> std::cell::RefMut<'_, AIPanelWidget> {
        self.ai_widget.borrow_mut()
    }

    /// Access the AI manager
    pub fn ai_manager(&self) -> std::cell::Ref<'_, AIManager> {
        self.ai_manager.borrow()
    }
}
