//! Modern input module for CX Terminal
//!
//! Provides an advanced input editor with:
//! - Multi-line support (Shift+Enter for newline)
//! - Syntax highlighting for shell commands
//! - Auto-complete for commands and paths
//! - History navigation (Ctrl+R search)
//! - Vi/Emacs keybindings option

pub mod complete;
pub mod editor;
pub mod highlight;

use crate::input::complete::Completer;
use crate::input::editor::{Editor, EditorAction};
use crate::input::highlight::{HighlightedSpan, SyntaxHighlighter};
use std::collections::VecDeque;

/// Configuration for the modern input
#[derive(Debug, Clone)]
pub struct InputConfig {
    /// Enable multi-line editing
    pub multiline_enabled: bool,
    /// Enable syntax highlighting
    pub syntax_highlighting: bool,
    /// Enable auto-completion
    pub completion_enabled: bool,
    /// Maximum history entries
    pub max_history: usize,
    /// Keybinding mode
    pub keybinding_mode: KeybindingMode,
}

impl Default for InputConfig {
    fn default() -> Self {
        Self {
            multiline_enabled: true,
            syntax_highlighting: true,
            completion_enabled: true,
            max_history: 1000,
            keybinding_mode: KeybindingMode::Default,
        }
    }
}

/// Keybinding mode for the editor
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum KeybindingMode {
    #[default]
    Default,
    Vi,
    Emacs,
}

/// Vi mode states
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ViMode {
    #[default]
    Insert,
    Normal,
    Visual,
    VisualLine,
}

/// State for history search (Ctrl+R)
#[derive(Debug, Clone)]
pub struct HistorySearch {
    /// Current search query
    pub query: String,
    /// Current match index
    pub match_index: usize,
    /// Matched entries
    pub matches: Vec<usize>,
}

impl Default for HistorySearch {
    fn default() -> Self {
        Self {
            query: String::new(),
            match_index: 0,
            matches: Vec::new(),
        }
    }
}

/// The modern input handler
pub struct ModernInput {
    /// The text editor
    pub editor: Editor,
    /// Syntax highlighter
    pub highlighter: SyntaxHighlighter,
    /// Command/path completer
    pub completer: Completer,
    /// Command history
    pub history: VecDeque<String>,
    /// Current position in history navigation
    pub history_pos: Option<usize>,
    /// Configuration
    pub config: InputConfig,
    /// Vi mode (if using vi keybindings)
    pub vi_mode: ViMode,
    /// Active history search
    pub history_search: Option<HistorySearch>,
    /// Current completion suggestions
    pub completions: Vec<String>,
    /// Selected completion index
    pub completion_index: usize,
    /// Whether completion popup is visible
    pub completion_visible: bool,
}

impl ModernInput {
    /// Create a new modern input handler
    pub fn new(config: InputConfig) -> Self {
        Self {
            editor: Editor::new(),
            highlighter: SyntaxHighlighter::new(),
            completer: Completer::new(),
            history: VecDeque::with_capacity(config.max_history),
            history_pos: None,
            config,
            vi_mode: ViMode::Insert,
            history_search: None,
            completions: Vec::new(),
            completion_index: 0,
            completion_visible: false,
        }
    }

    /// Get the current input text
    pub fn text(&self) -> &str {
        self.editor.text()
    }

    /// Set the input text
    pub fn set_text(&mut self, text: &str) {
        self.editor.set_text(text);
        self.update_completions();
    }

    /// Clear the input
    pub fn clear(&mut self) {
        self.editor.clear();
        self.history_pos = None;
        self.history_search = None;
        self.hide_completions();
    }

    /// Get highlighted spans for rendering
    pub fn highlighted_spans(&self) -> Vec<HighlightedSpan> {
        if self.config.syntax_highlighting {
            self.highlighter.highlight(self.editor.text())
        } else {
            vec![HighlightedSpan::default_text(self.editor.text())]
        }
    }

    /// Handle a key event
    pub fn handle_key(
        &mut self,
        key: termwiz::input::KeyCode,
        mods: termwiz::input::Modifiers,
    ) -> InputResult {
        use termwiz::input::KeyCode;
        use termwiz::input::Modifiers;

        // Handle history search mode
        if let Some(ref mut search) = self.history_search {
            return self.handle_history_search_key(key, mods);
        }

        // Handle completion navigation
        if self.completion_visible {
            match key {
                KeyCode::Tab if !mods.contains(Modifiers::SHIFT) => {
                    return self.select_next_completion();
                }
                KeyCode::Tab if mods.contains(Modifiers::SHIFT) => {
                    return self.select_prev_completion();
                }
                KeyCode::Enter => {
                    return self.accept_completion();
                }
                KeyCode::Escape => {
                    self.hide_completions();
                    return InputResult::Updated;
                }
                _ => {
                    self.hide_completions();
                }
            }
        }

        // Handle special key combinations
        match (key.clone(), mods) {
            // Ctrl+R - Start history search
            (KeyCode::Char('r'), m) if m.contains(Modifiers::CTRL) => {
                self.start_history_search();
                return InputResult::Updated;
            }

            // Shift+Enter - Insert newline (multi-line mode)
            (KeyCode::Enter, m)
                if m.contains(Modifiers::SHIFT) && self.config.multiline_enabled =>
            {
                self.editor.insert_char('\n');
                return InputResult::Updated;
            }

            // Enter - Submit
            (KeyCode::Enter, m) if !m.contains(Modifiers::SHIFT) => {
                let text = self.editor.text().to_string();
                if !text.trim().is_empty() {
                    self.add_to_history(text.clone());
                }
                self.clear();
                return InputResult::Submit(text);
            }

            // Tab - Trigger completion
            (KeyCode::Tab, m) if !m.contains(Modifiers::SHIFT) => {
                self.trigger_completion();
                return InputResult::Updated;
            }

            // Up arrow - History navigation
            (KeyCode::UpArrow, m) if !m.contains(Modifiers::ALT) => {
                self.navigate_history_up();
                return InputResult::Updated;
            }

            // Down arrow - History navigation
            (KeyCode::DownArrow, m) if !m.contains(Modifiers::ALT) => {
                self.navigate_history_down();
                return InputResult::Updated;
            }

            // Ctrl+A - Move to start of line
            (KeyCode::Char('a'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.move_to_line_start();
                return InputResult::Updated;
            }

            // Ctrl+E - Move to end of line
            (KeyCode::Char('e'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.move_to_line_end();
                return InputResult::Updated;
            }

            // Ctrl+K - Kill to end of line
            (KeyCode::Char('k'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.kill_to_line_end();
                return InputResult::Updated;
            }

            // Ctrl+U - Kill to start of line
            (KeyCode::Char('u'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.kill_to_line_start();
                return InputResult::Updated;
            }

            // Ctrl+W - Kill word backward
            (KeyCode::Char('w'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.kill_word_backward();
                return InputResult::Updated;
            }

            // Ctrl+Y - Yank (paste from kill ring)
            (KeyCode::Char('y'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.yank();
                return InputResult::Updated;
            }

            // Ctrl+Z - Undo
            (KeyCode::Char('z'), m) if m.contains(Modifiers::CTRL) => {
                self.editor.undo();
                return InputResult::Updated;
            }

            // Ctrl+Shift+Z - Redo
            (KeyCode::Char('Z'), m)
                if m.contains(Modifiers::CTRL) && m.contains(Modifiers::SHIFT) =>
            {
                self.editor.redo();
                return InputResult::Updated;
            }

            // Escape - Cancel/clear
            (KeyCode::Escape, _) => {
                if self.config.keybinding_mode == KeybindingMode::Vi {
                    self.vi_mode = ViMode::Normal;
                } else {
                    self.clear();
                }
                return InputResult::Updated;
            }

            _ => {}
        }

        // Handle regular editing
        let action = match key {
            KeyCode::Char(c) => {
                self.editor.insert_char(c);
                self.update_completions();
                EditorAction::Insert
            }
            KeyCode::Backspace => {
                self.editor.backspace();
                self.update_completions();
                EditorAction::Delete
            }
            KeyCode::Delete => {
                self.editor.delete();
                self.update_completions();
                EditorAction::Delete
            }
            KeyCode::LeftArrow => {
                if mods.contains(termwiz::input::Modifiers::CTRL) {
                    self.editor.move_word_left();
                } else {
                    self.editor.move_left();
                }
                EditorAction::Move
            }
            KeyCode::RightArrow => {
                if mods.contains(termwiz::input::Modifiers::CTRL) {
                    self.editor.move_word_right();
                } else {
                    self.editor.move_right();
                }
                EditorAction::Move
            }
            KeyCode::Home => {
                self.editor.move_to_line_start();
                EditorAction::Move
            }
            KeyCode::End => {
                self.editor.move_to_line_end();
                EditorAction::Move
            }
            _ => EditorAction::None,
        };

        if action != EditorAction::None {
            InputResult::Updated
        } else {
            InputResult::Ignored
        }
    }

    /// Start history search mode
    fn start_history_search(&mut self) {
        self.history_search = Some(HistorySearch::default());
    }

    /// Handle key in history search mode
    fn handle_history_search_key(
        &mut self,
        key: termwiz::input::KeyCode,
        mods: termwiz::input::Modifiers,
    ) -> InputResult {
        use termwiz::input::KeyCode;
        use termwiz::input::Modifiers;

        let search = match self.history_search.as_mut() {
            Some(s) => s,
            None => return InputResult::Ignored,
        };

        match key {
            KeyCode::Escape | KeyCode::Char('g') if mods.contains(Modifiers::CTRL) => {
                self.history_search = None;
                InputResult::Updated
            }
            KeyCode::Enter => {
                // Accept the current match
                if let Some(&idx) = search.matches.get(search.match_index) {
                    if let Some(entry) = self.history.get(idx) {
                        self.editor.set_text(entry);
                    }
                }
                self.history_search = None;
                InputResult::Updated
            }
            KeyCode::Char('r') if mods.contains(Modifiers::CTRL) => {
                // Next match
                if !search.matches.is_empty() {
                    search.match_index = (search.match_index + 1) % search.matches.len();
                    if let Some(&idx) = search.matches.get(search.match_index) {
                        if let Some(entry) = self.history.get(idx) {
                            self.editor.set_text(entry);
                        }
                    }
                }
                InputResult::Updated
            }
            KeyCode::Char('s') if mods.contains(Modifiers::CTRL) => {
                // Previous match
                if !search.matches.is_empty() {
                    search.match_index = if search.match_index == 0 {
                        search.matches.len() - 1
                    } else {
                        search.match_index - 1
                    };
                    if let Some(&idx) = search.matches.get(search.match_index) {
                        if let Some(entry) = self.history.get(idx) {
                            self.editor.set_text(entry);
                        }
                    }
                }
                InputResult::Updated
            }
            KeyCode::Backspace => {
                search.query.pop();
                self.update_history_search();
                InputResult::Updated
            }
            KeyCode::Char(c) => {
                search.query.push(c);
                self.update_history_search();
                InputResult::Updated
            }
            _ => InputResult::Ignored,
        }
    }

    /// Update history search matches
    fn update_history_search(&mut self) {
        if let Some(ref mut search) = self.history_search {
            search.matches.clear();
            search.match_index = 0;

            let query = search.query.to_lowercase();
            for (idx, entry) in self.history.iter().enumerate() {
                if entry.to_lowercase().contains(&query) {
                    search.matches.push(idx);
                }
            }

            // Show first match
            if let Some(&idx) = search.matches.first() {
                if let Some(entry) = self.history.get(idx) {
                    self.editor.set_text(entry);
                }
            }
        }
    }

    /// Navigate history up
    fn navigate_history_up(&mut self) {
        if self.history.is_empty() {
            return;
        }

        let new_pos = match self.history_pos {
            Some(pos) if pos + 1 < self.history.len() => Some(pos + 1),
            Some(pos) => Some(pos),
            None => Some(0),
        };

        if let Some(pos) = new_pos {
            self.history_pos = Some(pos);
            if let Some(entry) = self.history.get(pos) {
                self.editor.set_text(entry);
            }
        }
    }

    /// Navigate history down
    fn navigate_history_down(&mut self) {
        match self.history_pos {
            Some(0) => {
                self.history_pos = None;
                self.editor.clear();
            }
            Some(pos) => {
                self.history_pos = Some(pos - 1);
                if let Some(entry) = self.history.get(pos - 1) {
                    self.editor.set_text(entry);
                }
            }
            None => {}
        }
    }

    /// Add entry to history
    fn add_to_history(&mut self, entry: String) {
        // Don't add duplicates at the front
        if self.history.front() == Some(&entry) {
            return;
        }

        self.history.push_front(entry);

        // Trim to max size
        while self.history.len() > self.config.max_history {
            self.history.pop_back();
        }
    }

    /// Trigger completion
    fn trigger_completion(&mut self) {
        let text = self.editor.text();
        let cursor_pos = self.editor.cursor_pos();

        self.completions = self.completer.complete(text, cursor_pos);

        if self.completions.len() == 1 {
            // Single completion - apply directly
            self.apply_completion(&self.completions[0].clone());
        } else if !self.completions.is_empty() {
            // Multiple completions - show popup
            self.completion_visible = true;
            self.completion_index = 0;
        }
    }

    /// Update completions as user types
    fn update_completions(&mut self) {
        if !self.config.completion_enabled {
            return;
        }

        // Only update if popup is visible
        if self.completion_visible {
            let text = self.editor.text();
            let cursor_pos = self.editor.cursor_pos();
            self.completions = self.completer.complete(text, cursor_pos);

            if self.completions.is_empty() {
                self.hide_completions();
            } else {
                self.completion_index = self.completion_index.min(self.completions.len() - 1);
            }
        }
    }

    /// Select next completion
    fn select_next_completion(&mut self) -> InputResult {
        if !self.completions.is_empty() {
            self.completion_index = (self.completion_index + 1) % self.completions.len();
        }
        InputResult::Updated
    }

    /// Select previous completion
    fn select_prev_completion(&mut self) -> InputResult {
        if !self.completions.is_empty() {
            self.completion_index = if self.completion_index == 0 {
                self.completions.len() - 1
            } else {
                self.completion_index - 1
            };
        }
        InputResult::Updated
    }

    /// Accept current completion
    fn accept_completion(&mut self) -> InputResult {
        if let Some(completion) = self.completions.get(self.completion_index).cloned() {
            self.apply_completion(&completion);
            self.hide_completions();
        }
        InputResult::Updated
    }

    /// Apply a completion
    fn apply_completion(&mut self, completion: &str) {
        // Find the word start
        let text = self.editor.text();
        let cursor = self.editor.cursor_pos();

        let word_start = text[..cursor]
            .rfind(|c: char| c.is_whitespace() || c == '/' || c == '\\')
            .map(|i| i + 1)
            .unwrap_or(0);

        // Replace from word start to cursor
        self.editor.delete_range(word_start, cursor);
        self.editor.set_cursor(word_start);
        for c in completion.chars() {
            self.editor.insert_char(c);
        }
    }

    /// Hide completion popup
    fn hide_completions(&mut self) {
        self.completion_visible = false;
        self.completions.clear();
        self.completion_index = 0;
    }

    /// Get cursor position for rendering
    pub fn cursor_position(&self) -> (usize, usize) {
        self.editor.cursor_coords()
    }

    /// Check if in history search mode
    pub fn is_searching_history(&self) -> bool {
        self.history_search.is_some()
    }

    /// Get history search query
    pub fn search_query(&self) -> Option<&str> {
        self.history_search.as_ref().map(|s| s.query.as_str())
    }

    /// Load history from file
    pub fn load_history(&mut self, path: &std::path::Path) -> std::io::Result<()> {
        use std::fs::File;
        use std::io::{BufRead, BufReader};

        let file = File::open(path)?;
        let reader = BufReader::new(file);

        self.history.clear();
        for line in reader.lines() {
            if let Ok(entry) = line {
                if !entry.trim().is_empty() {
                    self.history.push_back(entry);
                }
            }
        }

        // Trim to max size
        while self.history.len() > self.config.max_history {
            self.history.pop_back();
        }

        Ok(())
    }

    /// Save history to file
    pub fn save_history(&self, path: &std::path::Path) -> std::io::Result<()> {
        use std::fs::File;
        use std::io::{BufWriter, Write};

        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let file = File::create(path)?;
        let mut writer = BufWriter::new(file);

        for entry in &self.history {
            writeln!(writer, "{}", entry)?;
        }

        Ok(())
    }
}

/// Result of handling an input event
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputResult {
    /// Input was updated
    Updated,
    /// Input was submitted with the given text
    Submit(String),
    /// Input event was ignored
    Ignored,
}
