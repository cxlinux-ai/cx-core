/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! Security Vulnerability Management Module
//!
//! Provides continuous vulnerability scanning, autonomous patching,
//! and scheduled security maintenance for CX Linux.
//!
//! # Features
//! - Vulnerability scanning against OSV and NVD databases
//! - Autonomous patching with safety controls
//! - Scheduled security maintenance via systemd timers
//! - Full rollback support via installation history
//!
//! # Example Usage
//! ```bash
//! # Scan all installed packages
//! cx security scan --all
//!
//! # Scan specific package
//! cx security scan --package openssl
//!
//! # Show only critical vulnerabilities
//! cx security scan --critical
//!
//! # Autonomous patching (dry-run by default)
//! cx security patch --scan-and-patch --strategy critical_only
//!
//! # Apply patches
//! cx security patch --scan-and-patch --strategy critical_only --apply
//!
//! # Schedule monthly patching
//! cx security schedule create monthly-patch --frequency monthly --enable-patch
//! ```

pub mod scanner;
pub mod patcher;
pub mod scheduler;
pub mod database;

use clap::{Parser, Subcommand};
use anyhow::Result;

/// Security vulnerability management commands
#[derive(Debug, Parser, Clone)]
pub struct SecurityCommand {
    #[command(subcommand)]
    pub sub: SecuritySubCommand,
}

#[derive(Debug, Subcommand, Clone)]
pub enum SecuritySubCommand {
    /// Scan installed packages for known vulnerabilities
    #[command(name = "scan")]
    Scan(ScanCommand),

    /// Apply security patches with safety controls
    #[command(name = "patch")]
    Patch(PatchCommand),

    /// Manage scheduled security scans and patches
    #[command(name = "schedule")]
    Schedule(ScheduleCommand),

    /// Show security status overview
    #[command(name = "status")]
    Status(StatusCommand),
}

/// Scan command options
#[derive(Debug, Parser, Clone)]
pub struct ScanCommand {
    /// Scan all installed packages
    #[arg(long, short = 'a')]
    pub all: bool,

    /// Scan specific package
    #[arg(long, short = 'p')]
    pub package: Option<String>,

    /// Show only critical vulnerabilities (CVSS >= 9.0)
    #[arg(long)]
    pub critical: bool,

    /// Show high and above vulnerabilities (CVSS >= 7.0)
    #[arg(long)]
    pub high: bool,

    /// Output format: table, json, or summary
    #[arg(long, default_value = "table")]
    pub format: OutputFormat,

    /// Skip cache and fetch fresh vulnerability data
    #[arg(long)]
    pub no_cache: bool,

    /// Verbose output with CVE details
    #[arg(long, short = 'v')]
    pub verbose: bool,
}

/// Patch command options
#[derive(Debug, Parser, Clone)]
pub struct PatchCommand {
    /// Scan and patch in one operation
    #[arg(long)]
    pub scan_and_patch: bool,

    /// Patching strategy
    #[arg(long, default_value = "critical_only")]
    pub strategy: PatchStrategy,

    /// Actually apply patches (default is dry-run)
    #[arg(long)]
    pub apply: bool,

    /// Skip confirmation prompts
    #[arg(long, short = 'y')]
    pub yes: bool,

    /// Packages to whitelist (always patch)
    #[arg(long)]
    pub whitelist: Vec<String>,

    /// Packages to blacklist (never patch)
    #[arg(long)]
    pub blacklist: Vec<String>,

    /// Create system snapshot before patching
    #[arg(long)]
    pub snapshot: bool,
}

/// Schedule command options
#[derive(Debug, Parser, Clone)]
pub struct ScheduleCommand {
    #[command(subcommand)]
    pub sub: ScheduleSubCommand,
}

#[derive(Debug, Subcommand, Clone)]
pub enum ScheduleSubCommand {
    /// Create a new security schedule
    #[command(name = "create")]
    Create(ScheduleCreateCommand),

    /// List all schedules
    #[command(name = "list")]
    List,

    /// Run a schedule manually
    #[command(name = "run")]
    Run { id: String },

    /// Delete a schedule
    #[command(name = "delete")]
    Delete { id: String },

    /// Install systemd timer for a schedule
    #[command(name = "install-timer")]
    InstallTimer { id: String },

    /// Remove systemd timer for a schedule
    #[command(name = "remove-timer")]
    RemoveTimer { id: String },
}

#[derive(Debug, Parser, Clone)]
pub struct ScheduleCreateCommand {
    /// Schedule name/identifier
    pub name: String,

    /// Frequency: daily, weekly, monthly
    #[arg(long, default_value = "monthly")]
    pub frequency: ScheduleFrequency,

    /// Enable automatic patching (default is scan-only)
    #[arg(long)]
    pub enable_patch: bool,

    /// Patch strategy if patching is enabled
    #[arg(long, default_value = "critical_only")]
    pub strategy: PatchStrategy,

    /// Send notification on completion
    #[arg(long)]
    pub notify: bool,
}

/// Status command options
#[derive(Debug, Parser, Clone)]
pub struct StatusCommand {
    /// Show detailed vulnerability breakdown
    #[arg(long, short = 'v')]
    pub verbose: bool,
}

/// Output format options
#[derive(Debug, Clone, Copy, Default)]
pub enum OutputFormat {
    #[default]
    Table,
    Json,
    Summary,
}

impl std::str::FromStr for OutputFormat {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "table" => Ok(OutputFormat::Table),
            "json" => Ok(OutputFormat::Json),
            "summary" => Ok(OutputFormat::Summary),
            _ => Err(anyhow::anyhow!("Unknown format: {}. Use table, json, or summary", s)),
        }
    }
}

/// Patching strategy
#[derive(Debug, Clone, Copy, Default, serde::Serialize, serde::Deserialize)]
pub enum PatchStrategy {
    /// Only patch critical vulnerabilities (CVSS >= 9.0)
    #[default]
    CriticalOnly,
    /// Patch high and critical (CVSS >= 7.0)
    HighAndAbove,
    /// Patch all vulnerabilities
    All,
    /// Automatic based on severity and confidence
    Automatic,
}

impl std::str::FromStr for PatchStrategy {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "critical_only" | "critical" => Ok(PatchStrategy::CriticalOnly),
            "high_and_above" | "high" => Ok(PatchStrategy::HighAndAbove),
            "all" => Ok(PatchStrategy::All),
            "automatic" | "auto" => Ok(PatchStrategy::Automatic),
            _ => Err(anyhow::anyhow!("Unknown strategy: {}. Use critical_only, high_and_above, all, or automatic", s)),
        }
    }
}

/// Schedule frequency
#[derive(Debug, Clone, Copy, Default, serde::Serialize, serde::Deserialize)]
pub enum ScheduleFrequency {
    Daily,
    Weekly,
    #[default]
    Monthly,
}

impl std::str::FromStr for ScheduleFrequency {
    type Err = anyhow::Error;
    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "daily" => Ok(ScheduleFrequency::Daily),
            "weekly" => Ok(ScheduleFrequency::Weekly),
            "monthly" => Ok(ScheduleFrequency::Monthly),
            _ => Err(anyhow::anyhow!("Unknown frequency: {}. Use daily, weekly, or monthly", s)),
        }
    }
}

impl SecurityCommand {
    pub fn run(self) -> Result<()> {
        match self.sub {
            SecuritySubCommand::Scan(cmd) => cmd.run(),
            SecuritySubCommand::Patch(cmd) => cmd.run(),
            SecuritySubCommand::Schedule(cmd) => cmd.run(),
            SecuritySubCommand::Status(cmd) => cmd.run(),
        }
    }
}

impl ScanCommand {
    pub fn run(self) -> Result<()> {
        scanner::run_scan(self)
    }
}

impl PatchCommand {
    pub fn run(self) -> Result<()> {
        patcher::run_patch(self)
    }
}

impl ScheduleCommand {
    pub fn run(self) -> Result<()> {
        scheduler::run_schedule(self)
    }
}

impl StatusCommand {
    pub fn run(self) -> Result<()> {
        scanner::show_status(self)
    }
}
