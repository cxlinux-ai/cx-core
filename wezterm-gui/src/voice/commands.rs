//! Voice Command Handling
//!
//! Parses transcribed text into terminal commands and AI queries.

use std::collections::HashMap;

/// Voice command types
#[derive(Debug, Clone)]
pub enum VoiceCommand {
    /// Execute a shell command
    Execute(String),

    /// Ask AI to explain something
    Explain(String),

    /// Ask AI to fix an error
    Fix(String),

    /// Ask AI to suggest commands
    Suggest(String),

    /// Route to a specific agent
    Agent { name: String, query: String },

    /// Toggle AI panel
    ToggleAI,

    /// Clear terminal
    Clear,

    /// Cancel current operation
    Cancel,

    /// Show help
    Help,

    /// Unknown command
    Unknown(String),
}

impl VoiceCommand {
    /// Get a description of this command
    pub fn description(&self) -> String {
        match self {
            VoiceCommand::Execute(cmd) => format!("Execute: {}", cmd),
            VoiceCommand::Explain(topic) => format!("Explain: {}", topic),
            VoiceCommand::Fix(error) => format!("Fix: {}", error),
            VoiceCommand::Suggest(task) => format!("Suggest: {}", task),
            VoiceCommand::Agent { name, query } => format!("Agent {}: {}", name, query),
            VoiceCommand::ToggleAI => "Toggle AI panel".to_string(),
            VoiceCommand::Clear => "Clear terminal".to_string(),
            VoiceCommand::Cancel => "Cancel operation".to_string(),
            VoiceCommand::Help => "Show help".to_string(),
            VoiceCommand::Unknown(text) => format!("Unknown: {}", text),
        }
    }

    /// Check if this command requires AI
    pub fn requires_ai(&self) -> bool {
        matches!(
            self,
            VoiceCommand::Explain(_)
                | VoiceCommand::Fix(_)
                | VoiceCommand::Suggest(_)
                | VoiceCommand::Agent { .. }
        )
    }
}

/// Result of executing a voice command
#[derive(Debug, Clone)]
pub struct VoiceCommandResult {
    /// Whether the command was successful
    pub success: bool,

    /// Output message
    pub message: String,

    /// Command to execute (if any)
    pub command: Option<String>,

    /// Response from AI (if any)
    pub ai_response: Option<String>,
}

impl VoiceCommandResult {
    pub fn success(message: impl Into<String>) -> Self {
        Self {
            success: true,
            message: message.into(),
            command: None,
            ai_response: None,
        }
    }

    pub fn with_command(mut self, command: impl Into<String>) -> Self {
        self.command = Some(command.into());
        self
    }

    pub fn with_ai_response(mut self, response: impl Into<String>) -> Self {
        self.ai_response = Some(response.into());
        self
    }

    pub fn failure(message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
            command: None,
            ai_response: None,
        }
    }
}

/// Voice command handler
///
/// Parses transcribed text and routes to appropriate handlers.
pub struct VoiceCommandHandler {
    /// Command aliases
    aliases: HashMap<String, String>,

    /// Trigger phrases for different actions
    triggers: CommandTriggers,

    /// Agent name patterns
    agent_patterns: Vec<(String, String)>, // (pattern, agent_name)
}

/// Trigger phrases for command parsing
struct CommandTriggers {
    /// Phrases that trigger command execution
    execute: Vec<&'static str>,

    /// Phrases that trigger AI explanation
    explain: Vec<&'static str>,

    /// Phrases that trigger AI fix suggestions
    fix: Vec<&'static str>,

    /// Phrases that trigger AI suggestions
    suggest: Vec<&'static str>,

    /// Phrases that clear the terminal
    clear: Vec<&'static str>,

    /// Phrases that cancel operations
    cancel: Vec<&'static str>,

    /// Phrases that show help
    help: Vec<&'static str>,

    /// Phrases that toggle AI
    toggle_ai: Vec<&'static str>,
}

impl Default for CommandTriggers {
    fn default() -> Self {
        Self {
            execute: vec![
                "run",
                "execute",
                "do",
                "perform",
                "launch",
                "start",
                "open",
                "show",
                "list",
                "get",
                "check",
            ],
            explain: vec![
                "explain",
                "what is",
                "what does",
                "how does",
                "tell me about",
                "describe",
                "help me understand",
            ],
            fix: vec![
                "fix",
                "solve",
                "resolve",
                "repair",
                "correct",
                "debug",
                "troubleshoot",
            ],
            suggest: vec![
                "suggest",
                "recommend",
                "how do i",
                "how can i",
                "what command",
                "help me",
            ],
            clear: vec!["clear", "clean", "reset screen"],
            cancel: vec!["cancel", "stop", "abort", "nevermind", "never mind"],
            help: vec!["help", "commands", "what can you do"],
            toggle_ai: vec!["toggle ai", "show ai", "hide ai", "ai panel"],
        }
    }
}

impl VoiceCommandHandler {
    /// Create a new voice command handler
    pub fn new() -> Self {
        let mut aliases = HashMap::new();

        // Common command aliases
        aliases.insert("status".to_string(), "git status".to_string());
        aliases.insert("containers".to_string(), "docker ps".to_string());
        aliases.insert("processes".to_string(), "ps aux".to_string());
        aliases.insert("disk usage".to_string(), "df -h".to_string());
        aliases.insert("memory".to_string(), "free -h".to_string());
        aliases.insert("network".to_string(), "ip addr".to_string());

        // Agent patterns
        let agent_patterns = vec![
            ("docker".to_string(), "docker".to_string()),
            ("container".to_string(), "docker".to_string()),
            ("git".to_string(), "git".to_string()),
            ("repository".to_string(), "git".to_string()),
            ("file".to_string(), "file".to_string()),
            ("folder".to_string(), "file".to_string()),
            ("directory".to_string(), "file".to_string()),
            ("package".to_string(), "package".to_string()),
            ("install".to_string(), "package".to_string()),
            ("system".to_string(), "system".to_string()),
            ("service".to_string(), "system".to_string()),
        ];

        Self {
            aliases,
            triggers: CommandTriggers::default(),
            agent_patterns,
        }
    }

    /// Parse transcribed text into a voice command
    pub fn parse(&self, text: &str) -> Option<VoiceCommand> {
        let text = text.trim().to_lowercase();

        if text.is_empty() {
            return None;
        }

        // Check for cancel/help first
        if self.matches_any(&text, &self.triggers.cancel) {
            return Some(VoiceCommand::Cancel);
        }

        if self.matches_any(&text, &self.triggers.help) {
            return Some(VoiceCommand::Help);
        }

        if self.matches_any(&text, &self.triggers.clear) {
            return Some(VoiceCommand::Clear);
        }

        if self.matches_any(&text, &self.triggers.toggle_ai) {
            return Some(VoiceCommand::ToggleAI);
        }

        // Check for AI actions
        if let Some(topic) = self.extract_after_trigger(&text, &self.triggers.explain) {
            return Some(VoiceCommand::Explain(topic));
        }

        if let Some(error) = self.extract_after_trigger(&text, &self.triggers.fix) {
            return Some(VoiceCommand::Fix(error));
        }

        if let Some(task) = self.extract_after_trigger(&text, &self.triggers.suggest) {
            return Some(VoiceCommand::Suggest(task));
        }

        // Check for agent routing
        if let Some((agent, query)) = self.extract_agent(&text) {
            return Some(VoiceCommand::Agent {
                name: agent,
                query,
            });
        }

        // Check for direct command execution
        if let Some(cmd) = self.extract_after_trigger(&text, &self.triggers.execute) {
            // Check aliases
            let resolved = self.aliases.get(&cmd).cloned().unwrap_or(cmd);
            return Some(VoiceCommand::Execute(resolved));
        }

        // Check if it looks like a direct command
        if self.looks_like_command(&text) {
            let resolved = self
                .aliases
                .get(&text)
                .cloned()
                .unwrap_or_else(|| text.clone());
            return Some(VoiceCommand::Execute(resolved));
        }

        // Unknown - could be a query
        Some(VoiceCommand::Unknown(text))
    }

    /// Check if text matches any trigger phrase
    fn matches_any(&self, text: &str, triggers: &[&str]) -> bool {
        triggers.iter().any(|&t| text.contains(t))
    }

    /// Extract content after a trigger phrase
    fn extract_after_trigger(&self, text: &str, triggers: &[&str]) -> Option<String> {
        for trigger in triggers {
            if let Some(pos) = text.find(trigger) {
                let after = text[pos + trigger.len()..].trim();
                if !after.is_empty() {
                    return Some(after.to_string());
                }
            }
        }
        None
    }

    /// Extract agent name and query from text
    fn extract_agent(&self, text: &str) -> Option<(String, String)> {
        for (pattern, agent_name) in &self.agent_patterns {
            if text.contains(pattern) {
                // Remove the pattern from the text to get the query
                let query = text.replace(pattern, "").trim().to_string();
                if !query.is_empty() {
                    return Some((agent_name.clone(), query));
                }
            }
        }
        None
    }

    /// Check if text looks like a shell command
    fn looks_like_command(&self, text: &str) -> bool {
        // Common command prefixes
        let command_prefixes = [
            "ls", "cd", "pwd", "cat", "grep", "find", "mkdir", "rm", "cp", "mv", "chmod", "chown",
            "sudo", "apt", "dnf", "pacman", "npm", "yarn", "pip", "git", "docker", "kubectl",
            "curl", "wget", "ssh", "scp", "tar", "unzip", "vim", "nano", "less", "more", "head",
            "tail", "sort", "uniq", "wc", "awk", "sed", "ps", "kill", "top", "htop", "df", "du",
            "free", "uptime", "who", "whoami", "hostname", "uname", "date", "cal", "echo",
            "export", "source", "which", "whereis", "man", "info", "history", "alias", "clear",
        ];

        let first_word = text.split_whitespace().next().unwrap_or("");
        command_prefixes.contains(&first_word)
    }

    /// Execute a voice command
    pub fn execute(&self, command: &VoiceCommand) -> VoiceCommandResult {
        match command {
            VoiceCommand::Execute(cmd) => VoiceCommandResult::success("Command ready to execute")
                .with_command(cmd.clone()),

            VoiceCommand::Explain(topic) => {
                VoiceCommandResult::success(format!("Explaining: {}", topic))
            }

            VoiceCommand::Fix(error) => {
                VoiceCommandResult::success(format!("Analyzing error: {}", error))
            }

            VoiceCommand::Suggest(task) => {
                VoiceCommandResult::success(format!("Finding suggestions for: {}", task))
            }

            VoiceCommand::Agent { name, query } => VoiceCommandResult::success(format!(
                "Routing to {} agent: {}",
                name, query
            )),

            VoiceCommand::ToggleAI => VoiceCommandResult::success("Toggling AI panel"),

            VoiceCommand::Clear => {
                VoiceCommandResult::success("Clearing terminal").with_command("clear")
            }

            VoiceCommand::Cancel => VoiceCommandResult::success("Operation cancelled"),

            VoiceCommand::Help => VoiceCommandResult::success(
                "Voice commands:\n\
                 - 'run <command>' - Execute a shell command\n\
                 - 'explain <topic>' - Get AI explanation\n\
                 - 'fix <error>' - Get help fixing an error\n\
                 - 'suggest <task>' - Get command suggestions\n\
                 - 'docker/git/file <query>' - Use specific agent\n\
                 - 'clear' - Clear the terminal\n\
                 - 'cancel' - Cancel current operation\n\
                 - 'help' - Show this help",
            ),

            VoiceCommand::Unknown(text) => VoiceCommandResult::failure(format!(
                "Unknown command: '{}'. Say 'help' for available commands.",
                text
            )),
        }
    }

    /// Add a command alias
    pub fn add_alias(&mut self, alias: String, command: String) {
        self.aliases.insert(alias, command);
    }

    /// Remove a command alias
    pub fn remove_alias(&mut self, alias: &str) {
        self.aliases.remove(alias);
    }

    /// Get all aliases
    pub fn aliases(&self) -> &HashMap<String, String> {
        &self.aliases
    }
}

impl Default for VoiceCommandHandler {
    fn default() -> Self {
        Self::new()
    }
}

/// Natural language to command converter
///
/// Uses pattern matching and heuristics to convert natural language
/// descriptions into shell commands.
pub struct NaturalLanguageConverter {
    /// Known command patterns
    patterns: Vec<CommandPattern>,
}

/// A pattern for converting natural language to commands
struct CommandPattern {
    /// Keywords that trigger this pattern
    keywords: Vec<&'static str>,

    /// The command template
    template: &'static str,

    /// Argument extraction pattern
    arg_pattern: Option<&'static str>,
}

impl NaturalLanguageConverter {
    /// Create a new converter with default patterns
    pub fn new() -> Self {
        let patterns = vec![
            CommandPattern {
                keywords: vec!["list", "show", "files", "directory"],
                template: "ls -la",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["find", "search", "file"],
                template: "find . -name '*{}*'",
                arg_pattern: Some("for|named|called"),
            },
            CommandPattern {
                keywords: vec!["create", "make", "directory", "folder"],
                template: "mkdir -p {}",
                arg_pattern: Some("called|named"),
            },
            CommandPattern {
                keywords: vec!["delete", "remove", "file"],
                template: "rm {}",
                arg_pattern: Some("called|named"),
            },
            CommandPattern {
                keywords: vec!["copy", "file"],
                template: "cp {} {}",
                arg_pattern: Some("to"),
            },
            CommandPattern {
                keywords: vec!["move", "rename", "file"],
                template: "mv {} {}",
                arg_pattern: Some("to"),
            },
            CommandPattern {
                keywords: vec!["show", "content", "file"],
                template: "cat {}",
                arg_pattern: Some("of|in"),
            },
            CommandPattern {
                keywords: vec!["disk", "space", "usage"],
                template: "df -h",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["memory", "ram", "usage"],
                template: "free -h",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["process", "running"],
                template: "ps aux | grep {}",
                arg_pattern: Some("for|named"),
            },
            CommandPattern {
                keywords: vec!["kill", "stop", "process"],
                template: "kill {}",
                arg_pattern: Some("process|pid"),
            },
            CommandPattern {
                keywords: vec!["git", "status"],
                template: "git status",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["git", "commit"],
                template: "git commit -m '{}'",
                arg_pattern: Some("message|with"),
            },
            CommandPattern {
                keywords: vec!["git", "push"],
                template: "git push",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["git", "pull"],
                template: "git pull",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["docker", "containers", "running"],
                template: "docker ps",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["docker", "images"],
                template: "docker images",
                arg_pattern: None,
            },
            CommandPattern {
                keywords: vec!["docker", "stop", "container"],
                template: "docker stop {}",
                arg_pattern: Some("named|called"),
            },
        ];

        Self { patterns }
    }

    /// Convert natural language to a command
    pub fn convert(&self, text: &str) -> Option<String> {
        let text_lower = text.to_lowercase();
        let words: Vec<&str> = text_lower.split_whitespace().collect();

        // Find best matching pattern
        let mut best_match: Option<(&CommandPattern, usize)> = None;

        for pattern in &self.patterns {
            let matches = pattern
                .keywords
                .iter()
                .filter(|&&kw| words.contains(&kw))
                .count();

            if matches > 0 {
                if let Some((_, best_count)) = best_match {
                    if matches > best_count {
                        best_match = Some((pattern, matches));
                    }
                } else {
                    best_match = Some((pattern, matches));
                }
            }
        }

        best_match.map(|(pattern, _)| {
            if pattern.template.contains("{}") {
                // Extract arguments if template has placeholders
                if let Some(_arg_pattern) = pattern.arg_pattern {
                    // Simple extraction - get the last word(s) after keywords
                    let arg = text_lower
                        .split_whitespace()
                        .last()
                        .unwrap_or("")
                        .to_string();
                    pattern.template.replacen("{}", &arg, 1)
                } else {
                    pattern.template.to_string()
                }
            } else {
                pattern.template.to_string()
            }
        })
    }
}

impl Default for NaturalLanguageConverter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_execute() {
        let handler = VoiceCommandHandler::new();

        if let Some(VoiceCommand::Execute(cmd)) = handler.parse("run git status") {
            assert_eq!(cmd, "git status");
        } else {
            panic!("Expected Execute command");
        }
    }

    #[test]
    fn test_parse_explain() {
        let handler = VoiceCommandHandler::new();

        if let Some(VoiceCommand::Explain(topic)) = handler.parse("explain this error") {
            assert_eq!(topic, "this error");
        } else {
            panic!("Expected Explain command");
        }
    }

    #[test]
    fn test_parse_agent() {
        let handler = VoiceCommandHandler::new();

        if let Some(VoiceCommand::Agent { name, query }) =
            handler.parse("docker list all containers")
        {
            assert_eq!(name, "docker");
            assert!(query.contains("list"));
        } else {
            panic!("Expected Agent command");
        }
    }

    #[test]
    fn test_parse_clear() {
        let handler = VoiceCommandHandler::new();

        if let Some(VoiceCommand::Clear) = handler.parse("clear") {
            // OK
        } else {
            panic!("Expected Clear command");
        }
    }

    #[test]
    fn test_nl_converter() {
        let converter = NaturalLanguageConverter::new();

        let cmd = converter.convert("show git status");
        assert_eq!(cmd, Some("git status".to_string()));

        let cmd = converter.convert("show disk usage");
        assert_eq!(cmd, Some("df -h".to_string()));
    }

    #[test]
    fn test_command_result() {
        let result = VoiceCommandResult::success("test").with_command("ls -la");

        assert!(result.success);
        assert_eq!(result.command, Some("ls -la".to_string()));
    }
}
