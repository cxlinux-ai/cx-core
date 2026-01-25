//! User Model
//!
//! Stores learned patterns and provides predictions.

use super::LearningError;
use chrono::{DateTime, Timelike, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// User model for command prediction and suggestions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserModel {
    /// Model version
    version: u32,

    /// Last training timestamp
    last_trained: Option<DateTime<Utc>>,

    /// Command frequency counts
    command_frequency: HashMap<String, f32>,

    /// Command sequences (n-grams)
    common_sequences: Vec<CommandSequence>,

    /// Error patterns
    error_patterns: Vec<ErrorPattern>,

    /// Project-specific patterns
    project_contexts: HashMap<String, ProjectModel>,

    /// Time-of-day patterns
    time_patterns: HashMap<u32, Vec<(String, f32)>>,

    /// Command aliases/abbreviations learned
    aliases: HashMap<String, String>,
}

/// A command sequence pattern
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandSequence {
    /// The sequence of commands
    pub commands: Vec<String>,

    /// How often this sequence occurs
    pub frequency: f32,

    /// Confidence score
    pub confidence: f32,
}

/// An error pattern
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorPattern {
    /// Command that caused the error
    pub command_pattern: String,

    /// Error message pattern
    pub error_pattern: String,

    /// Suggested fix
    pub suggested_fix: Option<String>,

    /// Explanation
    pub explanation: Option<String>,

    /// How often this error occurs
    pub frequency: usize,
}

/// Project-specific model
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ProjectModel {
    /// Project path
    pub path: String,

    /// Common commands for this project
    pub commands: HashMap<String, f32>,

    /// Project type detected
    pub project_type: Option<String>,

    /// Custom aliases for this project
    pub aliases: HashMap<String, String>,
}

/// Command pattern for matching
#[derive(Debug, Clone)]
pub struct CommandPattern {
    /// Pattern string
    pub pattern: String,

    /// Matched command prefix
    pub prefix: String,

    /// Expected arguments
    pub args: Vec<String>,
}

/// Suggestion context
#[derive(Debug, Clone)]
pub struct SuggestionContext {
    /// Current working directory
    pub working_dir: Option<PathBuf>,

    /// Last command executed
    pub last_command: Option<String>,

    /// Last N commands (for sequence matching)
    pub recent_commands: Vec<String>,

    /// Current hour
    pub hour: u32,

    /// Partial input
    pub partial_input: Option<String>,

    /// Current error (if any)
    pub current_error: Option<String>,
}

impl Default for SuggestionContext {
    fn default() -> Self {
        Self {
            working_dir: std::env::current_dir().ok(),
            last_command: None,
            recent_commands: Vec::new(),
            hour: chrono::Local::now().hour(),
            partial_input: None,
            current_error: None,
        }
    }
}

/// A command suggestion
#[derive(Debug, Clone)]
pub struct Suggestion {
    /// Suggested command
    pub command: String,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f32,

    /// Source of suggestion
    pub source: SuggestionSource,

    /// Brief explanation
    pub explanation: Option<String>,
}

/// Source of a suggestion
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SuggestionSource {
    /// Based on command frequency
    Frequency,
    /// Based on sequence pattern
    Sequence,
    /// Based on time of day
    TimePattern,
    /// Based on project context
    ProjectContext,
    /// Based on partial input completion
    Completion,
    /// Based on error fix
    ErrorFix,
}

impl UserModel {
    /// Create a new empty model
    pub fn new() -> Self {
        Self {
            version: 1,
            last_trained: None,
            command_frequency: HashMap::new(),
            common_sequences: Vec::new(),
            error_patterns: Vec::new(),
            project_contexts: HashMap::new(),
            time_patterns: HashMap::new(),
            aliases: HashMap::new(),
        }
    }

    /// Load model from file or create new
    pub fn load_or_create(path: &Path) -> Self {
        if path.exists() {
            match std::fs::read_to_string(path) {
                Ok(content) => match serde_json::from_str(&content) {
                    Ok(model) => {
                        log::info!("Loaded user model from {}", path.display());
                        return model;
                    }
                    Err(e) => {
                        log::warn!("Failed to parse model: {}", e);
                    }
                },
                Err(e) => {
                    log::warn!("Failed to read model file: {}", e);
                }
            }
        }

        log::info!("Creating new user model");
        Self::new()
    }

    /// Save model to file
    pub fn save(&self, path: &Path) -> Result<(), LearningError> {
        let content = serde_json::to_string_pretty(self)
            .map_err(|e| LearningError::Serialization(e.to_string()))?;

        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        std::fs::write(path, content)?;
        log::info!("Saved user model to {}", path.display());
        Ok(())
    }

    /// Get model version
    pub fn version(&self) -> u32 {
        self.version
    }

    /// Increment version
    pub fn increment_version(&mut self) {
        self.version += 1;
        self.last_trained = Some(Utc::now());
    }

    /// Get last training time
    pub fn last_trained(&self) -> Option<DateTime<Utc>> {
        self.last_trained
    }

    /// Update command frequency
    ///
    /// Returns true if command already existed, false if new
    pub fn update_command_frequency(&mut self, command: &str, learning_rate: f32) -> bool {
        let normalized = self.normalize_command(command);
        let exists = self.command_frequency.contains_key(&normalized);

        let entry = self.command_frequency.entry(normalized).or_insert(0.0);
        *entry = *entry * (1.0 - learning_rate) + learning_rate;

        exists
    }

    /// Normalize command for pattern matching
    fn normalize_command(&self, command: &str) -> String {
        // Extract just the command and first argument pattern
        let parts: Vec<&str> = command.split_whitespace().collect();
        match parts.len() {
            0 => String::new(),
            1 => parts[0].to_string(),
            _ => {
                // Keep command and generalize arguments
                let cmd = parts[0];
                let args = parts[1..]
                    .iter()
                    .map(|a| {
                        if a.starts_with('-') {
                            a.to_string()
                        } else if a.contains('/') || a.contains('.') {
                            "<path>".to_string()
                        } else {
                            "<arg>".to_string()
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(" ");
                format!("{} {}", cmd, args)
            }
        }
    }

    /// Add a command sequence
    ///
    /// Returns true if this is a new sequence
    pub fn add_sequence(&mut self, sequence: Vec<String>) -> bool {
        // Check if sequence exists
        for existing in &mut self.common_sequences {
            if existing.commands == sequence {
                existing.frequency += 1.0;
                existing.confidence = (existing.confidence * 0.9 + 0.1).min(1.0);
                return false;
            }
        }

        // Add new sequence
        self.common_sequences.push(CommandSequence {
            commands: sequence,
            frequency: 1.0,
            confidence: 0.5,
        });

        true
    }

    /// Update time pattern
    pub fn update_time_pattern(&mut self, hour: u32, commands: &[String]) {
        // First normalize all commands
        let normalized_cmds: Vec<String> = commands
            .iter()
            .map(|cmd| self.normalize_command(cmd))
            .collect();

        let entry = self.time_patterns.entry(hour).or_default();

        for normalized in normalized_cmds {
            // Find or add command
            if let Some(existing) = entry.iter_mut().find(|(c, _)| *c == normalized) {
                existing.1 += 1.0;
            } else {
                entry.push((normalized, 1.0));
            }
        }

        // Sort by frequency and keep top 10
        entry.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        entry.truncate(10);
    }

    /// Update project patterns
    pub fn update_project_patterns(&mut self, project: &str, commands: &[String]) {
        // First normalize all commands and detect project type
        let normalized_cmds: Vec<String> = commands
            .iter()
            .map(|cmd| self.normalize_command(cmd))
            .collect();
        let project_type = self.detect_project_type(commands);

        let entry = self
            .project_contexts
            .entry(project.to_string())
            .or_default();

        for normalized in normalized_cmds {
            let freq = entry.commands.entry(normalized).or_insert(0.0);
            *freq += 1.0;
        }

        // Set project type if not already set
        if entry.project_type.is_none() {
            entry.project_type = project_type;
        }
    }

    /// Detect project type from commands
    fn detect_project_type(&self, commands: &[String]) -> Option<String> {
        let mut indicators: HashMap<&str, usize> = HashMap::new();

        for cmd in commands {
            let cmd_lower = cmd.to_lowercase();
            if cmd_lower.contains("npm") || cmd_lower.contains("yarn") || cmd_lower.contains("node")
            {
                *indicators.entry("nodejs").or_default() += 1;
            }
            if cmd_lower.contains("python") || cmd_lower.contains("pip") {
                *indicators.entry("python").or_default() += 1;
            }
            if cmd_lower.contains("cargo") || cmd_lower.contains("rustc") {
                *indicators.entry("rust").or_default() += 1;
            }
            if cmd_lower.contains("go ") || cmd_lower.contains("go.mod") {
                *indicators.entry("go").or_default() += 1;
            }
            if cmd_lower.contains("docker") {
                *indicators.entry("docker").or_default() += 1;
            }
            if cmd_lower.contains("kubectl") || cmd_lower.contains("k8s") {
                *indicators.entry("kubernetes").or_default() += 1;
            }
        }

        indicators
            .into_iter()
            .max_by_key(|(_, count)| *count)
            .filter(|(_, count)| *count >= 2)
            .map(|(t, _)| t.to_string())
    }

    /// Add an error pattern
    ///
    /// Returns true if this is a new pattern
    pub fn add_error_pattern(&mut self, command: &str, error: &str) -> bool {
        // Generalize patterns
        let cmd_pattern = self.generalize_command_pattern(command);
        let err_pattern = self.generalize_error_pattern(error);

        // Check if pattern exists
        for existing in &mut self.error_patterns {
            if existing.command_pattern == cmd_pattern && existing.error_pattern == err_pattern {
                existing.frequency += 1;
                return false;
            }
        }

        // Add new pattern
        self.error_patterns.push(ErrorPattern {
            command_pattern: cmd_pattern,
            error_pattern: err_pattern,
            suggested_fix: self.generate_fix_suggestion(command, error),
            explanation: None,
            frequency: 1,
        });

        true
    }

    /// Generalize command for pattern matching
    fn generalize_command_pattern(&self, command: &str) -> String {
        let parts: Vec<&str> = command.split_whitespace().collect();
        if parts.is_empty() {
            return String::new();
        }

        // Keep command and flags, generalize arguments
        parts[0].to_string()
    }

    /// Generalize error message for pattern matching
    fn generalize_error_pattern(&self, error: &str) -> String {
        // Extract key error phrase
        let error_lower = error.to_lowercase();

        if error_lower.contains("permission denied") {
            return "permission denied".to_string();
        }
        if error_lower.contains("not found") {
            return "not found".to_string();
        }
        if error_lower.contains("no such file") {
            return "no such file".to_string();
        }
        if error_lower.contains("connection refused") {
            return "connection refused".to_string();
        }
        if error_lower.contains("syntax error") {
            return "syntax error".to_string();
        }

        // Fall back to first 50 chars
        error.chars().take(50).collect()
    }

    /// Generate fix suggestion for error
    fn generate_fix_suggestion(&self, command: &str, error: &str) -> Option<String> {
        let error_lower = error.to_lowercase();
        let cmd_parts: Vec<&str> = command.split_whitespace().collect();
        let base_cmd = cmd_parts.first().copied().unwrap_or("");

        if error_lower.contains("permission denied") {
            return Some(format!("sudo {}", command));
        }

        if error_lower.contains("not found") && base_cmd == "cd" {
            return Some("mkdir -p <directory>".to_string());
        }

        if error_lower.contains("command not found") {
            return Some(format!("which {} || apt search {}", base_cmd, base_cmd));
        }

        None
    }

    /// Suggest next command based on context
    pub fn suggest_next_command(&self, context: &SuggestionContext) -> Vec<Suggestion> {
        let mut suggestions = Vec::new();

        // 1. Sequence-based suggestions
        if let Some(ref recent) = context.last_command {
            for seq in &self.common_sequences {
                if seq.commands.len() >= 2 {
                    // Check if recent command matches start of sequence
                    for i in 0..seq.commands.len() - 1 {
                        if seq.commands[i] == *recent {
                            suggestions.push(Suggestion {
                                command: seq.commands[i + 1].clone(),
                                confidence: seq.confidence * 0.8,
                                source: SuggestionSource::Sequence,
                                explanation: Some(format!(
                                    "Often follows '{}'",
                                    recent
                                )),
                            });
                        }
                    }
                }
            }
        }

        // 2. Time-based suggestions
        if let Some(time_cmds) = self.time_patterns.get(&context.hour) {
            for (cmd, freq) in time_cmds.iter().take(3) {
                suggestions.push(Suggestion {
                    command: cmd.clone(),
                    confidence: (*freq / 100.0).min(0.7),
                    source: SuggestionSource::TimePattern,
                    explanation: Some(format!("Common at this hour")),
                });
            }
        }

        // 3. Project-based suggestions
        if let Some(ref dir) = context.working_dir {
            let project_key = dir
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();

            if let Some(project) = self.project_contexts.get(&project_key) {
                let mut project_cmds: Vec<_> = project.commands.iter().collect();
                project_cmds.sort_by(|a, b| {
                    b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal)
                });

                for (cmd, freq) in project_cmds.iter().take(3) {
                    suggestions.push(Suggestion {
                        command: (*cmd).clone(),
                        confidence: (**freq / 100.0).min(0.7),
                        source: SuggestionSource::ProjectContext,
                        explanation: Some(format!("Common in this project")),
                    });
                }
            }
        }

        // 4. Error fix suggestions
        if let Some(ref error) = context.current_error {
            let err_pattern = self.generalize_error_pattern(error);

            for pattern in &self.error_patterns {
                if pattern.error_pattern == err_pattern {
                    if let Some(ref fix) = pattern.suggested_fix {
                        suggestions.push(Suggestion {
                            command: fix.clone(),
                            confidence: 0.8,
                            source: SuggestionSource::ErrorFix,
                            explanation: pattern.explanation.clone(),
                        });
                    }
                }
            }
        }

        // 5. Completion suggestions
        if let Some(ref partial) = context.partial_input {
            for (cmd, freq) in &self.command_frequency {
                if cmd.starts_with(partial) && cmd != partial {
                    suggestions.push(Suggestion {
                        command: cmd.clone(),
                        confidence: *freq,
                        source: SuggestionSource::Completion,
                        explanation: None,
                    });
                }
            }
        }

        // Sort by confidence and deduplicate
        suggestions.sort_by(|a, b| {
            b.confidence
                .partial_cmp(&a.confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Deduplicate
        let mut seen = std::collections::HashSet::new();
        suggestions.retain(|s| seen.insert(s.command.clone()));

        // Limit results
        suggestions.truncate(10);

        suggestions
    }

    /// Explain an error based on learned patterns
    pub fn explain_error(&self, error: &str) -> Option<String> {
        let err_pattern = self.generalize_error_pattern(error);

        for pattern in &self.error_patterns {
            if pattern.error_pattern == err_pattern {
                let mut explanation = String::new();

                if let Some(ref exp) = pattern.explanation {
                    explanation.push_str(exp);
                } else {
                    explanation.push_str(&format!(
                        "This error '{}' is commonly caused by '{}' commands.",
                        pattern.error_pattern, pattern.command_pattern
                    ));
                }

                if let Some(ref fix) = pattern.suggested_fix {
                    explanation.push_str(&format!("\nSuggested fix: {}", fix));
                }

                return Some(explanation);
            }
        }

        None
    }

    /// Predict intent from partial input
    pub fn predict_intent(&self, partial: &str) -> Vec<String> {
        let mut predictions = Vec::new();

        // Check command frequency
        for (cmd, _) in &self.command_frequency {
            if cmd.starts_with(partial) {
                predictions.push(cmd.clone());
            }
        }

        // Check aliases
        for (alias, cmd) in &self.aliases {
            if alias.starts_with(partial) {
                predictions.push(cmd.clone());
            }
        }

        predictions.sort();
        predictions.dedup();
        predictions.truncate(10);

        predictions
    }

    /// Apply decay to all frequencies
    pub fn apply_decay(&mut self, rate: f32) {
        for freq in self.command_frequency.values_mut() {
            *freq *= rate;
        }

        for seq in &mut self.common_sequences {
            seq.frequency *= rate;
        }

        for (_, cmds) in &mut self.time_patterns {
            for (_, freq) in cmds {
                *freq *= rate;
            }
        }
    }

    /// Prune infrequent patterns
    ///
    /// Returns number of patterns removed
    pub fn prune_patterns(&mut self, min_occurrences: usize) -> usize {
        let threshold = min_occurrences as f32;
        let mut removed = 0;

        // Prune command frequency
        let before = self.command_frequency.len();
        self.command_frequency.retain(|_, v| *v >= threshold * 0.1);
        removed += before - self.command_frequency.len();

        // Prune sequences
        let before = self.common_sequences.len();
        self.common_sequences
            .retain(|s| s.frequency >= threshold);
        removed += before - self.common_sequences.len();

        // Prune error patterns
        let before = self.error_patterns.len();
        self.error_patterns
            .retain(|p| p.frequency >= min_occurrences);
        removed += before - self.error_patterns.len();

        removed
    }
}

impl Default for UserModel {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_user_model_new() {
        let model = UserModel::new();
        assert_eq!(model.version(), 1);
    }

    #[test]
    fn test_update_command_frequency() {
        let mut model = UserModel::new();

        let is_new = model.update_command_frequency("ls -la", 0.1);
        assert!(!is_new);

        let is_new = model.update_command_frequency("ls -la", 0.1);
        assert!(is_new);
    }

    #[test]
    fn test_add_sequence() {
        let mut model = UserModel::new();

        let is_new = model.add_sequence(vec!["git add".to_string(), "git commit".to_string()]);
        assert!(is_new);

        let is_new = model.add_sequence(vec!["git add".to_string(), "git commit".to_string()]);
        assert!(!is_new);
    }

    #[test]
    fn test_predict_intent() {
        let mut model = UserModel::new();
        model.update_command_frequency("ls -la", 0.1);
        model.update_command_frequency("less file.txt", 0.1);

        let predictions = model.predict_intent("l");
        assert!(predictions.iter().any(|p| p.starts_with("l")));
    }

    #[test]
    fn test_error_pattern() {
        let mut model = UserModel::new();

        model.add_error_pattern("rm /protected", "Permission denied");

        let explanation = model.explain_error("Permission denied");
        assert!(explanation.is_some());
        assert!(explanation.unwrap().contains("sudo"));
    }
}
