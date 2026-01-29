/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! Security Database Module
//!
//! SQLite-backed persistence for:
//! - Vulnerability scan results
//! - Patch history with rollback support
//! - Scheduled security jobs
//! - Vulnerability cache

use anyhow::{Context, Result};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::time::SystemTime;

use super::scanner::{Vulnerability, VulnerablePackage, ScanSummary, InstalledPackage, Severity};
use super::scheduler::Schedule;
use super::{ScheduleFrequency, PatchStrategy};

/// Get the database directory
fn get_db_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("/var/lib"))
        .join("cx-linux")
}

/// Get the database path
fn get_db_path() -> PathBuf {
    get_db_dir().join("security.db")
}

/// Get the cache path
fn get_cache_path() -> PathBuf {
    get_db_dir().join("vulnerability_cache.json")
}

/// Security database handler
pub struct SecurityDatabase {
    conn: Connection,
}

impl SecurityDatabase {
    /// Open or create the security database
    pub fn open() -> Result<Self> {
        let db_dir = get_db_dir();
        std::fs::create_dir_all(&db_dir)?;

        let db_path = get_db_path();
        let conn = Connection::open(&db_path)
            .context("Failed to open security database")?;

        let db = Self { conn };
        db.initialize_tables()?;

        Ok(db)
    }

    /// Initialize database tables
    fn initialize_tables(&self) -> Result<()> {
        self.conn.execute_batch(r#"
            -- Scan results table
            CREATE TABLE IF NOT EXISTS scan_results (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                packages_scanned INTEGER NOT NULL,
                vulnerabilities_found INTEGER NOT NULL,
                critical_count INTEGER NOT NULL,
                high_count INTEGER NOT NULL,
                medium_count INTEGER NOT NULL,
                low_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL
            );

            -- Vulnerable packages from scans
            CREATE TABLE IF NOT EXISTS vulnerable_packages (
                id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                package_name TEXT NOT NULL,
                package_version TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scan_results(id)
            );

            -- Vulnerabilities found
            CREATE TABLE IF NOT EXISTS vulnerabilities (
                id TEXT PRIMARY KEY,
                vuln_package_id TEXT NOT NULL,
                vuln_id TEXT NOT NULL,
                aliases TEXT,
                summary TEXT,
                severity TEXT NOT NULL,
                cvss_score REAL,
                fixed_version TEXT,
                FOREIGN KEY (vuln_package_id) REFERENCES vulnerable_packages(id)
            );

            -- Patch history
            CREATE TABLE IF NOT EXISTS patch_history (
                id TEXT PRIMARY KEY,
                package_name TEXT NOT NULL,
                from_version TEXT NOT NULL,
                to_version TEXT NOT NULL,
                vulnerabilities_fixed TEXT,
                status TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                rollback_available INTEGER NOT NULL DEFAULT 1
            );

            -- Security schedules
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                frequency TEXT NOT NULL,
                enable_patch INTEGER NOT NULL DEFAULT 0,
                patch_strategy TEXT,
                notify INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_run TEXT,
                next_run TEXT,
                timer_installed INTEGER NOT NULL DEFAULT 0
            );

            -- Pending patches (from latest scan)
            CREATE TABLE IF NOT EXISTS pending_patches (
                id TEXT PRIMARY KEY,
                package_name TEXT NOT NULL,
                current_version TEXT NOT NULL,
                fixed_version TEXT NOT NULL,
                severity TEXT NOT NULL,
                vuln_ids TEXT NOT NULL
            );

            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_scan_timestamp ON scan_results(timestamp);
            CREATE INDEX IF NOT EXISTS idx_patch_package ON patch_history(package_name);
            CREATE INDEX IF NOT EXISTS idx_schedule_name ON schedules(name);
        "#)?;

        Ok(())
    }

    /// Save scan result
    pub fn save_scan_result(&self, summary: &ScanSummary) -> Result<()> {
        let scan_id = uuid::Uuid::new_v4().to_string();
        let timestamp = chrono::Utc::now().to_rfc3339();

        self.conn.execute(
            "INSERT INTO scan_results (id, timestamp, packages_scanned, vulnerabilities_found,
             critical_count, high_count, medium_count, low_count, duration_ms)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                scan_id,
                timestamp,
                summary.scanned_packages,
                summary.vulnerabilities_found,
                summary.critical_count,
                summary.high_count,
                summary.medium_count,
                summary.low_count,
                summary.scan_duration_ms
            ],
        )?;

        // Clear and update pending patches
        self.conn.execute("DELETE FROM pending_patches", [])?;

        // Save vulnerable packages and vulnerabilities
        for vp in &summary.vulnerable_packages {
            let vp_id = uuid::Uuid::new_v4().to_string();

            self.conn.execute(
                "INSERT INTO vulnerable_packages (id, scan_id, package_name, package_version)
                 VALUES (?1, ?2, ?3, ?4)",
                params![vp_id, scan_id, vp.package.name, vp.package.version],
            )?;

            for vuln in &vp.vulnerabilities {
                let v_id = uuid::Uuid::new_v4().to_string();
                let aliases = serde_json::to_string(&vuln.aliases)?;

                self.conn.execute(
                    "INSERT INTO vulnerabilities (id, vuln_package_id, vuln_id, aliases, summary,
                     severity, cvss_score, fixed_version)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                    params![
                        v_id,
                        vp_id,
                        vuln.id,
                        aliases,
                        vuln.summary,
                        format!("{:?}", vuln.severity),
                        vuln.cvss_score,
                        vuln.fixed_version
                    ],
                )?;

                // Add to pending patches if there's a fix
                if let Some(ref fixed) = vuln.fixed_version {
                    let vuln_ids = serde_json::to_string(&vuln.aliases)?;
                    self.conn.execute(
                        "INSERT OR REPLACE INTO pending_patches
                         (id, package_name, current_version, fixed_version, severity, vuln_ids)
                         VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                        params![
                            uuid::Uuid::new_v4().to_string(),
                            vp.package.name,
                            vp.package.version,
                            fixed,
                            format!("{:?}", vuln.severity),
                            vuln_ids
                        ],
                    )?;
                }
            }
        }

        Ok(())
    }

    /// Get last scan result
    pub fn get_last_scan(&self) -> Result<Option<ScanResult>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, timestamp, packages_scanned, vulnerabilities_found,
             critical_count, high_count, medium_count, low_count, duration_ms
             FROM scan_results ORDER BY timestamp DESC LIMIT 1"
        )?;

        let result = stmt.query_row([], |row| {
            Ok(ScanResult {
                id: row.get(0)?,
                timestamp: row.get(1)?,
                packages_scanned: row.get(2)?,
                vulnerabilities_found: row.get(3)?,
                critical_count: row.get(4)?,
                high_count: row.get(5)?,
                medium_count: row.get(6)?,
                low_count: row.get(7)?,
                duration_ms: row.get(8)?,
            })
        });

        match result {
            Ok(scan) => Ok(Some(scan)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    /// Get vulnerable packages from last scan
    pub fn get_vulnerable_packages(&self) -> Result<Vec<VulnerablePackage>> {
        let last_scan = match self.get_last_scan()? {
            Some(scan) => scan,
            None => return Ok(Vec::new()),
        };

        let mut stmt = self.conn.prepare(
            "SELECT id, package_name, package_version FROM vulnerable_packages WHERE scan_id = ?1"
        )?;

        let packages: Vec<(String, String, String)> = stmt.query_map([&last_scan.id], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?))
        })?.filter_map(|r| r.ok()).collect();

        let mut result = Vec::new();

        for (vp_id, pkg_name, pkg_version) in packages {
            let mut vuln_stmt = self.conn.prepare(
                "SELECT vuln_id, aliases, summary, severity, cvss_score, fixed_version
                 FROM vulnerabilities WHERE vuln_package_id = ?1"
            )?;

            let vulns: Vec<Vulnerability> = vuln_stmt.query_map([&vp_id], |row| {
                let aliases_json: String = row.get(1)?;
                let aliases: Vec<String> = serde_json::from_str(&aliases_json).unwrap_or_default();
                let severity_str: String = row.get(3)?;
                let severity = match severity_str.as_str() {
                    "Critical" => Severity::Critical,
                    "High" => Severity::High,
                    "Medium" => Severity::Medium,
                    "Low" => Severity::Low,
                    _ => Severity::Unknown,
                };

                Ok(Vulnerability {
                    id: row.get(0)?,
                    aliases,
                    summary: row.get(2)?,
                    details: None,
                    severity,
                    cvss_score: row.get(4)?,
                    affected_versions: Vec::new(),
                    fixed_version: row.get(5)?,
                    references: Vec::new(),
                    published: None,
                    modified: None,
                })
            })?.filter_map(|r| r.ok()).collect();

            result.push(VulnerablePackage {
                package: InstalledPackage {
                    name: pkg_name,
                    version: pkg_version,
                    architecture: String::new(),
                    status: "installed".into(),
                },
                vulnerabilities: vulns,
            });
        }

        Ok(result)
    }

    /// Get pending patches
    pub fn get_pending_patches(&self) -> Result<Vec<PendingPatch>> {
        let mut stmt = self.conn.prepare(
            "SELECT package_name, current_version, fixed_version, severity
             FROM pending_patches"
        )?;

        let patches: Vec<PendingPatch> = stmt.query_map([], |row| {
            Ok(PendingPatch {
                package_name: row.get(0)?,
                current_version: row.get(1)?,
                fixed_version: row.get(2)?,
                severity: row.get(3)?,
            })
        })?.filter_map(|r| r.ok()).collect();

        Ok(patches)
    }

    /// Record a patch application
    pub fn record_patch(&self, record: &PatchRecord) -> Result<()> {
        let vulns_json = serde_json::to_string(&record.vulnerabilities_fixed)?;

        self.conn.execute(
            "INSERT INTO patch_history (id, package_name, from_version, to_version,
             vulnerabilities_fixed, status, applied_at, rollback_available)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                record.id,
                record.package_name,
                record.from_version,
                record.to_version,
                vulns_json,
                format!("{:?}", record.status),
                record.applied_at,
                record.rollback_available
            ],
        )?;

        Ok(())
    }

    /// Get a patch record by ID
    pub fn get_patch(&self, id: &str) -> Result<Option<PatchRecord>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, package_name, from_version, to_version, vulnerabilities_fixed,
             status, applied_at, rollback_available
             FROM patch_history WHERE id = ?1"
        )?;

        let result = stmt.query_row([id], |row| {
            let vulns_json: String = row.get(4)?;
            let vulns: Vec<String> = serde_json::from_str(&vulns_json).unwrap_or_default();
            let status_str: String = row.get(5)?;
            let status = match status_str.as_str() {
                "Applied" => PatchStatus::Applied,
                "RolledBack" => PatchStatus::RolledBack,
                "Failed" => PatchStatus::Failed,
                _ => PatchStatus::Pending,
            };

            Ok(PatchRecord {
                id: row.get(0)?,
                package_name: row.get(1)?,
                from_version: row.get(2)?,
                to_version: row.get(3)?,
                vulnerabilities_fixed: vulns,
                status,
                applied_at: row.get(6)?,
                rollback_available: row.get(7)?,
            })
        });

        match result {
            Ok(patch) => Ok(Some(patch)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    /// Update patch status
    pub fn update_patch_status(&self, id: &str, status: PatchStatus) -> Result<()> {
        self.conn.execute(
            "UPDATE patch_history SET status = ?1 WHERE id = ?2",
            params![format!("{:?}", status), id],
        )?;
        Ok(())
    }

    /// Save a schedule
    pub fn save_schedule(&self, schedule: &Schedule) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO schedules
             (id, name, frequency, enable_patch, patch_strategy, notify, created_at,
              last_run, next_run, timer_installed)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![
                schedule.id,
                schedule.name,
                format!("{:?}", schedule.frequency),
                schedule.enable_patch,
                format!("{:?}", schedule.patch_strategy),
                schedule.notify,
                schedule.created_at,
                schedule.last_run,
                schedule.next_run,
                schedule.timer_installed
            ],
        )?;
        Ok(())
    }

    /// Get a schedule by name or ID
    pub fn get_schedule(&self, name_or_id: &str) -> Result<Option<Schedule>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, frequency, enable_patch, patch_strategy, notify, created_at,
             last_run, next_run, timer_installed
             FROM schedules WHERE name = ?1 OR id = ?1"
        )?;

        let result = stmt.query_row([name_or_id], |row| {
            let freq_str: String = row.get(2)?;
            let frequency = match freq_str.as_str() {
                "Daily" => ScheduleFrequency::Daily,
                "Weekly" => ScheduleFrequency::Weekly,
                _ => ScheduleFrequency::Monthly,
            };

            let strategy_str: String = row.get(4)?;
            let patch_strategy = match strategy_str.as_str() {
                "CriticalOnly" => PatchStrategy::CriticalOnly,
                "HighAndAbove" => PatchStrategy::HighAndAbove,
                "All" => PatchStrategy::All,
                _ => PatchStrategy::Automatic,
            };

            Ok(Schedule {
                id: row.get(0)?,
                name: row.get(1)?,
                frequency,
                enable_patch: row.get(3)?,
                patch_strategy,
                notify: row.get(5)?,
                created_at: row.get(6)?,
                last_run: row.get(7)?,
                next_run: row.get(8)?,
                timer_installed: row.get(9)?,
            })
        });

        match result {
            Ok(schedule) => Ok(Some(schedule)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    /// Get all schedules
    pub fn get_schedules(&self) -> Result<Vec<Schedule>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, name, frequency, enable_patch, patch_strategy, notify, created_at,
             last_run, next_run, timer_installed
             FROM schedules ORDER BY created_at"
        )?;

        let schedules: Vec<Schedule> = stmt.query_map([], |row| {
            let freq_str: String = row.get(2)?;
            let frequency = match freq_str.as_str() {
                "Daily" => ScheduleFrequency::Daily,
                "Weekly" => ScheduleFrequency::Weekly,
                _ => ScheduleFrequency::Monthly,
            };

            let strategy_str: String = row.get(4)?;
            let patch_strategy = match strategy_str.as_str() {
                "CriticalOnly" => PatchStrategy::CriticalOnly,
                "HighAndAbove" => PatchStrategy::HighAndAbove,
                "All" => PatchStrategy::All,
                _ => PatchStrategy::Automatic,
            };

            Ok(Schedule {
                id: row.get(0)?,
                name: row.get(1)?,
                frequency,
                enable_patch: row.get(3)?,
                patch_strategy,
                notify: row.get(5)?,
                created_at: row.get(6)?,
                last_run: row.get(7)?,
                next_run: row.get(8)?,
                timer_installed: row.get(9)?,
            })
        })?.filter_map(|r| r.ok()).collect();

        Ok(schedules)
    }

    /// Update schedule last run time
    pub fn update_schedule_last_run(&self, id: &str) -> Result<()> {
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "UPDATE schedules SET last_run = ?1 WHERE id = ?2",
            params![now, id],
        )?;
        Ok(())
    }

    /// Delete a schedule
    pub fn delete_schedule(&self, id: &str) -> Result<()> {
        self.conn.execute("DELETE FROM schedules WHERE id = ?1", [id])?;
        Ok(())
    }
}

/// Scan result summary
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanResult {
    pub id: String,
    pub timestamp: String,
    pub packages_scanned: usize,
    pub vulnerabilities_found: usize,
    pub critical_count: usize,
    pub high_count: usize,
    pub medium_count: usize,
    pub low_count: usize,
    pub duration_ms: u64,
}

/// Pending patch info
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingPatch {
    pub package_name: String,
    pub current_version: String,
    pub fixed_version: String,
    pub severity: String,
}

/// Patch record for history
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchRecord {
    pub id: String,
    pub package_name: String,
    pub from_version: String,
    pub to_version: String,
    pub vulnerabilities_fixed: Vec<String>,
    pub status: PatchStatus,
    pub applied_at: String,
    pub rollback_available: bool,
}

/// Patch status
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum PatchStatus {
    Pending,
    Applied,
    Failed,
    RolledBack,
}

/// Vulnerability record for database
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VulnerabilityRecord {
    pub id: String,
    pub package_name: String,
    pub package_version: String,
    pub vuln_id: String,
    pub severity: String,
    pub cvss_score: Option<f32>,
    pub fixed_version: Option<String>,
}

/// Vulnerability cache (in-memory with file persistence)
pub struct VulnerabilityCache {
    data: HashMap<String, CacheEntry>,
    path: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub vulnerabilities: Vec<Vulnerability>,
    #[serde(with = "system_time_serde")]
    pub timestamp: SystemTime,
}

mod system_time_serde {
    use serde::{Deserialize, Deserializer, Serialize, Serializer};
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    pub fn serialize<S>(time: &SystemTime, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let duration = time.duration_since(UNIX_EPOCH).unwrap_or(Duration::ZERO);
        duration.as_secs().serialize(serializer)
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<SystemTime, D::Error>
    where
        D: Deserializer<'de>,
    {
        let secs = u64::deserialize(deserializer)?;
        Ok(UNIX_EPOCH + Duration::from_secs(secs))
    }
}

impl VulnerabilityCache {
    /// Load cache from disk
    pub fn load() -> Result<Self> {
        let path = get_cache_path();

        let data = if path.exists() {
            let content = std::fs::read_to_string(&path)?;
            serde_json::from_str(&content).unwrap_or_default()
        } else {
            HashMap::new()
        };

        Ok(Self { data, path })
    }

    /// Save cache to disk
    pub fn save(&self) -> Result<()> {
        let dir = self.path.parent().unwrap();
        std::fs::create_dir_all(dir)?;

        let content = serde_json::to_string_pretty(&self.data)?;
        std::fs::write(&self.path, content)?;

        Ok(())
    }

    /// Get cached vulnerabilities
    pub fn get(&self, key: &str) -> Option<&CacheEntry> {
        self.data.get(key)
    }

    /// Set cached vulnerabilities
    pub fn set(&mut self, key: &str, vulnerabilities: Vec<Vulnerability>) {
        self.data.insert(key.to_string(), CacheEntry {
            vulnerabilities,
            timestamp: SystemTime::now(),
        });
    }
}
