/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
//! CX Terminal: License validation module
//!
//! Validates licenses against the CX Linux license server.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Duration;

const LICENSE_SERVER_URL: &str = "https://license.cxlinux.com";
const LICENSE_KEY_DIR: &str = ".cx";
const LICENSE_KEY_FILE: &str = "license.key";
const GUI_LICENSE_DIR: &str = "cx-terminal";
const GUI_LICENSE_FILE: &str = "license.json";
const HTTP_TIMEOUT: Duration = Duration::from_secs(30);

/// Canonical activation command shown in docs, errors, and GUI copy.
pub const ACTIVATE_USAGE: &str = "cx activate <LICENSE_KEY>";

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct LicenseInfo {
    pub valid: bool,
    pub license_key: String,
    pub tier: String,
    pub customer_email: String,
    pub organization: Option<String>,
    pub expires_at: String,
    pub days_remaining: i32,
    pub systems_used: i32,
    pub systems_allowed: i32,
    pub device_activated: bool,
    pub features: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// JSON document written for the GUI (`~/.config/cx-terminal/license.json`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GuiLicenseDocument {
    pub id: String,
    pub email: String,
    pub name: Option<String>,
    pub tier: String,
    pub key: String,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub hardware_fingerprint: Option<String>,
    pub last_validated: Option<DateTime<Utc>>,
    pub stripe_customer_id: Option<String>,
    pub stripe_subscription_id: Option<String>,
    pub organization_id: Option<String>,
    pub organization_name: Option<String>,
    #[serde(default)]
    pub metadata: std::collections::HashMap<String, String>,
}

#[derive(Debug, Serialize)]
struct ValidateRequest {
    license_key: String,
    hardware_id: String,
}

#[derive(Debug, Serialize)]
struct ActivateRequest {
    license_key: String,
    hardware_id: String,
    device_name: String,
    platform: String,
    hostname: String,
}

fn http_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .map_err(|e| format!("Failed to build HTTP client: {}", e))
}

/// Show only the last four characters of a license key in user-facing output.
pub fn mask_license_key(key: &str) -> String {
    let trimmed = key.trim();
    if trimmed.len() <= 4 {
        return "****".to_string();
    }
    format!("****{}", &trimmed[trimmed.len() - 4..])
}

/// Generate a hardware fingerprint for this machine
pub fn generate_hardware_id() -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut hasher = DefaultHasher::new();

    if let Ok(hostname) = hostname::get() {
        hostname.to_string_lossy().hash(&mut hasher);
    }

    if let Ok(machine_id) = fs::read_to_string("/etc/machine-id") {
        machine_id.trim().hash(&mut hasher);
    }

    if let Ok(boot_id) = fs::read_to_string("/proc/sys/kernel/random/boot_id") {
        boot_id.trim().hash(&mut hasher);
    }

    if let Ok(user) = std::env::var("USER") {
        user.hash(&mut hasher);
    }

    format!("{:016x}", hasher.finish())
}

pub fn gui_license_path() -> PathBuf {
    dirs::config_dir()
        .or_else(dirs::home_dir)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(GUI_LICENSE_DIR)
        .join(GUI_LICENSE_FILE)
}

pub fn license_key_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(LICENSE_KEY_DIR)
        .join(LICENSE_KEY_FILE)
}

/// Legacy alias used by older call sites.
pub fn get_license_path() -> PathBuf {
    license_key_path()
}

#[cfg(unix)]
fn ensure_private_dir(path: &Path, mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::DirBuilderExt;
    let mut builder = fs::DirBuilder::new();
    builder.recursive(true).mode(mode);
    builder.create(path)
}

#[cfg(not(unix))]
fn ensure_private_dir(path: &Path, _mode: u32) -> std::io::Result<()> {
    fs::create_dir_all(path)
}

#[cfg(unix)]
fn write_private_file(path: &Path, contents: &[u8], mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    if let Some(parent) = path.parent() {
        ensure_private_dir(parent, 0o700)?;
    }
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(mode)
        .open(path)?;
    file.write_all(contents)?;
    Ok(())
}

#[cfg(not(unix))]
fn write_private_file(path: &Path, contents: &[u8], _mode: u32) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, contents)
}

pub fn parse_expires_at(raw: &str) -> DateTime<Utc> {
    if let Ok(dt) = DateTime::parse_from_rfc3339(raw) {
        return dt.with_timezone(&Utc);
    }
    if let Ok(dt) = raw.parse::<DateTime<Utc>>() {
        return dt;
    }
    Utc::now() + chrono::Duration::days(365)
}

pub fn build_gui_license_document(info: &LicenseInfo, license_key: &str) -> GuiLicenseDocument {
    let tier = info.tier.to_lowercase();
    let now = Utc::now();
    GuiLicenseDocument {
        id: license_key.to_string(),
        email: info.customer_email.clone(),
        name: None,
        tier,
        key: license_key.to_string(),
        issued_at: now,
        expires_at: parse_expires_at(&info.expires_at),
        hardware_fingerprint: None,
        last_validated: Some(now),
        stripe_customer_id: None,
        stripe_subscription_id: None,
        organization_id: None,
        organization_name: info.organization.clone(),
        metadata: std::collections::HashMap::new(),
    }
}

/// Persist activation artifacts for CLI and GUI after server-side success.
pub fn save_activated_license(info: &LicenseInfo, license_key: &str) -> Result<(), String> {
    let document = build_gui_license_document(info, license_key);
    let json = serde_json::to_string_pretty(&document)
        .map_err(|e| format!("Failed to encode license file: {}", e))?;

    let gui_path = gui_license_path();
    write_private_file(&gui_path, json.as_bytes(), 0o600)
        .map_err(|e| format!("Failed to save GUI license file: {}", e))?;

    let key_path = license_key_path();
    if let Some(parent) = key_path.parent() {
        ensure_private_dir(parent, 0o700).map_err(|e| format!("Failed to create ~/.cx: {}", e))?;
    }
    write_private_file(key_path.as_path(), license_key.as_bytes(), 0o600)
        .map_err(|e| format!("Failed to save license key: {}", e))?;

    Ok(())
}

/// Read the stored license key (GUI JSON first, then legacy ~/.cx/license.key).
pub fn read_license_key() -> Option<String> {
    let gui_path = gui_license_path();
    if gui_path.exists() {
        if let Ok(content) = fs::read_to_string(&gui_path) {
            if let Ok(doc) = serde_json::from_str::<GuiLicenseDocument>(&content) {
                if !doc.key.is_empty() {
                    return Some(doc.key);
                }
            }
        }
    }

    let path = license_key_path();
    fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

/// Validate license with the server
pub async fn validate_license(license_key: &str) -> Result<LicenseInfo, String> {
    let hardware_id = generate_hardware_id();

    let client = http_client()?;
    let response = client
        .post(format!("{}/api/v1/licenses/validate", LICENSE_SERVER_URL))
        .json(&ValidateRequest {
            license_key: license_key.to_string(),
            hardware_id,
        })
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    let info: LicenseInfo = response
        .json()
        .await
        .map_err(|e| format!("Invalid response: {}", e))?;

    if !info.valid {
        return Err(info.error.unwrap_or_else(|| "Invalid license".to_string()));
    }

    Ok(info)
}

/// Activate license on this device
pub async fn activate_license(license_key: &str) -> Result<LicenseInfo, String> {
    let hardware_id = generate_hardware_id();
    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown".to_string());
    let platform = std::env::consts::OS.to_string();

    let client = http_client()?;
    let response = client
        .post(format!("{}/api/v1/licenses/activate", LICENSE_SERVER_URL))
        .json(&ActivateRequest {
            license_key: license_key.to_string(),
            hardware_id,
            device_name: hostname.clone(),
            platform,
            hostname,
        })
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    let status = response.status();
    let text = response
        .text()
        .await
        .map_err(|e| format!("Read error: {}", e))?;

    if !status.is_success() {
        let error: serde_json::Value =
            serde_json::from_str(&text).unwrap_or_else(|_| serde_json::json!({"error": text}));
        return Err(error["error"]
            .as_str()
            .unwrap_or("Activation failed")
            .to_string());
    }

    let info = validate_license(license_key).await?;
    save_activated_license(&info, license_key)?;
    Ok(info)
}

/// Check if the current installation has a valid license
pub async fn check_license() -> Result<LicenseInfo, String> {
    let license_key = read_license_key()
        .ok_or_else(|| format!("No license key found. Run `{}` first.", ACTIVATE_USAGE))?;
    validate_license(&license_key).await
}

/// Check if a feature is available for the current license tier
#[allow(dead_code)]
pub fn has_feature(info: &LicenseInfo, feature: &str) -> bool {
    info.features.contains(&feature.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hardware_id_generation() {
        let id1 = generate_hardware_id();
        let id2 = generate_hardware_id();
        assert_eq!(id1, id2);
        assert_eq!(id1.len(), 16);
    }

    #[test]
    fn test_mask_license_key() {
        assert_eq!(mask_license_key("CX-PRO-ABCD-EFGH-IJKL-MNOP"), "****MNOP");
        assert_eq!(mask_license_key("abcd"), "****");
    }

    #[test]
    fn gui_license_document_matches_shared_cli_fixture() {
        let info = LicenseInfo {
            valid: true,
            license_key: "CX-PRO-AAAA-BBBB-CCCC-DDDD".into(),
            tier: "Pro".into(),
            customer_email: "user@example.com".into(),
            organization: Some("Example Org".into()),
            expires_at: "2030-06-01T00:00:00Z".into(),
            days_remaining: 100,
            systems_used: 1,
            systems_allowed: 5,
            device_activated: true,
            features: vec!["cloud_ai".into()],
            error: None,
        };
        let doc = build_gui_license_document(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD");
        doc.issued_at = chrono::DateTime::parse_from_rfc3339("2030-01-01T12:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc);
        doc.last_validated = Some(doc.issued_at);
        doc.expires_at = chrono::DateTime::parse_from_rfc3339("2030-06-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc);

        let fixture =
            std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../tests/fixtures/cli_activation_license.json"))
                .expect("fixture");
        let expected: GuiLicenseDocument = serde_json::from_str(&fixture).unwrap();
        assert_eq!(doc, expected);
    }

    #[cfg(unix)]
    #[test]
    fn save_activated_license_uses_private_permissions() {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path().join("home");
        let config = temp.path().join("config");
        std::fs::create_dir_all(&home).unwrap();
        std::fs::create_dir_all(&config).unwrap();

        std::env::set_var("HOME", &home);
        std::env::set_var("XDG_CONFIG_HOME", &config);

        let info = LicenseInfo {
                    valid: true,
                    license_key: "CX-PRO-AAAA-BBBB-CCCC-DDDD".into(),
                    tier: "pro".into(),
                    customer_email: "user@example.com".into(),
                    organization: None,
                    expires_at: "2030-01-01T00:00:00Z".into(),
                    days_remaining: 10,
                    systems_used: 1,
                    systems_allowed: 1,
                    device_activated: true,
                    features: vec![],
                    error: None,
                };
                save_activated_license(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD").unwrap();

                use std::os::unix::fs::PermissionsExt;
                let key_path = license_key_path();
                let key_mode = fs::metadata(&key_path).unwrap().permissions().mode() & 0o777;
                assert_eq!(key_mode, 0o600);

                let cx_dir = key_path.parent().unwrap();
                let dir_mode = fs::metadata(cx_dir).unwrap().permissions().mode() & 0o777;
                assert_eq!(dir_mode, 0o700);

                let gui_path = gui_license_path();
                let gui_mode = fs::metadata(&gui_path).unwrap().permissions().mode() & 0o777;
                assert_eq!(gui_mode, 0o600);
    }
}
