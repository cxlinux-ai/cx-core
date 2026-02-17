/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! Vulnerability Scanner Module
//!
//! Scans installed packages against OSV (Open Source Vulnerabilities) and
//! NVD (National Vulnerability Database) to identify security issues.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::Command;
use std::time::{Duration, SystemTime};

use super::database::{ScanResult, VulnerabilityCache, VulnerabilityRecord};
use super::{OutputFormat, ScanCommand, StatusCommand};

/// CVSS severity thresholds
const CVSS_CRITICAL: f32 = 9.0;
const CVSS_HIGH: f32 = 7.0;
const CVSS_MEDIUM: f32 = 4.0;

/// Cache duration (24 hours)
const CACHE_DURATION_SECS: u64 = 24 * 60 * 60;

/// OSV API endpoint
const OSV_API_URL: &str = "https://api.osv.dev/v1/query";

/// Installed package information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstalledPackage {
    pub name: String,
    pub version: String,
    pub architecture: String,
    pub status: String,
}

/// Vulnerability information from OSV/NVD
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Vulnerability {
    pub id: String,
    pub aliases: Vec<String>,
    pub summary: String,
    pub details: Option<String>,
    pub severity: Severity,
    pub cvss_score: Option<f32>,
    pub affected_versions: Vec<String>,
    pub fixed_version: Option<String>,
    pub references: Vec<String>,
    pub published: Option<String>,
    pub modified: Option<String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
    Unknown,
}

impl Severity {
    pub fn from_cvss(score: f32) -> Self {
        if score >= CVSS_CRITICAL {
            Severity::Critical
        } else if score >= CVSS_HIGH {
            Severity::High
        } else if score >= CVSS_MEDIUM {
            Severity::Medium
        } else {
            Severity::Low
        }
    }

    pub fn emoji(&self) -> &'static str {
        match self {
            Severity::Critical => "🔴",
            Severity::High => "🟠",
            Severity::Medium => "🟡",
            Severity::Low => "🟢",
            Severity::Unknown => "⚪",
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            Severity::Critical => "Critical",
            Severity::High => "High",
            Severity::Medium => "Medium",
            Severity::Low => "Low",
            Severity::Unknown => "Unknown",
        }
    }
}

/// Scan results aggregation
#[derive(Debug, Default, Serialize)]
pub struct ScanSummary {
    pub total_packages: usize,
    pub scanned_packages: usize,
    pub vulnerabilities_found: usize,
    pub critical_count: usize,
    pub high_count: usize,
    pub medium_count: usize,
    pub low_count: usize,
    pub vulnerable_packages: Vec<VulnerablePackage>,
    pub scan_duration_ms: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct VulnerablePackage {
    pub package: InstalledPackage,
    pub vulnerabilities: Vec<Vulnerability>,
}

/// Get list of installed packages from dpkg
pub fn get_installed_packages() -> Result<Vec<InstalledPackage>> {
    let dpkg_status = PathBuf::from("/var/lib/dpkg/status");

    if !dpkg_status.exists() {
        // Try apt-cache as fallback
        return get_packages_from_apt_cache();
    }

    let file = fs::File::open(&dpkg_status).context("Failed to open /var/lib/dpkg/status")?;
    let reader = BufReader::new(file);

    let mut packages = Vec::new();
    let mut current_package = InstalledPackage {
        name: String::new(),
        version: String::new(),
        architecture: String::new(),
        status: String::new(),
    };

    for line in reader.lines() {
        let line = line?;

        if line.is_empty() {
            if !current_package.name.is_empty() && current_package.status.contains("installed") {
                packages.push(current_package.clone());
            }
            current_package = InstalledPackage {
                name: String::new(),
                version: String::new(),
                architecture: String::new(),
                status: String::new(),
            };
            continue;
        }

        if let Some(name) = line.strip_prefix("Package: ") {
            current_package.name = name.to_string();
        } else if let Some(version) = line.strip_prefix("Version: ") {
            current_package.version = version.to_string();
        } else if let Some(arch) = line.strip_prefix("Architecture: ") {
            current_package.architecture = arch.to_string();
        } else if let Some(status) = line.strip_prefix("Status: ") {
            current_package.status = status.to_string();
        }
    }

    // Don't forget the last package
    if !current_package.name.is_empty() && current_package.status.contains("installed") {
        packages.push(current_package);
    }

    Ok(packages)
}

/// Fallback: get packages from apt-cache
fn get_packages_from_apt_cache() -> Result<Vec<InstalledPackage>> {
    let output = Command::new("dpkg-query")
        .args([
            "-W",
            "-f=${Package}\t${Version}\t${Architecture}\t${Status}\n",
        ])
        .output()
        .context("Failed to run dpkg-query")?;

    if !output.status.success() {
        anyhow::bail!("dpkg-query failed");
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let packages: Vec<InstalledPackage> = stdout
        .lines()
        .filter_map(|line| {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() >= 4 && parts[3].contains("installed") {
                Some(InstalledPackage {
                    name: parts[0].to_string(),
                    version: parts[1].to_string(),
                    architecture: parts[2].to_string(),
                    status: parts[3].to_string(),
                })
            } else {
                None
            }
        })
        .collect();

    Ok(packages)
}

/// Query OSV API for vulnerabilities
pub fn query_osv(
    package: &InstalledPackage,
    cache: &mut VulnerabilityCache,
) -> Result<Vec<Vulnerability>> {
    // Check cache first
    let cache_key = format!("{}:{}", package.name, package.version);
    if let Some(cached) = cache.get(&cache_key) {
        if cached.timestamp.elapsed().unwrap_or(Duration::MAX)
            < Duration::from_secs(CACHE_DURATION_SECS)
        {
            return Ok(cached.vulnerabilities.clone());
        }
    }

    // Build OSV query
    let query = serde_json::json!({
        "package": {
            "name": package.name,
            "ecosystem": "Debian"
        },
        "version": package.version
    });

    // Make HTTP request using ureq (lightweight HTTP client)
    let response = ureq::post(OSV_API_URL)
        .set("Content-Type", "application/json")
        .send_json(&query);

    let vulnerabilities = match response {
        Ok(resp) => {
            let body: serde_json::Value = resp.into_json()?;
            parse_osv_response(&body)
        }
        Err(ureq::Error::Status(404, _)) => Vec::new(),
        Err(e) => {
            eprintln!("⚠️  Warning: OSV query failed for {}: {}", package.name, e);
            Vec::new()
        }
    };

    // Update cache
    cache.set(&cache_key, vulnerabilities.clone());

    Ok(vulnerabilities)
}

/// Parse OSV API response
fn parse_osv_response(response: &serde_json::Value) -> Vec<Vulnerability> {
    let mut vulnerabilities = Vec::new();

    if let Some(vulns) = response.get("vulns").and_then(|v| v.as_array()) {
        for vuln in vulns {
            let id = vuln
                .get("id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let summary = vuln
                .get("summary")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let details = vuln
                .get("details")
                .and_then(|v| v.as_str())
                .map(String::from);

            // Extract CVSS score from severity array
            let (severity, cvss_score) = extract_severity(vuln);

            // Extract aliases (CVE numbers)
            let aliases: Vec<String> = vuln
                .get("aliases")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|a| a.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();

            // Extract fixed version
            let fixed_version = vuln
                .get("affected")
                .and_then(|v| v.as_array())
                .and_then(|arr| arr.first())
                .and_then(|a| a.get("ranges"))
                .and_then(|v| v.as_array())
                .and_then(|arr| arr.first())
                .and_then(|r| r.get("events"))
                .and_then(|v| v.as_array())
                .and_then(|events| {
                    events
                        .iter()
                        .find(|e| e.get("fixed").is_some())
                        .and_then(|e| e.get("fixed"))
                        .and_then(|v| v.as_str())
                        .map(String::from)
                });

            // Extract references
            let references: Vec<String> = vuln
                .get("references")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|r| r.get("url").and_then(|u| u.as_str()).map(String::from))
                        .collect()
                })
                .unwrap_or_default();

            let published = vuln
                .get("published")
                .and_then(|v| v.as_str())
                .map(String::from);
            let modified = vuln
                .get("modified")
                .and_then(|v| v.as_str())
                .map(String::from);

            vulnerabilities.push(Vulnerability {
                id,
                aliases,
                summary,
                details,
                severity,
                cvss_score,
                affected_versions: Vec::new(),
                fixed_version,
                references,
                published,
                modified,
            });
        }
    }

    vulnerabilities
}

/// Extract severity and CVSS score from OSV vulnerability
fn extract_severity(vuln: &serde_json::Value) -> (Severity, Option<f32>) {
    if let Some(severity_arr) = vuln.get("severity").and_then(|v| v.as_array()) {
        for sev in severity_arr {
            if let Some(score_str) = sev.get("score").and_then(|v| v.as_str()) {
                if let Ok(score) = score_str.parse::<f32>() {
                    return (Severity::from_cvss(score), Some(score));
                }
            }
        }
    }

    // Try database_specific for severity
    if let Some(db_specific) = vuln.get("database_specific") {
        if let Some(severity_str) = db_specific.get("severity").and_then(|v| v.as_str()) {
            let severity = match severity_str.to_uppercase().as_str() {
                "CRITICAL" => Severity::Critical,
                "HIGH" => Severity::High,
                "MEDIUM" | "MODERATE" => Severity::Medium,
                "LOW" => Severity::Low,
                _ => Severity::Unknown,
            };
            return (severity, None);
        }
    }

    (Severity::Unknown, None)
}

/// Run the vulnerability scan
pub fn run_scan(cmd: ScanCommand) -> Result<()> {
    let start_time = std::time::Instant::now();

    println!("🔍 CX Linux Security Scanner");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Get installed packages
    let packages = if let Some(ref pkg_name) = cmd.package {
        println!("📦 Scanning package: {}", pkg_name);
        get_installed_packages()?
            .into_iter()
            .filter(|p| p.name == *pkg_name)
            .collect()
    } else if cmd.all {
        println!("📦 Scanning all installed packages...");
        get_installed_packages()?
    } else {
        println!("📦 Scanning all installed packages (use --package to scan specific package)...");
        get_installed_packages()?
    };

    if packages.is_empty() {
        if let Some(ref pkg_name) = cmd.package {
            anyhow::bail!("Package '{}' not found", pkg_name);
        }
        anyhow::bail!("No packages found to scan");
    }

    let total_packages = packages.len();
    println!("   Found {} packages to scan", total_packages);
    println!();

    // Initialize cache
    let mut cache = VulnerabilityCache::load()?;

    // Scan packages
    let mut summary = ScanSummary {
        total_packages,
        ..Default::default()
    };

    let progress_interval = std::cmp::max(1, total_packages / 20);

    for (idx, package) in packages.iter().enumerate() {
        // Show progress
        if idx % progress_interval == 0 || idx == total_packages - 1 {
            let pct = ((idx + 1) as f32 / total_packages as f32 * 100.0) as usize;
            print!(
                "\r🔍 Scanning: {}/{} ({}%) | Vulnerabilities found: {}",
                idx + 1,
                total_packages,
                pct,
                summary.vulnerabilities_found
            );
            std::io::Write::flush(&mut std::io::stdout())?;
        }

        // Query vulnerabilities
        let vulns = if cmd.no_cache {
            // Skip cache
            let query = serde_json::json!({
                "package": {
                    "name": package.name,
                    "ecosystem": "Debian"
                },
                "version": package.version
            });

            match ureq::post(OSV_API_URL)
                .set("Content-Type", "application/json")
                .send_json(&query)
            {
                Ok(resp) => {
                    let body: serde_json::Value = resp.into_json()?;
                    parse_osv_response(&body)
                }
                Err(_) => Vec::new(),
            }
        } else {
            query_osv(package, &mut cache)?
        };

        summary.scanned_packages += 1;

        // Filter by severity if requested
        let filtered_vulns: Vec<_> = vulns
            .into_iter()
            .filter(|v| {
                if cmd.critical {
                    v.severity == Severity::Critical
                } else if cmd.high {
                    v.severity == Severity::Critical || v.severity == Severity::High
                } else {
                    true
                }
            })
            .collect();

        if !filtered_vulns.is_empty() {
            for vuln in &filtered_vulns {
                match vuln.severity {
                    Severity::Critical => summary.critical_count += 1,
                    Severity::High => summary.high_count += 1,
                    Severity::Medium => summary.medium_count += 1,
                    Severity::Low => summary.low_count += 1,
                    Severity::Unknown => {}
                }
            }
            summary.vulnerabilities_found += filtered_vulns.len();
            summary.vulnerable_packages.push(VulnerablePackage {
                package: package.clone(),
                vulnerabilities: filtered_vulns,
            });
        }
    }

    println!("\n");

    summary.scan_duration_ms = start_time.elapsed().as_millis() as u64;

    // Save cache
    cache.save()?;

    // Output results
    match cmd.format {
        OutputFormat::Json => {
            println!("{}", serde_json::to_string_pretty(&summary)?);
        }
        OutputFormat::Summary => {
            print_summary(&summary);
        }
        OutputFormat::Table => {
            print_summary(&summary);
            if cmd.verbose {
                print_detailed_results(&summary);
            } else {
                print_table_results(&summary);
            }
        }
    }

    // Save scan result to database
    let db = super::database::SecurityDatabase::open()?;
    db.save_scan_result(&summary)?;

    Ok(())
}

/// Print scan summary
fn print_summary(summary: &ScanSummary) {
    println!("📊 Scan Results:");
    println!("   🔴 Critical: {}", summary.critical_count);
    println!("   🟠 High:     {}", summary.high_count);
    println!("   🟡 Medium:   {}", summary.medium_count);
    println!("   🟢 Low:      {}", summary.low_count);
    println!();
    println!("   Total packages scanned: {}", summary.scanned_packages);
    println!(
        "   Vulnerable packages: {}",
        summary.vulnerable_packages.len()
    );
    println!("   Scan duration: {}ms", summary.scan_duration_ms);
    println!();
}

/// Print table format results
fn print_table_results(summary: &ScanSummary) {
    if summary.vulnerable_packages.is_empty() {
        println!("✅ No vulnerabilities found!");
        return;
    }

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!(
        "{:<30} {:<15} {:<8} {:<15} {}",
        "PACKAGE", "VERSION", "SEV", "CVE", "SUMMARY"
    );
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    for vp in &summary.vulnerable_packages {
        for vuln in &vp.vulnerabilities {
            let cve = vuln.aliases.first().map(|s| s.as_str()).unwrap_or(&vuln.id);
            let summary_text = if vuln.summary.len() > 40 {
                format!("{}...", &vuln.summary[..37])
            } else {
                vuln.summary.clone()
            };

            println!(
                "{:<30} {:<15} {} {:<6} {:<15} {}",
                truncate(&vp.package.name, 30),
                truncate(&vp.package.version, 15),
                vuln.severity.emoji(),
                vuln.severity.label(),
                truncate(cve, 15),
                summary_text
            );
        }
    }
    println!();
}

/// Print detailed results with full CVE information
fn print_detailed_results(summary: &ScanSummary) {
    for vp in &summary.vulnerable_packages {
        println!(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        );
        println!("📦 {} ({})", vp.package.name, vp.package.version);
        println!();

        for vuln in &vp.vulnerabilities {
            println!(
                "   {} {} - {}",
                vuln.severity.emoji(),
                vuln.id,
                vuln.aliases.join(", ")
            );
            println!("   Summary: {}", vuln.summary);

            if let Some(ref details) = vuln.details {
                let detail_preview = if details.len() > 200 {
                    format!("{}...", &details[..197])
                } else {
                    details.clone()
                };
                println!("   Details: {}", detail_preview);
            }

            if let Some(score) = vuln.cvss_score {
                println!("   CVSS Score: {:.1}", score);
            }

            if let Some(ref fixed) = vuln.fixed_version {
                println!("   Fixed in: {}", fixed);
            }

            if !vuln.references.is_empty() {
                println!("   References:");
                for (i, ref_url) in vuln.references.iter().take(3).enumerate() {
                    println!("     {}. {}", i + 1, ref_url);
                }
            }
            println!();
        }
    }
}

/// Show security status overview
pub fn show_status(cmd: StatusCommand) -> Result<()> {
    let db = super::database::SecurityDatabase::open()?;

    println!("🛡️  CX Linux Security Status");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // Get last scan info
    if let Some(last_scan) = db.get_last_scan()? {
        println!("📅 Last Scan: {}", last_scan.timestamp);
        println!("   Packages scanned: {}", last_scan.packages_scanned);
        println!(
            "   Vulnerabilities found: {}",
            last_scan.vulnerabilities_found
        );

        if cmd.verbose {
            println!();
            println!("   Breakdown:");
            println!("   🔴 Critical: {}", last_scan.critical_count);
            println!("   🟠 High:     {}", last_scan.high_count);
            println!("   🟡 Medium:   {}", last_scan.medium_count);
            println!("   🟢 Low:      {}", last_scan.low_count);
        }
    } else {
        println!("⚠️  No scans recorded yet. Run 'cx security scan --all' to scan.");
    }

    println!();

    // Get scheduled scans
    let schedules = db.get_schedules()?;
    if !schedules.is_empty() {
        println!("📆 Active Schedules:");
        for schedule in &schedules {
            println!(
                "   • {} ({:?}) - Last run: {}",
                schedule.name,
                schedule.frequency,
                schedule.last_run.as_deref().unwrap_or("Never")
            );
        }
    } else {
        println!("📆 No schedules configured. Run 'cx security schedule create' to set up.");
    }

    println!();

    // Get pending patches
    let pending = db.get_pending_patches()?;
    if !pending.is_empty() {
        println!("🔧 Pending Patches: {}", pending.len());
        if cmd.verbose {
            for patch in pending.iter().take(10) {
                println!(
                    "   • {} {} → {}",
                    patch.package_name, patch.current_version, patch.fixed_version
                );
            }
            if pending.len() > 10 {
                println!("   ... and {} more", pending.len() - 10);
            }
        }
        println!();
        println!("   Run 'cx security patch --scan-and-patch' to review patches.");
    } else {
        println!("✅ No pending patches.");
    }

    println!();

    Ok(())
}

/// Truncate string to max length
fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}...", &s[..max_len.saturating_sub(3)])
    }
}
