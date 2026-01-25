//! Block Manager - handles block lifecycle and state

use super::block::{Block, BlockAction, BlockId, BlockState};
use std::collections::HashMap;

/// Manages all command blocks in a terminal pane
pub struct BlockManager {
    /// All blocks, indexed by ID
    blocks: HashMap<BlockId, Block>,

    /// Blocks in display order
    block_order: Vec<BlockId>,

    /// Currently active (executing) block
    active_block: Option<BlockId>,

    /// Currently selected block (for UI)
    selected_block: Option<BlockId>,

    /// Pinned blocks
    pinned_blocks: Vec<BlockId>,

    /// Maximum number of blocks to keep in memory
    max_blocks: usize,
}

impl BlockManager {
    pub fn new() -> Self {
        Self {
            blocks: HashMap::new(),
            block_order: Vec::new(),
            active_block: None,
            selected_block: None,
            pinned_blocks: Vec::new(),
            max_blocks: 1000, // Configurable
        }
    }

    /// Start a new command block
    pub fn start_block(&mut self, command: String, working_dir: String, start_line: usize) -> BlockId {
        let block = Block::new(command, working_dir, start_line);
        let id = block.id;

        self.blocks.insert(id, block);
        self.block_order.push(id);
        self.active_block = Some(id);

        // Cleanup old blocks if we exceed max
        self.cleanup_old_blocks();

        id
    }

    /// End the current active block
    pub fn end_block(&mut self, exit_code: i32, end_line: usize) {
        if let Some(id) = self.active_block.take() {
            if let Some(block) = self.blocks.get_mut(&id) {
                block.complete(exit_code, end_line);
            }
        }
    }

    /// Interrupt the current active block
    pub fn interrupt_block(&mut self, end_line: usize) {
        if let Some(id) = self.active_block.take() {
            if let Some(block) = self.blocks.get_mut(&id) {
                block.interrupt(end_line);
            }
        }
    }

    /// Get a block by ID
    pub fn get(&self, id: BlockId) -> Option<&Block> {
        self.blocks.get(&id)
    }

    /// Get a mutable block by ID
    pub fn get_mut(&mut self, id: BlockId) -> Option<&mut Block> {
        self.blocks.get_mut(&id)
    }

    /// Get the active block
    pub fn active(&self) -> Option<&Block> {
        self.active_block.and_then(|id| self.blocks.get(&id))
    }

    /// Get the selected block
    pub fn selected(&self) -> Option<&Block> {
        self.selected_block.and_then(|id| self.blocks.get(&id))
    }

    /// Select a block
    pub fn select(&mut self, id: BlockId) {
        if self.blocks.contains_key(&id) {
            self.selected_block = Some(id);
        }
    }

    /// Clear selection
    pub fn clear_selection(&mut self) {
        self.selected_block = None;
    }

    /// Find block at a given line
    pub fn block_at_line(&self, line: usize) -> Option<&Block> {
        for id in self.block_order.iter().rev() {
            if let Some(block) = self.blocks.get(id) {
                if block.contains_line(line) {
                    return Some(block);
                }
            }
        }
        None
    }

    /// Get all blocks in order
    pub fn iter(&self) -> impl Iterator<Item = &Block> + '_ {
        let blocks = &self.blocks;
        self.block_order.iter().filter_map(move |id| blocks.get(id))
    }

    /// Get visible (non-collapsed) blocks
    pub fn visible_blocks(&self) -> impl Iterator<Item = &Block> + '_ {
        self.iter().filter(|b| !b.collapsed || b.pinned)
    }

    /// Get pinned blocks
    pub fn pinned(&self) -> impl Iterator<Item = &Block> + '_ {
        let blocks = &self.blocks;
        self.pinned_blocks
            .iter()
            .filter_map(move |id| blocks.get(id))
    }

    /// Get recent blocks (most recent first)
    pub fn recent_blocks(&self, count: usize) -> Vec<&Block> {
        self.block_order
            .iter()
            .rev()
            .take(count)
            .filter_map(|id| self.blocks.get(id))
            .collect()
    }

    /// Execute an action on a block
    pub fn execute_action(&mut self, id: BlockId, action: BlockAction) -> Option<BlockActionResult> {
        let block = self.blocks.get_mut(&id)?;

        match action {
            BlockAction::ToggleCollapse => {
                block.toggle_collapsed();
                Some(BlockActionResult::StateChanged)
            }
            BlockAction::CopyCommand => {
                Some(BlockActionResult::CopyToClipboard(block.command.clone()))
            }
            BlockAction::CopyOutput => {
                // This would need to extract text from terminal buffer
                Some(BlockActionResult::NeedsTerminalData)
            }
            BlockAction::CopyAll => {
                Some(BlockActionResult::NeedsTerminalData)
            }
            BlockAction::Rerun => {
                Some(BlockActionResult::ExecuteCommand(block.command.clone()))
            }
            BlockAction::EditAndRun => {
                Some(BlockActionResult::EditCommand(block.command.clone()))
            }
            BlockAction::Explain => {
                Some(BlockActionResult::SendToAI(block.command.clone()))
            }
            BlockAction::TogglePin => {
                block.toggle_pinned();
                if block.pinned {
                    if !self.pinned_blocks.contains(&id) {
                        self.pinned_blocks.push(id);
                    }
                } else {
                    self.pinned_blocks.retain(|&x| x != id);
                }
                Some(BlockActionResult::StateChanged)
            }
            BlockAction::AddNote(note) => {
                block.notes = Some(note);
                Some(BlockActionResult::StateChanged)
            }
            BlockAction::AddTag(tag) => {
                if !block.tags.contains(&tag) {
                    block.tags.push(tag);
                }
                Some(BlockActionResult::StateChanged)
            }
            BlockAction::Delete => {
                self.blocks.remove(&id);
                self.block_order.retain(|&x| x != id);
                self.pinned_blocks.retain(|&x| x != id);
                if self.selected_block == Some(id) {
                    self.selected_block = None;
                }
                Some(BlockActionResult::Deleted)
            }
            BlockAction::Share => {
                Some(BlockActionResult::NeedsTerminalData)
            }
        }
    }

    /// Search blocks by command
    pub fn search(&self, query: &str) -> Vec<BlockId> {
        let query = query.to_lowercase();
        self.block_order
            .iter()
            .filter(|id| {
                self.blocks
                    .get(id)
                    .map(|b| b.command.to_lowercase().contains(&query))
                    .unwrap_or(false)
            })
            .copied()
            .collect()
    }

    /// Get blocks with a specific state
    pub fn by_state(&self, state: BlockState) -> Vec<BlockId> {
        self.block_order
            .iter()
            .filter(|id| {
                self.blocks
                    .get(id)
                    .map(|b| b.state == state)
                    .unwrap_or(false)
            })
            .copied()
            .collect()
    }

    /// Cleanup old blocks when we exceed the limit
    fn cleanup_old_blocks(&mut self) {
        while self.block_order.len() > self.max_blocks {
            // Don't remove pinned blocks
            if let Some(pos) = self
                .block_order
                .iter()
                .position(|id| !self.pinned_blocks.contains(id))
            {
                let id = self.block_order.remove(pos);
                self.blocks.remove(&id);
            } else {
                break;
            }
        }
    }

    /// Get total block count
    pub fn len(&self) -> usize {
        self.blocks.len()
    }

    /// Get learning data for a recently completed block
    /// Returns None if the block doesn't exist or is still running
    pub fn get_learning_data(&self, id: BlockId) -> Option<BlockLearningData> {
        let block = self.blocks.get(&id)?;

        // Only return data for completed blocks
        if block.state == BlockState::Running {
            return None;
        }

        let exit_code = match block.state {
            BlockState::Success => 0,
            BlockState::Failed => block.exit_code.unwrap_or(1),
            BlockState::Interrupted => -1,
            BlockState::Running => return None,
        };

        Some(BlockLearningData {
            command: block.command.clone(),
            cwd: block.working_dir.clone(),
            exit_code,
            duration_ms: block.duration.map(|d| d.as_millis() as u64).unwrap_or(0),
            interrupted: block.state == BlockState::Interrupted,
        })
    }

    /// Get learning data for the most recently completed block
    pub fn get_last_completed_learning_data(&self) -> Option<BlockLearningData> {
        // Find the most recent non-running block
        for id in self.block_order.iter().rev() {
            if let Some(block) = self.blocks.get(id) {
                if block.state != BlockState::Running {
                    return self.get_learning_data(*id);
                }
            }
        }
        None
    }

    /// Check if there are no blocks
    pub fn is_empty(&self) -> bool {
        self.blocks.is_empty()
    }

    /// Get statistics about blocks
    pub fn stats(&self) -> BlockStats {
        let mut stats = BlockStats::default();
        for block in self.blocks.values() {
            stats.total += 1;
            match block.state {
                BlockState::Success => stats.success += 1,
                BlockState::Failed => stats.failed += 1,
                BlockState::Running => stats.running += 1,
                BlockState::Interrupted => stats.interrupted += 1,
            }
            if block.pinned {
                stats.pinned += 1;
            }
            if block.collapsed {
                stats.collapsed += 1;
            }
        }
        stats
    }
}

impl Default for BlockManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Result of executing a block action
#[derive(Debug)]
pub enum BlockActionResult {
    /// State was changed, UI needs refresh
    StateChanged,
    /// Copy this text to clipboard
    CopyToClipboard(String),
    /// Execute this command
    ExecuteCommand(String),
    /// Open editor with this command
    EditCommand(String),
    /// Send to AI panel
    SendToAI(String),
    /// Block was deleted
    Deleted,
    /// Need to extract data from terminal buffer
    NeedsTerminalData,
}

/// Statistics about blocks
#[derive(Debug, Default)]
pub struct BlockStats {
    pub total: usize,
    pub success: usize,
    pub failed: usize,
    pub running: usize,
    pub interrupted: usize,
    pub pinned: usize,
    pub collapsed: usize,
}

/// Data for learning from a completed command block
#[derive(Debug, Clone)]
pub struct BlockLearningData {
    /// The command that was executed
    pub command: String,
    /// Working directory
    pub cwd: String,
    /// Exit code
    pub exit_code: i32,
    /// Duration in milliseconds
    pub duration_ms: u64,
    /// Whether the command was interrupted
    pub interrupted: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_block_lifecycle() {
        let mut manager = BlockManager::new();

        let id = manager.start_block("ls".to_string(), "/".to_string(), 0);
        assert!(manager.active().is_some());

        manager.end_block(0, 10);
        assert!(manager.active().is_none());
        assert_eq!(manager.get(id).unwrap().state, BlockState::Success);
    }

    #[test]
    fn test_block_search() {
        let mut manager = BlockManager::new();

        manager.start_block("ls -la".to_string(), "/".to_string(), 0);
        manager.end_block(0, 5);

        manager.start_block("cat file.txt".to_string(), "/".to_string(), 5);
        manager.end_block(0, 10);

        manager.start_block("ls /tmp".to_string(), "/".to_string(), 10);
        manager.end_block(0, 15);

        let results = manager.search("ls");
        assert_eq!(results.len(), 2);
    }
}
