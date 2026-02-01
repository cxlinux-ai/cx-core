/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! CX Terminal: AI model download command
//!
//! Downloads the CX Linux fine-tuned model from HuggingFace.
//!
//! Example: cx ai download

use anyhow::{Context, Result};
use clap::Parser;

use super::model_utils::{model_cache_dir, model_path, HF_REPO, MODEL_FILENAME};

/// AI model management commands
#[derive(Debug, Parser, Clone)]
pub struct AICommand {
    #[command(subcommand)]
    pub subcommand: AISubCommand,
}

#[derive(Debug, Parser, Clone)]
pub enum AISubCommand {
    /// Download the CX Linux AI model from HuggingFace
    Download(DownloadCommand),
}

/// Download the CX Linux AI model
#[derive(Debug, Parser, Clone)]
pub struct DownloadCommand {
    /// Force re-download even if model already exists
    #[arg(long = "force", short = 'f')]
    pub force: bool,

    /// Show verbose progress
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl DownloadCommand {
    /// Download the model from HuggingFace
    pub async fn download(&self) -> Result<()> {
        let model_path = model_path();
        let cache_dir = model_cache_dir();

        // Check if model already exists (and is valid)
        if model_path.exists() && !self.force {
            println!("✓ Model already exists at: {:?}", model_path);
            println!("Use --force to re-download.");
            return Ok(());
        }

        // Check for broken symlink (exists() returns false for broken symlinks, but is_symlink() returns true)
        if model_path.is_symlink() && !model_path.exists() {
            println!(
                "⚠ Found broken symlink at {:?}, will recreate...",
                model_path
            );
            std::fs::remove_file(&model_path).ok();
        }

        // Create cache directory if it doesn't exist
        std::fs::create_dir_all(&cache_dir)
            .with_context(|| format!("Failed to create cache directory: {:?}", cache_dir))?;

        println!("Downloading CX Linux AI model from HuggingFace...");
        println!("Repository: {}", HF_REPO);
        println!("Model: {}", MODEL_FILENAME);
        println!("Destination: {:?}", model_path);

        if self.verbose {
            println!("Cache directory: {:?}", cache_dir);
        }

        // Download using hf-hub
        let api =
            hf_hub::api::tokio::Api::new().context("Failed to create HuggingFace API client")?;

        let repo = api.model(HF_REPO.to_string());

        println!("\nDownloading... (this may take a while, ~4.7GB)");

        let downloaded_path = repo.get(MODEL_FILENAME).await.with_context(|| {
            format!(
                "Failed to download model from HuggingFace: {}/{}",
                HF_REPO, MODEL_FILENAME
            )
        })?;

        // hf-hub downloads to its own cache and may return a path with relative symlinks.
        // Instead of moving (which breaks relative symlinks), create an absolute symlink
        // to the actual file in the HuggingFace cache.
        if downloaded_path != model_path {
            // Resolve to the actual file (follows symlinks)
            let actual_file = std::fs::canonicalize(&downloaded_path).with_context(|| {
                format!("Failed to resolve downloaded path: {:?}", downloaded_path)
            })?;

            if self.verbose {
                println!(
                    "Creating symlink from {:?} to {:?}",
                    model_path, actual_file
                );
            }

            // Remove existing file/symlink if present
            if model_path.exists() || model_path.is_symlink() {
                std::fs::remove_file(&model_path).ok();
            }

            // Create absolute symlink to the actual blob file
            #[cfg(unix)]
            std::os::unix::fs::symlink(&actual_file, &model_path)
                .with_context(|| format!("Failed to create symlink at {:?}", model_path))?;

            #[cfg(windows)]
            std::os::windows::fs::symlink_file(&actual_file, &model_path)
                .with_context(|| format!("Failed to create symlink at {:?}", model_path))?;
        }

        // Verify file exists and has reasonable size (> 1GB)
        let metadata = std::fs::metadata(&model_path)
            .with_context(|| format!("Failed to get metadata for {:?}", model_path))?;

        let size_mb = metadata.len() / (1024 * 1024);

        if metadata.len() < 1000_000_000 {
            eprintln!(
                "Warning: Downloaded file seems too small ({} MB). Download may have failed.",
                size_mb
            );
        }

        println!("\n✓ Model downloaded successfully!");
        println!("  Location: {:?}", model_path);
        println!("  Size: {} MB", size_mb);
        println!("\nYou can now use CX AI features in the terminal.");

        Ok(())
    }

    pub fn run(&self) -> Result<()> {
        let rt = tokio::runtime::Runtime::new().context("Failed to create tokio runtime")?;

        rt.block_on(self.download())
    }
}

impl AICommand {
    pub fn run(&self) -> Result<()> {
        match &self.subcommand {
            AISubCommand::Download(cmd) => cmd.run(),
        }
    }
}
