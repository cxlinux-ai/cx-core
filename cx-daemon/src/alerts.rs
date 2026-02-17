//! Alert database for persistent alert storage
//!
//! Stores alerts in SQLite database at ~/.cx/alerts.db

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use uuid::Uuid;

/// Alert severity levels
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum AlertSeverity {
    Info,
    Warning,
    Error,
    Critical,
}

impl AlertSeverity {
    pub fn as_str(&self) -> &'static str {
        match self {
            AlertSeverity::Info => "info",
            AlertSeverity::Warning => "warning",
            AlertSeverity::Error => "error",
            AlertSeverity::Critical => "critical",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "info" => Some(AlertSeverity::Info),
            "warning" => Some(AlertSeverity::Warning),
            "error" => Some(AlertSeverity::Error),
            "critical" => Some(AlertSeverity::Critical),
            _ => None,
        }
    }
}

/// Alert status
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum AlertStatus {
    Active,
    Acknowledged,
    Dismissed,
}

impl AlertStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            AlertStatus::Active => "active",
            AlertStatus::Acknowledged => "acknowledged",
            AlertStatus::Dismissed => "dismissed",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "active" => Some(AlertStatus::Active),
            "acknowledged" => Some(AlertStatus::Acknowledged),
            "dismissed" => Some(AlertStatus::Dismissed),
            _ => None,
        }
    }
}

/// A system alert
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Alert {
    pub id: String,
    pub severity: AlertSeverity,
    pub source: String,
    pub title: String,
    pub description: String,
    pub status: AlertStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Alert {
    pub fn new(severity: AlertSeverity, source: &str, title: &str, description: &str) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4().to_string(),
            severity,
            source: source.to_string(),
            title: title.to_string(),
            description: description.to_string(),
            status: AlertStatus::Active,
            created_at: now,
            updated_at: now,
        }
    }
}

/// Alert database
pub struct AlertDatabase {
    conn: Connection,
}

impl AlertDatabase {
    /// Open or create the alert database
    pub fn open(path: PathBuf) -> Result<Self> {
        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("Failed to create database directory")?;
        }

        let conn = Connection::open(&path)
            .with_context(|| format!("Failed to open database at {}", path.display()))?;

        let db = Self { conn };
        db.migrate()?;
        Ok(db)
    }

    /// Run database migrations
    fn migrate(&self) -> Result<()> {
        self.conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY NOT NULL,
                severity TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
            CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
            CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
            "#,
        )?;
        Ok(())
    }

    /// Insert a new alert
    pub fn insert(&self, alert: &Alert) -> Result<()> {
        self.conn.execute(
            r#"
            INSERT INTO alerts (id, severity, source, title, description, status, created_at, updated_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
            "#,
            params![
                alert.id,
                alert.severity.as_str(),
                alert.source,
                alert.title,
                alert.description,
                alert.status.as_str(),
                alert.created_at.to_rfc3339(),
                alert.updated_at.to_rfc3339(),
            ],
        )?;
        Ok(())
    }

    /// Get an alert by ID
    pub fn get(&self, id: &str) -> Result<Option<Alert>> {
        let alert = self
            .conn
            .query_row(
                "SELECT id, severity, source, title, description, status, created_at, updated_at FROM alerts WHERE id = ?1",
                params![id],
                |row| {
                    Ok(Alert {
                        id: row.get(0)?,
                        severity: AlertSeverity::from_str(&row.get::<_, String>(1)?)
                            .unwrap_or(AlertSeverity::Info),
                        source: row.get(2)?,
                        title: row.get(3)?,
                        description: row.get(4)?,
                        status: AlertStatus::from_str(&row.get::<_, String>(5)?)
                            .unwrap_or(AlertStatus::Active),
                        created_at: DateTime::parse_from_rfc3339(&row.get::<_, String>(6)?)
                            .ok()
                            .map(|dt| dt.with_timezone(&Utc))
                            .unwrap_or_else(Utc::now),
                        updated_at: DateTime::parse_from_rfc3339(&row.get::<_, String>(7)?)
                            .ok()
                            .map(|dt| dt.with_timezone(&Utc))
                            .unwrap_or_else(Utc::now),
                    })
                },
            )
            .optional()?;
        Ok(alert)
    }

    /// List all alerts with optional filters
    pub fn list(
        &self,
        status: Option<AlertStatus>,
        severity: Option<AlertSeverity>,
    ) -> Result<Vec<Alert>> {
        let mut query = "SELECT id, severity, source, title, description, status, created_at, updated_at FROM alerts WHERE 1=1".to_string();
        let mut params: Vec<String> = Vec::new();

        // Build query with placeholders to prevent SQL injection
        if status.is_some() {
            query.push_str(" AND status = ?");
        }
        if severity.is_some() {
            query.push_str(" AND severity = ?");
        }

        query.push_str(" ORDER BY created_at DESC");

        let mut stmt = self.conn.prepare(&query)?;

        // Build parameters in the same order as placeholders
        if let Some(s) = status {
            params.push(s.as_str().to_string());
        }
        if let Some(sev) = severity {
            params.push(sev.as_str().to_string());
        }

        let param_refs: Vec<&dyn rusqlite::ToSql> =
            params.iter().map(|p| p as &dyn rusqlite::ToSql).collect();

        let alerts = stmt
            .query_map(param_refs.as_slice(), |row| {
                Ok(Alert {
                    id: row.get(0)?,
                    severity: AlertSeverity::from_str(&row.get::<_, String>(1)?)
                        .unwrap_or(AlertSeverity::Info),
                    source: row.get(2)?,
                    title: row.get(3)?,
                    description: row.get(4)?,
                    status: AlertStatus::from_str(&row.get::<_, String>(5)?)
                        .unwrap_or(AlertStatus::Active),
                    created_at: DateTime::parse_from_rfc3339(&row.get::<_, String>(6)?)
                        .ok()
                        .map(|dt| dt.with_timezone(&Utc))
                        .unwrap_or_else(Utc::now),
                    updated_at: DateTime::parse_from_rfc3339(&row.get::<_, String>(7)?)
                        .ok()
                        .map(|dt| dt.with_timezone(&Utc))
                        .unwrap_or_else(Utc::now),
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(alerts)
    }

    /// Update alert status
    pub fn update_status(&self, id: &str, status: AlertStatus) -> Result<bool> {
        let rows_affected = self.conn.execute(
            "UPDATE alerts SET status = ?1, updated_at = ?2 WHERE id = ?3",
            params![status.as_str(), Utc::now().to_rfc3339(), id],
        )?;
        Ok(rows_affected > 0)
    }

    /// Acknowledge an alert
    pub fn acknowledge(&self, id: &str) -> Result<bool> {
        self.update_status(id, AlertStatus::Acknowledged)
    }

    /// Dismiss an alert
    pub fn dismiss(&self, id: &str) -> Result<bool> {
        self.update_status(id, AlertStatus::Dismissed)
    }

    /// Acknowledge all active alerts
    pub fn acknowledge_all(&self) -> Result<usize> {
        let rows = self.conn.execute(
            "UPDATE alerts SET status = ?1, updated_at = ?2 WHERE status = ?3",
            params![
                AlertStatus::Acknowledged.as_str(),
                Utc::now().to_rfc3339(),
                AlertStatus::Active.as_str()
            ],
        )?;
        Ok(rows)
    }

    /// Delete old dismissed alerts (older than days)
    pub fn cleanup_old_alerts(&self, days: i64) -> Result<usize> {
        let cutoff = Utc::now() - chrono::Duration::days(days);
        let rows = self.conn.execute(
            "DELETE FROM alerts WHERE status = ?1 AND updated_at < ?2",
            params![AlertStatus::Dismissed.as_str(), cutoff.to_rfc3339()],
        )?;
        Ok(rows)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_alert_database() {
        let temp_dir = std::env::temp_dir();
        let db_path = temp_dir.join("test_alerts.db");
        let _ = std::fs::remove_file(&db_path);

        let db = AlertDatabase::open(db_path.clone()).unwrap();

        // Create and insert an alert
        let alert = Alert::new(
            AlertSeverity::Warning,
            "memory_monitor",
            "High Memory Usage",
            "Memory usage is at 85%",
        );
        db.insert(&alert).unwrap();

        // Retrieve the alert
        let retrieved = db.get(&alert.id).unwrap().unwrap();
        assert_eq!(retrieved.id, alert.id);
        assert_eq!(retrieved.severity, AlertSeverity::Warning);
        assert_eq!(retrieved.status, AlertStatus::Active);

        // Acknowledge the alert
        assert!(db.acknowledge(&alert.id).unwrap());
        let acknowledged = db.get(&alert.id).unwrap().unwrap();
        assert_eq!(acknowledged.status, AlertStatus::Acknowledged);

        // List alerts
        let alerts = db.list(None, None).unwrap();
        assert_eq!(alerts.len(), 1);

        // Cleanup
        let _ = std::fs::remove_file(db_path);
    }
}
