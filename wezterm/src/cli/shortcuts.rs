/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/


//! CX Terminal: Shortcut commands
//!
//! Simplified aliases for common AI-powered operations:
//! - cx install <description> -> cx ask --do "install <description>"
//! - cx setup <description>   -> cx ask --do "setup <description>"
//! - cx what <question>       -> cx ask "what <question>"
//! - cx fix <error>           -> cx ask --do "fix <error>"
//! - cx explain <thing>       -> cx ask "explain <thing>"

use anyhow::Result;
use clap::Parser;

use super::ask::AskCommand;

/// Install packages or software using natural language
#[derive(Debug, Parser, Clone)]
pub struct InstallCommand {
    /// What to install (natural language description)
    #[arg(trailing_var_arg = true, required = true)]
    pub description: Vec<String>,

    /// Skip confirmation prompts
    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,

    /// Use local AI only
    #[arg(long = "local")]
    pub local_only: bool,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl InstallCommand {
    pub fn run(&self) -> Result<()> {
        let query = format!("install {}", self.description.join(" "));

        let ask = AskCommand {
            query: vec![query],
            execute: true,
            auto_confirm: self.auto_confirm,
            local_only: self.local_only,
            format: "text".to_string(),
            verbose: self.verbose,
        };

        ask.run()
    }
}

/// Setup or configure systems using natural language
#[derive(Debug, Parser, Clone)]
pub struct SetupCommand {
    /// What to setup (natural language description)
    #[arg(trailing_var_arg = true, required = true)]
    pub description: Vec<String>,

    /// Skip confirmation prompts
    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,

    /// Use local AI only
    #[arg(long = "local")]
    pub local_only: bool,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl SetupCommand {
    pub fn run(&self) -> Result<()> {
        let query = format!("setup {}", self.description.join(" "));

        let ask = AskCommand {
            query: vec![query],
            execute: true,
            auto_confirm: self.auto_confirm,
            local_only: self.local_only,
            format: "text".to_string(),
            verbose: self.verbose,
        };

        ask.run()
    }
}

/// Ask questions about the system
#[derive(Debug, Parser, Clone)]
pub struct WhatCommand {
    /// Question about the system
    #[arg(trailing_var_arg = true, required = true)]
    pub question: Vec<String>,

    /// Output format: text, json
    #[arg(long = "format", short = 'f', default_value = "text")]
    pub format: String,

    /// Use local AI only
    #[arg(long = "local")]
    pub local_only: bool,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl WhatCommand {
    pub fn run(&self) -> Result<()> {
        let query = format!("what {}", self.question.join(" "));

        let ask = AskCommand {
            query: vec![query],
            execute: false,
            auto_confirm: false,
            local_only: self.local_only,
            format: self.format.clone(),
            verbose: self.verbose,
        };

        ask.run()
    }
}

/// Fix errors or problems using AI
#[derive(Debug, Parser, Clone)]
pub struct FixCommand {
    /// Error message or problem description (reads last error if omitted)
    #[arg(trailing_var_arg = true)]
    pub error: Vec<String>,

    /// Skip confirmation prompts
    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,

    /// Use local AI only
    #[arg(long = "local")]
    pub local_only: bool,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl FixCommand {
    pub fn run(&self) -> Result<()> {
        let error_text = if self.error.is_empty() {
            // Try to read last error from shell integration
            self.read_last_error()?
        } else {
            self.error.join(" ")
        };

        if error_text.is_empty() {
            anyhow::bail!("No error to fix. Run a command first or provide an error message.");
        }

        let query = format!("fix this error: {}", error_text);

        let ask = AskCommand {
            query: vec![query],
            execute: true,
            auto_confirm: self.auto_confirm,
            local_only: self.local_only,
            format: "text".to_string(),
            verbose: self.verbose,
        };

        ask.run()
    }

    fn read_last_error(&self) -> Result<String> {
        let home = std::env::var("HOME").unwrap_or_default();
        let error_file = std::path::Path::new(&home).join(".cx").join("last_error");

        if error_file.exists() {
            let content = std::fs::read_to_string(&error_file)?;
            // Clear the file after reading
            let _ = std::fs::write(&error_file, "");
            Ok(content.trim().to_string())
        } else {
            Ok(String::new())
        }
    }
}

/// Explain a command, file, or concept
#[derive(Debug, Parser, Clone)]
pub struct ExplainCommand {
    /// What to explain
    #[arg(trailing_var_arg = true, required = true)]
    pub subject: Vec<String>,

    /// Output format: text, json
    #[arg(long = "format", short = 'f', default_value = "text")]
    pub format: String,

    /// Use local AI only
    #[arg(long = "local")]
    pub local_only: bool,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

impl ExplainCommand {
    pub fn run(&self) -> Result<()> {
        let query = format!("explain {}", self.subject.join(" "));

        let ask = AskCommand {
            query: vec![query],
            execute: false,
            auto_confirm: false,
            local_only: self.local_only,
            format: self.format.clone(),
            verbose: self.verbose,
        };

        ask.run()
    }
}
