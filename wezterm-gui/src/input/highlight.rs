//! Shell syntax highlighting for the modern input
//!
//! Provides syntax highlighting for shell commands with support for:
//! - Commands (green)
//! - Arguments (default)
//! - Flags (cyan)
//! - Strings (yellow)
//! - Paths (blue)
//! - Variables (magenta)
//! - Comments (gray)
//! - Operators (white)

use std::ops::Range;

/// A highlighted span of text
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HighlightedSpan {
    /// The text content
    pub text: String,
    /// The byte range in the original text
    pub range: Range<usize>,
    /// The highlight style
    pub style: HighlightStyle,
}

impl HighlightedSpan {
    /// Create a default (unstyled) text span
    pub fn default_text(text: &str) -> Self {
        Self {
            text: text.to_string(),
            range: 0..text.len(),
            style: HighlightStyle::Default,
        }
    }
}

/// Style for highlighted text
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum HighlightStyle {
    /// Default text color
    #[default]
    Default,
    /// Command (executable) - green
    Command,
    /// Argument - default color
    Argument,
    /// Flag (--flag or -f) - cyan
    Flag,
    /// String literal - yellow
    String,
    /// Path - blue
    Path,
    /// Variable ($VAR) - magenta
    Variable,
    /// Comment (# ...) - gray
    Comment,
    /// Operator (|, >, <, &&, ||, ;) - white/bold
    Operator,
    /// Error/invalid - red
    Error,
    /// Keyword (if, then, else, fi, etc.) - purple
    Keyword,
}

/// Token type for lexing
#[derive(Debug, Clone, PartialEq, Eq)]
enum TokenType {
    Word,
    Flag,
    String(char), // char is the quote character
    Variable,
    Comment,
    Operator,
    Whitespace,
    Path,
}

/// A token from the lexer
#[derive(Debug, Clone)]
struct Token {
    text: String,
    range: Range<usize>,
    token_type: TokenType,
}

/// Shell keywords
const KEYWORDS: &[&str] = &[
    "if", "then", "else", "elif", "fi",
    "case", "esac", "for", "in", "do", "done",
    "while", "until", "function", "select",
    "time", "coproc", "return", "exit",
    "break", "continue", "local", "export",
    "declare", "typeset", "readonly", "unset",
];

/// Common command names (partial list for highlighting first command)
const COMMON_COMMANDS: &[&str] = &[
    "ls", "cd", "pwd", "mkdir", "rmdir", "rm", "cp", "mv",
    "cat", "less", "more", "head", "tail", "grep", "find",
    "echo", "printf", "read", "source", ".", "exec",
    "git", "docker", "npm", "cargo", "python", "node",
    "sudo", "su", "ssh", "scp", "rsync",
    "vim", "nano", "emacs", "code",
    "make", "cmake", "gcc", "clang",
    "curl", "wget", "ping", "nc", "telnet",
    "ps", "top", "htop", "kill", "killall",
    "tar", "gzip", "gunzip", "zip", "unzip",
    "chmod", "chown", "chgrp",
    "apt", "yum", "dnf", "pacman", "brew",
    "systemctl", "service", "journalctl",
];

/// Syntax highlighter for shell commands
#[derive(Debug, Clone, Default)]
pub struct SyntaxHighlighter {
    /// Cache of PATH executables (for command highlighting)
    cached_commands: Vec<String>,
}

impl SyntaxHighlighter {
    /// Create a new syntax highlighter
    pub fn new() -> Self {
        Self {
            cached_commands: COMMON_COMMANDS.iter().map(|s| s.to_string()).collect(),
        }
    }

    /// Highlight the given text
    pub fn highlight(&self, text: &str) -> Vec<HighlightedSpan> {
        if text.is_empty() {
            return vec![];
        }

        let tokens = self.tokenize(text);
        self.style_tokens(&tokens)
    }

    /// Tokenize the input text
    fn tokenize(&self, text: &str) -> Vec<Token> {
        let mut tokens = Vec::new();
        let chars: Vec<char> = text.chars().collect();
        let mut pos = 0;
        let mut byte_pos = 0;

        while pos < chars.len() {
            let start_byte = byte_pos;
            let start_pos = pos;
            let c = chars[pos];

            match c {
                // Whitespace
                ' ' | '\t' | '\n' | '\r' => {
                    while pos < chars.len() && chars[pos].is_whitespace() {
                        byte_pos += chars[pos].len_utf8();
                        pos += 1;
                    }
                    tokens.push(Token {
                        text: chars[start_pos..pos].iter().collect(),
                        range: start_byte..byte_pos,
                        token_type: TokenType::Whitespace,
                    });
                }

                // Comment
                '#' => {
                    while pos < chars.len() && chars[pos] != '\n' {
                        byte_pos += chars[pos].len_utf8();
                        pos += 1;
                    }
                    tokens.push(Token {
                        text: chars[start_pos..pos].iter().collect(),
                        range: start_byte..byte_pos,
                        token_type: TokenType::Comment,
                    });
                }

                // String literals
                '"' | '\'' => {
                    let quote = c;
                    byte_pos += c.len_utf8();
                    pos += 1;

                    while pos < chars.len() {
                        let curr = chars[pos];
                        byte_pos += curr.len_utf8();
                        pos += 1;

                        if curr == quote {
                            break;
                        }
                        // Handle escape in double quotes
                        if quote == '"' && curr == '\\' && pos < chars.len() {
                            byte_pos += chars[pos].len_utf8();
                            pos += 1;
                        }
                    }

                    tokens.push(Token {
                        text: chars[start_pos..pos].iter().collect(),
                        range: start_byte..byte_pos,
                        token_type: TokenType::String(quote),
                    });
                }

                // Variable
                '$' => {
                    byte_pos += c.len_utf8();
                    pos += 1;

                    // Handle ${...} or $(...) or $VAR
                    if pos < chars.len() {
                        match chars[pos] {
                            '{' => {
                                byte_pos += chars[pos].len_utf8();
                                pos += 1;
                                while pos < chars.len() && chars[pos] != '}' {
                                    byte_pos += chars[pos].len_utf8();
                                    pos += 1;
                                }
                                if pos < chars.len() {
                                    byte_pos += chars[pos].len_utf8();
                                    pos += 1;
                                }
                            }
                            '(' => {
                                byte_pos += chars[pos].len_utf8();
                                pos += 1;
                                let mut depth = 1;
                                while pos < chars.len() && depth > 0 {
                                    match chars[pos] {
                                        '(' => depth += 1,
                                        ')' => depth -= 1,
                                        _ => {}
                                    }
                                    byte_pos += chars[pos].len_utf8();
                                    pos += 1;
                                }
                            }
                            _ => {
                                // Regular variable name
                                while pos < chars.len()
                                    && (chars[pos].is_alphanumeric() || chars[pos] == '_')
                                {
                                    byte_pos += chars[pos].len_utf8();
                                    pos += 1;
                                }
                            }
                        }
                    }

                    tokens.push(Token {
                        text: chars[start_pos..pos].iter().collect(),
                        range: start_byte..byte_pos,
                        token_type: TokenType::Variable,
                    });
                }

                // Operators
                '|' | '&' | ';' | '>' | '<' | '(' | ')' | '{' | '}' | '[' | ']' => {
                    byte_pos += c.len_utf8();
                    pos += 1;

                    // Handle double operators
                    if pos < chars.len() {
                        let next = chars[pos];
                        let is_double = match (c, next) {
                            ('|', '|') | ('&', '&') | ('>', '>') | ('<', '<') => true,
                            ('>', '&') | ('<', '&') | ('>', '|') => true, // Redirections
                            _ => false,
                        };
                        if is_double {
                            byte_pos += next.len_utf8();
                            pos += 1;
                        }
                    }

                    tokens.push(Token {
                        text: chars[start_pos..pos].iter().collect(),
                        range: start_byte..byte_pos,
                        token_type: TokenType::Operator,
                    });
                }

                // Flags or words
                '-' => {
                    // Could be a flag or part of a word/path
                    byte_pos += c.len_utf8();
                    pos += 1;

                    // Check if it looks like a flag
                    let is_flag = pos < chars.len()
                        && (chars[pos].is_alphanumeric() || chars[pos] == '-');

                    while pos < chars.len()
                        && !chars[pos].is_whitespace()
                        && !"\"'#$|&;><(){}[]".contains(chars[pos])
                    {
                        byte_pos += chars[pos].len_utf8();
                        pos += 1;
                    }

                    let text: String = chars[start_pos..pos].iter().collect();
                    tokens.push(Token {
                        text,
                        range: start_byte..byte_pos,
                        token_type: if is_flag {
                            TokenType::Flag
                        } else {
                            TokenType::Word
                        },
                    });
                }

                // Path or word
                '/' | '~' | '.' => {
                    // Likely a path
                    while pos < chars.len()
                        && !chars[pos].is_whitespace()
                        && !"\"'#$|&;><(){}[]".contains(chars[pos])
                    {
                        byte_pos += chars[pos].len_utf8();
                        pos += 1;
                    }

                    let text: String = chars[start_pos..pos].iter().collect();
                    let token_type = if text.contains('/') || text.starts_with('~') {
                        TokenType::Path
                    } else {
                        TokenType::Word
                    };

                    tokens.push(Token {
                        text,
                        range: start_byte..byte_pos,
                        token_type,
                    });
                }

                // Regular word
                _ => {
                    while pos < chars.len()
                        && !chars[pos].is_whitespace()
                        && !"\"'#$|&;><(){}[]".contains(chars[pos])
                    {
                        byte_pos += chars[pos].len_utf8();
                        pos += 1;
                    }

                    let text: String = chars[start_pos..pos].iter().collect();

                    // Determine if this is a path
                    let token_type = if text.contains('/') {
                        TokenType::Path
                    } else {
                        TokenType::Word
                    };

                    tokens.push(Token {
                        text,
                        range: start_byte..byte_pos,
                        token_type,
                    });
                }
            }
        }

        tokens
    }

    /// Apply styles to tokens
    fn style_tokens(&self, tokens: &[Token]) -> Vec<HighlightedSpan> {
        let mut spans = Vec::new();
        let mut is_first_word = true;
        let mut after_operator = false;

        for token in tokens {
            let style = match &token.token_type {
                TokenType::Whitespace => HighlightStyle::Default,
                TokenType::Comment => HighlightStyle::Comment,
                TokenType::String(_) => HighlightStyle::String,
                TokenType::Variable => HighlightStyle::Variable,
                TokenType::Operator => {
                    after_operator = true;
                    HighlightStyle::Operator
                }
                TokenType::Flag => HighlightStyle::Flag,
                TokenType::Path => HighlightStyle::Path,
                TokenType::Word => {
                    let word = &token.text;

                    // Check if it's a keyword
                    if KEYWORDS.contains(&word.as_str()) {
                        HighlightStyle::Keyword
                    } else if is_first_word || after_operator {
                        // First word or after operator is a command
                        is_first_word = false;
                        after_operator = false;

                        // Check if it's a known command
                        if self.is_command(word) {
                            HighlightStyle::Command
                        } else {
                            HighlightStyle::Command // Assume it's a command anyway
                        }
                    } else {
                        HighlightStyle::Argument
                    }
                }
            };

            // Update first_word tracking
            if token.token_type != TokenType::Whitespace
                && token.token_type != TokenType::Operator
            {
                is_first_word = false;
            }

            spans.push(HighlightedSpan {
                text: token.text.clone(),
                range: token.range.clone(),
                style,
            });
        }

        spans
    }

    /// Check if a word is a known command
    fn is_command(&self, word: &str) -> bool {
        self.cached_commands.iter().any(|cmd| cmd == word)
    }

    /// Refresh the cached commands from PATH
    pub fn refresh_commands(&mut self) {
        // In a full implementation, this would scan PATH directories
        // For now, we just use the common commands list
        self.cached_commands = COMMON_COMMANDS.iter().map(|s| s.to_string()).collect();
    }

    /// Add a command to the cache
    pub fn add_command(&mut self, cmd: &str) {
        if !self.cached_commands.contains(&cmd.to_string()) {
            self.cached_commands.push(cmd.to_string());
        }
    }
}

/// Convert highlight style to RGB color
impl HighlightStyle {
    /// Get RGB color for this style (r, g, b)
    pub fn to_rgb(&self) -> (u8, u8, u8) {
        match self {
            HighlightStyle::Default => (204, 204, 204),    // Light gray
            HighlightStyle::Command => (129, 199, 132),     // Green
            HighlightStyle::Argument => (204, 204, 204),    // Light gray
            HighlightStyle::Flag => (77, 208, 225),         // Cyan
            HighlightStyle::String => (255, 213, 79),       // Yellow
            HighlightStyle::Path => (100, 181, 246),        // Blue
            HighlightStyle::Variable => (206, 147, 216),    // Magenta
            HighlightStyle::Comment => (128, 128, 128),     // Gray
            HighlightStyle::Operator => (255, 255, 255),    // White
            HighlightStyle::Error => (239, 83, 80),         // Red
            HighlightStyle::Keyword => (186, 104, 200),     // Purple
        }
    }

    /// Check if this style should be bold
    pub fn is_bold(&self) -> bool {
        matches!(
            self,
            HighlightStyle::Command
                | HighlightStyle::Keyword
                | HighlightStyle::Operator
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_command() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("ls -la /tmp");

        assert!(!spans.is_empty());
        assert_eq!(spans[0].style, HighlightStyle::Command);
    }

    #[test]
    fn test_flags() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("grep --color -n pattern");

        // Find flag spans
        let flag_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::Flag)
            .collect();

        assert!(!flag_spans.is_empty());
    }

    #[test]
    fn test_string() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("echo \"hello world\"");

        let string_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::String)
            .collect();

        assert!(!string_spans.is_empty());
    }

    #[test]
    fn test_variable() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("echo $HOME ${PATH}");

        let var_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::Variable)
            .collect();

        assert_eq!(var_spans.len(), 2);
    }

    #[test]
    fn test_pipe() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("cat file | grep pattern");

        let op_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::Operator)
            .collect();

        assert!(!op_spans.is_empty());

        // Both cat and grep should be commands
        let cmd_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::Command)
            .collect();

        assert_eq!(cmd_spans.len(), 2);
    }

    #[test]
    fn test_comment() {
        let highlighter = SyntaxHighlighter::new();
        let spans = highlighter.highlight("ls # list files");

        let comment_spans: Vec<_> = spans
            .iter()
            .filter(|s| s.style == HighlightStyle::Comment)
            .collect();

        assert!(!comment_spans.is_empty());
    }
}
