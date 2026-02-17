/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
//! CX Terminal: Create new projects from templates
//!
//! This module provides the `new` command for creating new projects
//! from predefined templates. Templates include common project types
//! like Rust, Python, Node.js, and more.

use clap::Parser;

/// Command to create a new project from a template.
///
/// # Examples
///
/// ```bash
/// cx-terminal new rust --name my-project
/// cx-terminal new python --dir /path/to/projects
/// ```
#[derive(Debug, Parser, Clone)]
pub struct NewCommand {
    /// The template to use (e.g., "rust", "python", "node")
    #[arg(default_value = "default")]
    pub template: String,

    /// The name of the new project
    #[arg(short, long)]
    pub name: Option<String>,

    /// The directory to create the project in
    #[arg(short, long)]
    pub dir: Option<String>,
}

impl NewCommand {
    /// Execute the new command to create a project from template.
    ///
    /// Currently a stub implementation that prints a message.
    /// Future versions will scaffold actual project templates.
    ///
    /// # Returns
    ///
    /// Returns `Ok(())` on success, or an error if project creation fails.
    pub fn run(&self) -> anyhow::Result<()> {
        eprintln!(
            "CX Terminal: 'new' command is not yet implemented. Template: {}",
            self.template
        );
        eprintln!("This feature will create new projects from templates.");
        Ok(())
    }
}
