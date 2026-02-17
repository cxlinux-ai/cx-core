/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! Shared utilities for CX Linux AI model management
//!
//! This module provides common functions for model path resolution
//! used by both the GUI and CLI components.

use std::path::PathBuf;

/// HuggingFace repository containing the model
pub const HF_REPO: &str = "ShreemJ/cxlinux-ai-7b";

/// Model filename
pub const MODEL_FILENAME: &str = "cxlinux-ai-7b-Q4_K_M.gguf";

/// Get the cache directory for CX Linux models
pub fn model_cache_dir() -> PathBuf {
    let cache_dir = dirs::cache_dir()
        .or_else(|| {
            std::env::var("HOME")
                .ok()
                .map(|h| PathBuf::from(h).join(".cache"))
        })
        .unwrap_or_else(|| PathBuf::from("/tmp"));

    cache_dir.join("cx-linux").join("models")
}

/// Get the full path to the model file
pub fn model_path() -> PathBuf {
    model_cache_dir().join(MODEL_FILENAME)
}

/// Check if the model is available (downloaded)
pub fn is_model_available() -> bool {
    model_path().exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_model_path() {
        let path = model_path();
        assert!(path.to_string_lossy().contains("cx-linux"));
        assert!(path.to_string_lossy().contains(MODEL_FILENAME));
    }

    #[test]
    fn test_model_cache_dir() {
        let dir = model_cache_dir();
        assert!(dir.to_string_lossy().contains("cx-linux"));
        assert!(dir.to_string_lossy().contains("models"));
    }
}
