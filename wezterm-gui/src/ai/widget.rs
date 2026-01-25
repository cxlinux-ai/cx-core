//! AI Panel Widget for CX Terminal
//!
//! Renders the AI panel UI as a side panel in the terminal window.
//! Handles display of chat messages, input field, and loading states.

use super::{AIPanel, AIPanelState, ChatMessage, ChatRole};
use config::RgbColor;
use termwiz::cell::{Cell, CellAttributes};
use termwiz::color::{AnsiColor, ColorSpec};

// CX Terminal: AI Panel Widget implementation

/// Colors for the AI panel
#[derive(Clone, Debug)]
pub struct AIPanelColors {
    /// Panel background color
    pub background: RgbColor,
    /// Panel border color
    pub border: RgbColor,
    /// Header background color
    pub header_bg: RgbColor,
    /// Header text color
    pub header_fg: RgbColor,
    /// User message background
    pub user_bg: RgbColor,
    /// User message text
    pub user_fg: RgbColor,
    /// Assistant message background
    pub assistant_bg: RgbColor,
    /// Assistant message text
    pub assistant_fg: RgbColor,
    /// Input field background
    pub input_bg: RgbColor,
    /// Input field text
    pub input_fg: RgbColor,
    /// Placeholder text
    pub placeholder: RgbColor,
    /// Error text
    pub error: RgbColor,
    /// Loading indicator
    pub loading: RgbColor,
}

impl Default for AIPanelColors {
    fn default() -> Self {
        Self {
            // CX Dark theme colors
            background: RgbColor::new_8bpc(0x13, 0x14, 0x1a),
            border: RgbColor::new_8bpc(0x41, 0x48, 0x68),
            header_bg: RgbColor::new_8bpc(0x1a, 0x1b, 0x26),
            header_fg: RgbColor::new_8bpc(0xc0, 0xca, 0xf5),
            user_bg: RgbColor::new_8bpc(0x1e, 0x1f, 0x2b),
            user_fg: RgbColor::new_8bpc(0x7a, 0xa2, 0xf7),
            assistant_bg: RgbColor::new_8bpc(0x16, 0x17, 0x21),
            assistant_fg: RgbColor::new_8bpc(0xbb, 0x9a, 0xf7),
            input_bg: RgbColor::new_8bpc(0x1a, 0x1b, 0x26),
            input_fg: RgbColor::new_8bpc(0xc0, 0xca, 0xf5),
            placeholder: RgbColor::new_8bpc(0x56, 0x5f, 0x89),
            error: RgbColor::new_8bpc(0xf7, 0x76, 0x8e),
            loading: RgbColor::new_8bpc(0x7a, 0xa2, 0xf7),
        }
    }
}

/// Rendered line in the AI panel
#[derive(Clone, Debug)]
pub struct RenderedLine {
    /// Cells for this line
    pub cells: Vec<Cell>,
    /// Y position (row index)
    pub y: usize,
}

/// AI Panel Widget - handles rendering of the panel
pub struct AIPanelWidget {
    /// Panel colors
    pub colors: AIPanelColors,
    /// Current scroll offset
    pub scroll_offset: usize,
    /// Maximum scroll offset
    pub max_scroll: usize,
    /// Cursor position in input
    pub cursor_pos: usize,
    /// Whether input is focused
    pub input_focused: bool,
}

impl AIPanelWidget {
    pub fn new() -> Self {
        Self {
            colors: AIPanelColors::default(),
            scroll_offset: 0,
            max_scroll: 0,
            cursor_pos: 0,
            input_focused: true,
        }
    }

    /// Render the AI panel to a set of lines
    pub fn render(&mut self, panel: &AIPanel, width: usize, height: usize) -> Vec<RenderedLine> {
        if !panel.is_visible() || width < 10 || height < 5 {
            return Vec::new();
        }

        let mut lines = Vec::with_capacity(height);

        // Reserve space for components
        let header_height = 2;
        let input_height = 3;
        let error_height = if panel.error.is_some() { 2 } else { 0 };
        let loading_height = if panel.loading { 1 } else { 0 };
        let chat_height = height
            .saturating_sub(header_height)
            .saturating_sub(input_height)
            .saturating_sub(error_height)
            .saturating_sub(loading_height);

        let mut y = 0;

        // Render header
        lines.extend(self.render_header(panel, width, y));
        y += header_height;

        // Render chat messages
        lines.extend(self.render_chat(panel, width, chat_height, y));
        y += chat_height;

        // Render loading indicator
        if panel.loading {
            lines.extend(self.render_loading(width, y));
            y += loading_height;
        }

        // Render error if present
        if panel.error.is_some() {
            lines.extend(self.render_error(panel, width, y));
            y += error_height;
        }

        // Render input field
        lines.extend(self.render_input(panel, width, y));

        lines
    }

    /// Render the panel header
    fn render_header(&self, panel: &AIPanel, width: usize, start_y: usize) -> Vec<RenderedLine> {
        let mut lines = Vec::new();

        // Title line
        let title = match panel.state {
            AIPanelState::Hidden => "",
            AIPanelState::Chat => " CX AI Chat",
            AIPanelState::Suggestions => " Suggestions",
            AIPanelState::Explain => " Explain",
            AIPanelState::Minimized => " AI",
        };

        let provider_info = format!(" [{}]", panel.config.provider.as_str());
        let mut header_cells = self.make_line(width, &self.colors.header_bg);

        // Title
        self.write_text(&mut header_cells, 0, title, &self.colors.header_fg);

        // Provider info (right-aligned)
        let provider_start = width.saturating_sub(provider_info.len() + 1);
        self.write_text(
            &mut header_cells,
            provider_start,
            &provider_info,
            &self.colors.placeholder,
        );

        lines.push(RenderedLine {
            cells: header_cells,
            y: start_y,
        });

        // Separator line
        let mut separator = self.make_line(width, &self.colors.background);
        for cell in separator.iter_mut() {
            *cell = self.make_cell('─', &self.colors.border, &self.colors.background);
        }
        lines.push(RenderedLine {
            cells: separator,
            y: start_y + 1,
        });

        lines
    }

    /// Render chat messages
    fn render_chat(
        &mut self,
        panel: &AIPanel,
        width: usize,
        height: usize,
        start_y: usize,
    ) -> Vec<RenderedLine> {
        let mut lines = Vec::new();

        if height == 0 {
            return lines;
        }

        // Wrap and collect all messages
        let mut message_lines: Vec<(ChatRole, String)> = Vec::new();

        for msg in panel.history.messages() {
            let wrapped = self.wrap_text(&msg.content, width.saturating_sub(4));
            for line in wrapped {
                message_lines.push((msg.role, line));
            }
            // Add empty line between messages
            message_lines.push((msg.role, String::new()));
        }

        // Add streaming response if present
        if let Some(streaming) = &panel.streaming_response {
            let wrapped = self.wrap_text(streaming, width.saturating_sub(4));
            for line in wrapped {
                message_lines.push((ChatRole::Assistant, line));
            }
        }

        // Calculate scroll
        self.max_scroll = message_lines.len().saturating_sub(height);
        self.scroll_offset = self.scroll_offset.min(self.max_scroll);

        // Get visible messages
        let visible_start = self.scroll_offset;
        let visible_end = (visible_start + height).min(message_lines.len());

        // Render visible lines
        for (i, y) in (visible_start..visible_end).zip(start_y..) {
            let (role, text) = &message_lines[i];
            let (fg, bg) = match role {
                ChatRole::User => (&self.colors.user_fg, &self.colors.user_bg),
                ChatRole::Assistant => (&self.colors.assistant_fg, &self.colors.assistant_bg),
                ChatRole::System => (&self.colors.placeholder, &self.colors.background),
            };

            let mut cells = self.make_line(width, bg);

            // Role indicator for first line of each message
            let prefix = if !text.is_empty() {
                match role {
                    ChatRole::User => " > ",
                    ChatRole::Assistant => " < ",
                    ChatRole::System => " # ",
                }
            } else {
                "   "
            };

            self.write_text(&mut cells, 0, prefix, fg);
            self.write_text(&mut cells, 3, text, fg);

            lines.push(RenderedLine { cells, y });
        }

        // Fill remaining space
        for y in (start_y + lines.len())..(start_y + height) {
            lines.push(RenderedLine {
                cells: self.make_line(width, &self.colors.background),
                y,
            });
        }

        lines
    }

    /// Render loading indicator
    fn render_loading(&self, width: usize, y: usize) -> Vec<RenderedLine> {
        let mut cells = self.make_line(width, &self.colors.background);
        let loading_text = " Thinking...";
        self.write_text(&mut cells, 0, loading_text, &self.colors.loading);

        // Add animated dots (would need actual animation in termwindow)
        let dots = "●○○"; // Placeholder - actual animation would cycle these
        let dots_start = loading_text.len();
        self.write_text(&mut cells, dots_start, dots, &self.colors.loading);

        vec![RenderedLine { cells, y }]
    }

    /// Render error message
    fn render_error(&self, panel: &AIPanel, width: usize, start_y: usize) -> Vec<RenderedLine> {
        let mut lines = Vec::new();

        if let Some(error) = &panel.error {
            // Error prefix line
            let mut prefix_cells = self.make_line(width, &self.colors.background);
            self.write_text(&mut prefix_cells, 0, " Error:", &self.colors.error);
            lines.push(RenderedLine {
                cells: prefix_cells,
                y: start_y,
            });

            // Error message
            let mut error_cells = self.make_line(width, &self.colors.background);
            let truncated = if error.len() > width - 2 {
                format!("{}...", &error[..width - 5])
            } else {
                error.clone()
            };
            self.write_text(&mut error_cells, 1, &truncated, &self.colors.error);
            lines.push(RenderedLine {
                cells: error_cells,
                y: start_y + 1,
            });
        }

        lines
    }

    /// Render input field
    fn render_input(&self, panel: &AIPanel, width: usize, start_y: usize) -> Vec<RenderedLine> {
        let mut lines = Vec::new();

        // Separator
        let mut separator = self.make_line(width, &self.colors.background);
        for cell in separator.iter_mut() {
            *cell = self.make_cell('─', &self.colors.border, &self.colors.background);
        }
        lines.push(RenderedLine {
            cells: separator,
            y: start_y,
        });

        // Input line
        let mut input_cells = self.make_line(width, &self.colors.input_bg);

        // Prompt
        let prompt = match panel.state {
            AIPanelState::Explain => "? ",
            AIPanelState::Suggestions => "$ ",
            _ => "> ",
        };
        self.write_text(&mut input_cells, 0, prompt, &self.colors.input_fg);

        // Input text or placeholder
        let text_start = prompt.len();
        if panel.input.is_empty() {
            let placeholder = match panel.state {
                AIPanelState::Explain => "Ask about this...",
                AIPanelState::Suggestions => "What do you want to do?",
                _ => "Type a message...",
            };
            self.write_text(&mut input_cells, text_start, placeholder, &self.colors.placeholder);
        } else {
            // Show input with cursor
            let visible_width = width.saturating_sub(text_start + 1);
            let input = if panel.input.len() > visible_width {
                // Scroll input to show cursor
                let start = panel.input.len().saturating_sub(visible_width);
                &panel.input[start..]
            } else {
                &panel.input
            };
            self.write_text(&mut input_cells, text_start, input, &self.colors.input_fg);
        }

        lines.push(RenderedLine {
            cells: input_cells,
            y: start_y + 1,
        });

        // Hint line
        let mut hint_cells = self.make_line(width, &self.colors.background);
        let hint = " Enter to send • Esc to close";
        self.write_text(&mut hint_cells, 0, hint, &self.colors.placeholder);
        lines.push(RenderedLine {
            cells: hint_cells,
            y: start_y + 2,
        });

        lines
    }

    // Helper methods

    /// Create a line filled with background color
    fn make_line(&self, width: usize, bg: &RgbColor) -> Vec<Cell> {
        let cell = self.make_cell(' ', &self.colors.header_fg, bg);
        vec![cell; width]
    }

    /// Create a cell with foreground and background colors
    fn make_cell(&self, c: char, fg: &RgbColor, bg: &RgbColor) -> Cell {
        let mut attrs = CellAttributes::default();
        let fg_spec: ColorSpec = (*fg).into();
        let bg_spec: ColorSpec = (*bg).into();
        attrs.set_foreground(fg_spec);
        attrs.set_background(bg_spec);
        Cell::new(c, attrs)
    }

    /// Write text to cells at position
    fn write_text(&self, cells: &mut [Cell], start: usize, text: &str, fg: &RgbColor) {
        // Use background color from widget colors
        let bg = self.colors.background;

        for (i, ch) in text.chars().enumerate() {
            let pos = start + i;
            if pos < cells.len() {
                cells[pos] = self.make_cell(ch, fg, &bg);
            }
        }
    }

    /// Wrap text to fit width
    fn wrap_text(&self, text: &str, width: usize) -> Vec<String> {
        if width == 0 {
            return Vec::new();
        }

        let mut lines = Vec::new();
        let mut current_line = String::new();

        for word in text.split_whitespace() {
            if current_line.is_empty() {
                if word.len() > width {
                    // Word is longer than width, hard wrap
                    for chunk in word.as_bytes().chunks(width) {
                        lines.push(String::from_utf8_lossy(chunk).to_string());
                    }
                } else {
                    current_line = word.to_string();
                }
            } else if current_line.len() + 1 + word.len() <= width {
                current_line.push(' ');
                current_line.push_str(word);
            } else {
                lines.push(current_line);
                current_line = word.to_string();
            }
        }

        if !current_line.is_empty() {
            lines.push(current_line);
        }

        if lines.is_empty() && !text.is_empty() {
            // Handle case where text is only whitespace or single word
            lines.push(text.to_string());
        }

        lines
    }

    /// Scroll up
    pub fn scroll_up(&mut self, lines: usize) {
        self.scroll_offset = self.scroll_offset.saturating_sub(lines);
    }

    /// Scroll down
    pub fn scroll_down(&mut self, lines: usize) {
        self.scroll_offset = (self.scroll_offset + lines).min(self.max_scroll);
    }

    /// Scroll to bottom
    pub fn scroll_to_bottom(&mut self) {
        self.scroll_offset = self.max_scroll;
    }

    /// Move cursor left
    pub fn cursor_left(&mut self) {
        self.cursor_pos = self.cursor_pos.saturating_sub(1);
    }

    /// Move cursor right
    pub fn cursor_right(&mut self, max: usize) {
        self.cursor_pos = (self.cursor_pos + 1).min(max);
    }

    /// Move cursor to start
    pub fn cursor_home(&mut self) {
        self.cursor_pos = 0;
    }

    /// Move cursor to end
    pub fn cursor_end(&mut self, max: usize) {
        self.cursor_pos = max;
    }
}

impl Default for AIPanelWidget {
    fn default() -> Self {
        Self::new()
    }
}

/// UI Item type for AI panel interactions
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AIPanelUIItem {
    /// Header area
    Header,
    /// Chat message area
    ChatArea,
    /// Scroll up button
    ScrollUp,
    /// Scroll down button
    ScrollDown,
    /// Input field
    InputField,
    /// Close button
    CloseButton,
    /// Send button
    SendButton,
    /// Specific message
    Message(usize),
}

/// Hit test result for AI panel
#[derive(Clone, Debug)]
pub struct AIPanelHitTest {
    /// Item that was hit
    pub item: AIPanelUIItem,
    /// X position within item
    pub x: usize,
    /// Y position within item
    pub y: usize,
}

impl AIPanelWidget {
    /// Perform hit testing for mouse events
    pub fn hit_test(
        &self,
        panel: &AIPanel,
        panel_x: usize,
        panel_y: usize,
        panel_width: usize,
        panel_height: usize,
        mouse_x: usize,
        mouse_y: usize,
    ) -> Option<AIPanelHitTest> {
        // Check if click is within panel bounds
        if mouse_x < panel_x || mouse_x >= panel_x + panel_width {
            return None;
        }
        if mouse_y < panel_y || mouse_y >= panel_y + panel_height {
            return None;
        }

        let relative_x = mouse_x - panel_x;
        let relative_y = mouse_y - panel_y;

        // Header area (first 2 lines)
        if relative_y < 2 {
            // Close button in top-right corner
            if relative_x >= panel_width.saturating_sub(3) {
                return Some(AIPanelHitTest {
                    item: AIPanelUIItem::CloseButton,
                    x: relative_x,
                    y: relative_y,
                });
            }
            return Some(AIPanelHitTest {
                item: AIPanelUIItem::Header,
                x: relative_x,
                y: relative_y,
            });
        }

        // Input area (last 3 lines)
        let input_start = panel_height.saturating_sub(3);
        if relative_y >= input_start {
            // Send button on right side of input line
            if relative_y == input_start + 1 && relative_x >= panel_width.saturating_sub(6) {
                return Some(AIPanelHitTest {
                    item: AIPanelUIItem::SendButton,
                    x: relative_x,
                    y: relative_y - input_start,
                });
            }
            return Some(AIPanelHitTest {
                item: AIPanelUIItem::InputField,
                x: relative_x,
                y: relative_y - input_start,
            });
        }

        // Chat area
        Some(AIPanelHitTest {
            item: AIPanelUIItem::ChatArea,
            x: relative_x,
            y: relative_y - 2,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai::AIConfig;

    #[test]
    fn test_wrap_text() {
        let widget = AIPanelWidget::new();

        let lines = widget.wrap_text("Hello world this is a test", 10);
        assert_eq!(lines, vec!["Hello", "world this", "is a test"]);

        let lines = widget.wrap_text("Short", 20);
        assert_eq!(lines, vec!["Short"]);

        let lines = widget.wrap_text("Superlongwordthatneedstobesplit", 10);
        assert!(lines.len() > 1);
    }

    #[test]
    fn test_scroll() {
        let mut widget = AIPanelWidget::new();
        widget.max_scroll = 10;

        widget.scroll_down(5);
        assert_eq!(widget.scroll_offset, 5);

        widget.scroll_down(10);
        assert_eq!(widget.scroll_offset, 10); // Capped at max

        widget.scroll_up(3);
        assert_eq!(widget.scroll_offset, 7);

        widget.scroll_to_bottom();
        assert_eq!(widget.scroll_offset, 10);
    }

    #[test]
    fn test_render_empty_panel() {
        let mut widget = AIPanelWidget::new();
        let panel = AIPanel::new(AIConfig::default());

        let lines = widget.render(&panel, 40, 20);
        assert!(lines.is_empty()); // Panel is hidden by default
    }

    #[test]
    fn test_render_visible_panel() {
        let mut widget = AIPanelWidget::new();
        let mut panel = AIPanel::new(AIConfig::default());
        panel.toggle(); // Make visible

        let lines = widget.render(&panel, 40, 20);
        assert!(!lines.is_empty());
        assert_eq!(lines.len(), 20);
    }

    #[test]
    fn test_hit_test() {
        let widget = AIPanelWidget::new();
        let panel = AIPanel::new(AIConfig::default());

        // Hit test in header
        let hit = widget.hit_test(&panel, 0, 0, 40, 20, 5, 0);
        assert!(matches!(hit.unwrap().item, AIPanelUIItem::Header));

        // Hit test in chat area
        let hit = widget.hit_test(&panel, 0, 0, 40, 20, 5, 5);
        assert!(matches!(hit.unwrap().item, AIPanelUIItem::ChatArea));

        // Hit test in input area
        let hit = widget.hit_test(&panel, 0, 0, 40, 20, 5, 18);
        assert!(matches!(hit.unwrap().item, AIPanelUIItem::InputField));

        // Hit test outside panel
        let hit = widget.hit_test(&panel, 0, 0, 40, 20, 50, 10);
        assert!(hit.is_none());
    }
}
