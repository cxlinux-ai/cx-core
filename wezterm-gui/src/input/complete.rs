//! Command and path completion for the modern input
//!
//! Provides auto-completion for:
//! - Commands from PATH
//! - File and directory paths
//! - History-based suggestions
//! - Shell builtins

use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

/// Maximum number of completions to return
const MAX_COMPLETIONS: usize = 20;

/// Completer for commands and paths
#[derive(Debug, Clone)]
pub struct Completer {
    /// Cached commands from PATH
    path_commands: Vec<String>,
    /// Shell builtins
    builtins: Vec<String>,
    /// History entries for suggestions
    history: Vec<String>,
    /// Whether PATH cache is valid
    cache_valid: bool,
}

impl Default for Completer {
    fn default() -> Self {
        Self::new()
    }
}

impl Completer {
    /// Create a new completer
    pub fn new() -> Self {
        let builtins = vec![
            "alias", "bg", "bind", "break", "builtin", "caller", "cd", "command",
            "compgen", "complete", "compopt", "continue", "declare", "dirs",
            "disown", "echo", "enable", "eval", "exec", "exit", "export", "false",
            "fc", "fg", "getopts", "hash", "help", "history", "jobs", "kill",
            "let", "local", "logout", "mapfile", "popd", "printf", "pushd", "pwd",
            "read", "readarray", "readonly", "return", "set", "shift", "shopt",
            "source", "suspend", "test", "times", "trap", "true", "type",
            "typeset", "ulimit", "umask", "unalias", "unset", "wait",
        ]
        .into_iter()
        .map(String::from)
        .collect();

        Self {
            path_commands: Vec::new(),
            builtins,
            history: Vec::new(),
            cache_valid: false,
        }
    }

    /// Complete the input at the given cursor position
    pub fn complete(&self, text: &str, cursor_pos: usize) -> Vec<String> {
        let text_before_cursor = &text[..cursor_pos.min(text.len())];

        // Find the word being typed
        let word_start = text_before_cursor
            .rfind(|c: char| c.is_whitespace() || c == '|' || c == ';' || c == '&')
            .map(|i| i + 1)
            .unwrap_or(0);

        let word = &text_before_cursor[word_start..];

        // Determine if this is the first word (command) or an argument
        let is_command = self.is_command_position(text_before_cursor, word_start);

        if is_command {
            self.complete_command(word)
        } else if word.starts_with('~') || word.starts_with('/') || word.starts_with('.') || word.contains('/') {
            self.complete_path(word)
        } else if word.starts_with('$') {
            self.complete_variable(word)
        } else {
            // Could be either path or argument, try path first
            let mut completions = self.complete_path(word);
            if completions.is_empty() {
                // Fall back to history-based completion
                completions = self.complete_from_history(word);
            }
            completions
        }
    }

    /// Check if we're in a command position
    fn is_command_position(&self, text: &str, word_start: usize) -> bool {
        if word_start == 0 {
            return true;
        }

        // Check what's before the word
        let before_word = text[..word_start].trim_end();
        if before_word.is_empty() {
            return true;
        }

        // After pipe, semicolon, or && || we're in command position
        let last_char = before_word.chars().last();
        matches!(last_char, Some('|') | Some(';') | Some('&'))
    }

    /// Complete a command name
    fn complete_command(&self, prefix: &str) -> Vec<String> {
        let mut completions = HashSet::new();

        // Add matching builtins
        for builtin in &self.builtins {
            if builtin.starts_with(prefix) {
                completions.insert(builtin.clone());
            }
        }

        // Add matching PATH commands
        for cmd in &self.path_commands {
            if cmd.starts_with(prefix) {
                completions.insert(cmd.clone());
            }
        }

        // If cache is empty, scan PATH on demand
        if self.path_commands.is_empty() {
            for cmd in Self::scan_path_commands() {
                if cmd.starts_with(prefix) {
                    completions.insert(cmd);
                }
            }
        }

        // Sort and limit
        let mut result: Vec<_> = completions.into_iter().collect();
        result.sort();
        result.truncate(MAX_COMPLETIONS);
        result
    }

    /// Complete a file path
    fn complete_path(&self, prefix: &str) -> Vec<String> {
        let expanded = self.expand_tilde(prefix);
        let path = Path::new(&expanded);

        let (dir, file_prefix) = if expanded.ends_with('/') || expanded.ends_with('\\') {
            (PathBuf::from(&expanded), "")
        } else if let Some(parent) = path.parent() {
            let file_name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
            (parent.to_path_buf(), file_name)
        } else {
            (PathBuf::from("."), &*expanded)
        };

        let mut completions = Vec::new();

        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.filter_map(Result::ok) {
                let file_name = entry.file_name();
                let name = file_name.to_string_lossy();

                if name.starts_with(file_prefix) {
                    let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);

                    // Build the completion string
                    let completion = if prefix.starts_with('~') {
                        // Keep the ~ prefix
                        let home = dirs_next::home_dir().map(|h| h.to_string_lossy().to_string())
                            .unwrap_or_default();
                        let full_path = dir.join(&*name);
                        let full_str = full_path.to_string_lossy();
                        if full_str.starts_with(&home) {
                            format!("~{}", &full_str[home.len()..])
                        } else {
                            name.to_string()
                        }
                    } else if prefix.contains('/') {
                        // Keep the directory prefix
                        let parent_str = if dir.to_string_lossy() == "." {
                            String::new()
                        } else {
                            format!("{}/", dir.display())
                        };
                        format!("{}{}", parent_str, name)
                    } else {
                        name.to_string()
                    };

                    // Add trailing slash for directories
                    let completion = if is_dir && !completion.ends_with('/') {
                        format!("{}/", completion)
                    } else {
                        completion
                    };

                    completions.push(completion);
                }
            }
        }

        completions.sort();
        completions.truncate(MAX_COMPLETIONS);
        completions
    }

    /// Complete an environment variable
    fn complete_variable(&self, prefix: &str) -> Vec<String> {
        let var_prefix = prefix.trim_start_matches('$').trim_start_matches('{');
        let is_braced = prefix.starts_with("${");

        let mut completions = Vec::new();

        for (key, _) in env::vars() {
            if key.starts_with(var_prefix) {
                let completion = if is_braced {
                    format!("${{{}}}", key)
                } else {
                    format!("${}", key)
                };
                completions.push(completion);
            }
        }

        completions.sort();
        completions.truncate(MAX_COMPLETIONS);
        completions
    }

    /// Complete from history
    fn complete_from_history(&self, prefix: &str) -> Vec<String> {
        let mut completions = Vec::new();
        let mut seen = HashSet::new();

        for entry in self.history.iter().rev() {
            // Find words in history that match
            for word in entry.split_whitespace() {
                if word.starts_with(prefix) && seen.insert(word.to_string()) {
                    completions.push(word.to_string());
                    if completions.len() >= MAX_COMPLETIONS {
                        return completions;
                    }
                }
            }
        }

        completions
    }

    /// Expand ~ to home directory
    fn expand_tilde(&self, path: &str) -> String {
        if path.starts_with('~') {
            if let Some(home) = dirs_next::home_dir() {
                if path == "~" {
                    return home.to_string_lossy().to_string();
                } else if path.starts_with("~/") {
                    return format!("{}{}", home.display(), &path[1..]);
                }
                // ~user format not supported for now
            }
        }
        path.to_string()
    }

    /// Scan PATH for available commands
    fn scan_path_commands() -> Vec<String> {
        let mut commands = HashSet::new();

        if let Ok(path) = env::var("PATH") {
            for dir in env::split_paths(&path) {
                if let Ok(entries) = fs::read_dir(&dir) {
                    for entry in entries.filter_map(Result::ok) {
                        if let Ok(file_type) = entry.file_type() {
                            if file_type.is_file() || file_type.is_symlink() {
                                // Check if executable (on Unix)
                                #[cfg(unix)]
                                {
                                    use std::os::unix::fs::PermissionsExt;
                                    if let Ok(metadata) = entry.metadata() {
                                        let mode = metadata.permissions().mode();
                                        if mode & 0o111 == 0 {
                                            continue; // Not executable
                                        }
                                    }
                                }

                                if let Some(name) = entry.file_name().to_str() {
                                    commands.insert(name.to_string());
                                }
                            }
                        }
                    }
                }
            }
        }

        commands.into_iter().collect()
    }

    /// Refresh the PATH commands cache
    pub fn refresh_cache(&mut self) {
        self.path_commands = Self::scan_path_commands();
        self.cache_valid = true;
    }

    /// Add history entries for completion
    pub fn add_history(&mut self, entries: &[String]) {
        self.history = entries.to_vec();
    }

    /// Add a single history entry
    pub fn add_history_entry(&mut self, entry: String) {
        self.history.push(entry);
        // Keep reasonable size
        if self.history.len() > 1000 {
            self.history.remove(0);
        }
    }

    /// Check if a completion is a directory
    pub fn is_directory(&self, completion: &str) -> bool {
        completion.ends_with('/')
    }

    /// Get completion for a specific index
    pub fn get_completion(&self, text: &str, cursor_pos: usize, index: usize) -> Option<String> {
        let completions = self.complete(text, cursor_pos);
        completions.get(index).cloned()
    }
}

/// Information about a completion
#[derive(Debug, Clone)]
pub struct CompletionInfo {
    /// The completion text
    pub text: String,
    /// Description (e.g., for commands, the type)
    pub description: Option<String>,
    /// Whether this is a directory
    pub is_directory: bool,
    /// The type of completion
    pub kind: CompletionKind,
}

/// Type of completion
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompletionKind {
    /// Command from PATH
    Command,
    /// Shell builtin
    Builtin,
    /// File path
    File,
    /// Directory path
    Directory,
    /// Environment variable
    Variable,
    /// From history
    History,
}

impl Completer {
    /// Get detailed completions with metadata
    pub fn complete_with_info(&self, text: &str, cursor_pos: usize) -> Vec<CompletionInfo> {
        let text_before_cursor = &text[..cursor_pos.min(text.len())];

        let word_start = text_before_cursor
            .rfind(|c: char| c.is_whitespace() || c == '|' || c == ';' || c == '&')
            .map(|i| i + 1)
            .unwrap_or(0);

        let word = &text_before_cursor[word_start..];
        let is_command = self.is_command_position(text_before_cursor, word_start);

        if is_command {
            self.complete_command_with_info(word)
        } else if word.starts_with('$') {
            self.complete_variable_with_info(word)
        } else {
            self.complete_path_with_info(word)
        }
    }

    fn complete_command_with_info(&self, prefix: &str) -> Vec<CompletionInfo> {
        let mut completions = Vec::new();

        // Add builtins
        for builtin in &self.builtins {
            if builtin.starts_with(prefix) {
                completions.push(CompletionInfo {
                    text: builtin.clone(),
                    description: Some("builtin".to_string()),
                    is_directory: false,
                    kind: CompletionKind::Builtin,
                });
            }
        }

        // Add PATH commands
        for cmd in &self.path_commands {
            if cmd.starts_with(prefix) {
                completions.push(CompletionInfo {
                    text: cmd.clone(),
                    description: Some("command".to_string()),
                    is_directory: false,
                    kind: CompletionKind::Command,
                });
            }
        }

        completions.sort_by(|a, b| a.text.cmp(&b.text));
        completions.truncate(MAX_COMPLETIONS);
        completions
    }

    fn complete_path_with_info(&self, prefix: &str) -> Vec<CompletionInfo> {
        let expanded = self.expand_tilde(prefix);
        let path = Path::new(&expanded);

        let (dir, file_prefix) = if expanded.ends_with('/') || expanded.ends_with('\\') {
            (PathBuf::from(&expanded), "")
        } else if let Some(parent) = path.parent() {
            let file_name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
            (parent.to_path_buf(), file_name)
        } else {
            (PathBuf::from("."), &*expanded)
        };

        let mut completions = Vec::new();

        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.filter_map(Result::ok) {
                let file_name = entry.file_name();
                let name = file_name.to_string_lossy();

                if name.starts_with(file_prefix) {
                    let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);

                    let completion = if prefix.contains('/') {
                        let parent_str = if dir.to_string_lossy() == "." {
                            String::new()
                        } else {
                            format!("{}/", dir.display())
                        };
                        format!("{}{}", parent_str, name)
                    } else {
                        name.to_string()
                    };

                    let completion = if is_dir && !completion.ends_with('/') {
                        format!("{}/", completion)
                    } else {
                        completion
                    };

                    completions.push(CompletionInfo {
                        text: completion,
                        description: None,
                        is_directory: is_dir,
                        kind: if is_dir {
                            CompletionKind::Directory
                        } else {
                            CompletionKind::File
                        },
                    });
                }
            }
        }

        completions.sort_by(|a, b| {
            // Directories first, then alphabetically
            match (a.is_directory, b.is_directory) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => a.text.cmp(&b.text),
            }
        });
        completions.truncate(MAX_COMPLETIONS);
        completions
    }

    fn complete_variable_with_info(&self, prefix: &str) -> Vec<CompletionInfo> {
        let var_prefix = prefix.trim_start_matches('$').trim_start_matches('{');
        let is_braced = prefix.starts_with("${");

        let mut completions = Vec::new();

        for (key, value) in env::vars() {
            if key.starts_with(var_prefix) {
                let text = if is_braced {
                    format!("${{{}}}", key)
                } else {
                    format!("${}", key)
                };

                // Truncate value for description
                let desc = if value.len() > 30 {
                    format!("{}...", &value[..27])
                } else {
                    value
                };

                completions.push(CompletionInfo {
                    text,
                    description: Some(desc),
                    is_directory: false,
                    kind: CompletionKind::Variable,
                });
            }
        }

        completions.sort_by(|a, b| a.text.cmp(&b.text));
        completions.truncate(MAX_COMPLETIONS);
        completions
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_command_completion() {
        let mut completer = Completer::new();
        completer.path_commands = vec![
            "ls".to_string(),
            "lsof".to_string(),
            "grep".to_string(),
        ];

        let completions = completer.complete("l", 1);
        assert!(completions.contains(&"ls".to_string()));
        assert!(completions.contains(&"lsof".to_string()));
        assert!(!completions.contains(&"grep".to_string()));
    }

    #[test]
    fn test_path_completion() {
        let completer = Completer::new();
        let completions = completer.complete("/", 1);
        // Should return directories in /
        assert!(!completions.is_empty());
    }

    #[test]
    fn test_variable_completion() {
        let completer = Completer::new();
        let completions = completer.complete("$HO", 3);
        assert!(completions.iter().any(|c| c.contains("HOME")));
    }

    #[test]
    fn test_builtin_completion() {
        let completer = Completer::new();
        let completions = completer.complete("cd", 2);
        assert!(completions.contains(&"cd".to_string()));
    }
}
