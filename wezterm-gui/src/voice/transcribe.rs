//! Speech-to-Text Transcription
//!
//! Provides transcription backends for voice input:
//! - Local Whisper model (whisper.cpp)
//! - Cloud-based Whisper API

use std::path::PathBuf;

/// Transcription errors
#[derive(Debug, thiserror::Error)]
pub enum TranscribeError {
    #[error("Model not found: {0}")]
    ModelNotFound(PathBuf),

    #[error("Failed to load model: {0}")]
    ModelLoad(String),

    #[error("Transcription failed: {0}")]
    Transcription(String),

    #[error("API error: {status} - {message}")]
    Api { status: u16, message: String },

    #[error("Network error: {0}")]
    Network(String),

    #[error("Invalid audio format: {0}")]
    InvalidAudio(String),

    #[error("Timeout")]
    Timeout,
}

/// Transcription result with confidence
#[derive(Debug, Clone)]
pub struct TranscriptionResult {
    /// Transcribed text
    pub text: String,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f32,

    /// Language detected
    pub language: Option<String>,

    /// Duration of audio in seconds
    pub duration: f32,

    /// Word-level timestamps (if available)
    pub words: Vec<WordTimestamp>,
}

/// Word with timestamp
#[derive(Debug, Clone)]
pub struct WordTimestamp {
    /// The word
    pub word: String,

    /// Start time in seconds
    pub start: f32,

    /// End time in seconds
    pub end: f32,

    /// Confidence for this word
    pub confidence: f32,
}

/// Transcriber trait
///
/// Implemented by different transcription backends.
pub trait Transcriber: Send + Sync {
    /// Transcribe audio asynchronously
    fn transcribe(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, TranscribeError>> + Send + '_>>;

    /// Transcribe audio synchronously (blocking)
    fn transcribe_sync(&self, audio: &[i16]) -> Result<String, TranscribeError>;

    /// Transcribe with detailed result
    fn transcribe_detailed(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<TranscriptionResult, TranscribeError>> + Send + '_>>;

    /// Get the name of this transcriber
    fn name(&self) -> &str;

    /// Check if the transcriber is available
    fn is_available(&self) -> bool;
}

/// Local Whisper transcriber
///
/// Uses whisper.cpp for local transcription.
pub struct WhisperLocal {
    /// Path to the model file
    model_path: PathBuf,

    /// Model size/name
    model_name: String,

    /// Whether the model is loaded
    is_loaded: bool,

    /// Language to transcribe (None for auto-detect)
    language: Option<String>,
}

impl WhisperLocal {
    /// Create a new local Whisper transcriber
    pub fn new(model_path: PathBuf) -> Self {
        let model_name = model_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("whisper")
            .to_string();

        Self {
            model_path,
            model_name,
            is_loaded: false,
            language: None,
        }
    }

    /// Create with a specific model name
    pub fn with_model(model_name: &str) -> Self {
        let model_path = Self::default_model_path(model_name);
        Self {
            model_path,
            model_name: model_name.to_string(),
            is_loaded: false,
            language: None,
        }
    }

    /// Get the default model path for a model name
    pub fn default_model_path(model_name: &str) -> PathBuf {
        let base_dir = dirs_next::data_local_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("cx-terminal")
            .join("models");

        base_dir.join(format!("ggml-{}.bin", model_name))
    }

    /// Set the language for transcription
    pub fn set_language(&mut self, language: Option<String>) {
        self.language = language;
    }

    /// Load the model
    pub fn load(&mut self) -> Result<(), TranscribeError> {
        if !self.model_path.exists() {
            return Err(TranscribeError::ModelNotFound(self.model_path.clone()));
        }

        // In production, this would load the whisper.cpp model:
        //
        // let ctx = whisper_rs::WhisperContext::new(&self.model_path.to_string_lossy())
        //     .map_err(|e| TranscribeError::ModelLoad(e.to_string()))?;
        //
        // self.context = Some(ctx);

        log::info!("Loaded Whisper model: {}", self.model_path.display());
        self.is_loaded = true;
        Ok(())
    }

    /// Transcribe audio using the local model
    fn do_transcribe(&self, audio: &[i16]) -> Result<String, TranscribeError> {
        if !self.is_loaded && !self.model_path.exists() {
            return Err(TranscribeError::ModelNotFound(self.model_path.clone()));
        }

        // Validate audio
        if audio.is_empty() {
            return Err(TranscribeError::InvalidAudio("Empty audio buffer".to_string()));
        }

        // In production, this would use whisper.cpp:
        //
        // let mut state = self.context.as_ref().unwrap().create_state()
        //     .map_err(|e| TranscribeError::Transcription(e.to_string()))?;
        //
        // let mut params = whisper_rs::FullParams::new(whisper_rs::SamplingStrategy::Greedy { best_of: 1 });
        //
        // if let Some(lang) = &self.language {
        //     params.set_language(Some(lang));
        // }
        //
        // // Convert i16 to f32
        // let audio_f32: Vec<f32> = audio.iter().map(|&s| s as f32 / 32768.0).collect();
        //
        // state.full(params, &audio_f32)
        //     .map_err(|e| TranscribeError::Transcription(e.to_string()))?;
        //
        // let num_segments = state.full_n_segments()
        //     .map_err(|e| TranscribeError::Transcription(e.to_string()))?;
        //
        // let mut text = String::new();
        // for i in 0..num_segments {
        //     let segment = state.full_get_segment_text(i)
        //         .map_err(|e| TranscribeError::Transcription(e.to_string()))?;
        //     text.push_str(&segment);
        // }
        //
        // Ok(text.trim().to_string())

        // Stub implementation
        log::info!(
            "Would transcribe {} samples with model {}",
            audio.len(),
            self.model_name
        );
        Ok("[Transcription placeholder - whisper.cpp not integrated]".to_string())
    }
}

impl Transcriber for WhisperLocal {
    fn transcribe(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, TranscribeError>> + Send + '_>> {
        let audio = audio.to_vec();
        Box::pin(async move { self.do_transcribe(&audio) })
    }

    fn transcribe_sync(&self, audio: &[i16]) -> Result<String, TranscribeError> {
        self.do_transcribe(audio)
    }

    fn transcribe_detailed(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<TranscriptionResult, TranscribeError>> + Send + '_>> {
        let audio = audio.to_vec();
        Box::pin(async move {
            let text = self.do_transcribe(&audio)?;
            Ok(TranscriptionResult {
                text,
                confidence: 0.9, // Placeholder
                language: self.language.clone(),
                duration: audio.len() as f32 / 16000.0,
                words: Vec::new(),
            })
        })
    }

    fn name(&self) -> &str {
        &self.model_name
    }

    fn is_available(&self) -> bool {
        self.model_path.exists()
    }
}

/// Cloud-based Whisper transcriber
///
/// Uses OpenAI Whisper API or compatible endpoint.
pub struct WhisperCloud {
    /// API endpoint
    endpoint: String,

    /// API key
    api_key: String,

    /// Model to use (e.g., "whisper-1")
    model: String,

    /// Language hint
    language: Option<String>,

    /// Request timeout in seconds
    timeout_secs: u64,
}

impl WhisperCloud {
    /// Create a new cloud Whisper transcriber
    pub fn new(endpoint: String, api_key: String) -> Self {
        Self {
            endpoint,
            api_key,
            model: "whisper-1".to_string(),
            language: None,
            timeout_secs: 30,
        }
    }

    /// Create for OpenAI API
    pub fn openai(api_key: String) -> Self {
        Self::new(
            "https://api.openai.com/v1/audio/transcriptions".to_string(),
            api_key,
        )
    }

    /// Set the model
    pub fn set_model(&mut self, model: String) {
        self.model = model;
    }

    /// Set the language hint
    pub fn set_language(&mut self, language: Option<String>) {
        self.language = language;
    }

    /// Set the timeout
    pub fn set_timeout(&mut self, secs: u64) {
        self.timeout_secs = secs;
    }

    /// Transcribe audio using the cloud API
    async fn do_transcribe(&self, audio: &[i16]) -> Result<String, TranscribeError> {
        // Validate audio
        if audio.is_empty() {
            return Err(TranscribeError::InvalidAudio("Empty audio buffer".to_string()));
        }

        // Convert to WAV format for API
        let wav_data = self.encode_wav(audio)?;

        // In production, this would make an HTTP request:
        //
        // use reqwest::multipart::{Form, Part};
        //
        // let client = reqwest::Client::new();
        //
        // let audio_part = Part::bytes(wav_data)
        //     .file_name("audio.wav")
        //     .mime_str("audio/wav")
        //     .map_err(|e| TranscribeError::Api {
        //         status: 0,
        //         message: e.to_string(),
        //     })?;
        //
        // let mut form = Form::new()
        //     .part("file", audio_part)
        //     .text("model", self.model.clone());
        //
        // if let Some(lang) = &self.language {
        //     form = form.text("language", lang.clone());
        // }
        //
        // let response = client
        //     .post(&self.endpoint)
        //     .bearer_auth(&self.api_key)
        //     .multipart(form)
        //     .timeout(std::time::Duration::from_secs(self.timeout_secs))
        //     .send()
        //     .await
        //     .map_err(|e| TranscribeError::Network(e.to_string()))?;
        //
        // if !response.status().is_success() {
        //     let status = response.status().as_u16();
        //     let message = response.text().await.unwrap_or_default();
        //     return Err(TranscribeError::Api { status, message });
        // }
        //
        // #[derive(serde::Deserialize)]
        // struct ApiResponse {
        //     text: String,
        // }
        //
        // let result: ApiResponse = response.json().await
        //     .map_err(|e| TranscribeError::Api {
        //         status: 0,
        //         message: e.to_string(),
        //     })?;
        //
        // Ok(result.text)

        // Stub implementation
        log::info!(
            "Would send {} bytes to {} for transcription",
            wav_data.len(),
            self.endpoint
        );
        Ok("[Cloud transcription placeholder]".to_string())
    }

    /// Encode audio as WAV
    fn encode_wav(&self, audio: &[i16]) -> Result<Vec<u8>, TranscribeError> {
        let mut wav = Vec::new();

        // WAV header
        let sample_rate: u32 = 16000;
        let channels: u16 = 1;
        let bits_per_sample: u16 = 16;
        let byte_rate = sample_rate * channels as u32 * bits_per_sample as u32 / 8;
        let block_align = channels * bits_per_sample / 8;
        let data_size = audio.len() as u32 * 2; // 2 bytes per sample
        let file_size = 36 + data_size;

        // RIFF header
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&file_size.to_le_bytes());
        wav.extend_from_slice(b"WAVE");

        // fmt chunk
        wav.extend_from_slice(b"fmt ");
        wav.extend_from_slice(&16u32.to_le_bytes()); // chunk size
        wav.extend_from_slice(&1u16.to_le_bytes()); // audio format (PCM)
        wav.extend_from_slice(&channels.to_le_bytes());
        wav.extend_from_slice(&sample_rate.to_le_bytes());
        wav.extend_from_slice(&byte_rate.to_le_bytes());
        wav.extend_from_slice(&block_align.to_le_bytes());
        wav.extend_from_slice(&bits_per_sample.to_le_bytes());

        // data chunk
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&data_size.to_le_bytes());

        // Audio data
        for &sample in audio {
            wav.extend_from_slice(&sample.to_le_bytes());
        }

        Ok(wav)
    }
}

impl Transcriber for WhisperCloud {
    fn transcribe(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, TranscribeError>> + Send + '_>> {
        let audio = audio.to_vec();
        Box::pin(async move { self.do_transcribe(&audio).await })
    }

    fn transcribe_sync(&self, audio: &[i16]) -> Result<String, TranscribeError> {
        // For sync, we'd need to block on the async operation
        // In production, this would use a runtime
        log::warn!("Sync transcription called on cloud provider - not recommended");
        Ok("[Sync cloud transcription not supported]".to_string())
    }

    fn transcribe_detailed(
        &self,
        audio: &[i16],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<TranscriptionResult, TranscribeError>> + Send + '_>> {
        let audio = audio.to_vec();
        Box::pin(async move {
            let text = self.do_transcribe(&audio).await?;
            Ok(TranscriptionResult {
                text,
                confidence: 0.95,
                language: self.language.clone(),
                duration: audio.len() as f32 / 16000.0,
                words: Vec::new(),
            })
        })
    }

    fn name(&self) -> &str {
        "whisper-cloud"
    }

    fn is_available(&self) -> bool {
        !self.api_key.is_empty()
    }
}

/// Download a Whisper model
///
/// Downloads the model file to the default location.
pub async fn download_model(model_name: &str) -> Result<PathBuf, TranscribeError> {
    let model_path = WhisperLocal::default_model_path(model_name);

    if model_path.exists() {
        log::info!("Model already exists: {}", model_path.display());
        return Ok(model_path);
    }

    // Create directory
    if let Some(parent) = model_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            TranscribeError::ModelLoad(format!("Failed to create directory: {}", e))
        })?;
    }

    // Model URLs (using Hugging Face mirror)
    let model_url = match model_name {
        "tiny" | "tiny.en" => {
            format!(
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin",
                model_name
            )
        }
        "base" | "base.en" => {
            format!(
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin",
                model_name
            )
        }
        "small" | "small.en" => {
            format!(
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin",
                model_name
            )
        }
        "medium" | "medium.en" => {
            format!(
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin",
                model_name
            )
        }
        "large" | "large-v1" | "large-v2" | "large-v3" => {
            format!(
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{}.bin",
                model_name
            )
        }
        _ => {
            return Err(TranscribeError::ModelLoad(format!(
                "Unknown model: {}",
                model_name
            )));
        }
    };

    log::info!("Downloading Whisper model from {}", model_url);

    // In production, this would download the file:
    //
    // let response = reqwest::get(&model_url).await
    //     .map_err(|e| TranscribeError::Network(e.to_string()))?;
    //
    // if !response.status().is_success() {
    //     return Err(TranscribeError::Network(format!(
    //         "Failed to download model: {}",
    //         response.status()
    //     )));
    // }
    //
    // let bytes = response.bytes().await
    //     .map_err(|e| TranscribeError::Network(e.to_string()))?;
    //
    // std::fs::write(&model_path, bytes)
    //     .map_err(|e| TranscribeError::ModelLoad(format!("Failed to write model: {}", e)))?;

    log::info!("Model downloaded to: {}", model_path.display());
    Ok(model_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_whisper_local_default_path() {
        let path = WhisperLocal::default_model_path("base");
        assert!(path.to_string_lossy().contains("ggml-base.bin"));
    }

    #[test]
    fn test_wav_encoding() {
        let cloud = WhisperCloud::new(
            "https://example.com".to_string(),
            "test-key".to_string(),
        );

        let audio: Vec<i16> = vec![0, 1000, -1000, 0];
        let wav = cloud.encode_wav(&audio).unwrap();

        // Check WAV header
        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(&wav[8..12], b"WAVE");
        assert_eq!(&wav[12..16], b"fmt ");
    }

    #[test]
    fn test_transcription_result() {
        let result = TranscriptionResult {
            text: "hello world".to_string(),
            confidence: 0.95,
            language: Some("en".to_string()),
            duration: 1.5,
            words: Vec::new(),
        };

        assert_eq!(result.text, "hello world");
        assert!(result.confidence > 0.9);
    }
}
