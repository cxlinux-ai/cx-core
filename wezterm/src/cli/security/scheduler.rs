/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! Security Scheduler Module
//!
//! Manages scheduled security scans and patches using systemd timers.
//! Supports daily, weekly, and monthly schedules with configurable actions.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::process::Command;

use super::{ScheduleCommand, ScheduleSubCommand, ScheduleCreateCommand, ScheduleFrequency, PatchStrategy};
use super::database::SecurityDatabase;

/// Schedule record stored in database
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Schedule {
    pub id: String,
    pub name: String,
    pub frequency: ScheduleFrequency,
    pub enable_patch: bool,
    pub patch_strategy: PatchStrategy,
    pub notify: bool,
    pub created_at: String,
    pub last_run: Option<String>,
    pub next_run: Option<String>,
    pub timer_installed: bool,
}

/// Systemd unit file paths
fn get_systemd_user_dir() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("~/.config"))
        .join("systemd")
        .join("user")
}

fn get_systemd_system_dir() -> PathBuf {
    PathBuf::from("/etc/systemd/system")
}

/// Run schedule command
pub fn run_schedule(cmd: ScheduleCommand) -> Result<()> {
    match cmd.sub {
        ScheduleSubCommand::Create(create_cmd) => create_schedule(create_cmd),
        ScheduleSubCommand::List => list_schedules(),
        ScheduleSubCommand::Run { id } => run_schedule_now(&id),
        ScheduleSubCommand::Delete { id } => delete_schedule(&id),
        ScheduleSubCommand::InstallTimer { id } => install_timer(&id),
        ScheduleSubCommand::RemoveTimer { id } => remove_timer(&id),
    }
}

/// Create a new security schedule
fn create_schedule(cmd: ScheduleCreateCommand) -> Result<()> {
    println!("📆 Creating security schedule: {}", cmd.name);

    let db = SecurityDatabase::open()?;

    // Check if schedule already exists
    if db.get_schedule(&cmd.name)?.is_some() {
        anyhow::bail!("Schedule '{}' already exists", cmd.name);
    }

    let schedule = Schedule {
        id: uuid::Uuid::new_v4().to_string(),
        name: cmd.name.clone(),
        frequency: cmd.frequency,
        enable_patch: cmd.enable_patch,
        patch_strategy: cmd.strategy,
        notify: cmd.notify,
        created_at: chrono::Utc::now().to_rfc3339(),
        last_run: None,
        next_run: Some(calculate_next_run(cmd.frequency)),
        timer_installed: false,
    };

    db.save_schedule(&schedule)?;

    println!("✅ Schedule created: {}", cmd.name);
    println!();
    println!("   Frequency:  {:?}", cmd.frequency);
    println!("   Patching:   {}", if cmd.enable_patch { "Enabled" } else { "Scan only" });
    if cmd.enable_patch {
        println!("   Strategy:   {:?}", cmd.strategy);
    }
    println!("   Notify:     {}", if cmd.notify { "Yes" } else { "No" });
    println!();
    println!("ℹ️  Run 'cx security schedule install-timer {}' to activate systemd timer", cmd.name);

    Ok(())
}

/// List all schedules
fn list_schedules() -> Result<()> {
    let db = SecurityDatabase::open()?;
    let schedules = db.get_schedules()?;

    println!("📆 Security Schedules");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    if schedules.is_empty() {
        println!("   No schedules configured.");
        println!();
        println!("   Create one with: cx security schedule create <name> --frequency monthly");
        return Ok(());
    }

    println!("{:<20} {:<10} {:<12} {:<10} {:<20}",
        "NAME", "FREQUENCY", "PATCHING", "TIMER", "LAST RUN");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    for schedule in &schedules {
        let timer_status = if schedule.timer_installed { "Active" } else { "Inactive" };
        let patch_status = if schedule.enable_patch {
            format!("{:?}", schedule.patch_strategy)
        } else {
            "Scan only".into()
        };

        println!("{:<20} {:<10} {:<12} {:<10} {:<20}",
            truncate(&schedule.name, 20),
            format!("{:?}", schedule.frequency),
            patch_status,
            timer_status,
            schedule.last_run.as_deref().unwrap_or("Never")
        );
    }

    println!();
    Ok(())
}

/// Run a schedule manually
fn run_schedule_now(id: &str) -> Result<()> {
    let db = SecurityDatabase::open()?;

    let schedule = db.get_schedule(id)?
        .ok_or_else(|| anyhow::anyhow!("Schedule '{}' not found", id))?;

    println!("🚀 Running schedule: {}", schedule.name);
    println!();

    // Run scan
    let scan_cmd = super::ScanCommand {
        all: true,
        package: None,
        critical: false,
        high: false,
        format: super::OutputFormat::Summary,
        no_cache: false,
        verbose: false,
    };

    super::scanner::run_scan(scan_cmd)?;

    // Run patch if enabled
    if schedule.enable_patch {
        println!();
        println!("🔧 Running autonomous patcher...");
        println!();

        let patch_cmd = super::PatchCommand {
            scan_and_patch: true,
            strategy: schedule.patch_strategy,
            apply: true,
            yes: true, // Auto-confirm for scheduled runs
            whitelist: Vec::new(),
            blacklist: Vec::new(),
            snapshot: true,
        };

        super::patcher::run_patch(patch_cmd)?;
    }

    // Update last run time
    db.update_schedule_last_run(&schedule.id)?;

    // Send notification if enabled
    if schedule.notify {
        send_notification(&schedule)?;
    }

    println!();
    println!("✅ Schedule '{}' completed", schedule.name);

    Ok(())
}

/// Delete a schedule
fn delete_schedule(id: &str) -> Result<()> {
    let db = SecurityDatabase::open()?;

    let schedule = db.get_schedule(id)?
        .ok_or_else(|| anyhow::anyhow!("Schedule '{}' not found", id))?;

    // Remove timer if installed
    if schedule.timer_installed {
        remove_timer(id)?;
    }

    db.delete_schedule(&schedule.id)?;

    println!("✅ Schedule '{}' deleted", schedule.name);
    Ok(())
}

/// Install systemd timer for a schedule
fn install_timer(id: &str) -> Result<()> {
    let db = SecurityDatabase::open()?;

    let mut schedule = db.get_schedule(id)?
        .ok_or_else(|| anyhow::anyhow!("Schedule '{}' not found", id))?;

    println!("⏱️  Installing systemd timer for: {}", schedule.name);

    // Determine if we need root (system-wide) or user timer
    let (timer_dir, use_user_mode) = if is_root() {
        (get_systemd_system_dir(), false)
    } else {
        let user_dir = get_systemd_user_dir();
        fs::create_dir_all(&user_dir)?;
        (user_dir, true)
    };

    let unit_name = format!("cx-security-{}", sanitize_name(&schedule.name));

    // Create service unit
    let service_content = generate_service_unit(&schedule, use_user_mode);
    let service_path = timer_dir.join(format!("{}.service", unit_name));
    fs::write(&service_path, service_content)
        .context("Failed to write service unit")?;

    // Create timer unit
    let timer_content = generate_timer_unit(&schedule);
    let timer_path = timer_dir.join(format!("{}.timer", unit_name));
    fs::write(&timer_path, timer_content)
        .context("Failed to write timer unit")?;

    // Reload systemd and enable timer
    let systemctl_args: Vec<&str> = if use_user_mode {
        vec!["--user"]
    } else {
        vec![]
    };

    // Reload daemon
    let mut reload_cmd = Command::new("systemctl");
    reload_cmd.args(&systemctl_args);
    reload_cmd.arg("daemon-reload");
    reload_cmd.status().context("Failed to reload systemd")?;

    // Enable and start timer
    let mut enable_cmd = Command::new("systemctl");
    enable_cmd.args(&systemctl_args);
    enable_cmd.args(["enable", "--now", &format!("{}.timer", unit_name)]);
    let status = enable_cmd.status().context("Failed to enable timer")?;

    if !status.success() {
        anyhow::bail!("Failed to enable systemd timer");
    }

    // Update schedule
    schedule.timer_installed = true;
    db.save_schedule(&schedule)?;

    println!("✅ Timer installed and started");
    println!();
    println!("   Service: {}.service", unit_name);
    println!("   Timer:   {}.timer", unit_name);
    println!();

    // Show timer status
    let mut status_cmd = Command::new("systemctl");
    status_cmd.args(&systemctl_args);
    status_cmd.args(["status", &format!("{}.timer", unit_name)]);
    let _ = status_cmd.status();

    Ok(())
}

/// Remove systemd timer for a schedule
fn remove_timer(id: &str) -> Result<()> {
    let db = SecurityDatabase::open()?;

    let mut schedule = db.get_schedule(id)?
        .ok_or_else(|| anyhow::anyhow!("Schedule '{}' not found", id))?;

    if !schedule.timer_installed {
        println!("ℹ️  Timer not installed for '{}'", schedule.name);
        return Ok(());
    }

    println!("🗑️  Removing systemd timer for: {}", schedule.name);

    let (timer_dir, use_user_mode) = if is_root() {
        (get_systemd_system_dir(), false)
    } else {
        (get_systemd_user_dir(), true)
    };

    let unit_name = format!("cx-security-{}", sanitize_name(&schedule.name));
    let systemctl_args: Vec<&str> = if use_user_mode {
        vec!["--user"]
    } else {
        vec![]
    };

    // Stop and disable timer
    let mut disable_cmd = Command::new("systemctl");
    disable_cmd.args(&systemctl_args);
    disable_cmd.args(["disable", "--now", &format!("{}.timer", unit_name)]);
    let _ = disable_cmd.status();

    // Remove unit files
    let service_path = timer_dir.join(format!("{}.service", unit_name));
    let timer_path = timer_dir.join(format!("{}.timer", unit_name));

    if service_path.exists() {
        fs::remove_file(&service_path)?;
    }
    if timer_path.exists() {
        fs::remove_file(&timer_path)?;
    }

    // Reload daemon
    let mut reload_cmd = Command::new("systemctl");
    reload_cmd.args(&systemctl_args);
    reload_cmd.arg("daemon-reload");
    let _ = reload_cmd.status();

    // Update schedule
    schedule.timer_installed = false;
    db.save_schedule(&schedule)?;

    println!("✅ Timer removed");

    Ok(())
}

/// Generate systemd service unit content
fn generate_service_unit(schedule: &Schedule, use_user_mode: bool) -> String {
    let mut args = vec!["security", "schedule", "run", &schedule.name];

    let exec_path = std::env::current_exe()
        .unwrap_or_else(|_| PathBuf::from("/usr/bin/cx"));

    format!(
        r#"[Unit]
Description=CX Linux Security Schedule: {name}
Documentation=https://cxlinux.com/docs/security
After=network-online.target

[Service]
Type=oneshot
ExecStart={exec} {args}
{user_section}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy={wanted_by}
"#,
        name = schedule.name,
        exec = exec_path.display(),
        args = args.join(" "),
        user_section = if use_user_mode { "" } else { "User=root" },
        wanted_by = if use_user_mode { "default.target" } else { "multi-user.target" }
    )
}

/// Generate systemd timer unit content
fn generate_timer_unit(schedule: &Schedule) -> String {
    let on_calendar = match schedule.frequency {
        ScheduleFrequency::Daily => "daily",
        ScheduleFrequency::Weekly => "weekly",
        ScheduleFrequency::Monthly => "monthly",
    };

    format!(
        r#"[Unit]
Description=CX Linux Security Timer: {name}
Documentation=https://cxlinux.com/docs/security

[Timer]
OnCalendar={calendar}
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
"#,
        name = schedule.name,
        calendar = on_calendar
    )
}

/// Calculate next run time based on frequency
fn calculate_next_run(frequency: ScheduleFrequency) -> String {
    let now = chrono::Utc::now();
    let next = match frequency {
        ScheduleFrequency::Daily => now + chrono::Duration::days(1),
        ScheduleFrequency::Weekly => now + chrono::Duration::weeks(1),
        ScheduleFrequency::Monthly => {
            // Add roughly a month
            now + chrono::Duration::days(30)
        }
    };
    next.to_rfc3339()
}

/// Send notification after schedule completion
fn send_notification(schedule: &Schedule) -> Result<()> {
    // Try desktop notification first
    let notify_result = Command::new("notify-send")
        .args([
            "--urgency=normal",
            "--app-name=CX Linux Security",
            &format!("Security Schedule '{}' Complete", schedule.name),
            "Security scan and patching completed successfully.",
        ])
        .status();

    if notify_result.is_ok() {
        return Ok(());
    }

    // Fallback to wall message (for servers)
    let _ = Command::new("wall")
        .arg(format!(
            "CX Linux: Security schedule '{}' completed.",
            schedule.name
        ))
        .status();

    Ok(())
}

/// Check if running as root
fn is_root() -> bool {
    unsafe { libc::geteuid() == 0 }
}

/// Sanitize name for use in systemd unit names
fn sanitize_name(name: &str) -> String {
    name.chars()
        .map(|c| if c.is_alphanumeric() || c == '-' { c } else { '-' })
        .collect::<String>()
        .to_lowercase()
}

/// Truncate string to max length
fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}...", &s[..max_len.saturating_sub(3)])
    }
}
