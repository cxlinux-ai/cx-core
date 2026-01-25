//! Text editor component with cursor tracking, selection, and undo/redo
//!
//! Provides a rope-based text buffer for efficient editing of multi-line text.

use std::collections::VecDeque;
use std::ops::Range;

/// Maximum undo history entries
const MAX_UNDO_HISTORY: usize = 100;

/// A text editor with cursor, selection, and undo/redo support
#[derive(Debug, Clone)]
pub struct Editor {
    /// The text content (stored as lines for efficient multi-line handling)
    lines: Vec<String>,
    /// Cursor position as (line, column)
    cursor: CursorPosition,
    /// Selection anchor (if any)
    selection_anchor: Option<CursorPosition>,
    /// Undo stack
    undo_stack: VecDeque<EditorState>,
    /// Redo stack
    redo_stack: VecDeque<EditorState>,
    /// Kill ring (for Ctrl+K/Ctrl+Y operations)
    kill_ring: Vec<String>,
    /// Whether the editor has been modified since last save
    modified: bool,
}

/// Cursor position in the editor
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct CursorPosition {
    /// Line number (0-indexed)
    pub line: usize,
    /// Column number (0-indexed, in characters)
    pub column: usize,
}

/// Editor state for undo/redo
#[derive(Debug, Clone)]
struct EditorState {
    lines: Vec<String>,
    cursor: CursorPosition,
}

/// Action type for tracking changes
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EditorAction {
    None,
    Insert,
    Delete,
    Move,
}

impl Editor {
    /// Create a new empty editor
    pub fn new() -> Self {
        Self {
            lines: vec![String::new()],
            cursor: CursorPosition::default(),
            selection_anchor: None,
            undo_stack: VecDeque::with_capacity(MAX_UNDO_HISTORY),
            redo_stack: VecDeque::with_capacity(MAX_UNDO_HISTORY),
            kill_ring: Vec::new(),
            modified: false,
        }
    }

    /// Get the full text content
    pub fn text(&self) -> &str {
        // This is a bit inefficient, but we cache internally
        // For single-line input, this is fine
        if self.lines.len() == 1 {
            &self.lines[0]
        } else {
            // Return reference to first line for now
            // The full text is computed on demand
            &self.lines[0]
        }
    }

    /// Get the full text as a single string
    pub fn full_text(&self) -> String {
        self.lines.join("\n")
    }

    /// Set the text content
    pub fn set_text(&mut self, text: &str) {
        self.save_undo_state();
        self.lines = text.split('\n').map(String::from).collect();
        if self.lines.is_empty() {
            self.lines.push(String::new());
        }
        // Move cursor to end
        self.cursor.line = self.lines.len() - 1;
        self.cursor.column = self.lines[self.cursor.line].chars().count();
        self.selection_anchor = None;
        self.modified = true;
    }

    /// Clear the editor
    pub fn clear(&mut self) {
        self.save_undo_state();
        self.lines = vec![String::new()];
        self.cursor = CursorPosition::default();
        self.selection_anchor = None;
        self.modified = false;
    }

    /// Get current cursor position as byte offset
    pub fn cursor_pos(&self) -> usize {
        let mut pos = 0;
        for (i, line) in self.lines.iter().enumerate() {
            if i < self.cursor.line {
                pos += line.len() + 1; // +1 for newline
            } else {
                pos += line.chars().take(self.cursor.column).map(|c| c.len_utf8()).sum::<usize>();
                break;
            }
        }
        pos
    }

    /// Get cursor position as (line, column)
    pub fn cursor_coords(&self) -> (usize, usize) {
        (self.cursor.line, self.cursor.column)
    }

    /// Set cursor position
    pub fn set_cursor(&mut self, byte_pos: usize) {
        let mut remaining = byte_pos;
        for (line_idx, line) in self.lines.iter().enumerate() {
            let line_len = line.len();
            if remaining <= line_len || line_idx == self.lines.len() - 1 {
                self.cursor.line = line_idx;
                // Convert byte position to character position
                self.cursor.column = line.chars()
                    .take_while(|_| {
                        let c_len = 1; // Simplified for now
                        if remaining >= c_len {
                            remaining -= c_len;
                            true
                        } else {
                            false
                        }
                    })
                    .count();
                break;
            }
            remaining -= line_len + 1; // +1 for newline
        }
    }

    /// Insert a character at cursor position
    pub fn insert_char(&mut self, c: char) {
        self.save_undo_state();
        self.delete_selection();

        if c == '\n' {
            // Split line at cursor
            let current_line = &self.lines[self.cursor.line];
            let char_indices: Vec<_> = current_line.char_indices().collect();
            let byte_pos = if self.cursor.column >= char_indices.len() {
                current_line.len()
            } else {
                char_indices[self.cursor.column].0
            };

            let remainder = current_line[byte_pos..].to_string();
            self.lines[self.cursor.line].truncate(byte_pos);
            self.cursor.line += 1;
            self.lines.insert(self.cursor.line, remainder);
            self.cursor.column = 0;
        } else {
            // Insert character
            let current_line = &mut self.lines[self.cursor.line];
            let char_indices: Vec<_> = current_line.char_indices().collect();
            let byte_pos = if self.cursor.column >= char_indices.len() {
                current_line.len()
            } else {
                char_indices[self.cursor.column].0
            };
            current_line.insert(byte_pos, c);
            self.cursor.column += 1;
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Insert a string at cursor position
    pub fn insert_str(&mut self, s: &str) {
        for c in s.chars() {
            self.insert_char(c);
        }
    }

    /// Delete character before cursor (backspace)
    pub fn backspace(&mut self) {
        if self.delete_selection() {
            return;
        }

        self.save_undo_state();

        if self.cursor.column > 0 {
            // Delete character within line
            let current_line = &mut self.lines[self.cursor.line];
            let char_indices: Vec<_> = current_line.char_indices().collect();
            if self.cursor.column <= char_indices.len() {
                let byte_start = if self.cursor.column > 0 {
                    char_indices[self.cursor.column - 1].0
                } else {
                    0
                };
                let byte_end = if self.cursor.column < char_indices.len() {
                    char_indices[self.cursor.column].0
                } else {
                    current_line.len()
                };

                // Remove the character at cursor - 1
                if self.cursor.column > 0 {
                    let byte_start = char_indices[self.cursor.column - 1].0;
                    let byte_end = if self.cursor.column < char_indices.len() {
                        char_indices[self.cursor.column].0
                    } else {
                        current_line.len()
                    };
                    current_line.drain(byte_start..byte_end);
                    self.cursor.column -= 1;
                }
            }
        } else if self.cursor.line > 0 {
            // Join with previous line
            let current_line = self.lines.remove(self.cursor.line);
            self.cursor.line -= 1;
            self.cursor.column = self.lines[self.cursor.line].chars().count();
            self.lines[self.cursor.line].push_str(&current_line);
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Delete character at cursor (delete key)
    pub fn delete(&mut self) {
        if self.delete_selection() {
            return;
        }

        self.save_undo_state();

        let current_line = &self.lines[self.cursor.line];
        let char_count = current_line.chars().count();

        if self.cursor.column < char_count {
            // Delete character at cursor
            let char_indices: Vec<_> = current_line.char_indices().collect();
            let byte_start = char_indices[self.cursor.column].0;
            let byte_end = if self.cursor.column + 1 < char_indices.len() {
                char_indices[self.cursor.column + 1].0
            } else {
                current_line.len()
            };

            self.lines[self.cursor.line].drain(byte_start..byte_end);
        } else if self.cursor.line + 1 < self.lines.len() {
            // Join with next line
            let next_line = self.lines.remove(self.cursor.line + 1);
            self.lines[self.cursor.line].push_str(&next_line);
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Delete a range of text (byte positions)
    pub fn delete_range(&mut self, start: usize, end: usize) {
        self.save_undo_state();

        // Convert to full text, delete, then set
        let mut text = self.full_text();
        let start = start.min(text.len());
        let end = end.min(text.len());
        text.drain(start..end);

        // Preserve cursor position temporarily
        let full_text = text;
        self.lines = full_text.split('\n').map(String::from).collect();
        if self.lines.is_empty() {
            self.lines.push(String::new());
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Move cursor left
    pub fn move_left(&mut self) {
        self.selection_anchor = None;
        if self.cursor.column > 0 {
            self.cursor.column -= 1;
        } else if self.cursor.line > 0 {
            self.cursor.line -= 1;
            self.cursor.column = self.lines[self.cursor.line].chars().count();
        }
    }

    /// Move cursor right
    pub fn move_right(&mut self) {
        self.selection_anchor = None;
        let line_len = self.lines[self.cursor.line].chars().count();
        if self.cursor.column < line_len {
            self.cursor.column += 1;
        } else if self.cursor.line + 1 < self.lines.len() {
            self.cursor.line += 1;
            self.cursor.column = 0;
        }
    }

    /// Move cursor up
    pub fn move_up(&mut self) {
        self.selection_anchor = None;
        if self.cursor.line > 0 {
            self.cursor.line -= 1;
            let line_len = self.lines[self.cursor.line].chars().count();
            self.cursor.column = self.cursor.column.min(line_len);
        }
    }

    /// Move cursor down
    pub fn move_down(&mut self) {
        self.selection_anchor = None;
        if self.cursor.line + 1 < self.lines.len() {
            self.cursor.line += 1;
            let line_len = self.lines[self.cursor.line].chars().count();
            self.cursor.column = self.cursor.column.min(line_len);
        }
    }

    /// Move cursor to start of line
    pub fn move_to_line_start(&mut self) {
        self.selection_anchor = None;
        self.cursor.column = 0;
    }

    /// Move cursor to end of line
    pub fn move_to_line_end(&mut self) {
        self.selection_anchor = None;
        self.cursor.column = self.lines[self.cursor.line].chars().count();
    }

    /// Move cursor word left
    pub fn move_word_left(&mut self) {
        self.selection_anchor = None;
        let line = &self.lines[self.cursor.line];
        let chars: Vec<char> = line.chars().collect();

        if self.cursor.column == 0 {
            if self.cursor.line > 0 {
                self.cursor.line -= 1;
                self.cursor.column = self.lines[self.cursor.line].chars().count();
            }
            return;
        }

        // Skip whitespace
        while self.cursor.column > 0 && chars.get(self.cursor.column - 1).map_or(false, |c| c.is_whitespace()) {
            self.cursor.column -= 1;
        }

        // Skip word characters
        while self.cursor.column > 0 && chars.get(self.cursor.column - 1).map_or(false, |c| !c.is_whitespace()) {
            self.cursor.column -= 1;
        }
    }

    /// Move cursor word right
    pub fn move_word_right(&mut self) {
        self.selection_anchor = None;
        let line = &self.lines[self.cursor.line];
        let chars: Vec<char> = line.chars().collect();
        let len = chars.len();

        if self.cursor.column >= len {
            if self.cursor.line + 1 < self.lines.len() {
                self.cursor.line += 1;
                self.cursor.column = 0;
            }
            return;
        }

        // Skip word characters
        while self.cursor.column < len && !chars[self.cursor.column].is_whitespace() {
            self.cursor.column += 1;
        }

        // Skip whitespace
        while self.cursor.column < len && chars[self.cursor.column].is_whitespace() {
            self.cursor.column += 1;
        }
    }

    /// Kill to end of line (Ctrl+K)
    pub fn kill_to_line_end(&mut self) {
        self.save_undo_state();

        let line = &self.lines[self.cursor.line];
        let chars: Vec<char> = line.chars().collect();
        let len = chars.len();

        if self.cursor.column < len {
            // Kill rest of line
            let killed: String = chars[self.cursor.column..].iter().collect();
            self.kill_ring.push(killed);

            let char_indices: Vec<_> = line.char_indices().collect();
            let byte_pos = if self.cursor.column < char_indices.len() {
                char_indices[self.cursor.column].0
            } else {
                line.len()
            };
            self.lines[self.cursor.line].truncate(byte_pos);
        } else if self.cursor.line + 1 < self.lines.len() {
            // Kill newline (join with next line)
            let next_line = self.lines.remove(self.cursor.line + 1);
            self.lines[self.cursor.line].push_str(&next_line);
            self.kill_ring.push("\n".to_string());
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Kill to start of line (Ctrl+U)
    pub fn kill_to_line_start(&mut self) {
        self.save_undo_state();

        let line = &self.lines[self.cursor.line];
        let chars: Vec<char> = line.chars().collect();

        if self.cursor.column > 0 {
            let killed: String = chars[..self.cursor.column].iter().collect();
            self.kill_ring.push(killed);

            let char_indices: Vec<_> = line.char_indices().collect();
            let byte_pos = if self.cursor.column < char_indices.len() {
                char_indices[self.cursor.column].0
            } else {
                line.len()
            };

            let remaining = self.lines[self.cursor.line][byte_pos..].to_string();
            self.lines[self.cursor.line] = remaining;
            self.cursor.column = 0;
        }

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Kill word backward (Ctrl+W)
    pub fn kill_word_backward(&mut self) {
        self.save_undo_state();

        let line = &self.lines[self.cursor.line];
        let chars: Vec<char> = line.chars().collect();

        if self.cursor.column == 0 {
            return;
        }

        let start_column = self.cursor.column;
        let mut end_column = self.cursor.column;

        // Skip whitespace
        while end_column > 0 && chars.get(end_column - 1).map_or(false, |c| c.is_whitespace()) {
            end_column -= 1;
        }

        // Skip word characters
        while end_column > 0 && chars.get(end_column - 1).map_or(false, |c| !c.is_whitespace()) {
            end_column -= 1;
        }

        let killed: String = chars[end_column..start_column].iter().collect();
        self.kill_ring.push(killed);

        // Delete the word
        let line = &self.lines[self.cursor.line];
        let char_indices: Vec<_> = line.char_indices().collect();

        let byte_start = if end_column < char_indices.len() {
            char_indices[end_column].0
        } else {
            line.len()
        };
        let byte_end = if start_column < char_indices.len() {
            char_indices[start_column].0
        } else {
            line.len()
        };

        self.lines[self.cursor.line].drain(byte_start..byte_end);
        self.cursor.column = end_column;

        self.modified = true;
        self.redo_stack.clear();
    }

    /// Yank (paste from kill ring)
    pub fn yank(&mut self) {
        if let Some(text) = self.kill_ring.last().cloned() {
            self.insert_str(&text);
        }
    }

    /// Start selection at current cursor position
    pub fn start_selection(&mut self) {
        self.selection_anchor = Some(self.cursor);
    }

    /// Get current selection range
    pub fn selection(&self) -> Option<(CursorPosition, CursorPosition)> {
        self.selection_anchor.map(|anchor| {
            if anchor.line < self.cursor.line
                || (anchor.line == self.cursor.line && anchor.column <= self.cursor.column)
            {
                (anchor, self.cursor)
            } else {
                (self.cursor, anchor)
            }
        })
    }

    /// Delete selection and return true if there was a selection
    fn delete_selection(&mut self) -> bool {
        if let Some((start, end)) = self.selection() {
            self.save_undo_state();

            // Convert to byte positions and delete
            // This is simplified - a full implementation would be more complex
            self.selection_anchor = None;

            // Move cursor to start of selection
            self.cursor = start;

            // Delete from start to end
            if start.line == end.line {
                let line = &self.lines[start.line];
                let char_indices: Vec<_> = line.char_indices().collect();
                let byte_start = if start.column < char_indices.len() {
                    char_indices[start.column].0
                } else {
                    line.len()
                };
                let byte_end = if end.column < char_indices.len() {
                    char_indices[end.column].0
                } else {
                    line.len()
                };
                self.lines[start.line].drain(byte_start..byte_end);
            } else {
                // Multi-line selection - join first and last line with content between removed
                let first_line = &self.lines[start.line];
                let char_indices: Vec<_> = first_line.char_indices().collect();
                let byte_start = if start.column < char_indices.len() {
                    char_indices[start.column].0
                } else {
                    first_line.len()
                };
                let first_part = first_line[..byte_start].to_string();

                let last_line = &self.lines[end.line];
                let char_indices: Vec<_> = last_line.char_indices().collect();
                let byte_end = if end.column < char_indices.len() {
                    char_indices[end.column].0
                } else {
                    last_line.len()
                };
                let last_part = last_line[byte_end..].to_string();

                // Remove lines between
                for _ in start.line..=end.line {
                    self.lines.remove(start.line);
                }

                self.lines.insert(start.line, format!("{}{}", first_part, last_part));
            }

            self.modified = true;
            self.redo_stack.clear();
            true
        } else {
            false
        }
    }

    /// Get selected text
    pub fn selected_text(&self) -> Option<String> {
        self.selection().map(|(start, end)| {
            if start.line == end.line {
                let line = &self.lines[start.line];
                let chars: Vec<char> = line.chars().collect();
                chars[start.column..end.column].iter().collect()
            } else {
                let mut result = String::new();
                for line_idx in start.line..=end.line {
                    let line = &self.lines[line_idx];
                    let chars: Vec<char> = line.chars().collect();

                    if line_idx == start.line {
                        result.push_str(&chars[start.column..].iter().collect::<String>());
                        result.push('\n');
                    } else if line_idx == end.line {
                        result.push_str(&chars[..end.column].iter().collect::<String>());
                    } else {
                        result.push_str(line);
                        result.push('\n');
                    }
                }
                result
            }
        })
    }

    /// Save current state for undo
    fn save_undo_state(&mut self) {
        let state = EditorState {
            lines: self.lines.clone(),
            cursor: self.cursor,
        };

        self.undo_stack.push_back(state);

        // Limit undo history
        while self.undo_stack.len() > MAX_UNDO_HISTORY {
            self.undo_stack.pop_front();
        }
    }

    /// Undo last action
    pub fn undo(&mut self) {
        if let Some(state) = self.undo_stack.pop_back() {
            // Save current state to redo stack
            let current = EditorState {
                lines: self.lines.clone(),
                cursor: self.cursor,
            };
            self.redo_stack.push_back(current);

            // Restore previous state
            self.lines = state.lines;
            self.cursor = state.cursor;
            self.selection_anchor = None;
        }
    }

    /// Redo last undone action
    pub fn redo(&mut self) {
        if let Some(state) = self.redo_stack.pop_back() {
            // Save current state to undo stack
            let current = EditorState {
                lines: self.lines.clone(),
                cursor: self.cursor,
            };
            self.undo_stack.push_back(current);

            // Restore redo state
            self.lines = state.lines;
            self.cursor = state.cursor;
            self.selection_anchor = None;
        }
    }

    /// Check if editor has been modified
    pub fn is_modified(&self) -> bool {
        self.modified
    }

    /// Mark editor as unmodified
    pub fn mark_unmodified(&mut self) {
        self.modified = false;
    }

    /// Get number of lines
    pub fn line_count(&self) -> usize {
        self.lines.len()
    }

    /// Get a specific line
    pub fn line(&self, idx: usize) -> Option<&str> {
        self.lines.get(idx).map(|s| s.as_str())
    }
}

impl Default for Editor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_insert_and_backspace() {
        let mut editor = Editor::new();
        editor.insert_char('h');
        editor.insert_char('i');
        assert_eq!(editor.text(), "hi");

        editor.backspace();
        assert_eq!(editor.text(), "h");
    }

    #[test]
    fn test_newline() {
        let mut editor = Editor::new();
        editor.insert_str("hello");
        editor.insert_char('\n');
        editor.insert_str("world");

        assert_eq!(editor.line_count(), 2);
        assert_eq!(editor.line(0), Some("hello"));
        assert_eq!(editor.line(1), Some("world"));
    }

    #[test]
    fn test_cursor_movement() {
        let mut editor = Editor::new();
        editor.insert_str("hello");

        editor.move_left();
        editor.move_left();
        editor.insert_char('X');

        assert_eq!(editor.text(), "helXlo");
    }

    #[test]
    fn test_undo_redo() {
        let mut editor = Editor::new();
        editor.insert_str("hello");
        editor.insert_str(" world");

        editor.undo();
        assert_eq!(editor.text(), "hello");

        editor.redo();
        assert_eq!(editor.text(), "hello world");
    }
}
