/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/

//! CX Terminal: turn raw AI backend text into something a user can read and act on.
//!
//! The backends answer in three shapes:
//! - the CX local model (`cxlinux-ai-7b`) follows `CX_SYSTEM_PROMPT` and returns JSON:
//!   `{"summary", "commands": [{"command_template", "explanation"}]}`,
//!   `{"tool_call": {"name", "arguments"}}` or `{"refusal": true, ...}`;
//! - Claude and Ollama return Markdown with fenced ```bash blocks;
//! - anything else is plain text.
//!
//! Before this module the CLI printed the local model's JSON verbatim and never found
//! a command to run in any AI answer. Parsing is pure and deterministic so it can be
//! unit-tested without a model.

use serde_json::Value;

/// One suggested shell command.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SuggestedCommand {
    pub command: String,
    pub explanation: Option<String>,
}

/// A parsed AI answer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AiReply {
    /// Commands to show (and run only through the normal confirmation path).
    Commands {
        summary: Option<String>,
        commands: Vec<SuggestedCommand>,
    },
    /// The model declined; may offer a safer alternative.
    Refusal {
        message: String,
        safe_alternative: Option<String>,
    },
    /// Prose answer with no runnable command.
    Text(String),
}

impl AiReply {
    /// Commands in this reply, in order. Empty for refusals and plain text.
    pub fn commands(&self) -> Vec<String> {
        match self {
            AiReply::Commands { commands, .. } => {
                commands.iter().map(|c| c.command.clone()).collect()
            }
            _ => Vec::new(),
        }
    }

    /// Human-readable rendering for the terminal.
    pub fn render(&self) -> String {
        match self {
            AiReply::Commands { summary, commands } => {
                let mut out = String::new();
                if let Some(s) = summary {
                    out.push_str(s.trim());
                    out.push('\n');
                }
                for c in commands {
                    out.push_str(&format!("\n  $ {}", c.command));
                    if let Some(e) = &c.explanation {
                        out.push_str(&format!("\n    {}", e.trim()));
                    }
                }
                out
            }
            AiReply::Refusal {
                message,
                safe_alternative,
            } => {
                let mut out = format!("Declined: {}", message.trim());
                if let Some(alt) = safe_alternative {
                    out.push_str(&format!("\nSafer alternative: {}", alt.trim()));
                }
                out
            }
            AiReply::Text(t) => t.trim().to_string(),
        }
    }
}

/// Parse the text an AI backend returned.
pub fn parse_ai_text(text: &str) -> AiReply {
    if let Some(json) = first_json_object(text) {
        if let Some(reply) = from_model_json(&json) {
            return reply;
        }
    }

    let fenced = fenced_shell_commands(text);
    if !fenced.is_empty() {
        let summary = text
            .split("```")
            .next()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);
        return AiReply::Commands {
            summary,
            commands: fenced
                .into_iter()
                .map(|command| SuggestedCommand {
                    command,
                    explanation: None,
                })
                .collect(),
        };
    }

    AiReply::Text(text.trim().to_string())
}

/// Commands found in a full `cx ask` response envelope (`{"response": "..."}`).
pub fn commands_from_envelope(envelope: &Value) -> Vec<String> {
    envelope
        .get("response")
        .and_then(Value::as_str)
        .map(|t| parse_ai_text(t).commands())
        .unwrap_or_default()
}

fn from_model_json(json: &Value) -> Option<AiReply> {
    if json.get("refusal").and_then(Value::as_bool) == Some(true) {
        return Some(AiReply::Refusal {
            message: json
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("request declined")
                .to_string(),
            safe_alternative: json
                .get("safe_alternative")
                .and_then(Value::as_str)
                .map(str::to_string),
        });
    }

    if let Some(list) = json.get("commands").and_then(Value::as_array) {
        let commands: Vec<SuggestedCommand> = list
            .iter()
            .filter_map(|c| {
                let command = c
                    .get("command_template")
                    .or_else(|| c.get("command"))
                    .and_then(Value::as_str)?
                    .trim();
                if command.is_empty() {
                    return None;
                }
                Some(SuggestedCommand {
                    command: command.to_string(),
                    explanation: c
                        .get("explanation")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                })
            })
            .collect();
        if !commands.is_empty() {
            return Some(AiReply::Commands {
                summary: json
                    .get("summary")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                commands,
            });
        }
    }

    if let Some(call) = json.get("tool_call") {
        return Some(from_tool_call(call));
    }

    None
}

/// The CLI has no tool runtime, so a tool call becomes the equivalent read-only
/// command for the user to run. Arguments are only accepted when they are plain
/// identifiers (package, service or app names); anything else is shown as text and
/// never turned into a command.
fn from_tool_call(call: &Value) -> AiReply {
    let name = call.get("name").and_then(Value::as_str).unwrap_or("");
    let args = call.get("arguments").cloned().unwrap_or(Value::Null);
    let arg = |k: &str| args.get(k).and_then(Value::as_str).map(str::trim);
    let lines = args
        .get("lines")
        .and_then(Value::as_u64)
        .unwrap_or(50)
        .clamp(1, 1000);

    let suggestion: Option<(String, String)> = match name {
        "search_packages" => arg("query").filter(|q| is_plain_token(q)).map(|q| {
            match arg("source").unwrap_or("apt") {
                "snap" => (
                    format!("snap find {}", q),
                    format!("Search snaps for {}", q),
                ),
                _ => (
                    format!("apt-cache search {}", q),
                    format!("Search APT packages for {}", q),
                ),
            }
        }),
        "get_system_info" => match arg("info_type").unwrap_or("") {
            "disk" | "storage" => Some(("df -h".into(), "Disk usage".into())),
            "memory" | "ram" => Some(("free -h".into(), "Memory usage".into())),
            "cpu" => Some(("lscpu".into(), "CPU details".into())),
            "os" | "version" => Some(("cat /etc/os-release".into(), "OS version".into())),
            "network" => Some(("ip -brief addr".into(), "Network interfaces".into())),
            "processes" => Some((
                "ps aux --sort=-%cpu | head -n 15".into(),
                "Top processes".into(),
            )),
            _ => None,
        },
        "troubleshoot" => arg("service").filter(|s| is_plain_token(s)).map(|s| {
            (
                format!("systemctl status {} --no-pager", s),
                format!("Status of {}", s),
            )
        }),
        "read_logs" => arg("service")
            .or_else(|| arg("source"))
            .filter(|s| is_plain_token(s))
            .map(|s| {
                (
                    format!("journalctl -u {} -n {} --no-pager", s, lines),
                    format!("Last {} log lines for {}", lines, s),
                )
            }),
        "kb_lookup" => arg("application")
            .filter(|a| is_plain_token(a))
            .map(|a| (format!("man {}", a), format!("Manual for {}", a))),
        _ => None,
    };

    match suggestion {
        Some((command, explanation)) => AiReply::Commands {
            summary: None,
            commands: vec![SuggestedCommand {
                command,
                explanation: Some(explanation),
            }],
        },
        None => AiReply::Text(format!(
            "The model asked for a tool this CLI can't run yet: {} {}",
            name,
            if args.is_null() {
                String::new()
            } else {
                args.to_string()
            }
        )),
    }
}

/// A package/service/app name: no whitespace or shell metacharacters.
fn is_plain_token(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '+' | '-' | '@' | ':'))
        && !s.starts_with('-')
}

/// First balanced `{...}` object in the text that parses as JSON (the model sometimes
/// wraps it in prose or a ```json fence).
fn first_json_object(text: &str) -> Option<Value> {
    let bytes = text.as_bytes();
    let mut start = 0;
    while let Some(off) = text[start..].find('{') {
        let open = start + off;
        let mut depth = 0i32;
        let mut in_str = false;
        let mut escaped = false;
        for (i, &b) in bytes.iter().enumerate().skip(open) {
            if in_str {
                match b {
                    _ if escaped => escaped = false,
                    b'\\' => escaped = true,
                    b'"' => in_str = false,
                    _ => {}
                }
                continue;
            }
            match b {
                b'"' => in_str = true,
                b'{' => depth += 1,
                b'}' => {
                    depth -= 1;
                    if depth == 0 {
                        if let Ok(v) = serde_json::from_str::<Value>(&text[open..=i]) {
                            if v.is_object() {
                                return Some(v);
                            }
                        }
                        break;
                    }
                }
                _ => {}
            }
        }
        start = open + 1;
    }
    None
}

/// Lines inside ```bash / ```sh / ```shell / ``` fences, with `$ ` prompts and
/// comment-only lines removed.
fn fenced_shell_commands(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut in_block = false;
    let mut shell_block = false;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(lang) = trimmed.strip_prefix("```") {
            if in_block {
                in_block = false;
            } else {
                in_block = true;
                let lang = lang.trim().to_ascii_lowercase();
                shell_block = matches!(
                    lang.as_str(),
                    "" | "bash" | "sh" | "shell" | "zsh" | "console"
                );
            }
            continue;
        }
        if in_block && shell_block {
            let cmd = trimmed.strip_prefix("$ ").unwrap_or(trimmed).trim();
            if !cmd.is_empty() && !cmd.starts_with('#') {
                out.push(cmd.to_string());
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    // Verbatim output of cxlinux-ai-7b-Q4_K_M.gguf on 2026-10-21 for
    // `cx ask -d "how do I check disk usage"`.
    const LOCAL_COMMANDS: &str = r#"{"summary": "Check disk usage", "commands": [{"command_template": "df -h", "explanation": "Show disk space usage"}, {"command_template": "du -sh *", "explanation": "Show directory sizes"}]}"#;
    // Verbatim output for `cx ask -d "install nginx"`.
    const LOCAL_TOOL_CALL: &str = r#"{"tool_call": {"name": "search_packages", "arguments": {"query": "nginx", "source": "apt"}}}"#;

    #[test]
    fn local_model_commands_are_parsed() {
        let reply = parse_ai_text(LOCAL_COMMANDS);
        assert_eq!(reply.commands(), vec!["df -h", "du -sh *"]);
        let shown = reply.render();
        assert!(shown.starts_with("Check disk usage"));
        assert!(shown.contains("$ df -h"));
        assert!(shown.contains("Show directory sizes"));
        assert!(!shown.contains("command_template"));
    }

    #[test]
    fn search_packages_tool_call_becomes_apt_search() {
        let reply = parse_ai_text(LOCAL_TOOL_CALL);
        assert_eq!(reply.commands(), vec!["apt-cache search nginx"]);
    }

    #[test]
    fn tool_call_with_shell_metacharacters_is_never_a_command() {
        for q in ["nginx; rm -rf /", "$(id)", "a b", "`id`", "-o x", ""] {
            let text = serde_json::json!({
                "tool_call": {"name": "search_packages", "arguments": {"query": q}}
            })
            .to_string();
            let reply = parse_ai_text(&text);
            assert!(
                reply.commands().is_empty(),
                "query {:?} produced a command",
                q
            );
        }
    }

    #[test]
    fn other_tool_calls_map_to_read_only_commands() {
        let c = |t: &str| parse_ai_text(t).commands();
        assert_eq!(
            c(r#"{"tool_call":{"name":"get_system_info","arguments":{"info_type":"memory"}}}"#),
            vec!["free -h"]
        );
        assert_eq!(
            c(
                r#"{"tool_call":{"name":"read_logs","arguments":{"source":"journal","service":"nginx","lines":20}}}"#
            ),
            vec!["journalctl -u nginx -n 20 --no-pager"]
        );
        assert_eq!(
            c(r#"{"tool_call":{"name":"troubleshoot","arguments":{"service":"docker"}}}"#),
            vec!["systemctl status docker --no-pager"]
        );
        assert!(c(r#"{"tool_call":{"name":"unknown","arguments":{}}}"#).is_empty());
    }

    #[test]
    fn refusal_is_rendered_and_has_no_commands() {
        let reply = parse_ai_text(
            r#"{"refusal": true, "message": "That would wipe the disk", "safe_alternative": "lsblk"}"#,
        );
        assert!(reply.commands().is_empty());
        assert_eq!(
            reply.render(),
            "Declined: That would wipe the disk\nSafer alternative: lsblk"
        );
    }

    #[test]
    fn json_wrapped_in_prose_or_fence_is_found() {
        let text = format!("Here you go:\n```json\n{}\n```\n", LOCAL_COMMANDS);
        assert_eq!(parse_ai_text(&text).commands(), vec!["df -h", "du -sh *"]);
    }

    #[test]
    fn braces_inside_strings_do_not_break_json_detection() {
        let text = r#"{"summary": "a } b", "commands": [{"command_template": "echo '{}'"}]}"#;
        assert_eq!(parse_ai_text(text).commands(), vec!["echo '{}'"]);
    }

    #[test]
    fn markdown_bash_blocks_are_extracted() {
        let text = "Install it with:\n\n```bash\n# refresh\n$ sudo apt update\nsudo apt install -y nginx\n```\n\nThen open port 80.";
        let reply = parse_ai_text(text);
        assert_eq!(
            reply.commands(),
            vec!["sudo apt update", "sudo apt install -y nginx"]
        );
        assert!(reply.render().starts_with("Install it with:"));
    }

    #[test]
    fn non_shell_fences_are_ignored() {
        let text = "Config:\n```yaml\nkey: value\n```";
        assert_eq!(parse_ai_text(text), AiReply::Text(text.to_string()));
    }

    #[test]
    fn plain_text_passes_through() {
        assert_eq!(
            parse_ai_text("  Use df to see disk usage.  "),
            AiReply::Text("Use df to see disk usage.".to_string())
        );
    }

    #[test]
    fn envelope_helper_reads_response_field() {
        let env =
            serde_json::json!({"status": "success", "source": "local", "response": LOCAL_COMMANDS});
        assert_eq!(commands_from_envelope(&env), vec!["df -h", "du -sh *"]);
        assert!(commands_from_envelope(&serde_json::json!({"status": "error"})).is_empty());
    }
}
