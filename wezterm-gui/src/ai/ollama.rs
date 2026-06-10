//! Native Llama Provider for CX Terminal
//!
//! Implements the AIProvider trait using the native C++ llama.cpp wrapper.

use super::provider::{AIError, AIProvider, AIProviderConfig, AIResponse, AIResponseStream};
use super::{ChatMessage, ChatRole};
use std::future::Future;
use std::pin::Pin;
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int, c_void};
use std::sync::Mutex;

extern "C" {
    fn cortex_model_load(model_path: *const c_char) -> c_int;
    fn cortex_infer_generate(prompt: *const c_char) -> *mut c_char;
    fn cortex_infer_generate_stream(
        prompt: *const c_char,
        callback: extern "C" fn(*const c_char, *mut c_void),
        user_data: *mut c_void,
    ) -> c_int;
}

pub struct OllamaProvider {
    config: AIProviderConfig,
    load_success: bool,
}

impl OllamaProvider {
    pub fn new(config: AIProviderConfig) -> Self {
        let load_success = match CString::new(config.model.clone()) {
            Ok(model_path) => unsafe {
                cortex_model_load(model_path.as_ptr()) == 1
            },
            Err(_) => false,
        };
        Self { config, load_success }
    }
}

extern "C" fn stream_callback(token: *const c_char, user_data: *mut c_void) {
    if token.is_null() || user_data.is_null() {
        return;
    }
    let s = unsafe { CStr::from_ptr(token).to_string_lossy().into_owned() };
    let chunks = unsafe { &mut *(user_data as *mut Vec<String>) };
    chunks.push(s);
}

impl AIProvider for OllamaProvider {
    fn chat_completion(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponse, AIError>> + Send + '_>> {
        let mut prompt = String::new();
        if let Some(sys) = system_prompt {
            prompt.push_str(&format!("System: {}\n", sys));
        }
        for msg in messages {
            let role = match msg.role {
                ChatRole::User => "User",
                ChatRole::Assistant => "Assistant",
                ChatRole::System => "System",
            };
            prompt.push_str(&format!("{}: {}\n", role, msg.content));
        }
        prompt.push_str("Assistant:");

        Box::pin(async move {
            let c_prompt = match CString::new(prompt) {
                Ok(c) => c,
                Err(_) => return Err(AIError::ApiError("Invalid prompt containing NUL bytes".to_string())),
            };
            let c_result = unsafe { cortex_infer_generate(c_prompt.as_ptr()) };
            if c_result.is_null() {
                return Err(AIError::ApiError("Failed to generate response".to_string()));
            }
            
            let result_str = unsafe { CStr::from_ptr(c_result).to_string_lossy().into_owned() };
            unsafe { libc::free(c_result as *mut libc::c_void); }
            
            Ok(AIResponse {
                content: result_str,
                finish_reason: Some("stop".to_string()),
                tokens_used: None,
            })
        })
    }

    fn chat_completion_stream(
        &self,
        messages: Vec<ChatMessage>,
        system_prompt: Option<String>,
    ) -> Pin<Box<dyn Future<Output = Result<AIResponseStream, AIError>> + Send + '_>> {
        let mut prompt = String::new();
        if let Some(sys) = system_prompt {
            prompt.push_str(&format!("System: {}\n", sys));
        }
        for msg in messages {
            let role = match msg.role {
                ChatRole::User => "User",
                ChatRole::Assistant => "Assistant",
                ChatRole::System => "System",
            };
            prompt.push_str(&format!("{}: {}\n", role, msg.content));
        }
        prompt.push_str("Assistant:");

        Box::pin(async move {
            let mut chunks: Vec<String> = Vec::new();
            let c_prompt = match CString::new(prompt) {
                Ok(c) => c,
                Err(_) => return Err(AIError::ApiError("Invalid prompt containing NUL bytes".to_string())),
            };
            
            unsafe {
                cortex_infer_generate_stream(
                    c_prompt.as_ptr(),
                    stream_callback,
                    &mut chunks as *mut Vec<String> as *mut c_void,
                );
            }
            
            Ok(AIResponseStream::new(chunks))
        })
    }

    fn is_available(&self) -> bool {
        self.load_success
    }

    fn name(&self) -> &str {
        "NativeLlama"
    }
}

pub fn create_local_provider(model: Option<&str>) -> OllamaProvider {
    let mut config = AIProviderConfig {
        provider_type: super::AIProviderType::Local,
        endpoint: String::new(),
        api_key: None,
        model: model.unwrap_or("models/llama.gguf").to_string(),
        max_tokens: 512,
        temperature: 0.7,
    };
    OllamaProvider::new(config)
}
