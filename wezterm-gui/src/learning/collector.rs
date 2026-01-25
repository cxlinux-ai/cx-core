//! Learning Data Collector
//!
//! Collects and stores learning data for the continuous learning pipeline.

use super::LearningError;
use chrono::{DateTime, Datelike, Timelike, Utc};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;

/// Configuration for data collection
#[derive(Debug, Clone)]
pub struct LearningConfig {
    /// Collect command history
    pub collect_commands: bool,

    /// Collect command outputs
    pub collect_outputs: bool,

    /// Collect AI interactions
    pub collect_ai_interactions: bool,

    /// Collect error patterns
    pub collect_errors: bool,

    /// Maximum events to keep in memory
    pub max_memory_events: usize,

    /// Flush to disk after this many events
    pub flush_threshold: usize,

    /// Enable real-time collection
    pub real_time: bool,
}

impl Default for LearningConfig {
    fn default() -> Self {
        Self {
            collect_commands: true,
            collect_outputs: false, // Off by default for privacy
            collect_ai_interactions: true,
            collect_errors: true,
            max_memory_events: 1000,
            flush_threshold: 100,
            real_time: true,
        }
    }
}

/// A command execution event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandEvent {
    /// The command that was executed
    pub command: String,

    /// Command output (if collected)
    pub output: Option<String>,

    /// Exit code
    pub exit_code: i32,

    /// Duration in milliseconds
    pub duration_ms: u64,

    /// Timestamp
    pub timestamp: DateTime<Utc>,

    /// Working directory
    pub working_dir: Option<PathBuf>,
}

/// An AI interaction event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InteractionEvent {
    /// User query
    pub query: String,

    /// AI response
    pub response: String,

    /// Whether the user found it helpful
    pub was_helpful: bool,

    /// Timestamp
    pub timestamp: DateTime<Utc>,
}

/// An error event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorEvent {
    /// Error message
    pub error: String,

    /// Command that caused the error (if known)
    pub command: Option<String>,

    /// Timestamp
    pub timestamp: DateTime<Utc>,
}

/// Learning event wrapper
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum LearningEvent {
    Command(CommandEvent),
    Interaction(InteractionEvent),
    Error(ErrorEvent),
}

impl LearningEvent {
    pub fn timestamp(&self) -> DateTime<Utc> {
        match self {
            LearningEvent::Command(e) => e.timestamp,
            LearningEvent::Interaction(e) => e.timestamp,
            LearningEvent::Error(e) => e.timestamp,
        }
    }
}

/// Data collector for learning events
pub struct LearningCollector {
    /// Configuration
    config: LearningConfig,

    /// Data directory
    data_dir: PathBuf,

    /// In-memory event buffer
    buffer: VecDeque<LearningEvent>,

    /// Number of events since last flush
    pending_flush: usize,

    /// Counters
    command_count: usize,
    interaction_count: usize,
    error_count: usize,
}

impl LearningCollector {
    /// Create a new collector
    pub fn new(config: LearningConfig, data_dir: PathBuf) -> Self {
        Self {
            config,
            data_dir,
            buffer: VecDeque::new(),
            pending_flush: 0,
            command_count: 0,
            interaction_count: 0,
            error_count: 0,
        }
    }

    /// Record a command event
    pub fn record_command(&mut self, event: CommandEvent) -> Result<(), LearningError> {
        if !self.config.collect_commands {
            return Ok(());
        }

        self.command_count += 1;
        self.add_event(LearningEvent::Command(event))
    }

    /// Record an AI interaction event
    pub fn record_interaction(&mut self, event: InteractionEvent) -> Result<(), LearningError> {
        if !self.config.collect_ai_interactions {
            return Ok(());
        }

        self.interaction_count += 1;
        self.add_event(LearningEvent::Interaction(event))
    }

    /// Record an error event
    pub fn record_error(&mut self, error: &str, command: Option<&str>) -> Result<(), LearningError> {
        if !self.config.collect_errors {
            return Ok(());
        }

        let event = ErrorEvent {
            error: error.to_string(),
            command: command.map(|c| c.to_string()),
            timestamp: Utc::now(),
        };

        self.error_count += 1;
        self.add_event(LearningEvent::Error(event))
    }

    /// Add an event to the buffer
    fn add_event(&mut self, event: LearningEvent) -> Result<(), LearningError> {
        // Add to buffer
        self.buffer.push_back(event);
        self.pending_flush += 1;

        // Trim buffer if needed
        while self.buffer.len() > self.config.max_memory_events {
            self.buffer.pop_front();
        }

        // Flush if threshold reached
        if self.pending_flush >= self.config.flush_threshold {
            self.flush()?;
        }

        Ok(())
    }

    /// Flush buffered events to disk
    pub fn flush(&mut self) -> Result<(), LearningError> {
        if self.buffer.is_empty() {
            return Ok(());
        }

        // Create data directory if needed
        std::fs::create_dir_all(&self.data_dir)?;

        // Generate filename based on date
        let date = Utc::now().format("%Y-%m-%d").to_string();
        let events_file = self.data_dir.join(format!("events-{}.jsonl", date));

        // Append events to file
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&events_file)?;

        for event in &self.buffer {
            let json = serde_json::to_string(event)
                .map_err(|e| LearningError::Serialization(e.to_string()))?;
            writeln!(file, "{}", json)?;
        }

        self.pending_flush = 0;
        log::debug!("Flushed {} events to {}", self.buffer.len(), events_file.display());

        Ok(())
    }

    /// Get recent events from memory
    pub fn get_recent_events(&self) -> Result<Vec<LearningEvent>, LearningError> {
        Ok(self.buffer.iter().cloned().collect())
    }

    /// Load events from disk
    pub fn load_events(&self) -> Result<Vec<LearningEvent>, LearningError> {
        let mut events = Vec::new();

        for entry in std::fs::read_dir(&self.data_dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.extension().map(|e| e == "jsonl").unwrap_or(false) {
                let file = File::open(&path)?;
                let reader = BufReader::new(file);

                for line in reader.lines() {
                    let line = line?;
                    if let Ok(event) = serde_json::from_str::<LearningEvent>(&line) {
                        events.push(event);
                    }
                }
            }
        }

        // Sort by timestamp
        events.sort_by_key(|e| e.timestamp());

        Ok(events)
    }

    /// Clean up events before a certain date
    pub fn cleanup_before(&self, cutoff: DateTime<Utc>) -> Result<(), LearningError> {
        for entry in std::fs::read_dir(&self.data_dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.extension().map(|e| e == "jsonl").unwrap_or(false) {
                // Parse date from filename
                if let Some(stem) = path.file_stem() {
                    if let Some(date_str) = stem.to_str() {
                        if let Some(date) = date_str.strip_prefix("events-") {
                            if let Ok(file_date) =
                                chrono::NaiveDate::parse_from_str(date, "%Y-%m-%d")
                            {
                                let file_datetime = file_date
                                    .and_hms_opt(0, 0, 0)
                                    .map(|dt| DateTime::<Utc>::from_naive_utc_and_offset(dt, Utc));

                                if let Some(dt) = file_datetime {
                                    if dt < cutoff {
                                        log::info!("Removing old events file: {}", path.display());
                                        std::fs::remove_file(&path)?;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// Export all data to a file
    pub fn export(&self, path: &PathBuf) -> Result<(), LearningError> {
        let events = self.load_events()?;

        let file = File::create(path)?;
        serde_json::to_writer_pretty(file, &events)
            .map_err(|e| LearningError::Serialization(e.to_string()))?;

        log::info!("Exported {} events to {}", events.len(), path.display());
        Ok(())
    }

    /// Clear all collected data
    pub fn clear(&mut self) -> Result<(), LearningError> {
        self.buffer.clear();
        self.pending_flush = 0;
        self.command_count = 0;
        self.interaction_count = 0;
        self.error_count = 0;

        // Remove all event files
        for entry in std::fs::read_dir(&self.data_dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.extension().map(|e| e == "jsonl").unwrap_or(false) {
                std::fs::remove_file(&path)?;
            }
        }

        Ok(())
    }

    /// Get command count
    pub fn command_count(&self) -> usize {
        self.command_count
    }

    /// Get interaction count
    pub fn interaction_count(&self) -> usize {
        self.interaction_count
    }

    /// Get error count
    pub fn error_count(&self) -> usize {
        self.error_count
    }

    /// Get configuration
    pub fn config(&self) -> &LearningConfig {
        &self.config
    }

    /// Update configuration
    pub fn set_config(&mut self, config: LearningConfig) {
        self.config = config;
    }
}

/// Aggregated statistics (privacy-preserving)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregatedStats {
    /// Total commands executed
    pub total_commands: usize,

    /// Commands by hour of day
    pub commands_by_hour: [usize; 24],

    /// Commands by day of week
    pub commands_by_day: [usize; 7],

    /// Most common command prefixes
    pub common_prefixes: Vec<(String, usize)>,

    /// Average command duration
    pub avg_duration_ms: f64,

    /// Error rate
    pub error_rate: f64,

    /// AI interaction count
    pub ai_interactions: usize,

    /// AI helpfulness rate
    pub ai_helpfulness_rate: f64,
}

impl AggregatedStats {
    /// Create empty stats
    pub fn new() -> Self {
        Self {
            total_commands: 0,
            commands_by_hour: [0; 24],
            commands_by_day: [0; 7],
            common_prefixes: Vec::new(),
            avg_duration_ms: 0.0,
            error_rate: 0.0,
            ai_interactions: 0,
            ai_helpfulness_rate: 0.0,
        }
    }

    /// Aggregate from events
    pub fn from_events(events: &[LearningEvent]) -> Self {
        let mut stats = Self::new();
        let mut total_duration = 0u64;
        let mut error_count = 0usize;
        let mut helpful_count = 0usize;
        let mut prefix_counts: std::collections::HashMap<String, usize> =
            std::collections::HashMap::new();

        for event in events {
            match event {
                LearningEvent::Command(cmd) => {
                    stats.total_commands += 1;
                    total_duration += cmd.duration_ms;

                    // Count by hour and day
                    let hour = cmd.timestamp.hour() as usize;
                    let day = cmd.timestamp.weekday().num_days_from_sunday() as usize;
                    stats.commands_by_hour[hour] += 1;
                    stats.commands_by_day[day] += 1;

                    // Count prefix
                    if let Some(prefix) = cmd.command.split_whitespace().next() {
                        *prefix_counts.entry(prefix.to_string()).or_insert(0) += 1;
                    }

                    if cmd.exit_code != 0 {
                        error_count += 1;
                    }
                }
                LearningEvent::Interaction(int) => {
                    stats.ai_interactions += 1;
                    if int.was_helpful {
                        helpful_count += 1;
                    }
                }
                LearningEvent::Error(_) => {
                    error_count += 1;
                }
            }
        }

        // Calculate averages
        if stats.total_commands > 0 {
            stats.avg_duration_ms = total_duration as f64 / stats.total_commands as f64;
            stats.error_rate = error_count as f64 / stats.total_commands as f64;
        }

        if stats.ai_interactions > 0 {
            stats.ai_helpfulness_rate = helpful_count as f64 / stats.ai_interactions as f64;
        }

        // Top prefixes
        let mut prefixes: Vec<_> = prefix_counts.into_iter().collect();
        prefixes.sort_by(|a, b| b.1.cmp(&a.1));
        stats.common_prefixes = prefixes.into_iter().take(10).collect();

        stats
    }
}

impl Default for AggregatedStats {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_learning_config_default() {
        let config = LearningConfig::default();
        assert!(config.collect_commands);
        assert!(!config.collect_outputs); // Off by default
        assert!(config.collect_ai_interactions);
    }

    #[test]
    fn test_collector_record_command() {
        let dir = tempdir().unwrap();
        let mut collector = LearningCollector::new(LearningConfig::default(), dir.path().to_path_buf());

        let event = CommandEvent {
            command: "ls -la".to_string(),
            output: None,
            exit_code: 0,
            duration_ms: 50,
            timestamp: Utc::now(),
            working_dir: None,
        };

        collector.record_command(event).unwrap();
        assert_eq!(collector.command_count(), 1);
    }

    #[test]
    fn test_aggregated_stats() {
        let events = vec![
            LearningEvent::Command(CommandEvent {
                command: "ls".to_string(),
                output: None,
                exit_code: 0,
                duration_ms: 10,
                timestamp: Utc::now(),
                working_dir: None,
            }),
            LearningEvent::Command(CommandEvent {
                command: "ls -la".to_string(),
                output: None,
                exit_code: 0,
                duration_ms: 20,
                timestamp: Utc::now(),
                working_dir: None,
            }),
        ];

        let stats = AggregatedStats::from_events(&events);
        assert_eq!(stats.total_commands, 2);
        assert_eq!(stats.common_prefixes[0].0, "ls");
        assert_eq!(stats.common_prefixes[0].1, 2);
    }
}
