/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
*/

//! Dry-run-by-default guards for `cx ask` and related natural-language entry points.

use std::io::{self, Write};

/// True when a **pattern-matched** `cx …` invocation is read-only (may run without `--execute`).
/// Does not apply to arbitrary AI-suggested shell text.
pub fn is_read_only_cx_cli(command: &str) -> bool {
    let cmd = command.trim();

    // Reject shell metacharacters to prevent command injection
    if cmd.contains(&[';', '&', '|', '$', '`', '>', '<', '\n'][..]) {
        return false;
    }

    // Exact match only to prevent injection via suffix
    matches!(
        cmd,
        "cx snapshots -l"
            | "cx snapshots --list"
            | "cx new --list"
            | "cx daemon status"
            | "cx daemon health"
    )
}

/// Whether stdin is an interactive terminal (required for confirmation prompts).
pub fn stdin_is_interactive() -> bool {
    #[cfg(unix)]
    {
        unsafe { libc::isatty(libc::STDIN_FILENO) == 1 }
    }
    #[cfg(not(unix))]
    {
        false
    }
}

/// Print the dry-run preview banner and exact command(s).
pub fn print_dry_run_preview(commands: &[&str]) {
    eprintln!();
    eprintln!("┌─ Dry-run preview (no changes applied) ─────────────────");
    for c in commands {
        eprintln!("│  $ {}", c);
    }
    eprintln!("└────────────────────────────────────────────────────────");
    eprintln!("To run: add --execute (-d) and confirm at the prompt, or use -d -y");
    eprintln!();
}

/// Whether execution is allowed for a state-changing command.
///
/// `-y` / `auto_confirm` is ignored unless `execute_flag` is set — preview-only stays preview-only.
pub fn execution_gate(execute_flag: bool, auto_confirm: bool) -> ExecutionGate {
    if !execute_flag {
        return ExecutionGate::PreviewOnly;
    }
    if auto_confirm && execute_flag {
        return ExecutionGate::RunNow;
    }
    ExecutionGate::ConfirmFirst
}

/// Effective auto-confirm: `-y` only applies together with `--execute` / `-d`.
pub fn effective_auto_confirm(execute_flag: bool, auto_confirm: bool) -> bool {
    execute_flag && auto_confirm
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionGate {
    PreviewOnly,
    ConfirmFirst,
    RunNow,
}

/// Interpret the answer to a `[Y/n]` prompt (default yes when interactive).
pub fn confirmed_default_yes(answer: Option<&str>) -> bool {
    match answer {
        None => false,
        Some(line) => {
            let line = line.trim();
            line.is_empty() || line.eq_ignore_ascii_case("y")
        }
    }
}

/// Interpret the answer to a `[y/N]` prompt (default no).
pub fn confirmed_default_no(answer: Option<&str>) -> bool {
    match answer {
        None => false,
        Some(line) => line.trim().eq_ignore_ascii_case("y"),
    }
}

/// Read a confirmation line; `None` means EOF (never consent).
pub fn read_confirmation_line() -> io::Result<Option<String>> {
    let mut input = String::new();
    let bytes_read = io::stdin().read_line(&mut input)?;
    if bytes_read == 0 {
        Ok(None)
    } else {
        Ok(Some(input))
    }
}

/// Prompt for `[Y/n]` with default yes; returns false on EOF or explicit no.
pub fn prompt_default_yes(message: &str) -> io::Result<bool> {
    eprint!("{}", message);
    io::stderr().flush()?;
    let answer = read_confirmation_line()?;
    Ok(confirmed_default_yes(answer.as_deref()))
}

/// Prompt for `[y/N]` with default no; returns false on EOF or empty line.
pub fn prompt_default_no(message: &str) -> io::Result<bool> {
    eprint!("{}", message);
    io::stderr().flush()?;
    let answer = read_confirmation_line()?;
    Ok(confirmed_default_no(answer.as_deref()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn read_only_cx_listing() {
        assert!(is_read_only_cx_cli("cx snapshots -l"));
        assert!(is_read_only_cx_cli("cx new --list"));
        assert!(!is_read_only_cx_cli("cx save my-work"));
        assert!(!is_read_only_cx_cli("cx daemon alerts --acknowledge-all"));
    }

    #[test]
    fn read_only_rejects_command_injection() {
        // Command injection via semicolon
        assert!(!is_read_only_cx_cli("cx snapshots -l; touch /tmp/x"));
        assert!(!is_read_only_cx_cli("cx snapshots -l && rm -rf /"));

        // Command injection via pipe
        assert!(!is_read_only_cx_cli("cx snapshots -l | sh"));

        // Command injection via command substitution
        assert!(!is_read_only_cx_cli("cx snapshots -l $(malicious)"));
        assert!(!is_read_only_cx_cli("cx snapshots -l `malicious`"));

        // Additional arguments that don't match the exact pattern
        assert!(!is_read_only_cx_cli("cx snapshots -l --extra"));
    }

    #[test]
    fn execution_gate_preview_by_default() {
        assert_eq!(execution_gate(false, false), ExecutionGate::PreviewOnly);
        assert_eq!(
            execution_gate(false, true),
            ExecutionGate::PreviewOnly,
            "-y without --execute must not run"
        );
        assert_eq!(execution_gate(true, true), ExecutionGate::RunNow);
        assert_eq!(execution_gate(true, false), ExecutionGate::ConfirmFirst);
    }

    #[test]
    fn effective_auto_confirm_requires_execute() {
        assert!(!effective_auto_confirm(false, true));
        assert!(effective_auto_confirm(true, true));
    }

    #[test]
    fn eof_is_never_consent_yes_default() {
        assert!(!confirmed_default_yes(None));
    }

    #[test]
    fn eof_is_never_consent_no_default() {
        assert!(!confirmed_default_no(None));
        assert!(!confirmed_default_no(Some("\n")));
    }

    #[test]
    fn explicit_yes_confirms_no_default() {
        assert!(confirmed_default_no(Some("y\n")));
    }
}
