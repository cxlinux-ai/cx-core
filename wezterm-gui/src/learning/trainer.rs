//! Local Model Trainer
//!
//! Trains user models based on collected data patterns.

use super::model::UserModel;
use super::{CommandEvent, LearningError, LearningEvent};
use chrono::Timelike;
use std::collections::HashMap;

/// Training configuration
#[derive(Debug, Clone)]
pub struct TrainingConfig {
    /// Minimum events required for training
    pub min_events: usize,

    /// Learning rate for frequency updates
    pub learning_rate: f32,

    /// Decay rate for old patterns
    pub decay_rate: f32,

    /// Maximum sequence length for pattern detection
    pub max_sequence_length: usize,

    /// Minimum pattern occurrences to keep
    pub min_pattern_occurrences: usize,

    /// Enable time-of-day learning
    pub learn_time_patterns: bool,

    /// Enable project context learning
    pub learn_project_patterns: bool,

    /// Enable error pattern learning
    pub learn_error_patterns: bool,
}

impl Default for TrainingConfig {
    fn default() -> Self {
        Self {
            min_events: 10,
            learning_rate: 0.1,
            decay_rate: 0.99,
            max_sequence_length: 5,
            min_pattern_occurrences: 2,
            learn_time_patterns: true,
            learn_project_patterns: true,
            learn_error_patterns: true,
        }
    }
}

/// Training statistics
#[derive(Debug, Clone)]
pub struct TrainingStats {
    /// Number of events processed
    pub events_processed: usize,

    /// Number of commands analyzed
    pub commands_analyzed: usize,

    /// Number of new patterns found
    pub new_patterns: usize,

    /// Number of patterns updated
    pub patterns_updated: usize,

    /// Number of patterns pruned
    pub patterns_pruned: usize,

    /// Training duration in milliseconds
    pub duration_ms: u64,

    /// Model accuracy improvement (if measurable)
    pub accuracy_improvement: Option<f32>,
}

/// Local model trainer
///
/// Uses collected data to train and update the user model.
pub struct LocalTrainer {
    /// Configuration
    config: TrainingConfig,
}

impl LocalTrainer {
    /// Create a new trainer
    pub fn new(config: TrainingConfig) -> Self {
        Self { config }
    }

    /// Train the model with new events
    pub fn train(
        &self,
        model: &mut UserModel,
        events: &[LearningEvent],
    ) -> Result<TrainingStats, LearningError> {
        let start = std::time::Instant::now();
        let mut stats = TrainingStats {
            events_processed: events.len(),
            commands_analyzed: 0,
            new_patterns: 0,
            patterns_updated: 0,
            patterns_pruned: 0,
            duration_ms: 0,
            accuracy_improvement: None,
        };

        if events.len() < self.config.min_events {
            log::info!(
                "Not enough events for training ({}/{})",
                events.len(),
                self.config.min_events
            );
            return Ok(stats);
        }

        // Extract command events
        let commands: Vec<&CommandEvent> = events
            .iter()
            .filter_map(|e| match e {
                LearningEvent::Command(c) => Some(c),
                _ => None,
            })
            .collect();

        stats.commands_analyzed = commands.len();

        // Update command frequencies
        self.update_frequencies(model, &commands, &mut stats);

        // Learn command sequences
        self.learn_sequences(model, &commands, &mut stats);

        // Learn time patterns
        if self.config.learn_time_patterns {
            self.learn_time_patterns(model, &commands, &mut stats);
        }

        // Learn project patterns
        if self.config.learn_project_patterns {
            self.learn_project_patterns(model, &commands, &mut stats);
        }

        // Learn error patterns
        if self.config.learn_error_patterns {
            self.learn_error_patterns(model, events, &mut stats);
        }

        // Prune infrequent patterns
        let pruned = model.prune_patterns(self.config.min_pattern_occurrences);
        stats.patterns_pruned = pruned;

        // Apply decay
        model.apply_decay(self.config.decay_rate);

        // Update model version and timestamp
        model.increment_version();

        stats.duration_ms = start.elapsed().as_millis() as u64;
        Ok(stats)
    }

    /// Update command frequency counts
    fn update_frequencies(
        &self,
        model: &mut UserModel,
        commands: &[&CommandEvent],
        stats: &mut TrainingStats,
    ) {
        for cmd in commands {
            let updated = model.update_command_frequency(&cmd.command, self.config.learning_rate);
            if updated {
                stats.patterns_updated += 1;
            } else {
                stats.new_patterns += 1;
            }
        }
    }

    /// Learn command sequences
    fn learn_sequences(
        &self,
        model: &mut UserModel,
        commands: &[&CommandEvent],
        stats: &mut TrainingStats,
    ) {
        if commands.len() < 2 {
            return;
        }

        // Build n-gram sequences
        for window_size in 2..=self.config.max_sequence_length.min(commands.len()) {
            for window in commands.windows(window_size) {
                let sequence: Vec<String> = window.iter().map(|c| c.command.clone()).collect();

                let is_new = model.add_sequence(sequence);
                if is_new {
                    stats.new_patterns += 1;
                } else {
                    stats.patterns_updated += 1;
                }
            }
        }
    }

    /// Learn time-of-day patterns
    fn learn_time_patterns(
        &self,
        model: &mut UserModel,
        commands: &[&CommandEvent],
        _stats: &mut TrainingStats,
    ) {
        // Group commands by hour
        let mut by_hour: HashMap<u32, Vec<String>> = HashMap::new();

        for cmd in commands {
            let hour = cmd.timestamp.hour();
            by_hour
                .entry(hour)
                .or_default()
                .push(cmd.command.clone());
        }

        // Update time patterns in model
        for (hour, cmds) in by_hour {
            model.update_time_pattern(hour, &cmds);
        }
    }

    /// Learn project-specific patterns
    fn learn_project_patterns(
        &self,
        model: &mut UserModel,
        commands: &[&CommandEvent],
        _stats: &mut TrainingStats,
    ) {
        // Group commands by project directory
        let mut by_project: HashMap<String, Vec<String>> = HashMap::new();

        for cmd in commands {
            if let Some(dir) = &cmd.working_dir {
                // Extract project root (first 2-3 path components after home)
                let project_key = self.extract_project_key(dir);
                if let Some(key) = project_key {
                    by_project
                        .entry(key)
                        .or_default()
                        .push(cmd.command.clone());
                }
            }
        }

        // Update project patterns in model
        for (project, cmds) in by_project {
            model.update_project_patterns(&project, &cmds);
        }
    }

    /// Extract project key from path
    fn extract_project_key(&self, path: &std::path::Path) -> Option<String> {
        let home = dirs_next::home_dir()?;

        if let Ok(relative) = path.strip_prefix(&home) {
            let components: Vec<_> = relative.components().take(2).collect();
            if !components.is_empty() {
                return Some(
                    components
                        .iter()
                        .map(|c| c.as_os_str().to_string_lossy().to_string())
                        .collect::<Vec<_>>()
                        .join("/"),
                );
            }
        }

        // Fall back to last directory component
        path.file_name()
            .map(|n| n.to_string_lossy().to_string())
    }

    /// Learn error patterns
    fn learn_error_patterns(
        &self,
        model: &mut UserModel,
        events: &[LearningEvent],
        stats: &mut TrainingStats,
    ) {
        // Collect errors with their preceding commands
        let mut error_pairs: Vec<(String, String)> = Vec::new();

        let mut last_command: Option<&CommandEvent> = None;
        for event in events {
            match event {
                LearningEvent::Command(cmd) => {
                    // Check if previous command failed
                    if let Some(prev) = last_command {
                        if prev.exit_code != 0 {
                            // Record error pattern
                            let error_msg = prev
                                .output
                                .as_ref()
                                .map(|o| self.extract_error_message(o))
                                .unwrap_or_else(|| format!("exit code {}", prev.exit_code));

                            error_pairs.push((prev.command.clone(), error_msg));
                        }
                    }
                    last_command = Some(cmd);
                }
                LearningEvent::Error(err) => {
                    if let Some(cmd) = &err.command {
                        error_pairs.push((cmd.clone(), err.error.clone()));
                    }
                }
                _ => {}
            }
        }

        // Update error patterns in model
        for (cmd, error) in error_pairs {
            let is_new = model.add_error_pattern(&cmd, &error);
            if is_new {
                stats.new_patterns += 1;
            }
        }
    }

    /// Extract error message from output
    fn extract_error_message(&self, output: &str) -> String {
        // Look for common error patterns
        for line in output.lines().rev().take(5) {
            let line = line.trim();
            let line_lower = line.to_lowercase();

            if line_lower.contains("error")
                || line_lower.contains("failed")
                || line_lower.contains("cannot")
                || line_lower.contains("not found")
                || line_lower.contains("permission denied")
            {
                return line.to_string();
            }
        }

        // Fall back to last non-empty line
        output
            .lines()
            .rev()
            .find(|l| !l.trim().is_empty())
            .map(|l| l.trim().to_string())
            .unwrap_or_else(|| "Unknown error".to_string())
    }

    /// Get configuration
    pub fn config(&self) -> &TrainingConfig {
        &self.config
    }

    /// Update configuration
    pub fn set_config(&mut self, config: TrainingConfig) {
        self.config = config;
    }
}

/// Analyze command patterns for insights
pub fn analyze_patterns(events: &[LearningEvent]) -> PatternAnalysis {
    let mut analysis = PatternAnalysis::default();

    let commands: Vec<&CommandEvent> = events
        .iter()
        .filter_map(|e| match e {
            LearningEvent::Command(c) => Some(c),
            _ => None,
        })
        .collect();

    // Command frequency
    let mut freq: HashMap<&str, usize> = HashMap::new();
    for cmd in &commands {
        let prefix = cmd.command.split_whitespace().next().unwrap_or("");
        *freq.entry(prefix).or_default() += 1;
    }

    let mut freq_vec: Vec<_> = freq.into_iter().collect();
    freq_vec.sort_by(|a, b| b.1.cmp(&a.1));
    analysis.top_commands = freq_vec
        .into_iter()
        .take(10)
        .map(|(k, v)| (k.to_string(), v))
        .collect();

    // Error rate
    let errors = commands.iter().filter(|c| c.exit_code != 0).count();
    if !commands.is_empty() {
        analysis.error_rate = errors as f32 / commands.len() as f32;
    }

    // Average session length (commands between long gaps)
    let mut session_lengths = Vec::new();
    let mut current_session = 0;
    for window in commands.windows(2) {
        let gap = window[1]
            .timestamp
            .signed_duration_since(window[0].timestamp);
        if gap.num_minutes() > 30 {
            if current_session > 0 {
                session_lengths.push(current_session);
            }
            current_session = 1;
        } else {
            current_session += 1;
        }
    }
    if current_session > 0 {
        session_lengths.push(current_session);
    }

    if !session_lengths.is_empty() {
        analysis.avg_session_length =
            session_lengths.iter().sum::<usize>() as f32 / session_lengths.len() as f32;
    }

    analysis
}

/// Pattern analysis results
#[derive(Debug, Clone, Default)]
pub struct PatternAnalysis {
    /// Top commands by frequency
    pub top_commands: Vec<(String, usize)>,

    /// Error rate
    pub error_rate: f32,

    /// Average session length
    pub avg_session_length: f32,

    /// Peak usage hours
    pub peak_hours: Vec<u32>,

    /// Common workflows detected
    pub workflows: Vec<Vec<String>>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn test_training_config_default() {
        let config = TrainingConfig::default();
        assert_eq!(config.min_events, 10);
        assert!(config.learn_time_patterns);
    }

    #[test]
    fn test_trainer_insufficient_events() {
        let trainer = LocalTrainer::new(TrainingConfig::default());
        let mut model = UserModel::new();

        let events = vec![LearningEvent::Command(CommandEvent {
            command: "ls".to_string(),
            output: None,
            exit_code: 0,
            duration_ms: 10,
            timestamp: Utc::now(),
            working_dir: None,
        })];

        let stats = trainer.train(&mut model, &events).unwrap();
        assert_eq!(stats.commands_analyzed, 0); // Not enough events
    }

    #[test]
    fn test_analyze_patterns() {
        let events: Vec<LearningEvent> = (0..20)
            .map(|i| {
                LearningEvent::Command(CommandEvent {
                    command: if i % 3 == 0 {
                        "git status".to_string()
                    } else {
                        "ls".to_string()
                    },
                    output: None,
                    exit_code: if i % 5 == 0 { 1 } else { 0 },
                    duration_ms: 10,
                    timestamp: Utc::now(),
                    working_dir: None,
                })
            })
            .collect();

        let analysis = analyze_patterns(&events);
        assert!(!analysis.top_commands.is_empty());
        assert!(analysis.error_rate > 0.0);
    }
}
