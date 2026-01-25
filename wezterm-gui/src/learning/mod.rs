//! Continuous Learning Pipeline
//!
//! Provides privacy-preserving local learning for CX Terminal:
//! - Track user commands and corrections
//! - Learn from AI interactions
//! - Improve suggestions over time
//! - User control over data collection

mod collector;
mod model;
mod privacy;
mod trainer;

pub use collector::{
    CommandEvent, InteractionEvent, LearningCollector, LearningConfig, LearningEvent,
};
pub use model::{
    CommandPattern, ErrorPattern, ProjectModel, Suggestion, SuggestionContext, UserModel,
};
pub use privacy::{PrivacyConfig, PrivacyFilter, SensitivePattern};
pub use trainer::{LocalTrainer, TrainingConfig, TrainingStats};

use std::path::PathBuf;
use std::sync::Arc;

/// Learning system configuration
#[derive(Debug, Clone)]
pub struct LearningSystemConfig {
    /// Enable learning system
    pub enabled: bool,

    /// Data collection settings
    pub collection: LearningConfig,

    /// Privacy settings
    pub privacy: PrivacyConfig,

    /// Training settings
    pub training: TrainingConfig,

    /// Data directory
    pub data_dir: PathBuf,

    /// Maximum age of data in days
    pub max_data_age_days: u32,
}

impl Default for LearningSystemConfig {
    fn default() -> Self {
        let data_dir = dirs_next::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("cx-terminal")
            .join("learning");

        Self {
            enabled: false,
            collection: LearningConfig::default(),
            privacy: PrivacyConfig::default(),
            training: TrainingConfig::default(),
            data_dir,
            max_data_age_days: 30,
        }
    }
}

/// Learning system manager
///
/// Coordinates data collection, model training, and suggestions.
pub struct LearningSystem {
    /// Configuration
    config: LearningSystemConfig,

    /// Data collector
    collector: LearningCollector,

    /// Privacy filter
    privacy_filter: PrivacyFilter,

    /// Local trainer
    trainer: LocalTrainer,

    /// User model
    model: UserModel,

    /// Whether the system is running
    running: bool,
}

impl LearningSystem {
    /// Create a new learning system
    pub fn new(config: LearningSystemConfig) -> Self {
        // Ensure data directory exists
        if let Err(e) = std::fs::create_dir_all(&config.data_dir) {
            log::warn!("Failed to create learning data directory: {}", e);
        }

        let collector = LearningCollector::new(config.collection.clone(), config.data_dir.clone());
        let privacy_filter = PrivacyFilter::new(config.privacy.clone());
        let trainer = LocalTrainer::new(config.training.clone());
        let model = UserModel::load_or_create(&config.data_dir.join("model.json"));

        Self {
            config,
            collector,
            privacy_filter,
            trainer,
            model,
            running: false,
        }
    }

    /// Start the learning system
    pub fn start(&mut self) {
        if !self.config.enabled {
            log::info!("Learning system is disabled");
            return;
        }

        log::info!("Starting learning system");
        self.running = true;

        // Clean up old data
        self.cleanup_old_data();
    }

    /// Stop the learning system
    pub fn stop(&mut self) {
        if self.running {
            log::info!("Stopping learning system");

            // Save the model
            if let Err(e) = self.model.save(&self.config.data_dir.join("model.json")) {
                log::error!("Failed to save user model: {}", e);
            }

            // Flush any pending data
            if let Err(e) = self.collector.flush() {
                log::error!("Failed to flush collector: {}", e);
            }

            self.running = false;
        }
    }

    /// Record a command event
    pub fn record_command(
        &mut self,
        command: &str,
        output: Option<&str>,
        exit_code: i32,
        duration_ms: u64,
    ) {
        if !self.running || !self.config.collection.collect_commands {
            return;
        }

        // Filter sensitive data
        let filtered_command = self.privacy_filter.filter_command(command);
        let filtered_output = output.map(|o| self.privacy_filter.filter_output(o));

        let event = CommandEvent {
            command: filtered_command,
            output: filtered_output,
            exit_code,
            duration_ms,
            timestamp: chrono::Utc::now(),
            working_dir: std::env::current_dir().ok(),
        };

        if let Err(e) = self.collector.record_command(event) {
            log::warn!("Failed to record command: {}", e);
        }
    }

    /// Record an AI interaction
    pub fn record_ai_interaction(&mut self, query: &str, response: &str, was_helpful: bool) {
        if !self.running || !self.config.collection.collect_ai_interactions {
            return;
        }

        let filtered_query = self.privacy_filter.filter_command(query);
        let filtered_response = self.privacy_filter.filter_output(response);

        let event = InteractionEvent {
            query: filtered_query,
            response: filtered_response,
            was_helpful,
            timestamp: chrono::Utc::now(),
        };

        if let Err(e) = self.collector.record_interaction(event) {
            log::warn!("Failed to record AI interaction: {}", e);
        }
    }

    /// Record an error
    pub fn record_error(&mut self, error: &str, command: Option<&str>) {
        if !self.running || !self.config.collection.collect_errors {
            return;
        }

        let filtered_error = self.privacy_filter.filter_output(error);
        let filtered_command = command.map(|c| self.privacy_filter.filter_command(c));

        if let Err(e) = self.collector.record_error(&filtered_error, filtered_command.as_deref()) {
            log::warn!("Failed to record error: {}", e);
        }
    }

    /// Get suggestions for next command
    pub fn suggest_next(&self, context: &SuggestionContext) -> Vec<Suggestion> {
        if !self.running {
            return Vec::new();
        }

        self.model.suggest_next_command(context)
    }

    /// Get explanation for an error
    pub fn explain_error(&self, error: &str) -> Option<String> {
        if !self.running {
            return None;
        }

        self.model.explain_error(error)
    }

    /// Predict intent from partial input
    pub fn predict_intent(&self, partial: &str) -> Vec<String> {
        if !self.running {
            return Vec::new();
        }

        self.model.predict_intent(partial)
    }

    /// Train the model with collected data
    pub fn train(&mut self) -> Result<TrainingStats, LearningError> {
        if !self.running {
            return Err(LearningError::NotRunning);
        }

        log::info!("Starting model training");

        // Get collected data
        let events = self.collector.get_recent_events()?;

        // Train the model
        let stats = self.trainer.train(&mut self.model, &events)?;

        // Save the updated model
        self.model.save(&self.config.data_dir.join("model.json"))?;

        log::info!("Training complete: {:?}", stats);
        Ok(stats)
    }

    /// Get learning statistics
    pub fn stats(&self) -> LearningStats {
        LearningStats {
            enabled: self.config.enabled,
            running: self.running,
            commands_collected: self.collector.command_count(),
            interactions_collected: self.collector.interaction_count(),
            errors_collected: self.collector.error_count(),
            model_version: self.model.version(),
            last_training: self.model.last_trained(),
            data_size_bytes: self.calculate_data_size(),
        }
    }

    /// Calculate total data size
    fn calculate_data_size(&self) -> u64 {
        walkdir::WalkDir::new(&self.config.data_dir)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
            .filter_map(|e| e.metadata().ok())
            .map(|m| m.len())
            .sum()
    }

    /// Clean up old data
    fn cleanup_old_data(&self) {
        let cutoff = chrono::Utc::now()
            - chrono::Duration::days(self.config.max_data_age_days as i64);

        if let Err(e) = self.collector.cleanup_before(cutoff) {
            log::warn!("Failed to cleanup old data: {}", e);
        }
    }

    /// Export collected data
    pub fn export_data(&self, path: &PathBuf) -> Result<(), LearningError> {
        self.collector.export(path)
    }

    /// Delete all collected data
    pub fn delete_data(&mut self) -> Result<(), LearningError> {
        log::warn!("Deleting all learning data");

        // Clear collector
        self.collector.clear()?;

        // Reset model
        self.model = UserModel::new();

        // Delete data directory contents
        for entry in std::fs::read_dir(&self.config.data_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_file() {
                std::fs::remove_file(path)?;
            } else if path.is_dir() {
                std::fs::remove_dir_all(path)?;
            }
        }

        Ok(())
    }

    /// Update configuration
    pub fn update_config(&mut self, config: LearningSystemConfig) {
        let was_running = self.running;

        if was_running {
            self.stop();
        }

        self.config = config.clone();
        self.collector = LearningCollector::new(config.collection, config.data_dir.clone());
        self.privacy_filter = PrivacyFilter::new(config.privacy);
        self.trainer = LocalTrainer::new(config.training);

        if was_running && config.enabled {
            self.start();
        }
    }

    /// Check if system is running
    pub fn is_running(&self) -> bool {
        self.running
    }

    /// Get current configuration
    pub fn config(&self) -> &LearningSystemConfig {
        &self.config
    }
}

impl Drop for LearningSystem {
    fn drop(&mut self) {
        self.stop();
    }
}

/// Learning system statistics
#[derive(Debug, Clone)]
pub struct LearningStats {
    /// Whether learning is enabled
    pub enabled: bool,

    /// Whether the system is currently running
    pub running: bool,

    /// Number of commands collected
    pub commands_collected: usize,

    /// Number of AI interactions collected
    pub interactions_collected: usize,

    /// Number of errors collected
    pub errors_collected: usize,

    /// Model version
    pub model_version: u32,

    /// Last training timestamp
    pub last_training: Option<chrono::DateTime<chrono::Utc>>,

    /// Total data size in bytes
    pub data_size_bytes: u64,
}

/// Learning system errors
#[derive(Debug, thiserror::Error)]
pub enum LearningError {
    #[error("Learning system is not running")]
    NotRunning,

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Training error: {0}")]
    Training(String),

    #[error("Model error: {0}")]
    Model(String),
}

/// Create a default learning system
pub fn create_learning_system() -> Arc<std::sync::Mutex<LearningSystem>> {
    let config = LearningSystemConfig::default();
    Arc::new(std::sync::Mutex::new(LearningSystem::new(config)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_learning_system_config_default() {
        let config = LearningSystemConfig::default();
        assert!(!config.enabled);
        assert_eq!(config.max_data_age_days, 30);
    }

    #[test]
    fn test_learning_system_new() {
        let config = LearningSystemConfig::default();
        let system = LearningSystem::new(config);
        assert!(!system.is_running());
    }

    #[test]
    fn test_learning_stats() {
        let config = LearningSystemConfig::default();
        let system = LearningSystem::new(config);
        let stats = system.stats();
        assert!(!stats.enabled);
        assert!(!stats.running);
    }
}
