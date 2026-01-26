//! CX Terminal: AI provider implementations
//!
//! Handles communication with AI backends: CX Daemon, Claude API, and Ollama.

use anyhow::Result;
use std::env;
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::Command;

use super::ask_context::ProjectContext;

const CX_DAEMON_SOCKET: &str = "/var/run/cx/daemon.sock";
const CX_USER_SOCKET_TEMPLATE: &str = "/run/user/{}/cx/daemon.sock";

/// Query AI backends in order: Daemon → Claude → Ollama
pub fn query_ai(query: &str, local_only: bool) -> Result<String> {
    // Try daemon first
    if let Some(response) = try_daemon(query, local_only)? {
        return Ok(response);
    }

    // Try Claude API
    if !local_only {
        if let Ok(api_key) = env::var("ANTHROPIC_API_KEY") {
            if !api_key.is_empty() {
                if let Ok(response) = query_claude(query, &api_key) {
                    return Ok(response);
                }
            }
        }
    }

    // Try Ollama (auto-detect at localhost:11434 if OLLAMA_HOST not set)
    let ollama_host =
        env::var("OLLAMA_HOST").unwrap_or_else(|_| "http://localhost:11434".to_string());
    if let Ok(response) = query_ollama(query, &ollama_host) {
        return Ok(response);
    }

    // No AI available
    let response = serde_json::json!({
        "status": "no_ai",
        "message": "No AI backend available.",
        "hint": "Set ANTHROPIC_API_KEY or OLLAMA_HOST"
    });
    Ok(serde_json::to_string_pretty(&response)?)
}

/// Try to connect to CX daemon
fn try_daemon(query: &str, local_only: bool) -> Result<Option<String>> {
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
                "local_only": local_only,
            });
            stream.write_all(&serde_json::to_vec(&request)?)?;
            stream.shutdown(std::net::Shutdown::Write)?;

            let mut response = String::new();
            stream.read_to_string(&mut response)?;
            Ok(Some(response))
        }
        Err(_) => Ok(None),
    }
}

/// Query Claude API
fn query_claude(query: &str, api_key: &str) -> Result<String> {
    let context = ProjectContext::detect();
    let system_prompt = build_agent_prompt(&context);

    let base_url = env::var("ANTHROPIC_BASE_URL")
        .unwrap_or_else(|_| "https://api.anthropic.com".to_string());
    let model =
        env::var("CX_MODEL").unwrap_or_else(|_| "claude-sonnet-4-20250514".to_string());

    let payload = serde_json::json!({
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": query}]
    });

    let output = Command::new("curl")
        .args([
            "-s",
            "-X",
            "POST",
            &format!("{}/v1/messages", base_url),
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
            return Ok(serde_json::json!({
                "status": "success",
                "source": "claude",
                "response": content,
            })
            .to_string());
        }
    }
    anyhow::bail!("Claude API request failed")
}

/// Query Ollama local LLM
fn query_ollama(query: &str, host: &str) -> Result<String> {
    // Get model from env, or auto-detect best available model
    let model = env::var("OLLAMA_MODEL").unwrap_or_else(|_| detect_best_ollama_model(host));

    let context = ProjectContext::detect();
    let system_prompt = build_agent_prompt(&context);

    let payload = serde_json::json!({
        "model": model,
        "system": system_prompt,
        "prompt": query,
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
            return Ok(serde_json::json!({
                "status": "success",
                "source": "ollama",
                "response": text,
            })
            .to_string());
        }
    }
    anyhow::bail!("Ollama request failed")
}

/// Auto-detect best available Ollama model
fn detect_best_ollama_model(host: &str) -> String {
    if let Ok(output) = Command::new("curl")
        .args(["-s", &format!("{}/api/tags", host)])
        .output()
    {
        if let Ok(tags) = serde_json::from_slice::<serde_json::Value>(&output.stdout) {
            if let Some(models) = tags["models"].as_array() {
                // Prefer 7b+ models over smaller ones
                for model in models {
                    if let Some(name) = model["name"].as_str() {
                        if name.contains("7b") || name.contains("8b") || name.contains("13b") {
                            return name.to_string();
                        }
                    }
                }
                // Fallback to first model
                if let Some(first) = models.first() {
                    if let Some(name) = first["name"].as_str() {
                        return name.to_string();
                    }
                }
            }
        }
    }
    "llama3".to_string() // fallback
}

/// Build the agent-focused system prompt
fn build_agent_prompt(context: &ProjectContext) -> String {
    let is_macos = cfg!(target_os = "macos");

    format!(
        r#"You are CX, an AI terminal assistant.

OS: {os}
Directory: {cwd}

If the user wants to DO something on their computer (check files, install software, see system info, run programs), give a shell command in ```bash block.

If the user is just TALKING to you (greetings, questions about you, chitchat), respond naturally with text - no commands.

Keep commands simple. One command when possible. No explanations unless asked."#,
        os = if is_macos {
            "macOS (use brew, not apt)"
        } else {
            "Linux"
        },
        cwd = context.cwd.display(),
    )
}
