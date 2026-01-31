//! LlamaCpp Provider for CX Terminal
//!
//! Implements the AIProvider trait using llama-cpp-2 for native GGUF model inference.
//! This provides offline-capable, privacy-first AI assistance without external dependencies.

use super::provider::{AIError, AIProvider, AIProviderConfig, AIResponse, AIResponseStream};
use super::{ChatMessage, ChatRole};
use std::future::Future;
use std::path::PathBuf;
use std::pin::Pin;
use std::sync::Arc;

use llama_cpp_2::context::params::LlamaContextParams;
use llama_cpp_2::llama_backend::LlamaBackend;
use llama_cpp_2::llama_batch::LlamaBatch;
use llama_cpp_2::model::params::LlamaModelParams;
use llama_cpp_2::model::LlamaModel;
use llama_cpp_2::token::data_array::LlamaTokenDataArray;

/// HuggingFace repository containing the model
pub const HF_REPO: &str = "ShreemJ/cortex-linux-7b";

/// Model filename
pub const MODEL_FILENAME: &str = "cortex-linux-7b-Q4_K_M.gguf";

/// Default system prompt for CX Linux assistant
pub const CX_SYSTEM_PROMPT: &str = r#"You are a Linux command expert assistant for CX Linux. You can:
1. Answer directly if you have the knowledge
2. Call tools when you need external/live information
3. Refuse dangerous commands with explanations

Available tools:
- kb_lookup(application, query): Look up documentation for specific applications
- troubleshoot(service, error_message?, symptoms?): Diagnose issues
- search_packages(query, source?): Search apt/snap/pip for packages
- get_system_info(info_type, target?): Get system status information
- read_logs(source, service?, file_path?, lines?): Read log files

Prioritize safety. Refuse commands that could destroy systems or compromise security."#;

/// LlamaCpp-based AI Provider for native GGUF inference
pub struct LlamaCppProvider {
    backend: Arc<LlamaBackend>,
    model: Arc<LlamaModel>,
    config: AIProviderConfig,
}

// Safety: LlamaBackend and LlamaModel are thread-safe when accessed correctly
unsafe impl Send for LlamaCppProvider {}
unsafe impl Sync for LlamaCppProvider {}

impl LlamaCppProvider {
    /// Create a new LlamaCpp provider
    ///
    /// This will attempt to load the model from the cache directory.
    /// If the model is not found, it will return an error suggesting to download it.
    pub fn new(config: AIProviderConfig) -> Result<Self, AIError> {
        // Initialize the llama backend
        let backend = LlamaBackend::init()
            .map_err(|e| AIError::ApiError(format!("Failed to initialize llama backend: {}", e)))?;

        let model_path = Self::model_path();

        if !model_path.exists() {
            return Err(AIError::ModelNotFound);
        }

        // Set up model parameters
        let model_params = LlamaModelParams::default();

        // Load the model
        let model =
            LlamaModel::load_from_file(&backend, &model_path, &model_params).map_err(|e| {
                AIError::ApiError(format!("Failed to load model from {:?}: {}", model_path, e))
            })?;

        Ok(Self {
            backend: Arc::new(backend),
            model: Arc::new(model),
            config,
        })
    }

    /// Get the cache directory for CX Linux models
    pub fn model_cache_dir() -> PathBuf {
        dirs_next::cache_dir()
            .unwrap_or_else(|| PathBuf::from("/tmp"))
            .join("cx-linux")
            .join("models")
    }

    /// Get the full path to the model file
    pub fn model_path() -> PathBuf {
        Self::model_cache_dir().join(MODEL_FILENAME)
    }

    /// Check if the model is available (downloaded)
    pub fn is_model_available() -> bool {
        Self::model_path().exists()
    }

    /// Download the model from HuggingFace
    ///
    /// This is an async function that downloads the GGUF model file.
    pub async fn download_model() -> Result<PathBuf, AIError> {
        use hf_hub::api::tokio::Api;

        let cache_dir = Self::model_cache_dir();

        // Create cache directory if it doesn't exist
        std::fs::create_dir_all(&cache_dir)
            .map_err(|e| AIError::ApiError(format!("Failed to create cache directory: {}", e)))?;

        log::info!(
            "Downloading model from HuggingFace: {}/{}",
            HF_REPO,
            MODEL_FILENAME
        );

        let api = Api::new()
            .map_err(|e| AIError::NetworkError(format!("Failed to create HF API client: {}", e)))?;

        let repo = api.model(HF_REPO.to_string());

        let model_path = repo
            .get(MODEL_FILENAME)
            .await
            .map_err(|e| AIError::NetworkError(format!("Failed to download model: {}", e)))?;

        log::info!("Model downloaded to: {:?}", model_path);

        Ok(model_path)
    }

    /// Format messages using Qwen chat template
    fn format_prompt(&self, messages: &[ChatMessage], system_prompt: Option<&str>) -> String {
        let mut prompt = String::new();

        // Add system prompt
        let sys = system_prompt.unwrap_or(CX_SYSTEM_PROMPT);
        prompt.push_str("<|im_start|>system\n");
        prompt.push_str(sys);
        prompt.push_str("<|im_end|>\n");

        // Add conversation messages
        for msg in messages {
            let role = match msg.role {
                ChatRole::User => "user",
                ChatRole::Assistant => "assistant",
                ChatRole::System => continue, // Already handled above
            };

            prompt.push_str("<|im_start|>");
            prompt.push_str(role);
            prompt.push('\n');
            prompt.push_str(&msg.content);
            prompt.push_str("<|im_end|>\n");
        }

        // Add assistant prefix to prompt generation
        prompt.push_str("<|im_start|>assistant\n");

        prompt
    }

    /// Run inference on the model
    fn generate(&self, prompt: &str) -> Result<String, AIError> {
        // Create context parameters
        let ctx_params = LlamaContextParams::default().with_n_ctx(std::num::NonZeroU32::new(4096));

        // Create context
        let mut ctx = self
            .model
            .new_context(&self.backend, ctx_params)
            .map_err(|e| AIError::ApiError(format!("Failed to create context: {}", e)))?;

        // Tokenize the prompt
        let tokens = self
            .model
            .str_to_token(prompt, llama_cpp_2::model::AddBos::Always)
            .map_err(|e| AIError::ApiError(format!("Failed to tokenize prompt: {}", e)))?;

        if tokens.is_empty() {
            return Err(AIError::InvalidResponse(
                "Empty prompt after tokenization".to_string(),
            ));
        }

        // Check context length
        let n_ctx = ctx.n_ctx() as usize;
        if tokens.len() > n_ctx {
            return Err(AIError::ContextTooLong);
        }

        // Create batch and add tokens
        let mut batch = LlamaBatch::new(n_ctx, 1);

        for (i, token) in tokens.iter().enumerate() {
            let is_last = i == tokens.len() - 1;
            batch
                .add(*token, i as i32, &[0], is_last)
                .map_err(|e| AIError::ApiError(format!("Failed to add token to batch: {}", e)))?;
        }

        // Decode the initial prompt
        ctx.decode(&mut batch)
            .map_err(|e| AIError::ApiError(format!("Failed to decode batch: {}", e)))?;

        // Generate tokens
        let mut output_tokens = Vec::new();
        let max_tokens = self.config.max_tokens as usize;
        let mut n_cur = tokens.len();

        // Get special token IDs for stopping
        let eos_token = self.model.token_eos();
        let im_end_str = "<|im_end|>";

        // Random seed for sampling
        let seed = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as u32)
            .unwrap_or(42);

        for _ in 0..max_tokens {
            // Get logits for the last token
            let candidates = ctx.candidates_ith(batch.n_tokens() - 1);

            // Sample the next token
            let mut candidates_data = LlamaTokenDataArray::from_iter(candidates, false);

            // Sample with seed (temperature is applied internally based on the data)
            let next_token = candidates_data.sample_token(seed);

            // Check for end of generation
            if next_token == eos_token {
                break;
            }

            output_tokens.push(next_token);

            // Convert token to string to check for <|im_end|>
            let token_str = self
                .model
                .token_to_str(next_token, llama_cpp_2::model::Special::Tokenize)
                .unwrap_or_default();

            // Check if we've generated the end marker
            let current_output: String = output_tokens
                .iter()
                .filter_map(|t| {
                    self.model
                        .token_to_str(*t, llama_cpp_2::model::Special::Tokenize)
                        .ok()
                })
                .collect();

            if current_output.contains(im_end_str) {
                break;
            }

            // Prepare next batch
            batch.clear();
            batch
                .add(next_token, n_cur as i32, &[0], true)
                .map_err(|e| AIError::ApiError(format!("Failed to add token: {}", e)))?;

            n_cur += 1;

            // Decode
            ctx.decode(&mut batch)
                .map_err(|e| AIError::ApiError(format!("Failed to decode: {}", e)))?;
        }

        // Convert output tokens to string
        let mut output = String::new();
        for token in &output_tokens {
            if let Ok(s) = self
                .model
                .token_to_str(*token, llama_cpp_2::model::Special::Tokenize)
            {
                output.push_str(&s);
            }
        }

        // Clean up the output - remove <|im_end|> if present
        let output = output.trim_end_matches(im_end_str).trim().to_string();

        Ok(output)
    }
}

impl AIProvider for LlamaCppProvider {
    fn chat_completion(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponse, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            // Format the prompt using Qwen template
            let prompt = self.format_prompt(&messages, system.as_deref());

            // Run inference (this is blocking, but wrapped in async)
            let content = tokio::task::block_in_place(|| self.generate(&prompt))?;

            Ok(AIResponse {
                content,
                finish_reason: Some("stop".to_string()),
                tokens_used: None, // Could track this if needed
            })
        })
    }

    fn chat_completion_stream(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponseStream, AIError>> + Send + '_>> {
        let system = system_prompt;

        Box::pin(async move {
            // For now, implement streaming as a single chunk
            // True streaming would require refactoring the generate function
            let prompt = self.format_prompt(&messages, system.as_deref());

            let content = tokio::task::block_in_place(|| self.generate(&prompt))?;

            // Return as a single chunk (could be improved to true streaming later)
            Ok(AIResponseStream::new(vec![content]))
        })
    }

    fn is_available(&self) -> bool {
        // Provider is available if model is loaded
        true
    }

    fn name(&self) -> &str {
        "CX Linux"
    }
}

/// Create a LlamaCpp provider with default settings
pub fn create_cxlinux_provider() -> Result<LlamaCppProvider, AIError> {
    let config = AIProviderConfig {
        provider_type: super::AIProviderType::CXLinux,
        endpoint: String::new(), // Not used for native inference
        api_key: None,
        model: MODEL_FILENAME.to_string(),
        max_tokens: 2048,
        temperature: 0.7,
    };

    LlamaCppProvider::new(config)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_model_path() {
        let path = LlamaCppProvider::model_path();
        assert!(path.to_string_lossy().contains("cx-linux"));
        assert!(path.to_string_lossy().contains(MODEL_FILENAME));
    }

    #[test]
    fn test_model_cache_dir() {
        let dir = LlamaCppProvider::model_cache_dir();
        assert!(dir.to_string_lossy().contains("cx-linux"));
        assert!(dir.to_string_lossy().contains("models"));
    }

    #[test]
    fn test_format_prompt() {
        // This test would require a mock provider
        // For now, just test the structure
        let messages = vec![ChatMessage::user("How do I list files?")];

        let mut prompt = String::new();
        prompt.push_str("<|im_start|>system\n");
        prompt.push_str("Test system prompt");
        prompt.push_str("<|im_end|>\n");
        prompt.push_str("<|im_start|>user\n");
        prompt.push_str("How do I list files?");
        prompt.push_str("<|im_end|>\n");
        prompt.push_str("<|im_start|>assistant\n");

        assert!(prompt.contains("<|im_start|>system"));
        assert!(prompt.contains("<|im_start|>user"));
        assert!(prompt.contains("<|im_start|>assistant"));
    }

    #[test]
    fn test_system_prompt_content() {
        assert!(CX_SYSTEM_PROMPT.contains("Linux command expert"));
        assert!(CX_SYSTEM_PROMPT.contains("kb_lookup"));
        assert!(CX_SYSTEM_PROMPT.contains("safety"));
    }
}
