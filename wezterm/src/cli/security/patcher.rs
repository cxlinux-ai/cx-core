/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! Autonomous Patcher Module
//!
//! Applies security patches with safety controls including:
//! - Dry-run by default
//! - Whitelist/blacklist support
//! - Severity-based filtering
//! - Rollback capability via installation history

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::process::Command;

use super::database::{PatchRecord, PatchStatus, SecurityDatabase};
use super::scanner::{self, ScanSummary, Severity, VulnerablePackage};
use super::{PatchCommand, PatchStrategy};

/// Patch plan for a single package
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchPlan {
    pub package_name: String,
    pub current_version: String,
    pub target_version: String,
    pub vulnerabilities_fixed: Vec<String>,
    pub severity: Severity,
    pub safe_to_apply: bool,
    pub reason: Option<String>,
}

/// Overall patching result
#[derive(Debug, Default, Serialize)]
pub struct PatchResult {
    pub planned: usize,
    pub applied: usize,
    pub skipped: usize,
    pub failed: usize,
    pub patches: Vec<PatchPlan>,
    pub errors: Vec<String>,
}

/// Run the patching operation
pub fn run_patch(cmd: PatchCommand) -> Result<()> {
    println!("🔧 CX Linux Autonomous Patcher");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    if !cmd.apply {
        println!("⚠️  DRY-RUN MODE (use --apply to actually patch)");
        println!();
    }

    // Load configuration
    let config = load_patcher_config()?;
    let whitelist: HashSet<String> = cmd
        .whitelist
        .iter()
        .cloned()
        .chain(config.whitelist.iter().cloned())
        .collect();
    let blacklist: HashSet<String> = cmd
        .blacklist
        .iter()
        .cloned()
        .chain(config.blacklist.iter().cloned())
        .collect();

    // Get vulnerabilities to patch
    let vulnerable_packages = if cmd.scan_and_patch {
        println!("🔍 Running security scan first...");
        println!();

        // Run a scan
        let packages = scanner::get_installed_packages()?;
        let mut cache = super::database::VulnerabilityCache::load()?;

        let mut vulnerable = Vec::new();
        for package in &packages {
            let vulns = scanner::query_osv(package, &mut cache)?;
            if !vulns.is_empty() {
                vulnerable.push(VulnerablePackage {
                    package: package.clone(),
                    vulnerabilities: vulns,
                });
            }
        }
        cache.save()?;
        vulnerable
    } else {
        // Load from last scan
        let db = SecurityDatabase::open()?;
        db.get_vulnerable_packages()?
    };

    if vulnerable_packages.is_empty() {
        println!("✅ No vulnerabilities found. System is secure!");
        return Ok(());
    }

    // Build patch plan
    let mut result = PatchResult::default();

    println!("📋 Building patch plan...");
    println!();

    for vp in &vulnerable_packages {
        // Check blacklist
        if blacklist.contains(&vp.package.name) {
            println!("⏭️  Skipping {} (blacklisted)", vp.package.name);
            result.skipped += 1;
            continue;
        }

        // Get highest severity
        let max_severity = vp
            .vulnerabilities
            .iter()
            .map(|v| &v.severity)
            .max()
            .cloned()
            .unwrap_or(Severity::Unknown);

        // Check strategy
        let should_patch = match cmd.strategy {
            PatchStrategy::CriticalOnly => max_severity == Severity::Critical,
            PatchStrategy::HighAndAbove => {
                max_severity == Severity::Critical || max_severity == Severity::High
            }
            PatchStrategy::All => true,
            PatchStrategy::Automatic => {
                // Auto: patch critical and high, or if whitelisted
                max_severity == Severity::Critical
                    || max_severity == Severity::High
                    || whitelist.contains(&vp.package.name)
            }
        };

        if !should_patch && !whitelist.contains(&vp.package.name) {
            println!(
                "⏭️  Skipping {} ({} severity, strategy: {:?})",
                vp.package.name,
                max_severity.label(),
                cmd.strategy
            );
            result.skipped += 1;
            continue;
        }

        // Get available update
        let target_version = get_available_update(&vp.package.name)?;

        if let Some(ref target) = target_version {
            // Check if fix version is available
            let has_fix = vp.vulnerabilities.iter().any(|v| {
                v.fixed_version
                    .as_ref()
                    .map(|f| target >= f)
                    .unwrap_or(false)
            });

            let vuln_ids: Vec<String> = vp
                .vulnerabilities
                .iter()
                .flat_map(|v| {
                    if !v.aliases.is_empty() {
                        v.aliases.clone()
                    } else {
                        vec![v.id.clone()]
                    }
                })
                .collect();

            let plan = PatchPlan {
                package_name: vp.package.name.clone(),
                current_version: vp.package.version.clone(),
                target_version: target.clone(),
                vulnerabilities_fixed: vuln_ids,
                severity: max_severity,
                safe_to_apply: has_fix,
                reason: if has_fix {
                    None
                } else {
                    Some("Update may not fully fix vulnerability".into())
                },
            };

            println!(
                "{} {} {} → {}",
                max_severity.emoji(),
                plan.package_name,
                plan.current_version,
                plan.target_version
            );
            for cve in &plan.vulnerabilities_fixed {
                println!("     Fixes: {}", cve);
            }
            if let Some(ref reason) = plan.reason {
                println!("     ⚠️  {}", reason);
            }

            result.patches.push(plan);
            result.planned += 1;
        } else {
            println!("⚠️  {} - No update available", vp.package.name);
            result.skipped += 1;
        }
    }

    println!();
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("📊 Patch Plan Summary:");
    println!("   To be patched: {}", result.planned);
    println!("   Skipped:       {}", result.skipped);
    println!();

    if result.planned == 0 {
        println!("✅ No patches to apply based on current strategy.");
        return Ok(());
    }

    // Apply patches if --apply flag is set
    if cmd.apply {
        // Confirm unless --yes
        if !cmd.yes {
            println!(
                "⚠️  This will modify {} packages. Continue? [y/N] ",
                result.planned
            );
            let mut input = String::new();
            std::io::stdin().read_line(&mut input)?;
            if !input.trim().eq_ignore_ascii_case("y") {
                println!("Aborted.");
                return Ok(());
            }
        }

        // Create snapshot if requested
        if cmd.snapshot {
            println!("📸 Creating system snapshot...");
            create_snapshot()?;
        }

        // Open database for recording
        let db = SecurityDatabase::open()?;

        println!();
        println!("🚀 Applying patches...");
        println!();

        for plan in &result.patches {
            print!("   {} {}... ", plan.severity.emoji(), plan.package_name);
            std::io::Write::flush(&mut std::io::stdout())?;

            match apply_patch(&plan.package_name, &plan.target_version) {
                Ok(()) => {
                    println!("✅");
                    result.applied += 1;

                    // Record in database
                    db.record_patch(&PatchRecord {
                        id: uuid::Uuid::new_v4().to_string(),
                        package_name: plan.package_name.clone(),
                        from_version: plan.current_version.clone(),
                        to_version: plan.target_version.clone(),
                        vulnerabilities_fixed: plan.vulnerabilities_fixed.clone(),
                        status: PatchStatus::Applied,
                        applied_at: chrono::Utc::now().to_rfc3339(),
                        rollback_available: true,
                    })?;
                }
                Err(e) => {
                    println!("❌ {}", e);
                    result.failed += 1;
                    result.errors.push(format!("{}: {}", plan.package_name, e));
                }
            }
        }

        println!();
        println!(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        );
        println!("✅ Patching complete:");
        println!("   Applied: {}", result.applied);
        println!("   Failed:  {}", result.failed);

        if !result.errors.is_empty() {
            println!();
            println!("❌ Errors:");
            for err in &result.errors {
                println!("   • {}", err);
            }
        }
    } else {
        println!("ℹ️  Run with --apply to execute these patches.");
        println!(
            "   Example: cx security patch --scan-and-patch --strategy {:?} --apply",
            cmd.strategy
        );
    }

    Ok(())
}

/// Get available update version for a package
fn get_available_update(package_name: &str) -> Result<Option<String>> {
    // First, update package cache (silently)
    let _ = Command::new("apt-get").args(["update", "-qq"]).output();

    // Check for available updates
    let output = Command::new("apt-cache")
        .args(["policy", package_name])
        .output()
        .context("Failed to run apt-cache")?;

    if !output.status.success() {
        return Ok(None);
    }

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Parse apt-cache policy output
    let mut candidate_version = None;
    let mut installed_version = None;

    for line in stdout.lines() {
        let line = line.trim();
        if let Some(version) = line.strip_prefix("Candidate:") {
            candidate_version = Some(version.trim().to_string());
        } else if let Some(version) = line.strip_prefix("Installed:") {
            let v = version.trim();
            if v != "(none)" {
                installed_version = Some(v.to_string());
            }
        }
    }

    // Return candidate if it's different from installed
    match (candidate_version, installed_version) {
        (Some(candidate), Some(installed)) if candidate != installed => Ok(Some(candidate)),
        _ => Ok(None),
    }
}

/// Apply a patch to a specific package
fn apply_patch(package_name: &str, target_version: &str) -> Result<()> {
    // Use apt-get to install specific version
    let status = Command::new("apt-get")
        .args([
            "install",
            "-y",
            "--only-upgrade",
            &format!("{}={}", package_name, target_version),
        ])
        .status()
        .context("Failed to run apt-get")?;

    if !status.success() {
        // Try without version constraint
        let status = Command::new("apt-get")
            .args(["install", "-y", "--only-upgrade", package_name])
            .status()
            .context("Failed to run apt-get")?;

        if !status.success() {
            anyhow::bail!("apt-get returned non-zero exit code");
        }
    }

    Ok(())
}

/// Create a system snapshot before patching
fn create_snapshot() -> Result<()> {
    // Try timeshift first (common on many distros)
    let timeshift_result = Command::new("timeshift")
        .args(["--create", "--comments", "CX Security Auto-Patch Snapshot"])
        .status();

    if let Ok(status) = timeshift_result {
        if status.success() {
            println!("   ✅ Timeshift snapshot created");
            return Ok(());
        }
    }

    // Try snapper (openSUSE, some enterprise distros)
    let snapper_result = Command::new("snapper")
        .args(["create", "-d", "CX Security Auto-Patch"])
        .status();

    if let Ok(status) = snapper_result {
        if status.success() {
            println!("   ✅ Snapper snapshot created");
            return Ok(());
        }
    }

    // Log dpkg selections as fallback
    let dpkg_output = Command::new("dpkg")
        .args(["--get-selections"])
        .output()
        .context("Failed to get dpkg selections")?;

    let snapshot_dir = dirs::data_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("/var/lib"))
        .join("cx-linux")
        .join("snapshots");

    std::fs::create_dir_all(&snapshot_dir)?;

    let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S");
    let snapshot_file = snapshot_dir.join(format!("dpkg_selections_{}.txt", timestamp));

    std::fs::write(&snapshot_file, &dpkg_output.stdout)?;
    println!("   ✅ Package list saved to {:?}", snapshot_file);

    Ok(())
}

/// Patcher configuration
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct PatcherConfig {
    pub whitelist: Vec<String>,
    pub blacklist: Vec<String>,
    pub min_severity: String,
    pub auto_snapshot: bool,
}

/// Load patcher configuration
fn load_patcher_config() -> Result<PatcherConfig> {
    let config_path = dirs::config_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("~/.config"))
        .join("cx-linux")
        .join("patcher_config.json");

    if config_path.exists() {
        let content = std::fs::read_to_string(&config_path)?;
        Ok(serde_json::from_str(&content)?)
    } else {
        // Return default config
        Ok(PatcherConfig {
            whitelist: vec!["openssl".into(), "openssh-server".into()],
            blacklist: vec!["linux-image-generic".into()],
            min_severity: "medium".into(),
            auto_snapshot: true,
        })
    }
}

/// Rollback a previously applied patch
pub fn rollback_patch(patch_id: &str) -> Result<()> {
    let db = SecurityDatabase::open()?;
    let patch = db
        .get_patch(patch_id)?
        .ok_or_else(|| anyhow::anyhow!("Patch record not found: {}", patch_id))?;

    if !patch.rollback_available {
        anyhow::bail!("Rollback not available for this patch");
    }

    println!(
        "🔄 Rolling back {} from {} to {}",
        patch.package_name, patch.to_version, patch.from_version
    );

    // Install the previous version
    let status = Command::new("apt-get")
        .args([
            "install",
            "-y",
            "--allow-downgrades",
            &format!("{}={}", patch.package_name, patch.from_version),
        ])
        .status()
        .context("Failed to run apt-get")?;

    if !status.success() {
        anyhow::bail!("Rollback failed");
    }

    // Update record
    db.update_patch_status(patch_id, PatchStatus::RolledBack)?;

    println!("✅ Rollback complete");
    Ok(())
}
