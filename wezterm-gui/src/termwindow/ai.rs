//! AI Panel methods for TermWindow
//!
//! This module adds AI panel handling to the terminal window,
//! including panel toggle, input routing, and AI request handling.

use crate::ai::{
    AIAction, AIConfig, AIError, AIManager, AIPanel, AIPanelState, AIPanelWidget,
    AIProvider, ChatMessage, create_provider,
};
use crate::termwindow::TermWindowNotif;
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

        // Check if this is an agent command (starts with @ or contains agent keywords)
        let user_input = action.user_prompt();
        if self.try_agent_command(&user_input) {
            return;
        }

        // Get window for async callback
        let window = match self.window.as_ref() {
            Some(w) => w.clone(),
            None => {
                log::error!("No window available for AI action");
                return;
            }
        };

        // Check if provider is configured
        let manager = self.ai_manager.borrow();
        if manager.provider().is_none() {
            drop(manager);
            self.ai_panel.borrow_mut().set_error(
                "No AI provider configured. Set config.ai in your wezterm config.".to_string(),
            );
            if let Some(w) = self.window.as_ref() { w.invalidate(); }
            return;
        }

        // Get config to recreate provider in async context
        let panel = self.ai_panel.borrow();
        let ai_config = panel.config.clone();
        let use_streaming = ai_config.stream;
        let messages: Vec<ChatMessage> = panel
            .history
            .messages()
            .iter()
            .cloned()
            .collect();
        drop(panel);
        drop(manager);

        let system_prompt = Some(action.system_prompt().to_string());
        let provider_name = ai_config.provider;

        log::info!(
            "Sending to {:?}: {} messages with system prompt (streaming: {})",
            provider_name,
            messages.len(),
            use_streaming
        );

        // Spawn async task to call provider
        promise::spawn::spawn(async move {
            // Create provider in async context
            let provider: Option<Box<dyn AIProvider>> = create_provider(&ai_config);

            let result = match provider {
                Some(p) => {
                    if use_streaming {
                        // Use streaming mode - get all chunks then send
                        match p.chat_completion_stream(messages, system_prompt).await {
                            Ok(mut stream) => {
                                // Collect chunks and send updates
                                let mut full_response = String::new();
                                let win = window.clone();

                                // Process all chunks
                                while let Some(chunk) = stream.next_chunk() {
                                    full_response.push_str(&chunk);

                                    // Send incremental update for each chunk
                                    let chunk_clone = chunk.clone();
                                    win.notify(TermWindowNotif::Apply(Box::new(move |term_window| {
                                        term_window.ai_panel.borrow_mut().append_response(&chunk_clone);
                                        if let Some(w) = term_window.window.as_ref() { w.invalidate(); }
                                    })));
                                }

                                // Signal completion
                                window.notify(TermWindowNotif::Apply(Box::new(move |term_window| {
                                    term_window.ai_panel.borrow_mut().complete_response();
                                    if let Some(w) = term_window.window.as_ref() { w.invalidate(); }
                                })));

                                return; // Already handled
                            }
                            Err(e) => Err(e),
                        }
                    } else {
                        // Use non-streaming mode
                        p.chat_completion(messages, system_prompt).await
                    }
                }
                None => {
                    Err(AIError::NotConfigured)
                }
            };

            // Send result back to main thread via window notification
            match result {
                Ok(response) => {
                    let content = response.content.clone();
                    window.notify(TermWindowNotif::Apply(Box::new(move |term_window| {
                        term_window.ai_panel.borrow_mut().append_response(&content);
                        term_window.ai_panel.borrow_mut().complete_response();
                        if let Some(w) = term_window.window.as_ref() { w.invalidate(); }
                    })));
                }
                Err(e) => {
                    let error_msg = e.to_string();
                    window.notify(TermWindowNotif::Apply(Box::new(move |term_window| {
                        term_window.ai_panel.borrow_mut().set_error(error_msg);
                        if let Some(w) = term_window.window.as_ref() { w.invalidate(); }
                    })));
                }
            }
        })
        .detach();

        // Immediately invalidate to show loading state
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

        let _pane = match mux.get_pane(pane_id) {
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
    pub fn update_ai_config(&mut self, _config: &config::ConfigHandle) {
        // TODO: Read AI config from Lua config
        // For now, use defaults or environment

        // Check for Claude API key first (cloud provider)
        let claude_api_key = std::env::var("ANTHROPIC_API_KEY").ok();

        // Check for OpenAI API key
        let openai_api_key = std::env::var("OPENAI_API_KEY").ok();

        // Check for Ollama host (local provider) - default to localhost if not set
        let ollama_host = std::env::var("OLLAMA_HOST")
            .unwrap_or_else(|_| "http://localhost:11434".to_string());

        // Prefer Claude if API key is set
        if let Some(api_key) = claude_api_key {
            let ai_config = AIConfig {
                enabled: true,
                provider: crate::ai::AIProviderType::Claude,
                api_key: Some(api_key),
                model: "claude-3-5-sonnet-20241022".to_string(),
                stream: true,
                ..AIConfig::default()
            };

            *self.ai_panel.borrow_mut() = AIPanel::new(ai_config.clone());
            self.ai_manager.borrow_mut().update_config(ai_config);

            log::info!("AI panel configured with Claude provider");
        } else if let Some(api_key) = openai_api_key {
            // OpenAI provider (not fully implemented yet, but config it)
            let ai_config = AIConfig {
                enabled: true,
                provider: crate::ai::AIProviderType::OpenAI,
                api_key: Some(api_key),
                model: "gpt-4-turbo-preview".to_string(),
                stream: true,
                ..AIConfig::default()
            };

            *self.ai_panel.borrow_mut() = AIPanel::new(ai_config.clone());
            self.ai_manager.borrow_mut().update_config(ai_config);

            log::info!("AI panel configured with OpenAI provider");
        } else {
            // Fall back to Ollama (local provider) - always available
            let ai_config = AIConfig {
                enabled: true,
                provider: crate::ai::AIProviderType::Local,
                api_endpoint: Some(ollama_host),
                model: std::env::var("OLLAMA_MODEL").unwrap_or_else(|_| "llama3".to_string()),
                stream: true,
                ..AIConfig::default()
            };

            *self.ai_panel.borrow_mut() = AIPanel::new(ai_config.clone());
            self.ai_manager.borrow_mut().update_config(ai_config);

            log::info!("AI panel configured with Ollama provider (local)");
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

    /// Access the agent runtime
    pub fn agent_runtime(&self) -> std::cell::Ref<'_, crate::agents::AgentRuntime> {
        self.agent_runtime.borrow()
    }

    /// Try to execute a command using the agent system
    /// Returns true if the command was handled by an agent
    fn try_agent_command(&mut self, input: &str) -> bool {
        let runtime = self.agent_runtime.borrow();

        // Try to parse the command
        if let Some(request) = runtime.parse_command(input) {
            log::info!("Agent handling command: {} -> agent '{}'", input, request.agent);

            // Execute the agent command
            let response = runtime.handle(request);
            drop(runtime);

            // Format the response for the AI panel
            let formatted = self.format_agent_response(&response);

            // Add the response to the AI panel
            let mut panel = self.ai_panel.borrow_mut();
            panel.append_response(&formatted);
            panel.complete_response();
            drop(panel);

            if let Some(w) = self.window.as_ref() {
                w.invalidate();
            }

            return true;
        }

        false
    }

    /// Format an agent response for display in the AI panel
    fn format_agent_response(&self, response: &crate::agents::AgentResponse) -> String {
        let mut output = String::new();

        if response.success {
            output.push_str(&response.result);
        } else {
            if let Some(ref error) = response.error {
                output.push_str(&format!("Error: {}\n", error));
            }
        }

        // Add commands that were executed
        if !response.commands_executed.is_empty() {
            output.push_str("\n\n---\nCommands executed:\n");
            for cmd in &response.commands_executed {
                output.push_str(&format!("  $ {}\n", cmd));
            }
        }

        // Add suggestions if any
        if !response.suggestions.is_empty() {
            output.push_str("\nTry also:\n");
            for suggestion in &response.suggestions {
                output.push_str(&format!("  - {}\n", suggestion));
            }
        }

        output
    }

    /// List available agents
    pub fn list_agents(&self) -> Vec<(String, String)> {
        self.agent_runtime.borrow()
            .list_agents()
            .into_iter()
            .map(|(name, desc)| (name.to_string(), desc.to_string()))
            .collect()
    }
}
