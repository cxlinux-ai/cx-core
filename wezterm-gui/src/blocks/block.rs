//! Command Block data structure

use chrono::{DateTime, Utc};
use std::time::Duration;

/// Unique identifier for a command block
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct BlockId(pub u64);

impl BlockId {
    pub fn new() -> Self {
        use std::sync::atomic::{AtomicU64, Ordering};
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        Self(COUNTER.fetch_add(1, Ordering::Relaxed))
    }
}

/// State of a command block
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockState {
    /// Command is currently executing
    Running,
    /// Command completed successfully (exit code 0)
    Success,
    /// Command failed (non-zero exit code)
    Failed,
    /// Command was interrupted/killed
    Interrupted,
}

/// A command block containing a command and its output
#[derive(Debug, Clone)]
pub struct Block {
    /// Unique identifier
    pub id: BlockId,

    /// The command that was executed
    pub command: String,

    /// Working directory when command was run
    pub working_dir: String,

    /// Start line in the terminal buffer
    pub start_line: usize,

    /// End line in the terminal buffer (exclusive)
    pub end_line: usize,

    /// Current state
    pub state: BlockState,

    /// Exit code if completed
    pub exit_code: Option<i32>,

    /// When the command started
    pub started_at: DateTime<Utc>,

    /// When the command finished
    pub finished_at: Option<DateTime<Utc>>,

    /// Execution duration
    pub duration: Option<Duration>,

    /// Whether the block is collapsed in the UI
    pub collapsed: bool,

    /// Whether the block is pinned (won't scroll away)
    pub pinned: bool,

    /// User-added notes/annotations
    pub notes: Option<String>,

    /// Tags for organization
    pub tags: Vec<String>,
}

impl Block {
    /// Create a new block for a command
    pub fn new(command: String, working_dir: String, start_line: usize) -> Self {
        Self {
            id: BlockId::new(),
            command,
            working_dir,
            start_line,
            end_line: start_line,
            state: BlockState::Running,
            exit_code: None,
            started_at: Utc::now(),
            finished_at: None,
            duration: None,
            collapsed: false,
            pinned: false,
            notes: None,
            tags: Vec::new(),
        }
    }

    /// Mark the block as completed
    pub fn complete(&mut self, exit_code: i32, end_line: usize) {
        self.exit_code = Some(exit_code);
        self.end_line = end_line;
        self.finished_at = Some(Utc::now());
        self.duration = Some(
            self.finished_at
                .unwrap()
                .signed_duration_since(self.started_at)
                .to_std()
                .unwrap_or_default(),
        );
        self.state = if exit_code == 0 {
            BlockState::Success
        } else {
            BlockState::Failed
        };
    }

    /// Mark the block as interrupted
    pub fn interrupt(&mut self, end_line: usize) {
        self.end_line = end_line;
        self.finished_at = Some(Utc::now());
        self.state = BlockState::Interrupted;
    }

    /// Toggle collapsed state
    pub fn toggle_collapsed(&mut self) {
        self.collapsed = !self.collapsed;
    }

    /// Toggle pinned state
    pub fn toggle_pinned(&mut self) {
        self.pinned = !self.pinned;
    }

    /// Check if this block contains the given line
    pub fn contains_line(&self, line: usize) -> bool {
        line >= self.start_line && line < self.end_line
    }

    /// Get the number of lines in this block
    pub fn line_count(&self) -> usize {
        self.end_line.saturating_sub(self.start_line)
    }

    /// Check if this is a long-running command
    pub fn is_long_running(&self) -> bool {
        self.duration.map(|d| d.as_secs() > 5).unwrap_or(false)
    }

    /// Format the duration for display
    pub fn duration_display(&self) -> String {
        match self.duration {
            Some(d) => {
                let secs = d.as_secs();
                if secs < 60 {
                    format!("{}s", secs)
                } else if secs < 3600 {
                    format!("{}m {}s", secs / 60, secs % 60)
                } else {
                    format!("{}h {}m", secs / 3600, (secs % 3600) / 60)
                }
            }
            None => "...".to_string(),
        }
    }
}

/// Actions that can be performed on a block
#[derive(Debug, Clone)]
pub enum BlockAction {
    /// Toggle collapse state
    ToggleCollapse,
    /// Copy command to clipboard
    CopyCommand,
    /// Copy output to clipboard
    CopyOutput,
    /// Copy both command and output
    CopyAll,
    /// Re-run the command
    Rerun,
    /// Edit and run
    EditAndRun,
    /// Send to AI for explanation
    Explain,
    /// Pin/unpin the block
    TogglePin,
    /// Add a note
    AddNote(String),
    /// Add a tag
    AddTag(String),
    /// Delete the block (from history, not terminal)
    Delete,
    /// Share/export the block
    Share,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_block_creation() {
        let block = Block::new("ls -la".to_string(), "/home/user".to_string(), 10);
        assert_eq!(block.command, "ls -la");
        assert_eq!(block.state, BlockState::Running);
        assert!(block.exit_code.is_none());
    }

    #[test]
    fn test_block_completion() {
        let mut block = Block::new("ls".to_string(), "/".to_string(), 0);
        block.complete(0, 10);
        assert_eq!(block.state, BlockState::Success);
        assert_eq!(block.exit_code, Some(0));
        assert_eq!(block.line_count(), 10);
    }

    #[test]
    fn test_block_failure() {
        let mut block = Block::new("false".to_string(), "/".to_string(), 0);
        block.complete(1, 1);
        assert_eq!(block.state, BlockState::Failed);
        assert_eq!(block.exit_code, Some(1));
    }
}
