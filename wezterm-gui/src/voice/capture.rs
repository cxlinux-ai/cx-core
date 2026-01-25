//! Audio Capture for Voice Input
//!
//! Provides audio capture functionality for voice commands:
//! - Push-to-talk recording
//! - Voice Activity Detection (VAD)
//! - Audio format: 16kHz mono PCM

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

/// Audio capture configuration
#[derive(Debug, Clone)]
pub struct AudioConfig {
    /// Sample rate in Hz (default: 16000)
    pub sample_rate: u32,

    /// Number of channels (default: 1 - mono)
    pub channels: u16,

    /// Buffer size in samples
    pub buffer_size: usize,
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000,
            channels: 1,
            buffer_size: 1024,
        }
    }
}

/// Audio capture state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CaptureState {
    /// Not initialized
    Uninitialized,
    /// Ready to record
    Ready,
    /// Currently recording
    Recording,
    /// Stopped, audio available
    Stopped,
    /// Error state
    Error,
}

/// Audio capture errors
#[derive(Debug, thiserror::Error)]
pub enum CaptureError {
    #[error("Failed to initialize audio device: {0}")]
    DeviceInit(String),

    #[error("Failed to start recording: {0}")]
    StartRecording(String),

    #[error("Failed to stop recording: {0}")]
    StopRecording(String),

    #[error("No audio device available")]
    NoDevice,

    #[error("Audio capture not initialized")]
    NotInitialized,

    #[error("Audio capture already running")]
    AlreadyRunning,

    #[error("Buffer overflow")]
    BufferOverflow,
}

/// Voice Activity Detector
///
/// Simple energy-based VAD to detect speech.
pub struct VoiceActivityDetector {
    /// Threshold for detecting voice activity
    threshold: f32,

    /// Minimum consecutive frames of activity to trigger
    min_active_frames: usize,

    /// Minimum consecutive frames of silence to stop
    min_silent_frames: usize,

    /// Current consecutive active frames
    active_frame_count: usize,

    /// Current consecutive silent frames
    silent_frame_count: usize,

    /// Whether speech is currently detected
    is_active: bool,

    /// Energy history for adaptive thresholding
    energy_history: Vec<f32>,

    /// Maximum history size
    history_size: usize,
}

impl VoiceActivityDetector {
    /// Create a new VAD with the given threshold
    pub fn new(threshold: f32) -> Self {
        Self {
            threshold,
            min_active_frames: 3,
            min_silent_frames: 10,
            active_frame_count: 0,
            silent_frame_count: 0,
            is_active: false,
            energy_history: Vec::new(),
            history_size: 50,
        }
    }

    /// Process a frame of audio samples
    ///
    /// Returns true if voice activity is detected.
    pub fn process(&mut self, samples: &[i16]) -> bool {
        let energy = self.compute_energy(samples);

        // Update energy history for adaptive thresholding
        self.energy_history.push(energy);
        if self.energy_history.len() > self.history_size {
            self.energy_history.remove(0);
        }

        // Compute adaptive threshold based on recent energy levels
        let adaptive_threshold = self.compute_adaptive_threshold();

        let is_active_frame = energy > adaptive_threshold;

        if is_active_frame {
            self.active_frame_count += 1;
            self.silent_frame_count = 0;

            if self.active_frame_count >= self.min_active_frames {
                self.is_active = true;
            }
        } else {
            self.silent_frame_count += 1;
            self.active_frame_count = 0;

            if self.silent_frame_count >= self.min_silent_frames {
                self.is_active = false;
            }
        }

        self.is_active
    }

    /// Compute the energy (RMS) of a frame
    fn compute_energy(&self, samples: &[i16]) -> f32 {
        if samples.is_empty() {
            return 0.0;
        }

        let sum_squares: f64 = samples.iter().map(|&s| (s as f64).powi(2)).sum();
        let rms = (sum_squares / samples.len() as f64).sqrt();

        // Normalize to 0.0 - 1.0 range
        (rms / 32768.0) as f32
    }

    /// Compute adaptive threshold based on energy history
    fn compute_adaptive_threshold(&self) -> f32 {
        if self.energy_history.is_empty() {
            return self.threshold;
        }

        // Use the 25th percentile of recent energy as noise floor
        let mut sorted = self.energy_history.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let percentile_idx = (sorted.len() as f32 * 0.25) as usize;
        let noise_floor = sorted.get(percentile_idx).copied().unwrap_or(0.0);

        // Threshold is noise floor + configured sensitivity
        (noise_floor + self.threshold).min(1.0)
    }

    /// Reset VAD state
    pub fn reset(&mut self) {
        self.active_frame_count = 0;
        self.silent_frame_count = 0;
        self.is_active = false;
        self.energy_history.clear();
    }

    /// Check if currently detecting voice activity
    pub fn is_active(&self) -> bool {
        self.is_active
    }
}

/// Audio capture device
///
/// Note: This is a stub implementation. In production, this would use
/// the cpal crate for cross-platform audio capture.
pub struct AudioCapture {
    /// Configuration
    config: AudioConfig,

    /// Current state
    state: CaptureState,

    /// Recording flag
    is_recording: Arc<AtomicBool>,

    /// Audio buffer
    buffer: Arc<Mutex<Vec<i16>>>,

    /// Voice activity detector
    vad: Option<VoiceActivityDetector>,
}

impl AudioCapture {
    /// Create a new audio capture device
    pub fn new(config: AudioConfig) -> Result<Self, CaptureError> {
        // In production, this would initialize the audio device using cpal:
        //
        // let host = cpal::default_host();
        // let device = host.default_input_device()
        //     .ok_or(CaptureError::NoDevice)?;
        //
        // let config = cpal::StreamConfig {
        //     channels: config.channels,
        //     sample_rate: cpal::SampleRate(config.sample_rate),
        //     buffer_size: cpal::BufferSize::Fixed(config.buffer_size as u32),
        // };

        log::info!(
            "Initializing audio capture: {}Hz, {} channels",
            config.sample_rate,
            config.channels
        );

        Ok(Self {
            config,
            state: CaptureState::Ready,
            is_recording: Arc::new(AtomicBool::new(false)),
            buffer: Arc::new(Mutex::new(Vec::new())),
            vad: None,
        })
    }

    /// Enable voice activity detection
    pub fn enable_vad(&mut self, threshold: f32) {
        self.vad = Some(VoiceActivityDetector::new(threshold));
    }

    /// Disable voice activity detection
    pub fn disable_vad(&mut self) {
        self.vad = None;
    }

    /// Start recording
    pub fn start(&mut self) -> Result<(), CaptureError> {
        if self.state == CaptureState::Uninitialized {
            return Err(CaptureError::NotInitialized);
        }

        if self.is_recording.load(Ordering::SeqCst) {
            return Err(CaptureError::AlreadyRunning);
        }

        // Clear the buffer
        if let Ok(mut buffer) = self.buffer.lock() {
            buffer.clear();
        }

        // Reset VAD state
        if let Some(vad) = &mut self.vad {
            vad.reset();
        }

        self.is_recording.store(true, Ordering::SeqCst);
        self.state = CaptureState::Recording;

        log::info!("Audio capture started");

        // In production, this would start the audio stream:
        //
        // let is_recording = self.is_recording.clone();
        // let buffer = self.buffer.clone();
        //
        // self.stream = Some(device.build_input_stream(
        //     &config,
        //     move |data: &[i16], _: &cpal::InputCallbackInfo| {
        //         if is_recording.load(Ordering::SeqCst) {
        //             if let Ok(mut buf) = buffer.lock() {
        //                 buf.extend_from_slice(data);
        //             }
        //         }
        //     },
        //     |err| log::error!("Audio capture error: {}", err),
        //     None,
        // )?);
        //
        // self.stream.as_ref().unwrap().play()?;

        Ok(())
    }

    /// Stop recording and return captured audio
    pub fn stop(&mut self) -> Result<Vec<i16>, CaptureError> {
        if !self.is_recording.load(Ordering::SeqCst) {
            return Ok(Vec::new());
        }

        self.is_recording.store(false, Ordering::SeqCst);
        self.state = CaptureState::Stopped;

        // In production, this would stop the audio stream:
        // drop(self.stream.take());

        let buffer = self
            .buffer
            .lock()
            .map_err(|_| CaptureError::StopRecording("Failed to lock buffer".to_string()))?
            .clone();

        log::info!("Audio capture stopped, {} samples captured", buffer.len());

        Ok(buffer)
    }

    /// Get current state
    pub fn state(&self) -> CaptureState {
        self.state
    }

    /// Check if currently recording
    pub fn is_recording(&self) -> bool {
        self.is_recording.load(Ordering::SeqCst)
    }

    /// Get configuration
    pub fn config(&self) -> &AudioConfig {
        &self.config
    }

    /// Get current buffer size
    pub fn buffer_size(&self) -> usize {
        self.buffer
            .lock()
            .map(|b| b.len())
            .unwrap_or(0)
    }

    /// Get audio duration in seconds
    pub fn duration(&self) -> f32 {
        let samples = self.buffer_size();
        samples as f32 / self.config.sample_rate as f32
    }

    /// Process audio samples (for VAD)
    ///
    /// Returns true if voice activity is detected.
    pub fn process_samples(&mut self, samples: &[i16]) -> bool {
        if let Some(vad) = &mut self.vad {
            vad.process(samples)
        } else {
            true // If VAD is disabled, always return true
        }
    }
}

/// Audio format utilities
pub mod format {
    /// Convert f32 samples to i16 PCM
    pub fn f32_to_i16(samples: &[f32]) -> Vec<i16> {
        samples
            .iter()
            .map(|&s| (s * 32767.0).clamp(-32768.0, 32767.0) as i16)
            .collect()
    }

    /// Convert i16 PCM to f32 samples
    pub fn i16_to_f32(samples: &[i16]) -> Vec<f32> {
        samples.iter().map(|&s| s as f32 / 32768.0).collect()
    }

    /// Resample audio to target sample rate
    ///
    /// Simple linear interpolation resampling.
    pub fn resample(samples: &[i16], source_rate: u32, target_rate: u32) -> Vec<i16> {
        if source_rate == target_rate {
            return samples.to_vec();
        }

        let ratio = source_rate as f64 / target_rate as f64;
        let output_len = (samples.len() as f64 / ratio) as usize;
        let mut output = Vec::with_capacity(output_len);

        for i in 0..output_len {
            let src_pos = i as f64 * ratio;
            let src_idx = src_pos as usize;
            let frac = src_pos - src_idx as f64;

            let sample = if src_idx + 1 < samples.len() {
                let s0 = samples[src_idx] as f64;
                let s1 = samples[src_idx + 1] as f64;
                (s0 + (s1 - s0) * frac) as i16
            } else if src_idx < samples.len() {
                samples[src_idx]
            } else {
                0
            };

            output.push(sample);
        }

        output
    }

    /// Convert stereo to mono
    pub fn stereo_to_mono(samples: &[i16]) -> Vec<i16> {
        samples
            .chunks(2)
            .map(|chunk| {
                let left = chunk.first().copied().unwrap_or(0) as i32;
                let right = chunk.get(1).copied().unwrap_or(0) as i32;
                ((left + right) / 2) as i16
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_config_default() {
        let config = AudioConfig::default();
        assert_eq!(config.sample_rate, 16000);
        assert_eq!(config.channels, 1);
    }

    #[test]
    fn test_vad_energy() {
        let vad = VoiceActivityDetector::new(0.01);

        // Silence should have low energy
        let silence: Vec<i16> = vec![0; 1024];
        let energy = vad.compute_energy(&silence);
        assert!(energy < 0.001);

        // Loud signal should have high energy
        let loud: Vec<i16> = vec![16384; 1024];
        let energy = vad.compute_energy(&loud);
        assert!(energy > 0.4);
    }

    #[test]
    fn test_format_conversion() {
        let i16_samples: Vec<i16> = vec![-16384, 0, 16383];
        let f32_samples = format::i16_to_f32(&i16_samples);

        assert!(f32_samples[0] < -0.4);
        assert!(f32_samples[1].abs() < 0.001);
        assert!(f32_samples[2] > 0.4);

        let back_to_i16 = format::f32_to_i16(&f32_samples);
        assert_eq!(back_to_i16.len(), i16_samples.len());
    }

    #[test]
    fn test_stereo_to_mono() {
        let stereo: Vec<i16> = vec![100, 200, -100, -200];
        let mono = format::stereo_to_mono(&stereo);

        assert_eq!(mono.len(), 2);
        assert_eq!(mono[0], 150); // (100 + 200) / 2
        assert_eq!(mono[1], -150); // (-100 + -200) / 2
    }
}
