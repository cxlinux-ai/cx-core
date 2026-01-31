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
use std::path::{Path, PathBuf};
use std::process::Command;

use super::ask_context::ProjectContext;
use super::ask_patterns::PatternMatcher;

// Local GGUF model constants
const HF_REPO: &str = "shree3112/cortex-linux-7b";
const MODEL_FILENAME: &str = "cortex-linux-7b-Q4_K_M.gguf";

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

/// Get the path to the local model cache directory
fn model_cache_dir() -> PathBuf {
    dirs::cache_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join("cx-linux")
        .join("models")
}

/// Get the full path to the GGUF model file
fn model_path() -> PathBuf {
    model_cache_dir().join(MODEL_FILENAME)
}

/// Check if the local model is available
fn is_local_model_available() -> bool {
    model_path().exists()
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

        // Try local GGUF model (preferred for --local or when available)
        if self.local_only || is_local_model_available() {
            if let Ok(response) = self.query_local(query) {
                return Ok(response);
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
        use std::os::unix::io::AsRawFd;

        let model_file = model_path();
        if !model_file.exists() {
            anyhow::bail!("Local model not found at {:?}", model_file);
        }

        if self.verbose {
            eprintln!("Loading local model from {:?}...", model_file);
        }

        // RAII guard to ensure stderr is restored on drop (even on error)
        struct StderrGuard {
            saved: Option<i32>,
            fd: i32,
        }
        impl Drop for StderrGuard {
            fn drop(&mut self) {
                if let Some(saved) = self.saved {
                    unsafe { libc::dup2(saved, self.fd) };
                    unsafe { libc::close(saved) };
                }
            }
        }

        // Suppress llama.cpp verbose logging by redirecting stderr temporarily
        let stderr_fd = std::io::stderr().as_raw_fd();
        let _stderr_guard = if !self.verbose {
            let saved = unsafe { libc::dup(stderr_fd) };
            let devnull = std::fs::OpenOptions::new()
                .write(true)
                .open("/dev/null")?;
            unsafe { libc::dup2(devnull.as_raw_fd(), stderr_fd) };
            StderrGuard { saved: Some(saved), fd: stderr_fd }
        } else {
            StderrGuard { saved: None, fd: stderr_fd }
        };

        // Initialize backend and load model (stderr suppressed, restored on error or completion)
        let backend = LlamaBackend::init()?;
        let model_params = LlamaModelParams::default().with_n_gpu_layers(35);
        let model = LlamaModel::load_from_file(&backend, &model_file, &model_params)?;

        // Create context (also outputs logs)
        let ctx_params = LlamaContextParams::default()
            .with_n_ctx(std::num::NonZeroU32::new(2048))
            .with_n_threads(4)
            .with_n_threads_batch(4);
        let mut ctx = model.new_context(&backend, ctx_params)?;

        // _stderr_guard drops here, restoring stderr


        // Format prompt using Qwen chat template
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

        // Tokenize
        let tokens = model.str_to_token(&prompt, llama_cpp_2::model::AddBos::Always)?;

        // Create batch and add tokens
        let mut batch = LlamaBatch::new(2048, 1);
        for (i, token) in tokens.iter().enumerate() {
            let is_last = i == tokens.len() - 1;
            batch.add(*token, i as i32, &[0], is_last)?;
        }

        // Decode initial prompt
        ctx.decode(&mut batch)?;

        // Generate tokens
        let mut output = String::new();
        let max_tokens = 512;
        let mut n_cur = tokens.len();

        for _ in 0..max_tokens {
            // Sample next token
            let candidates = ctx.candidates();
            let mut candidates_data = LlamaTokenDataArray::from_iter(candidates, false);
            let token = candidates_data.sample_token(42);

            // Check for end of generation
            if model.is_eog_token(token) {
                break;
            }

            // Decode token to text
            let token_str = model.token_to_str(token, llama_cpp_2::model::Special::Tokenize)?;
            
            // Stop on end markers
            if token_str.contains("<|im_end|>") || token_str.contains("<|endoftext|>") {
                break;
            }
            
            output.push_str(&token_str);

            // Prepare next batch
            batch.clear();
            batch.add(token, n_cur as i32, &[0], true)?;
            n_cur += 1;

            // Decode
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
