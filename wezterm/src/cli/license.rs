/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
//! CX Terminal: License validation module
//!
//! Validates licenses against the CX Linux license server.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

const LICENSE_SERVER_URL: &str = "https://license.vibetravel.club";
const LICENSE_FILE: &str = ".cx/license.key";

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

/// Generate a hardware fingerprint for this machine
pub fn generate_hardware_id() -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut hasher = DefaultHasher::new();

    // Combine multiple system identifiers
    if let Ok(hostname) = hostname::get() {
        hostname.to_string_lossy().hash(&mut hasher);
    }

    // Add machine-id on Linux
    if let Ok(machine_id) = fs::read_to_string("/etc/machine-id") {
        machine_id.trim().hash(&mut hasher);
    }

    // Add boot-id for additional uniqueness
    if let Ok(boot_id) = fs::read_to_string("/proc/sys/kernel/random/boot_id") {
        boot_id.trim().hash(&mut hasher);
    }

    // Add username
    if let Ok(user) = std::env::var("USER") {
        user.hash(&mut hasher);
    }

    format!("{:016x}", hasher.finish())
}

/// Get the license file path
pub fn get_license_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(LICENSE_FILE)
}

/// Read the stored license key
pub fn read_license_key() -> Option<String> {
    let path = get_license_path();
    fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

/// Save license key to file
pub fn save_license_key(key: &str) -> std::io::Result<()> {
    let path = get_license_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, key)
}

/// Validate license with the server
pub async fn validate_license(license_key: &str) -> Result<LicenseInfo, String> {
    let hardware_id = generate_hardware_id();

    let client = reqwest::Client::new();
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

    let client = reqwest::Client::new();
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

    // Save the license key
    save_license_key(license_key).map_err(|e| format!("Failed to save license: {}", e))?;

    // Validate to get full info
    validate_license(license_key).await
}

/// Check if the current installation has a valid license
pub async fn check_license() -> Result<LicenseInfo, String> {
    let license_key =
        read_license_key().ok_or("No license key found. Run 'cx activate <key>' first.")?;
    validate_license(&license_key).await
}

/// Check if a feature is available for the current license tier
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
        assert_eq!(id1, id2); // Should be deterministic
        assert_eq!(id1.len(), 16); // 64-bit hash as hex
    }
}
