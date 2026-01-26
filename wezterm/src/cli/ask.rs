//! CX Terminal: Agentic AI command interface
//!
//! True agent behavior - automatically executes safe commands and returns results.
//! Not just a command suggester, but an AI that DOES things.
//!
//! Example: cx ask "what time is it" → "Sun Jan 26 15:47:32 IST 2026"
//! Example: cx ask "create a python project" → Creates and shows the result

use anyhow::Result;
use clap::Parser;
use std::io::{self, Read, Write};
use std::process::Command;

use super::ask_agent::execute_and_capture;
use super::ask_ai;
use super::ask_context::ProjectContext;
use super::ask_executor::extract_commands;
use super::ask_patterns::PatternMatcher;
use super::branding::{colors, print_error, print_info};
use super::plan::{Plan, PlanAction};

/// AI-powered agentic command interface
///
/// By default, safe commands are auto-executed and results shown.
/// Use --no-exec to get suggestions instead of execution.
#[derive(Debug, Parser, Clone)]
pub struct AskCommand {
    /// Don't auto-execute, just show suggestions
    #[arg(long = "no-exec", short = 'n')]
    pub no_execute: bool,

    /// Skip confirmation prompts for moderate-risk commands
    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,

    /// Use local AI only (no cloud)
    #[arg(long = "local")]
    pub local_only: bool,

    /// Output format: text, json, commands
    #[arg(long = "format", short = 'f', default_value = "text")]
    pub format: String,

    /// Verbose output (show commands being run)
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,

    /// The question or task description
    #[arg(trailing_var_arg = true)]
    pub query: Vec<String>,
}

impl AskCommand {
    pub fn run(&self) -> Result<()> {
        let query = self.query.join(" ");

        if query.is_empty() {
            return self.run_interactive();
        }

        if self.verbose {
            eprintln!("cx ask: {}", query);
        }

        // Step 1: Try CX command patterns (new, save, restore, etc.)
        if self.try_cx_command(&query)?.is_some() {
            return Ok(());
        }

        // Step 2: Query AI and handle response agentically
        let response = ask_ai::query_ai(&query, self.local_only)?;
        self.handle_agentic_response(&query, &response)
    }

    /// Handle response with true agent behavior
    fn handle_agentic_response(&self, _original_query: &str, response: &str) -> Result<()> {
        // Extract commands from AI response
        let extraction = extract_commands(response);

        // If no-exec mode, just show the response
        if self.no_execute {
            return self.show_suggestion(response, &extraction);
        }

        // If we extracted commands, decide how to handle them
        if !extraction.commands.is_empty() {
            let plan = Plan::from_commands(&extraction.commands);

            // Check if any command is dangerous or blocked
            let needs_confirmation =
                plan.has_dangerous() || plan.has_blocked() || plan.requires_sudo;

            if needs_confirmation {
                // Dangerous/sudo commands → show Plan UI for confirmation
                return self.execute_with_plan(plan);
            } else {
                // Safe/moderate commands → execute immediately (autonomous agent!)
                return self.execute_plan_immediately(&plan);
            }
        }

        // No commands found - show the text response
        self.print_ai_response(response);
        Ok(())
    }

    /// Execute plan immediately without prompting (autonomous agent mode)
    fn execute_plan_immediately(&self, plan: &Plan) -> Result<()> {
        use colors::*;

        for step in &plan.commands {
            if self.verbose {
                eprintln!("{DIM}${RESET} {}", step.command);
            }

            let output = execute_and_capture(&step.command)?;

            if output.success {
                let out = output.primary_output();
                print!("{}", out);
                if !out.ends_with('\n') && !out.is_empty() {
                    println!();
                }
            } else {
                print_error(&format!("Command failed: {}", step.command));
                let out = output.primary_output();
                if !out.trim().is_empty() {
                    eprintln!("{}", out);
                }
                // Stop on first failure
                return Ok(());
            }
        }
        Ok(())
    }

    /// Execute with Plan UI - shows plan, prompts user, then executes
    fn execute_with_plan(&self, plan: Plan) -> Result<()> {
        // Display the plan
        plan.display();

        // Multi-step plans ALWAYS prompt (this is the "Prompt-to-Plan" feature)
        let action = plan.prompt_action()?;

        match action {
            PlanAction::Execute => plan.execute(false),
            PlanAction::DryRun => plan.execute(true),
            PlanAction::Cancel => {
                print_info("Cancelled");
                Ok(())
            }
        }
    }

    /// Show suggestion without executing (--no-exec mode)
    fn show_suggestion(
        &self,
        response: &str,
        extraction: &super::ask_executor::ExtractionResult,
    ) -> Result<()> {
        match self.format.as_str() {
            "json" => println!("{}", response),
            "commands" => {
                for cmd in &extraction.commands {
                    println!("{}", cmd.command);
                }
            }
            _ => self.print_ai_response(response),
        }
        Ok(())
    }

    /// Print AI response text
    fn print_ai_response(&self, response: &str) {
        use colors::*;

        if let Ok(json) = serde_json::from_str::<serde_json::Value>(response) {
            if json.get("status").and_then(|s| s.as_str()) == Some("no_ai") {
                if let Some(msg) = json.get("message").and_then(|m| m.as_str()) {
                    eprintln!("{YELLOW}{msg}{RESET}");
                }
                if let Some(hint) = json.get("hint").and_then(|h| h.as_str()) {
                    eprintln!("\n{DIM}Hint:{RESET} {hint}");
                }
                return;
            }
            if let Some(ai_response) = json.get("response").and_then(|r| r.as_str()) {
                println!("{}", ai_response);
                return;
            }
        }
        println!("{}", response);
    }

    /// Try to match query against CX command patterns
    fn try_cx_command(&self, query: &str) -> Result<Option<()>> {
        let matcher = PatternMatcher::new();
        let context = ProjectContext::detect();

        if let Some(pattern_match) = matcher.match_query(query) {
            if pattern_match.confidence >= 0.7 {
                let mut command = pattern_match.command.clone();

                if pattern_match.needs_name {
                    let name = matcher
                        .extract_name(query)
                        .unwrap_or_else(|| context.smart_snapshot_name());
                    command = command.replace("{name}", &name);
                }

                if self.verbose {
                    eprintln!("{}", pattern_match.description);
                    eprintln!("$ {}", command);
                }

                // Execute the CX command
                let status = Command::new("sh").arg("-c").arg(&command).status()?;
                if !status.success() {
                    eprintln!("Command failed with exit code: {:?}", status.code());
                }
                return Ok(Some(()));
            }
        }
        Ok(None)
    }

    fn run_interactive(&self) -> Result<()> {
        use colors::*;
        eprintln!("{CX_PURPLE}▶{RESET} Enter your question (Ctrl+D to finish):");
        let mut input = String::new();
        io::stdin().read_to_string(&mut input)?;

        let query = input.trim();
        if query.is_empty() {
            anyhow::bail!("No query provided");
        }

        if self.try_cx_command(query)?.is_some() {
            return Ok(());
        }

        let response = ask_ai::query_ai(query, self.local_only)?;
        self.handle_agentic_response(query, &response)
    }
}
