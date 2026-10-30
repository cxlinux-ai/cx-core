/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
*/

//! Local-first audit log and reversible operation history for CX CLI actions.

use super::command_sandbox::run_sandboxed_shell_in;
use super::execution_safety::{
    effective_auto_confirm, execution_gate, print_dry_run_preview, prompt_default_no,
    stdin_is_interactive, ExecutionGate,
};
use anyhow::{Context, Result};
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

const AUDIT_LOG: &str = "audit.log";
const TRANSACTIONS_LOG: &str = "transactions.jsonl";
const UNDONE_IDS: &str = "transactions.undone";

#[derive(Debug, Serialize, Deserialize)]
pub struct AuditEntry {
    pub ts: String,
    pub event: String,
    pub command: Option<String>,
    pub detail: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TransactionRecord {
    pub id: String,
    pub ts: String,
    pub command: String,
    pub undo: String,
    /// Working directory when the forward command ran (required for safe undo).
    #[serde(default)]
    pub cwd: Option<String>,
}

pub fn cx_data_dir() -> PathBuf {
    dirs::home_dir()
        .map(|h| h.join(".cx"))
        .unwrap_or_else(|| PathBuf::from(".cx"))
}

fn audit_path() -> PathBuf {
    cx_data_dir().join(AUDIT_LOG)
}

fn transactions_path() -> PathBuf {
    cx_data_dir().join(TRANSACTIONS_LOG)
}

fn undone_path() -> PathBuf {
    cx_data_dir().join(UNDONE_IDS)
}

fn ensure_data_dir() -> Result<PathBuf> {
    let dir = cx_data_dir();
    fs::create_dir_all(&dir).with_context(|| format!("create {}", dir.display()))?;
    Ok(dir)
}

/// Append a line to `~/.cx/audit.log` (JSON per line).
pub fn append_audit(event: &str, command: Option<&str>, detail: serde_json::Value) -> Result<()> {
    ensure_data_dir()?;
    let entry = AuditEntry {
        ts: chrono::Utc::now().to_rfc3339(),
        event: event.to_string(),
        command: command.map(|s| s.to_string()),
        detail,
    };
    let line = serde_json::to_string(&entry)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(audit_path())?;
    writeln!(file, "{}", line)?;
    Ok(())
}

/// Record a reversible command and return the transaction id.
pub fn record_transaction(command: &str, undo: &str) -> Result<String> {
    ensure_data_dir()?;
    let id = format!("tx-{}", chrono::Utc::now().timestamp_millis());
    let cwd = std::env::current_dir()
        .ok()
        .map(|p| p.to_string_lossy().to_string());
    let record = TransactionRecord {
        id: id.clone(),
        ts: chrono::Utc::now().to_rfc3339(),
        command: command.to_string(),
        undo: undo.to_string(),
        cwd,
    };
    let line = serde_json::to_string(&record)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(transactions_path())?;
    writeln!(file, "{}", line)?;
    Ok(id)
}

fn load_undone_ids() -> Result<HashSet<String>> {
    let path = undone_path();
    if !path.exists() {
        return Ok(HashSet::new());
    }
    let file = fs::File::open(&path)?;
    let reader = BufReader::new(file);
    let mut ids = HashSet::new();
    for line in reader.lines() {
        let line = line?.trim().to_string();
        if !line.is_empty() {
            ids.insert(line);
        }
    }
    Ok(ids)
}

fn mark_transaction_undone(id: &str) -> Result<()> {
    ensure_data_dir()?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(undone_path())?;
    writeln!(file, "{}", id)?;
    Ok(())
}

fn read_last_pending_transaction() -> Result<Option<TransactionRecord>> {
    let path = transactions_path();
    if !path.exists() {
        return Ok(None);
    }
    let undone = load_undone_ids()?;
    let file = fs::File::open(&path)?;
    let reader = BufReader::new(file);
    let mut last: Option<TransactionRecord> = None;
    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let record: TransactionRecord = serde_json::from_str(&line)?;
        if !undone.contains(&record.id) {
            last = Some(record);
        }
    }
    Ok(last)
}

/// Undo the most recent pending transaction (preview by default).
pub fn undo_last_transaction(execute: bool, auto_confirm: bool) -> Result<()> {
    let record = read_last_pending_transaction()?
        .ok_or_else(|| anyhow::anyhow!("No reversible operations in ~/.cx/transactions.jsonl"))?;

    print_dry_run_preview(&[&record.undo]);
    eprintln!("Undo forward command: {}", record.command);
    if let Some(ref cwd) = record.cwd {
        eprintln!("Original directory: {}", cwd);
    } else {
        eprintln!("Original directory: unknown (record predates cwd metadata; refusing undo).");
        return Ok(());
    }

    let auto = effective_auto_confirm(execute, auto_confirm);
    match execution_gate(execute, auto) {
        ExecutionGate::PreviewOnly => {
            append_audit(
                "undo_preview",
                Some(&record.undo),
                serde_json::json!({ "transaction_id": record.id }),
            )?;
            return Ok(());
        }
        ExecutionGate::ConfirmFirst => {
            if !stdin_is_interactive() {
                eprintln!("Non-interactive stdin; not undoing. Use: cx undo --execute -y");
                return Ok(());
            }
            if !prompt_default_no("\nRun undo? [y/N] ")? {
                eprintln!("Cancelled.");
                return Ok(());
            }
        }
        ExecutionGate::RunNow => {}
    }

    let cwd = Path::new(record.cwd.as_ref().unwrap());
    if !cwd.is_dir() {
        anyhow::bail!("Original directory no longer exists: {}", cwd.display());
    }

    eprintln!("$ {}", record.undo);
    let status =
        run_sandboxed_shell_in(&record.undo, Some(cwd)).context("failed to run undo command")?;

    if !status.success() {
        anyhow::bail!("Undo command failed with {:?}", status.code());
    }

    mark_transaction_undone(&record.id)?;

    append_audit(
        "undo",
        Some(&record.undo),
        serde_json::json!({
            "transaction_id": record.id,
            "original_command": record.command,
            "cwd": record.cwd,
        }),
    )?;

    eprintln!("✅ Undone.");
    Ok(())
}

/// Show the tail of the audit log (for demos and troubleshooting).
pub fn show_audit_tail(lines: usize) -> Result<()> {
    let path = audit_path();
    if !path.exists() {
        println!("(no audit log at {})", path.display());
        return Ok(());
    }
    let file = fs::File::open(&path)?;
    let reader = BufReader::new(file);
    let all: Vec<String> = reader.lines().collect::<Result<_, _>>()?;
    let start = all.len().saturating_sub(lines);
    for line in &all[start..] {
        println!("{}", line);
    }
    Ok(())
}

/// Remove CX local data (preview by default).
pub fn clean_local_data(execute: bool, auto_confirm: bool) -> Result<()> {
    let dir = cx_data_dir();
    print_dry_run_preview(&[&format!("rm -rf {}", dir.display())]);

    let auto = effective_auto_confirm(execute, auto_confirm);
    match execution_gate(execute, auto) {
        ExecutionGate::PreviewOnly => {
            eprintln!(
                "Dry-run only. Use: cx clean-local-data --execute and confirm, or -y with -d."
            );
            return Ok(());
        }
        ExecutionGate::ConfirmFirst => {
            if !stdin_is_interactive() {
                eprintln!(
                    "Non-interactive stdin; not deleting. Use: cx clean-local-data --execute -y"
                );
                return Ok(());
            }
            if !prompt_default_no("\nDelete all local CX data? [y/N] ")? {
                eprintln!("Cancelled.");
                return Ok(());
            }
        }
        ExecutionGate::RunNow => {}
    }

    if dir.exists() {
        fs::remove_dir_all(&dir).with_context(|| format!("remove {}", dir.display()))?;
        println!("Removed {}", dir.display());
    } else {
        println!("No {} directory", dir.display());
    }
    Ok(())
}

#[derive(Debug, Parser, Clone)]
pub struct UndoCommand {
    #[arg(long = "execute", short = 'd')]
    pub execute: bool,

    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,
}

impl UndoCommand {
    pub fn run(&self) -> Result<()> {
        undo_last_transaction(self.execute, self.auto_confirm)
    }
}

#[derive(Debug, Parser, Clone)]
pub struct AuditCommand {
    #[arg(long, short = 'n', default_value_t = 5)]
    pub tail: usize,
}

impl AuditCommand {
    pub fn run(&self) -> Result<()> {
        show_audit_tail(self.tail)
    }
}

#[derive(Debug, Parser, Clone)]
pub struct CleanLocalDataCommand {
    #[arg(long = "execute", short = 'd')]
    pub execute: bool,

    #[arg(long = "yes", short = 'y')]
    pub auto_confirm: bool,
}

impl CleanLocalDataCommand {
    pub fn run(&self) -> Result<()> {
        clean_local_data(self.execute, self.auto_confirm)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn audit_entry_roundtrip() {
        let entry = AuditEntry {
            ts: "2026-01-01T00:00:00Z".into(),
            event: "test".into(),
            command: Some("echo hi".into()),
            detail: serde_json::json!({}),
        };
        let line = serde_json::to_string(&entry).unwrap();
        let back: AuditEntry = serde_json::from_str(&line).unwrap();
        assert_eq!(back.event, "test");
    }
}
