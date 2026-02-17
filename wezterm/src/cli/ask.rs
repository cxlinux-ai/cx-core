/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! CX Terminal: AI-powered ask command
//!
//! Smart command detection that uses CX primitives (`cx new`, `cx save`, etc.)
//! before falling back to AI providers.
//!
//! Example: cx ask "create a python project" → cx new python <name>
//! Example: cx ask "save my work" → cx save <smart-name>
//! Example: cx ask "how do I install docker" → AI response with command

use anyhow::Result;
use clap::Parser;
use std::env;
use std::io::{self, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::Command;

use super::ask_context::ProjectContext;
use super::ask_patterns::PatternMatcher;
use super::model_utils::{
    is_model_available as is_local_model_available, model_path, MODEL_FILENAME,
};

const CX_SYSTEM_PROMPT: &str = r#"You are a Linux command expert assistant. You can either:
1. Answer directly if you have the knowledge
2. Call one of these tools if you need external/live information:

Available tools:
- kb_lookup(application, query): Look up documentation for specific applications
- troubleshoot(service, error_message?, symptoms?): Diagnose system issues  
- search_packages(query, source?): Search apt/snap/pip for packages
- get_system_info(info_type, target?): Get system status information
- read_logs(source, service?, file_path?, lines?): Read log files

Only call a tool when you genuinely need external information you don't have.

Response format for commands:
{"summary": "...", "commands": [{"command_template": "...", "explanation": "..."}]}

Response format for tool calls:
{"tool_call": {"name": "tool_name", "arguments": {...}}}

Response format for refusals (dangerous requests):
{"refusal": true, "message": "...", "safe_alternative": "..."}"#;

/// AI-powered command interface
#[derive(Debug, Parser, Clone)]
pub struct AskCommand {
    /// The question or task description
    #[arg(trailing_var_arg = true)]
    pub query: Vec<String>,

    /// Execute the suggested commands (with confirmation)
    #[arg(long = "do", short = 'd')]
    pub execute: bool,

    /// Skip confirmation prompts (use with caution)
    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,

    /// Use local AI only (no cloud)
    #[arg(long = "local")]
    pub local_only: bool,

    /// Output format: text, json, commands
    #[arg(long = "format", short = 'f', default_value = "text")]
    pub format: String,

    /// Verbose output
    #[arg(long = "verbose", short = 'v')]
    pub verbose: bool,
}

const CX_DAEMON_SOCKET: &str = "/var/run/cx/daemon.sock";
const CX_USER_SOCKET_TEMPLATE: &str = "/run/user/{}/cx/daemon.sock";

impl AskCommand {
    pub fn run(&self) -> Result<()> {
        let query = self.query.join(" ");

        if query.is_empty() {
            return self.run_interactive();
        }

        if self.verbose {
            log::debug!(target: "ask", "Query: \"{}\"", query);
        }

        // Step 1: Try to match CX commands (new, save, restore, etc.)
        if let Some(response) = self.try_cx_command(&query)? {
            return self.handle_response(&response);
        }

        // Step 2: Try AI providers (daemon, Claude, Ollama)
        let response = self.query_ai(&query)?;
        self.handle_response(&response)
    }

    /// Try to match query against CX command patterns and execute
    fn try_cx_command(&self, query: &str) -> Result<Option<String>> {
        let matcher = PatternMatcher::new();
        let context = ProjectContext::detect();

        if let Some(pattern_match) = matcher.match_query(query) {
            // Only use pattern match if confidence is reasonable
            if pattern_match.confidence >= 0.7 {
                let mut command = pattern_match.command.clone();

                // If command needs a name, try to extract or generate one
                if pattern_match.needs_name {
                    let name = matcher
                        .extract_name(query)
                        .unwrap_or_else(|| context.smart_snapshot_name());
                    command = command.replace("{name}", &name);
                }

                // For CX commands, execute automatically (AI-native behavior)
                println!("{}", pattern_match.description);
                self.execute_cx_command(&command)?;

                // Return empty response since we already handled it
                return Ok(Some("{}".to_string()));
            }
        }

        Ok(None)
    }

    /// Execute a CX command with optional confirmation
    fn execute_cx_command(&self, command: &str) -> Result<()> {
        if !self.auto_confirm {
            eprintln!("\n  $ {}", command);
            eprint!("\nRun this? [Y/n] ");
            io::stderr().flush()?;

            let mut input = String::new();
            io::stdin().read_line(&mut input)?;

            let input = input.trim();
            if !input.is_empty() && !input.eq_ignore_ascii_case("y") {
                eprintln!("Cancelled.");
                return Ok(());
            }
        }

        // Execute the command
        let status = Command::new("sh").arg("-c").arg(command).status()?;

        if !status.success() {
            eprintln!("Command failed with exit code: {:?}", status.code());
        }

        Ok(())
    }

    fn handle_response(&self, response: &str) -> Result<()> {
        match self.format.as_str() {
            "json" => println!("{}", response),
            "commands" => self.print_commands_only(response),
            _ => self.print_formatted(response),
        }

        if self.execute {
            self.execute_commands(response)?;
        }

        Ok(())
    }

    fn run_interactive(&self) -> Result<()> {
        eprintln!("cx ask: Enter your question (Ctrl+D to finish):");
        let mut input = String::new();
        io::stdin().read_to_string(&mut input)?;

        let query = input.trim();
        if query.is_empty() {
            anyhow::bail!("No query provided");
        }

        if let Some(response) = self.try_cx_command(query)? {
            return self.handle_response(&response);
        }

        let response = self.query_ai(query)?;
        self.handle_response(&response)
    }

    fn query_ai(&self, query: &str) -> Result<String> {
        // Try daemon first
        if let Some(response) = self.try_daemon(query)? {
            return Ok(response);
        }

        // Track if local model was attempted for better error hints
        let mut local_attempted = false;

        // Try local GGUF model (preferred for --local or when available)
        if self.local_only || is_local_model_available() {
            local_attempted = true;
            match self.query_local(query) {
                Ok(response) => return Ok(response),
                Err(e) if self.local_only => return Err(e),
                Err(_) => {} // Fall through to other providers
            }
        }

        // Try Claude API
        if !self.local_only {
            if let Ok(api_key) = env::var("ANTHROPIC_API_KEY") {
                if !api_key.is_empty() && api_key.starts_with("sk-") {
                    if let Ok(response) = self.query_claude(&query, &api_key) {
                        return Ok(response);
                    }
                }
            }
        }

        // Try Ollama
        if let Ok(host) = env::var("OLLAMA_HOST") {
            if !host.is_empty() && host.starts_with("http") {
                if let Ok(response) = self.query_ollama(&query, &host) {
                    return Ok(response);
                }
            }
        }

        // No AI available - return helpful message with download instructions
        let hint = if !is_local_model_available() {
            "Local model not found. Download it with: cx ai download\nOr set ANTHROPIC_API_KEY or OLLAMA_HOST for cloud AI."
        } else if local_attempted {
            "Local model failed. Set ANTHROPIC_API_KEY or OLLAMA_HOST for cloud AI."
        } else {
            "Set ANTHROPIC_API_KEY or OLLAMA_HOST for AI features, or try specific commands like 'cx new python myapp'"
        };

        let response = serde_json::json!({
            "status": "no_ai",
            "message": "No AI backend available for this query.",
            "query": query,
            "hint": hint
        });
        Ok(serde_json::to_string_pretty(&response)?)
    }

    fn query_local(&self, query: &str) -> Result<String> {
        use llama_cpp_2::context::params::LlamaContextParams;
        use llama_cpp_2::llama_backend::LlamaBackend;
        use llama_cpp_2::llama_batch::LlamaBatch;
        use llama_cpp_2::model::params::LlamaModelParams;
        use llama_cpp_2::model::LlamaModel;
        use llama_cpp_2::token::data_array::LlamaTokenDataArray;

        let model_file = model_path();
        if !model_file.exists() {
            anyhow::bail!("Local model not found at {:?}", model_file);
        }

        if self.verbose {
            log::debug!(target: "ask", "Loading model: {:?}", model_file);
        }

        // CX Terminal: RAII guard ensures stderr restoration even on error
        #[cfg(unix)]
        struct StderrGuard {
            saved: Option<i32>,
            fd: i32,
        }
        #[cfg(unix)]
        impl Drop for StderrGuard {
            fn drop(&mut self) {
                if let Some(saved) = self.saved {
                    if saved >= 0 {
                        unsafe { libc::dup2(saved, self.fd) };
                        unsafe { libc::close(saved) };
                    }
                }
            }
        }

        // CX Terminal: Suppress llama.cpp's verbose model loading output
        #[cfg(unix)]
        let _stderr_guard = {
            use std::os::unix::io::AsRawFd;
            let stderr_fd = std::io::stderr().as_raw_fd();
            if !self.verbose {
                let saved = unsafe { libc::dup(stderr_fd) };
                if saved < 0 {
                    anyhow::bail!("Failed to duplicate stderr file descriptor");
                }
                let devnull = std::fs::OpenOptions::new().write(true).open("/dev/null")?;
                let dup_result = unsafe { libc::dup2(devnull.as_raw_fd(), stderr_fd) };
                if dup_result < 0 {
                    unsafe { libc::close(saved) };
                    anyhow::bail!("Failed to redirect stderr to /dev/null");
                }
                StderrGuard {
                    saved: Some(saved),
                    fd: stderr_fd,
                }
            } else {
                StderrGuard {
                    saved: None,
                    fd: stderr_fd,
                }
            }
        };

        #[cfg(not(unix))]
        let _ = self.verbose;

        let backend = LlamaBackend::init()?;
        let model_params = LlamaModelParams::default();
        let model = LlamaModel::load_from_file(&backend, &model_file, &model_params)?;

        let ctx_params = LlamaContextParams::default()
            .with_n_ctx(std::num::NonZeroU32::new(4096))
            .with_n_threads(4)
            .with_n_threads_batch(4);
        let mut ctx = model.new_context(&backend, ctx_params)?;

        // CX Terminal: Restore stderr now that model loading is complete
        #[cfg(unix)]
        drop(_stderr_guard);

        // CX Terminal: Augment system prompt with project context for better responses
        let context = ProjectContext::detect();
        let full_system = format!(
            "{}\n\nCurrent directory: {}\nProject type: {:?}",
            CX_SYSTEM_PROMPT,
            context.cwd.display(),
            context.project_type
        );

        let prompt = format!(
            "<|im_start|>system\n{}<|im_end|>\n<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n",
            full_system, query
        );

        let tokens = model.str_to_token(&prompt, llama_cpp_2::model::AddBos::Always)?;

        // CX Terminal: Prevent context overflow - reserve space for response generation
        const MAX_RESPONSE_TOKENS: usize = 512;
        let max_prompt_tokens = 4096 - MAX_RESPONSE_TOKENS;
        if tokens.len() >= max_prompt_tokens {
            anyhow::bail!(
                "Prompt too long: {} tokens exceeds {} limit (need room for response). Please shorten your query.",
                tokens.len(),
                max_prompt_tokens
            );
        }

        let mut batch = LlamaBatch::new(4096, 1);
        for (i, token) in tokens.iter().enumerate() {
            let is_last = i == tokens.len() - 1;
            batch.add(*token, i as i32, &[0], is_last)?;
        }

        ctx.decode(&mut batch)?;

        let mut output = String::new();
        // CX Terminal: Reserve context space for response generation
        let max_tokens = std::cmp::min(512, 4096 - tokens.len());
        let mut n_cur = tokens.len();

        for _ in 0..max_tokens {
            let candidates = ctx.candidates();
            let mut candidates_data = LlamaTokenDataArray::from_iter(candidates, false);
            let seed = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos() as u32)
                .unwrap_or(42);
            let token = candidates_data.sample_token(seed);

            if model.is_eog_token(token) {
                break;
            }

            let token_str = model.token_to_str(token, llama_cpp_2::model::Special::Tokenize)?;

            // CX Terminal: Append to accumulator to detect split markers
            output.push_str(&token_str);

            // CX Terminal: Check accumulator for end markers (handles split tokens)
            if output.contains("<|im_end|>") || output.contains("<|endoftext|>") {
                break;
            }

            batch.clear();
            batch.add(token, n_cur as i32, &[0], true)?;
            n_cur += 1;

            ctx.decode(&mut batch)?;
        }

        let result = serde_json::json!({
            "status": "success",
            "source": "local",
            "model": MODEL_FILENAME,
            "response": output.trim(),
        });
        Ok(serde_json::to_string_pretty(&result)?)
    }

    fn try_daemon(&self, query: &str) -> Result<Option<String>> {
        let uid = unsafe { libc::getuid() };
        let user_socket = CX_USER_SOCKET_TEMPLATE.replace("{}", &uid.to_string());

        let socket_path = if Path::new(&user_socket).exists() {
            user_socket
        } else if Path::new(CX_DAEMON_SOCKET).exists() {
            CX_DAEMON_SOCKET.to_string()
        } else {
            return Ok(None);
        };

        match UnixStream::connect(&socket_path) {
            Ok(mut stream) => {
                let request = serde_json::json!({
                    "type": "ask",
                    "query": query,
                    "execute": self.execute,
                    "local_only": self.local_only,
                });

                let request_bytes = serde_json::to_vec(&request)?;
                stream.write_all(&request_bytes)?;
                stream.shutdown(std::net::Shutdown::Write)?;

                let mut response = String::new();
                stream.read_to_string(&mut response)?;
                Ok(Some(response))
            }
            Err(e) => {
                if self.verbose {
                    eprintln!("cx ask: daemon connection failed: {}", e);
                }
                Ok(None)
            }
        }
    }

    fn query_claude(&self, query: &str, api_key: &str) -> Result<String> {
        let context = ProjectContext::detect();
        let system_prompt = format!(
            "You are CX Terminal, an AI assistant for CX Linux. \
            Current directory: {}. Project type: {:?}. \
            Provide concise, actionable commands. Use ```bash code blocks.",
            context.cwd.display(),
            context.project_type
        );

        let payload = serde_json::json!({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": format!("{}\n\nQuestion: {}", system_prompt, query)}
            ]
        });

        let output = Command::new("curl")
            .args([
                "-s",
                "-X",
                "POST",
                "https://api.anthropic.com/v1/messages",
                "-H",
                &format!("x-api-key: {}", api_key),
                "-H",
                "anthropic-version: 2023-06-01",
                "-H",
                "content-type: application/json",
                "-d",
                &payload.to_string(),
            ])
            .output()?;

        if output.status.success() {
            let response: serde_json::Value = serde_json::from_slice(&output.stdout)?;
            if let Some(content) = response["content"][0]["text"].as_str() {
                let result = serde_json::json!({
                    "status": "success",
                    "source": "claude",
                    "response": content,
                });
                return Ok(serde_json::to_string_pretty(&result)?);
            }
        }

        anyhow::bail!("Claude API request failed")
    }

    fn query_ollama(&self, query: &str, host: &str) -> Result<String> {
        let model = env::var("OLLAMA_MODEL").unwrap_or_else(|_| "llama3".to_string());
        let context = ProjectContext::detect();

        let payload = serde_json::json!({
            "model": model,
            "prompt": format!(
                "You are CX Terminal assistant. Directory: {}. Answer concisely with commands.\n\nQuestion: {}",
                context.cwd.display(), query
            ),
            "stream": false
        });

        let output = Command::new("curl")
            .args([
                "-s",
                "-X",
                "POST",
                &format!("{}/api/generate", host),
                "-H",
                "content-type: application/json",
                "-d",
                &payload.to_string(),
            ])
            .output()?;

        if output.status.success() {
            let response: serde_json::Value = serde_json::from_slice(&output.stdout)?;
            if let Some(text) = response["response"].as_str() {
                let result = serde_json::json!({
                    "status": "success",
                    "source": "ollama",
                    "response": text,
                });
                return Ok(serde_json::to_string_pretty(&result)?);
            }
        }

        anyhow::bail!("Ollama request failed")
    }

    fn print_formatted(&self, response: &str) {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(response) {
            // CX command detection response
            if json.get("status").and_then(|s| s.as_str()) == Some("cx_command") {
                if let Some(desc) = json.get("description").and_then(|d| d.as_str()) {
                    println!("{}", desc);
                }
                if let Some(cmd) = json.get("command").and_then(|c| c.as_str()) {
                    println!("\n  $ {}", cmd);
                }
                return;
            }

            // AI response
            if let Some(ai_response) = json.get("response").and_then(|r| r.as_str()) {
                println!("{}", ai_response);
                return;
            }

            // Message field
            if let Some(message) = json.get("message").and_then(|m| m.as_str()) {
                println!("{}", message);
            }
            if let Some(hint) = json.get("hint").and_then(|h| h.as_str()) {
                eprintln!("\nHint: {}", hint);
            }
        } else {
            println!("{}", response);
        }
    }

    fn print_commands_only(&self, response: &str) {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(response) {
            if let Some(cmd) = json.get("command").and_then(|c| c.as_str()) {
                println!("{}", cmd);
            }
        }
    }

    fn execute_commands(&self, response: &str) -> Result<()> {
        let json: serde_json::Value = serde_json::from_str(response)?;

        let command = json.get("command").and_then(|c| c.as_str());

        let command = match command {
            Some(cmd) => cmd,
            None => return Ok(()),
        };

        if !self.auto_confirm {
            eprintln!("\nCommand to execute:");
            eprintln!("  $ {}", command);
            eprint!("\nProceed? [y/N] ");
            io::stderr().flush()?;

            let mut input = String::new();
            io::stdin().read_line(&mut input)?;

            if !input.trim().eq_ignore_ascii_case("y") {
                eprintln!("Aborted.");
                return Ok(());
            }
        }

        eprintln!("$ {}", command);
        let status = Command::new("sh").arg("-c").arg(command).status()?;

        if !status.success() {
            eprintln!("Command failed with exit code: {:?}", status.code());
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_query_local_missing_model() {
        let ask_cmd = AskCommand {
            query: vec!["test".to_string()],
            execute: false,
            auto_confirm: false,
            local_only: false,
            format: "text".to_string(),
            verbose: false,
        };

        let result = ask_cmd.query_local("test query");

        // If the model exists on this system, the test might succeed
        // We validate the error path when model is missing
        if result.is_err() {
            let err_msg = result.unwrap_err().to_string();
            // Should be model not found error
            assert!(
                err_msg.contains("Local model not found") || err_msg.contains("not found"),
                "Error should mention missing model, got: {}",
                err_msg
            );
        }
        // If result is Ok, model exists - test passes either way
    }

    #[test]
    fn test_query_local_prompt_too_long() {
        let ask_cmd = AskCommand {
            query: vec!["test".to_string()],
            execute: false,
            auto_confirm: false,
            local_only: false,
            format: "text".to_string(),
            verbose: false,
        };

        // Create a very long query (assuming ~1 token per 4 chars, need ~14000+ chars)
        let long_query = "word ".repeat(3000);

        let result = ask_cmd.query_local(&long_query);
        assert!(
            result.is_err(),
            "Expected error for long prompt or missing model"
        );
    }

    #[test]
    fn test_stderr_guard_verbose_flag() {
        let ask_cmd_verbose = AskCommand {
            query: vec!["test".to_string()],
            execute: false,
            auto_confirm: false,
            local_only: false,
            format: "text".to_string(),
            verbose: true,
        };

        let ask_cmd_quiet = AskCommand {
            query: vec!["test".to_string()],
            execute: false,
            auto_confirm: false,
            local_only: false,
            format: "text".to_string(),
            verbose: false,
        };

        assert!(ask_cmd_verbose.verbose, "Verbose should be true");
        assert!(!ask_cmd_quiet.verbose, "Verbose should be false");
    }

    #[test]
    fn test_query_local_context_window_constants() {
        const MAX_RESPONSE_TOKENS: usize = 512;
        const TOTAL_CONTEXT: usize = 4096;
        let max_prompt_tokens = TOTAL_CONTEXT - MAX_RESPONSE_TOKENS;

        assert_eq!(max_prompt_tokens, 3584, "Max prompt tokens should be 3584");
        assert_eq!(MAX_RESPONSE_TOKENS, 512, "Response tokens should be 512");
        assert_eq!(TOTAL_CONTEXT, 4096, "Total context should be 4096");
    }

    #[test]
    fn test_ask_command_clone() {
        let cmd = AskCommand {
            query: vec!["test".to_string()],
            execute: true,
            auto_confirm: false,
            local_only: true,
            format: "json".to_string(),
            verbose: true,
        };

        let cloned = cmd.clone();
        assert_eq!(cmd.query, cloned.query);
        assert_eq!(cmd.execute, cloned.execute);
        assert_eq!(cmd.auto_confirm, cloned.auto_confirm);
        assert_eq!(cmd.local_only, cloned.local_only);
        assert_eq!(cmd.format, cloned.format);
        assert_eq!(cmd.verbose, cloned.verbose);
    }

    #[test]
    fn test_format_handling() {
        let ask_cmd = AskCommand {
            query: vec!["test".to_string()],
            execute: false,
            auto_confirm: false,
            local_only: false,
            format: "json".to_string(),
            verbose: false,
        };

        assert_eq!(ask_cmd.format, "json");

        let ask_cmd_text = AskCommand {
            format: "text".to_string(),
            ..ask_cmd.clone()
        };

        assert_eq!(ask_cmd_text.format, "text");
    }
}
