/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
//! CX Terminal: License validation module
//!
//! Validates licenses against the CX Linux license server.

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration as StdDuration;

const LICENSE_SERVER_BASE: &str = "https://license.cxlinux.com";
pub use LICENSE_SERVER_BASE as LICENSE_SERVER_BASE_URL;
const LICENSE_KEY_DIR: &str = ".cx";
const LICENSE_KEY_FILE: &str = "license.key";
const GUI_LICENSE_DIR: &str = "cx-terminal";
const GUI_LICENSE_FILE: &str = "license.json";
const HTTP_TIMEOUT: StdDuration = StdDuration::from_secs(30);

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

fn license_server_base_url() -> &'static str {
    LICENSE_SERVER_BASE
}

async fn validate_license_at(license_key: &str, base: &str) -> Result<LicenseInfo, String> {
    let hardware_id = generate_hardware_id();

    let client = http_client()?;
    let response = client
        .post(format!("{}/api/v1/licenses/validate", base))
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

async fn activate_license_at(license_key: &str, base: &str) -> Result<LicenseInfo, String> {
    let hardware_id = generate_hardware_id();
    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown".to_string());
    let platform = std::env::consts::OS.to_string();

    let client = http_client()?;
    let response = client
        .post(format!("{}/api/v1/licenses/activate", base))
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

    let info = validate_license_at(license_key, base).await?;
    save_activated_license(&info, license_key)?;
    Ok(info)
}

fn normalize_tier(tier: &str) -> String {
    match tier.to_lowercase().as_str() {
        "pro" | "professional" => "pro".to_string(),
        "team" | "teams" | "business" => "team".to_string(),
        "enterprise" | "org" | "organization" => "enterprise".to_string(),
        "core" | "free" => "core".to_string(),
        _ => "core".to_string(),
    }
}

fn http_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .map_err(|e| format!("Failed to build HTTP client: {}", e))
}

/// Show only the last four characters of a license key in user-facing output.
pub fn mask_license_key(key: &str) -> String {
    let chars: Vec<char> = key.trim().chars().collect();
    if chars.len() <= 4 {
        return "****".to_string();
    }
    let suffix: String = chars[chars.len() - 4..].iter().collect();
    format!("****{}", suffix)
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
fn tighten_path_mode(path: &Path, mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    if path.exists() {
        fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    }
    Ok(())
}

#[cfg(not(unix))]
fn tighten_path_mode(_path: &Path, _mode: u32) -> std::io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn write_private_file(path: &Path, contents: &[u8], mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    if let Some(parent) = path.parent() {
        if parent.exists() {
            tighten_path_mode(parent, 0o700)?;
        }
        ensure_private_dir(parent, 0o700)?;
        tighten_path_mode(parent, 0o700)?;
    }
    if path.exists() {
        tighten_path_mode(path, mode)?;
    }
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(mode)
        .open(path)?;
    file.write_all(contents)?;
    tighten_path_mode(path, mode)?;
    Ok(())
}

#[cfg(not(unix))]
fn write_private_file(path: &Path, contents: &[u8], _mode: u32) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, contents)
}

pub fn parse_expires_at(raw: &str) -> Result<DateTime<Utc>, String> {
    if let Ok(dt) = DateTime::parse_from_rfc3339(raw) {
        return Ok(dt.with_timezone(&Utc));
    }
    raw.parse::<DateTime<Utc>>()
        .map_err(|_| format!("Invalid license expiration timestamp: {}", raw))
}

pub fn build_gui_license_document(
    info: &LicenseInfo,
    license_key: &str,
) -> Result<GuiLicenseDocument, String> {
    let tier = normalize_tier(&info.tier);
    let now = Utc::now();
    Ok(GuiLicenseDocument {
        id: license_key.to_string(),
        email: info.customer_email.clone(),
        name: None,
        tier,
        key: license_key.to_string(),
        issued_at: now,
        expires_at: parse_expires_at(&info.expires_at)?,
        hardware_fingerprint: None,
        last_validated: Some(now),
        stripe_customer_id: None,
        stripe_subscription_id: None,
        organization_id: None,
        organization_name: info.organization.clone(),
        metadata: std::collections::HashMap::new(),
    })
}

/// Persist activation artifacts for CLI and GUI after server-side success.
pub fn save_activated_license(info: &LicenseInfo, license_key: &str) -> Result<(), String> {
    let document = build_gui_license_document(info, license_key)?;
    let json = serde_json::to_string_pretty(&document)
        .map_err(|e| format!("Failed to encode license file: {}", e))?;

    let gui_path = gui_license_path();
    write_private_file(&gui_path, json.as_bytes(), 0o600)
        .map_err(|e| format!("Failed to save GUI license file: {}", e))?;

    let key_path = license_key_path();
    if let Some(parent) = key_path.parent() {
        if parent.exists() {
            tighten_path_mode(parent, 0o700)
                .map_err(|e| format!("Failed to tighten ~/.cx permissions: {}", e))?;
        }
        ensure_private_dir(parent, 0o700).map_err(|e| format!("Failed to create ~/.cx: {}", e))?;
        tighten_path_mode(parent, 0o700)
            .map_err(|e| format!("Failed to tighten ~/.cx permissions: {}", e))?;
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
    validate_license_at(license_key, license_server_base_url()).await
}

/// Activate license on this device
pub async fn activate_license(license_key: &str) -> Result<LicenseInfo, String> {
    activate_license_at(license_key, license_server_base_url()).await
}

#[cfg(test)]
pub(crate) async fn activate_license_with_server_base(
    license_key: &str,
    base: &str,
) -> Result<LicenseInfo, String> {
    activate_license_at(license_key, base).await
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
    use std::sync::{Mutex, MutexGuard};

    static ENV_TEST_LOCK: Mutex<()> = Mutex::new(());

    struct EnvRestore {
        saved: Vec<(String, Option<String>)>,
    }

    impl EnvRestore {
        fn new() -> Self {
            Self { saved: Vec::new() }
        }

        fn set(&mut self, key: &str, value: &str) {
            self.saved.push((key.to_string(), std::env::var(key).ok()));
            std::env::set_var(key, value);
        }
    }

    impl Drop for EnvRestore {
        fn drop(&mut self) {
            for (key, value) in self.saved.drain(..) {
                match value {
                    Some(v) => std::env::set_var(&key, v),
                    None => std::env::remove_var(&key),
                }
            }
        }
    }

    fn env_test_guard() -> MutexGuard<'static, ()> {
        ENV_TEST_LOCK
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn sample_info(expires_at: &str, tier: &str) -> LicenseInfo {
        LicenseInfo {
            valid: true,
            license_key: "CX-PRO-AAAA-BBBB-CCCC-DDDD".into(),
            tier: tier.into(),
            customer_email: "user@example.com".into(),
            organization: Some("Example Org".into()),
            expires_at: expires_at.into(),
            days_remaining: 100,
            systems_used: 1,
            systems_allowed: 5,
            device_activated: true,
            features: vec!["cloud_ai".into()],
            error: None,
        }
    }

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
        assert_eq!(mask_license_key("キー1234"), "****1234");
    }

    #[test]
    fn parse_expires_at_rejects_invalid_timestamp() {
        assert!(parse_expires_at("not-a-date").is_err());
    }

    #[test]
    fn build_gui_license_document_normalizes_free_tier() {
        let expires = (Utc::now() + Duration::days(30)).to_rfc3339();
        let info = sample_info(&expires, "free");
        let doc = build_gui_license_document(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD").unwrap();
        assert_eq!(doc.tier, "core");
        assert!(doc.expires_at > Utc::now() + Duration::days(29));
    }

    #[test]
    fn gui_license_document_json_roundtrip_uses_relative_expiry() {
        let expires = (Utc::now() + Duration::days(30)).to_rfc3339();
        let info = sample_info(&expires, "Pro");
        let doc = build_gui_license_document(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD").unwrap();
        let json = serde_json::to_string(&doc).unwrap();
        let parsed: GuiLicenseDocument = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, doc);
        assert!(parsed.last_validated.unwrap() <= Utc::now() + Duration::seconds(5));
    }

    #[test]
    fn save_activated_license_rejects_invalid_expiry() {
        let _guard = env_test_guard();
        let temp = tempfile::tempdir().unwrap();
        let mut env = EnvRestore::new();
        env.set("HOME", temp.path().to_str().unwrap());
        env.set("XDG_CONFIG_HOME", temp.path().join("cfg").to_str().unwrap());

        let info = sample_info("not-a-date", "pro");
        let err = save_activated_license(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD").unwrap_err();
        assert!(err.contains("Invalid license expiration timestamp"));
    }

    #[cfg(unix)]
    #[test]
    fn save_activated_license_tightens_loose_permissions() {
        let _guard = env_test_guard();
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path().join("home");
        let config = temp.path().join("config");
        let loose_cx = home.join(".cx");
        std::fs::create_dir_all(&loose_cx).unwrap();
        std::fs::write(loose_cx.join("license.key"), b"old-key").unwrap();
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&loose_cx, fs::Permissions::from_mode(0o755)).unwrap();
            std::fs::set_permissions(
                loose_cx.join("license.key"),
                fs::Permissions::from_mode(0o644),
            )
            .unwrap();
        }

        let mut env = EnvRestore::new();
        env.set("HOME", home.to_str().unwrap());
        env.set("XDG_CONFIG_HOME", config.to_str().unwrap());

        let expires = (Utc::now() + Duration::days(30)).to_rfc3339();
        let info = sample_info(&expires, "pro");
        save_activated_license(&info, "CX-PRO-AAAA-BBBB-CCCC-DDDD").unwrap();

        use std::os::unix::fs::PermissionsExt;
        let key_path = license_key_path();
        assert_eq!(
            fs::metadata(&key_path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(
            fs::metadata(key_path.parent().unwrap())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(gui_license_path())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }

    #[test]
    fn check_license_without_local_key_is_specific_error() {
        let _guard = env_test_guard();
        let temp = tempfile::tempdir().unwrap();
        let mut env = EnvRestore::new();
        env.set("HOME", temp.path().to_str().unwrap());
        env.set("XDG_CONFIG_HOME", temp.path().join("cfg").to_str().unwrap());

        let rt = tokio::runtime::Runtime::new().unwrap();
        let err = rt.block_on(check_license()).unwrap_err();
        assert!(err.contains("No license key found"));
    }

    #[test]
    fn activate_with_unreachable_server_reports_network_error() {
        let _guard = env_test_guard();
        let temp = tempfile::tempdir().unwrap();
        let mut env = EnvRestore::new();
        env.set("HOME", temp.path().to_str().unwrap());
        env.set("XDG_CONFIG_HOME", temp.path().join("cfg").to_str().unwrap());

        let rt = tokio::runtime::Runtime::new().unwrap();
        let err = rt
            .block_on(activate_license_with_server_base(
                "CX-PRO-AAAA-BBBB-CCCC-DDDD",
                "http://127.0.0.1:1",
            ))
            .unwrap_err();
        assert!(err.starts_with("Network error:"));
    }
}
