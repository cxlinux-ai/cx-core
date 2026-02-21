//! Block management methods for TermWindow
//!
//! This module adds command block handling to the terminal window,
//! including OSC sequence processing and block UI interactions.

use crate::blocks::{
    BlockAction, BlockActionResult, BlockId, BlockManager, BlockRenderer, BlockUIElement,
    CXSequence,
};
use mux::pane::PaneId;
use mux::Mux;

impl crate::TermWindow {
    /// Get the current cursor line for a pane
    pub fn get_pane_cursor_line(&self, pane_id: PaneId) -> Option<usize> {
        let mux = Mux::try_get()?;
        let pane = mux.get_pane(pane_id)?;
        let cursor = pane.get_cursor_position();
        Some(cursor.y as usize)
    }

    /// Get or create a BlockManager for a pane
    pub fn get_block_manager(&self, pane_id: PaneId) -> std::cell::RefMut<'_, BlockManager> {
        let mut managers = self.block_managers.borrow_mut();
        if !managers.contains_key(&pane_id) {
            managers.insert(pane_id, BlockManager::new());
        }
        std::cell::RefMut::map(self.block_managers.borrow_mut(), |m| {
            m.get_mut(&pane_id).unwrap()
        })
    }

    /// Get the BlockRenderer
    pub fn block_renderer(&self) -> std::cell::RefMut<'_, BlockRenderer> {
        self.block_renderer.borrow_mut()
    }

    /// Get the current working directory for a pane
    pub fn get_pane_cwd(&self, pane_id: PaneId) -> Option<String> {
        self.pane_cwd.borrow().get(&pane_id).cloned()
    }

    /// Set the current working directory for a pane
    pub fn set_pane_cwd(&self, pane_id: PaneId, cwd: String) {
        self.pane_cwd.borrow_mut().insert(pane_id, cwd);
    }

    /// Handle a CX Terminal OSC sequence
    ///
    /// This is called when we receive an OSC sequence starting with "777;cx;"
    /// The sequence has already been parsed into a CXSequence enum.
    pub fn handle_cx_sequence(
        &mut self,
        pane_id: PaneId,
        sequence: CXSequence,
        current_line: usize,
    ) {
        log::trace!("CX sequence for pane {}: {:?}", pane_id, sequence);

        match sequence {
            CXSequence::BlockStart {
                command,
                timestamp: _,
            } => {
                let cwd = self.get_pane_cwd(pane_id).unwrap_or_default();
                let mut managers = self.block_managers.borrow_mut();
                let manager = managers.entry(pane_id).or_insert_with(BlockManager::new);
                let block_id = manager.start_block(command, cwd, current_line);
                log::debug!(
                    "Started block {:?} at line {} for pane {}",
                    block_id,
                    current_line,
                    pane_id
                );
            }

            CXSequence::BlockEnd {
                exit_code,
                timestamp: _,
            } => {
                let mut managers = self.block_managers.borrow_mut();
                if let Some(manager) = managers.get_mut(&pane_id) {
                    manager.end_block(exit_code, current_line);
                    log::debug!(
                        "Ended block at line {} with exit code {} for pane {}",
                        current_line,
                        exit_code,
                        pane_id
                    );
                }
            }

            CXSequence::CwdChanged { path } => {
                self.set_pane_cwd(pane_id, path.clone());
                log::debug!("CWD changed to {} for pane {}", path, pane_id);
            }

            CXSequence::PromptStart | CXSequence::PromptEnd => {
                // These can be used for additional block boundary hints
                // Currently handled by shell integration
            }

            CXSequence::AIExplain { text } => {
                // Route to AI panel for explanation
                log::debug!("AI Explain request: {}", text);
                self.show_ai_panel(crate::ai::AIPanelState::Explain);
                let action = self.ai_panel.borrow_mut().explain(text);
                self.execute_ai_action(action);
            }

            CXSequence::AISuggest { query } => {
                // Route to AI panel for suggestions
                log::debug!("AI Suggest request: {}", query);
                self.show_ai_panel(crate::ai::AIPanelState::Suggestions);
                let action = crate::ai::AIAction::Suggest(query);
                self.execute_ai_action(action);
            }

            CXSequence::AgentRequest { name, command } => {
                // Agent system for automated tasks (reserved for future use)
                log::info!("Agent request received: {} - {}", name, command);
            }

            CXSequence::Features { blocks, ai, agents } => {
                log::info!(
                    "Shell integration features: blocks={}, ai={}, agents={}",
                    blocks,
                    ai,
                    agents
                );
            }

            CXSequence::Unknown(s) => {
                log::warn!("Unknown CX sequence: {}", s);
            }
        }
    }

    /// Handle a click on a block UI element
    pub fn handle_block_click(
        &mut self,
        pane_id: PaneId,
        element: &BlockUIElement,
    ) -> Option<BlockActionResult> {
        let action = match element {
            BlockUIElement::CollapseToggle(id) => Some((id, BlockAction::ToggleCollapse)),
            BlockUIElement::CopyCommand(id) => Some((id, BlockAction::CopyCommand)),
            BlockUIElement::RerunButton(id) => Some((id, BlockAction::Rerun)),
            BlockUIElement::ExplainButton(id) => Some((id, BlockAction::Explain)),
            BlockUIElement::Header(_)
            | BlockUIElement::StatusIndicator(_)
            | BlockUIElement::Content(_)
            | BlockUIElement::Border(_) => None,
        };

        if let Some((block_id, action)) = action {
            let mut managers = self.block_managers.borrow_mut();
            if let Some(manager) = managers.get_mut(&pane_id) {
                return manager.execute_action(*block_id, action);
            }
        }

        None
    }

    /// Select a block
    pub fn select_block(&mut self, pane_id: PaneId, block_id: BlockId) {
        let mut managers = self.block_managers.borrow_mut();
        if let Some(manager) = managers.get_mut(&pane_id) {
            manager.select(block_id);
        }
    }

    /// Clear block selection
    pub fn clear_block_selection(&mut self, pane_id: PaneId) {
        let mut managers = self.block_managers.borrow_mut();
        if let Some(manager) = managers.get_mut(&pane_id) {
            manager.clear_selection();
        }
    }

    /// Toggle block collapse state
    pub fn toggle_block_collapse(&mut self, pane_id: PaneId, block_id: BlockId) {
        let mut managers = self.block_managers.borrow_mut();
        if let Some(manager) = managers.get_mut(&pane_id) {
            manager.execute_action(block_id, BlockAction::ToggleCollapse);
        }
    }

    /// Get block at a screen line
    pub fn block_at_line(&self, pane_id: PaneId, line: usize) -> Option<BlockId> {
        let managers = self.block_managers.borrow();
        managers
            .get(&pane_id)
            .and_then(|m| m.block_at_line(line).map(|b| b.id))
    }

    /// Interrupt the active block (e.g., on Ctrl+C)
    pub fn interrupt_active_block(&mut self, pane_id: PaneId, current_line: usize) {
        let mut managers = self.block_managers.borrow_mut();
        if let Some(manager) = managers.get_mut(&pane_id) {
            manager.interrupt_block(current_line);
        }
    }

    /// Get block statistics for a pane
    pub fn block_stats(&self, pane_id: PaneId) -> Option<crate::blocks::BlockStats> {
        let managers = self.block_managers.borrow();
        managers.get(&pane_id).map(|m| m.stats())
    }

    /// Search blocks by command text
    pub fn search_blocks(&self, pane_id: PaneId, query: &str) -> Vec<BlockId> {
        let managers = self.block_managers.borrow();
        managers
            .get(&pane_id)
            .map(|m| m.search(query))
            .unwrap_or_default()
    }
}
