//! Voice Input for CX Terminal
//!
//! Provides voice-activated terminal control and AI queries:
//! - Push-to-talk voice commands
//! - Speech-to-text via Whisper (local) or cloud
//! - Voice-activated AI queries
//! - Natural language command execution

mod capture;
mod commands;
mod transcribe;

pub use capture::{AudioCapture, AudioConfig, CaptureState, VoiceActivityDetector};
pub use commands::{VoiceCommand, VoiceCommandHandler, VoiceCommandResult};
pub use transcribe::{TranscribeError, Transcriber, WhisperCloud, WhisperLocal};

use std::path::PathBuf;
use std::sync::Arc;

/// Voice input configuration
#[derive(Debug, Clone)]
pub struct VoiceConfig {
    /// Whether voice input is enabled
    pub enabled: bool,

    /// Audio sample rate (default: 16000 Hz)
    pub sample_rate: u32,

    /// Audio channels (default: 1 - mono)
    pub channels: u16,

    /// Push-to-talk keybinding (default: Ctrl+Shift+V)
    pub push_to_talk_key: String,

    /// Whether to use voice activity detection
    pub use_vad: bool,

    /// VAD sensitivity (0.0 - 1.0)
    pub vad_sensitivity: f32,

    /// Transcription backend
    pub transcription_backend: TranscriptionBackend,

    /// Whisper model path (for local transcription)
    pub whisper_model_path: Option<PathBuf>,

    /// Cloud API endpoint (for cloud transcription)
    pub cloud_api_endpoint: Option<String>,

    /// Cloud API key
    pub cloud_api_key: Option<String>,

    /// Maximum recording duration in seconds
    pub max_recording_duration: f32,

    /// Minimum audio level to trigger VAD
    pub vad_threshold: f32,
}

impl Default for VoiceConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            sample_rate: 16000,
            channels: 1,
            push_to_talk_key: "Ctrl+Shift+V".to_string(),
            use_vad: false,
            vad_sensitivity: 0.5,
            transcription_backend: TranscriptionBackend::Local,
            whisper_model_path: None,
            cloud_api_endpoint: None,
            cloud_api_key: None,
            max_recording_duration: 30.0,
            vad_threshold: 0.01,
        }
    }
}

impl VoiceConfig {
    /// Get the default Whisper model path
    pub fn default_whisper_model_path() -> PathBuf {
        dirs_next::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("cx-terminal")
            .join("whisper-base.bin")
    }

    /// Check if transcription is available
    pub fn is_transcription_available(&self) -> bool {
        match self.transcription_backend {
            TranscriptionBackend::Local => self
                .whisper_model_path
                .as_ref()
                .map(|p| p.exists())
                .unwrap_or(false),
            TranscriptionBackend::Cloud => {
                self.cloud_api_endpoint.is_some() && self.cloud_api_key.is_some()
            }
            TranscriptionBackend::None => false,
        }
    }
}

/// Transcription backend type
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TranscriptionBackend {
    /// No transcription
    None,
    /// Local Whisper model
    Local,
    /// Cloud-based transcription (Whisper API, etc.)
    Cloud,
}

impl TranscriptionBackend {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "local" | "whisper" | "whisper.cpp" => Self::Local,
            "cloud" | "api" | "openai" => Self::Cloud,
            _ => Self::None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Local => "local",
            Self::Cloud => "cloud",
        }
    }
}

/// Voice input state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoiceInputState {
    /// Idle, waiting for activation
    Idle,
    /// Push-to-talk key held, recording
    Recording,
    /// Processing audio
    Processing,
    /// Transcribing audio
    Transcribing,
    /// Executing command
    Executing,
    /// Error occurred
    Error,
}

impl VoiceInputState {
    pub fn is_active(&self) -> bool {
        matches!(
            self,
            Self::Recording | Self::Processing | Self::Transcribing | Self::Executing
        )
    }

    pub fn status_text(&self) -> &'static str {
        match self {
            Self::Idle => "Ready",
            Self::Recording => "Recording...",
            Self::Processing => "Processing...",
            Self::Transcribing => "Transcribing...",
            Self::Executing => "Executing...",
            Self::Error => "Error",
        }
    }

    pub fn status_icon(&self) -> &'static str {
        match self {
            Self::Idle => "", // nf-fa-microphone
            Self::Recording => "", // nf-fa-circle (recording indicator)
            Self::Processing => "", // nf-fa-cog
            Self::Transcribing => "", // nf-fa-comment
            Self::Executing => "", // nf-fa-play
            Self::Error => "", // nf-fa-exclamation_triangle
        }
    }
}

/// Voice input manager
///
/// Coordinates audio capture, transcription, and command handling.
pub struct VoiceInputManager {
    /// Configuration
    config: VoiceConfig,

    /// Audio capture
    capture: Option<AudioCapture>,

    /// Transcriber
    transcriber: Option<Arc<dyn Transcriber + Send + Sync>>,

    /// Command handler
    command_handler: VoiceCommandHandler,

    /// Current state
    state: VoiceInputState,

    /// Audio buffer for current recording
    audio_buffer: Vec<i16>,

    /// Last transcription result
    last_transcription: Option<String>,

    /// Last error message
    last_error: Option<String>,
}

impl VoiceInputManager {
    /// Create a new voice input manager
    pub fn new(config: VoiceConfig) -> Self {
        let transcriber: Option<Arc<dyn Transcriber + Send + Sync>> =
            match config.transcription_backend {
                TranscriptionBackend::Local => {
                    let model_path = config
                        .whisper_model_path
                        .clone()
                        .unwrap_or_else(VoiceConfig::default_whisper_model_path);
                    Some(Arc::new(WhisperLocal::new(model_path)))
                }
                TranscriptionBackend::Cloud => config.cloud_api_endpoint.as_ref().map(|endpoint| {
                    Arc::new(WhisperCloud::new(
                        endpoint.clone(),
                        config.cloud_api_key.clone().unwrap_or_default(),
                    )) as Arc<dyn Transcriber + Send + Sync>
                }),
                TranscriptionBackend::None => None,
            };

        Self {
            config,
            capture: None,
            transcriber,
            command_handler: VoiceCommandHandler::new(),
            state: VoiceInputState::Idle,
            audio_buffer: Vec::new(),
            last_transcription: None,
            last_error: None,
        }
    }

    /// Get current state
    pub fn state(&self) -> VoiceInputState {
        self.state
    }

    /// Check if voice input is enabled
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Check if currently recording
    pub fn is_recording(&self) -> bool {
        self.state == VoiceInputState::Recording
    }

    /// Start recording (push-to-talk pressed)
    pub fn start_recording(&mut self) -> Result<(), VoiceError> {
        if !self.config.enabled {
            return Err(VoiceError::Disabled);
        }

        if self.state.is_active() {
            return Err(VoiceError::AlreadyActive);
        }

        // Clear previous audio buffer
        self.audio_buffer.clear();
        self.last_error = None;

        // Initialize audio capture if needed
        if self.capture.is_none() {
            let audio_config = AudioConfig {
                sample_rate: self.config.sample_rate,
                channels: self.config.channels,
                buffer_size: 1024,
            };
            self.capture = Some(AudioCapture::new(audio_config)?);
        }

        if let Some(capture) = &mut self.capture {
            capture.start()?;
        }

        self.state = VoiceInputState::Recording;
        log::info!("Voice recording started");
        Ok(())
    }

    /// Stop recording (push-to-talk released)
    pub fn stop_recording(&mut self) -> Result<Option<String>, VoiceError> {
        if self.state != VoiceInputState::Recording {
            return Ok(None);
        }

        // Stop audio capture
        if let Some(capture) = &mut self.capture {
            self.audio_buffer = capture.stop()?;
        }

        log::info!(
            "Voice recording stopped, {} samples captured",
            self.audio_buffer.len()
        );

        // Check if we have enough audio
        let min_samples = (self.config.sample_rate as f32 * 0.5) as usize; // 0.5 seconds minimum
        if self.audio_buffer.len() < min_samples {
            self.state = VoiceInputState::Idle;
            return Ok(None);
        }

        // Process the audio
        self.process_audio()
    }

    /// Process recorded audio
    fn process_audio(&mut self) -> Result<Option<String>, VoiceError> {
        self.state = VoiceInputState::Processing;

        // Apply any audio preprocessing (noise reduction, etc.)
        let processed_audio = self.preprocess_audio(&self.audio_buffer);

        self.state = VoiceInputState::Transcribing;

        // Transcribe the audio
        let transcription = if let Some(transcriber) = &self.transcriber {
            // Note: In production, this would be async
            match transcriber.transcribe_sync(&processed_audio) {
                Ok(text) => {
                    self.last_transcription = Some(text.clone());
                    Some(text)
                }
                Err(e) => {
                    self.last_error = Some(e.to_string());
                    self.state = VoiceInputState::Error;
                    return Err(VoiceError::Transcription(e));
                }
            }
        } else {
            self.state = VoiceInputState::Error;
            self.last_error = Some("No transcriber configured".to_string());
            return Err(VoiceError::NoTranscriber);
        };

        self.state = VoiceInputState::Idle;
        Ok(transcription)
    }

    /// Preprocess audio (noise reduction, normalization)
    fn preprocess_audio(&self, audio: &[i16]) -> Vec<i16> {
        // Simple normalization
        let max_amplitude = audio.iter().map(|&s| s.abs()).max().unwrap_or(1) as f32;
        let scale = 32767.0 / max_amplitude.max(1.0);

        audio
            .iter()
            .map(|&s| ((s as f32) * scale * 0.95) as i16)
            .collect()
    }

    /// Parse transcription into a command
    pub fn parse_command(&self, transcription: &str) -> Option<VoiceCommand> {
        self.command_handler.parse(transcription)
    }

    /// Execute a voice command
    pub fn execute_command(&mut self, command: &VoiceCommand) -> VoiceCommandResult {
        self.state = VoiceInputState::Executing;
        let result = self.command_handler.execute(command);
        self.state = VoiceInputState::Idle;
        result
    }

    /// Get last transcription
    pub fn last_transcription(&self) -> Option<&str> {
        self.last_transcription.as_deref()
    }

    /// Get last error
    pub fn last_error(&self) -> Option<&str> {
        self.last_error.as_deref()
    }

    /// Update configuration
    pub fn update_config(&mut self, config: VoiceConfig) {
        self.config = config;
        // Reinitialize transcriber with new config
        self.transcriber = match self.config.transcription_backend {
            TranscriptionBackend::Local => {
                let model_path = self
                    .config
                    .whisper_model_path
                    .clone()
                    .unwrap_or_else(VoiceConfig::default_whisper_model_path);
                Some(Arc::new(WhisperLocal::new(model_path)))
            }
            TranscriptionBackend::Cloud => {
                self.config.cloud_api_endpoint.as_ref().map(|endpoint| {
                    Arc::new(WhisperCloud::new(
                        endpoint.clone(),
                        self.config.cloud_api_key.clone().unwrap_or_default(),
                    )) as Arc<dyn Transcriber + Send + Sync>
                })
            }
            TranscriptionBackend::None => None,
        };
    }
}

/// Voice input errors
#[derive(Debug, thiserror::Error)]
pub enum VoiceError {
    #[error("Voice input is disabled")]
    Disabled,

    #[error("Voice input is already active")]
    AlreadyActive,

    #[error("Audio capture error: {0}")]
    Capture(#[from] capture::CaptureError),

    #[error("Transcription error: {0}")]
    Transcription(#[from] TranscribeError),

    #[error("No transcriber configured")]
    NoTranscriber,

    #[error("Command execution error: {0}")]
    Command(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_voice_config_default() {
        let config = VoiceConfig::default();
        assert!(!config.enabled);
        assert_eq!(config.sample_rate, 16000);
        assert_eq!(config.channels, 1);
    }

    #[test]
    fn test_voice_input_state() {
        assert!(!VoiceInputState::Idle.is_active());
        assert!(VoiceInputState::Recording.is_active());
        assert!(VoiceInputState::Processing.is_active());
        assert!(VoiceInputState::Transcribing.is_active());
    }

    #[test]
    fn test_transcription_backend_from_str() {
        assert_eq!(
            TranscriptionBackend::from_str("local"),
            TranscriptionBackend::Local
        );
        assert_eq!(
            TranscriptionBackend::from_str("cloud"),
            TranscriptionBackend::Cloud
        );
        assert_eq!(
            TranscriptionBackend::from_str("unknown"),
            TranscriptionBackend::None
        );
    }
}
