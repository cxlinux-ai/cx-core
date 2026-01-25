//! License management and validation
//!
//! Handles license file storage, validation, and hardware fingerprinting
//! for subscription verification.
//!
//! License files are stored at: `~/.config/cx-terminal/license.json`
//!
//! Features:
//! - Hardware fingerprint binding
//! - Offline grace period (7 days)
//! - License server validation

use super::tier::SubscriptionTier;
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// License file structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct License {
    /// Unique license ID
    pub id: String,
    /// User email
    pub email: String,
    /// User name
    pub name: Option<String>,
    /// Subscription tier
    pub tier: SubscriptionTier,
    /// License key (JWT or signed token)
    pub key: String,
    /// When the license was issued
    pub issued_at: DateTime<Utc>,
    /// When the license expires
    pub expires_at: DateTime<Utc>,
    /// Hardware fingerprint the license is bound to
    pub hardware_fingerprint: Option<String>,
    /// Last successful validation time
    pub last_validated: Option<DateTime<Utc>>,
    /// Stripe customer ID for subscription management
    pub stripe_customer_id: Option<String>,
    /// Stripe subscription ID
    pub stripe_subscription_id: Option<String>,
    /// Organization ID (for Enterprise)
    pub organization_id: Option<String>,
    /// Organization name (for Enterprise)
    pub organization_name: Option<String>,
    /// Additional metadata
    #[serde(default)]
    pub metadata: std::collections::HashMap<String, String>,
}

impl License {
    /// Create a new license
    pub fn new(
        id: String,
        email: String,
        tier: SubscriptionTier,
        key: String,
        expires_at: DateTime<Utc>,
    ) -> Self {
        Self {
            id,
            email,
            name: None,
            tier,
            key,
            issued_at: Utc::now(),
            expires_at,
            hardware_fingerprint: None,
            last_validated: None,
            stripe_customer_id: None,
            stripe_subscription_id: None,
            organization_id: None,
            organization_name: None,
            metadata: std::collections::HashMap::new(),
        }
    }

    /// Check if the license is expired
    pub fn is_expired(&self) -> bool {
        Utc::now() > self.expires_at
    }

    /// Check if the license is valid for the current hardware
    pub fn is_valid_for_hardware(&self, fingerprint: &HardwareFingerprint) -> bool {
        match &self.hardware_fingerprint {
            Some(bound) => bound == &fingerprint.to_string(),
            None => true, // Not bound to specific hardware
        }
    }

    /// Bind license to hardware
    pub fn bind_to_hardware(&mut self, fingerprint: &HardwareFingerprint) {
        self.hardware_fingerprint = Some(fingerprint.to_string());
    }

    /// Get days until expiration
    pub fn days_until_expiry(&self) -> i64 {
        (self.expires_at - Utc::now()).num_days()
    }
}

/// Hardware fingerprint for license binding
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareFingerprint {
    /// Machine ID or hostname hash
    pub machine_id: String,
    /// Primary MAC address hash
    pub mac_hash: Option<String>,
    /// OS identifier
    pub os_id: String,
    /// CPU identifier (optional)
    pub cpu_id: Option<String>,
}

impl HardwareFingerprint {
    /// Generate fingerprint for current machine
    pub fn generate() -> Self {
        Self {
            machine_id: Self::get_machine_id(),
            mac_hash: Self::get_mac_hash(),
            os_id: Self::get_os_id(),
            cpu_id: Self::get_cpu_id(),
        }
    }

    fn get_machine_id() -> String {
        // Try to read machine-id on Linux
        #[cfg(target_os = "linux")]
        {
            if let Ok(id) = std::fs::read_to_string("/etc/machine-id") {
                return Self::hash_string(id.trim());
            }
            if let Ok(id) = std::fs::read_to_string("/var/lib/dbus/machine-id") {
                return Self::hash_string(id.trim());
            }
        }

        // On macOS, use IOPlatformUUID
        #[cfg(target_os = "macos")]
        {
            if let Ok(output) = std::process::Command::new("ioreg")
                .args(["-rd1", "-c", "IOPlatformExpertDevice"])
                .output()
            {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    if line.contains("IOPlatformUUID") {
                        if let Some(uuid) = line.split('"').nth(3) {
                            return Self::hash_string(uuid);
                        }
                    }
                }
            }
        }

        // Fallback to hostname
        gethostname::gethostname()
            .to_string_lossy()
            .to_string()
            .chars()
            .filter(|c| c.is_alphanumeric())
            .collect::<String>()
    }

    fn get_mac_hash() -> Option<String> {
        // Get MAC address on Linux
        #[cfg(target_os = "linux")]
        {
            for entry in std::fs::read_dir("/sys/class/net").ok()? {
                let entry = entry.ok()?;
                let name = entry.file_name().to_string_lossy().to_string();
                if name == "lo" {
                    continue;
                }
                let address_path = entry.path().join("address");
                if let Ok(mac) = std::fs::read_to_string(address_path) {
                    let mac = mac.trim();
                    if mac != "00:00:00:00:00:00" {
                        return Some(Self::hash_string(mac));
                    }
                }
            }
        }

        // On macOS, use networksetup
        #[cfg(target_os = "macos")]
        {
            if let Ok(output) = std::process::Command::new("networksetup")
                .args(["-listallhardwareports"])
                .output()
            {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    if line.starts_with("Ethernet Address:") {
                        let mac = line.replace("Ethernet Address:", "").trim().to_string();
                        if !mac.is_empty() && mac != "N/A" {
                            return Some(Self::hash_string(&mac));
                        }
                    }
                }
            }
        }

        None
    }

    fn get_os_id() -> String {
        format!(
            "{}-{}-{}",
            std::env::consts::OS,
            std::env::consts::ARCH,
            std::env::consts::FAMILY
        )
    }

    fn get_cpu_id() -> Option<String> {
        #[cfg(target_os = "linux")]
        {
            if let Ok(cpuinfo) = std::fs::read_to_string("/proc/cpuinfo") {
                for line in cpuinfo.lines() {
                    if line.starts_with("model name") {
                        if let Some(name) = line.split(':').nth(1) {
                            return Some(Self::hash_string(name.trim()));
                        }
                    }
                }
            }
        }

        #[cfg(target_os = "macos")]
        {
            if let Ok(output) = std::process::Command::new("sysctl")
                .args(["-n", "machdep.cpu.brand_string"])
                .output()
            {
                let cpu = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !cpu.is_empty() {
                    return Some(Self::hash_string(&cpu));
                }
            }
        }

        None
    }

    fn hash_string(s: &str) -> String {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        s.hash(&mut hasher);
        format!("{:x}", hasher.finish())
    }

    /// Compare fingerprints with some tolerance
    pub fn matches(&self, other: &HardwareFingerprint) -> bool {
        // Machine ID must match
        if self.machine_id != other.machine_id {
            return false;
        }

        // OS must match
        if self.os_id != other.os_id {
            return false;
        }

        // MAC hash should match if both present
        if let (Some(a), Some(b)) = (&self.mac_hash, &other.mac_hash) {
            if a != b {
                return false;
            }
        }

        true
    }
}

impl std::fmt::Display for HardwareFingerprint {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}-{}-{}",
            self.machine_id,
            self.os_id,
            self.mac_hash.as_deref().unwrap_or("none")
        )
    }
}

/// License validation errors
#[derive(Debug, Clone)]
pub enum LicenseError {
    /// License file not found
    NotFound,
    /// License file is corrupted or invalid
    InvalidFormat(String),
    /// License has expired
    Expired,
    /// Hardware fingerprint mismatch
    HardwareMismatch,
    /// License key is invalid
    InvalidKey(String),
    /// License server unreachable
    ServerUnreachable,
    /// License has been revoked
    Revoked,
    /// IO error
    IoError(String),
    /// Network error during validation
    NetworkError(String),
    /// Grace period expired
    GracePeriodExpired,
}

impl std::fmt::Display for LicenseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotFound => write!(f, "License file not found"),
            Self::InvalidFormat(msg) => write!(f, "Invalid license format: {}", msg),
            Self::Expired => write!(f, "License has expired"),
            Self::HardwareMismatch => write!(f, "License is bound to different hardware"),
            Self::InvalidKey(msg) => write!(f, "Invalid license key: {}", msg),
            Self::ServerUnreachable => write!(f, "License server is unreachable"),
            Self::Revoked => write!(f, "License has been revoked"),
            Self::IoError(msg) => write!(f, "IO error: {}", msg),
            Self::NetworkError(msg) => write!(f, "Network error: {}", msg),
            Self::GracePeriodExpired => write!(f, "Offline grace period has expired"),
        }
    }
}

impl std::error::Error for LicenseError {}

impl From<std::io::Error> for LicenseError {
    fn from(e: std::io::Error) -> Self {
        Self::IoError(e.to_string())
    }
}

impl From<serde_json::Error> for LicenseError {
    fn from(e: serde_json::Error) -> Self {
        Self::InvalidFormat(e.to_string())
    }
}

/// License validator
pub struct LicenseValidator {
    /// License file path
    license_path: PathBuf,
    /// License server URL
    server_url: String,
    /// Offline grace period in days
    grace_period_days: i64,
    /// Current hardware fingerprint
    hardware_fingerprint: HardwareFingerprint,
}

impl LicenseValidator {
    /// Create a new license validator
    pub fn new() -> Self {
        let config_dir = dirs_next::config_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("cx-terminal");

        Self {
            license_path: config_dir.join("license.json"),
            server_url: "https://license.cxlinux.com/api/v1".to_string(),
            grace_period_days: 7,
            hardware_fingerprint: HardwareFingerprint::generate(),
        }
    }

    /// Get the license file path
    pub fn license_path(&self) -> &PathBuf {
        &self.license_path
    }

    /// Load license from disk
    pub fn load_license(&self) -> Result<License, LicenseError> {
        if !self.license_path.exists() {
            return Err(LicenseError::NotFound);
        }

        let content = std::fs::read_to_string(&self.license_path)?;
        let license: License = serde_json::from_str(&content)?;

        Ok(license)
    }

    /// Save license to disk
    pub fn save_license(&self, license: &License) -> Result<(), LicenseError> {
        // Ensure directory exists
        if let Some(parent) = self.license_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(license)?;
        std::fs::write(&self.license_path, content)?;

        Ok(())
    }

    /// Delete license from disk
    pub fn delete_license(&self) -> Result<(), LicenseError> {
        if self.license_path.exists() {
            std::fs::remove_file(&self.license_path)?;
        }
        Ok(())
    }

    /// Validate a license
    pub fn validate(&self, license: &License) -> Result<(), LicenseError> {
        // Check expiration
        if license.is_expired() {
            return Err(LicenseError::Expired);
        }

        // Check hardware fingerprint
        if !license.is_valid_for_hardware(&self.hardware_fingerprint) {
            return Err(LicenseError::HardwareMismatch);
        }

        // Check grace period if needed
        if let Some(last_validated) = license.last_validated {
            let days_since_validation = (Utc::now() - last_validated).num_days();
            if days_since_validation > self.grace_period_days {
                // Try online validation
                // For now, we'll just mark as expired
                // In production, this would call the license server
                return Err(LicenseError::GracePeriodExpired);
            }
        }

        Ok(())
    }

    /// Check if license is valid (simple check)
    pub fn is_valid(&self, license: &License) -> bool {
        self.validate(license).is_ok()
    }

    /// Check if we're in offline grace period
    pub fn is_in_grace_period(&self, license: &License) -> bool {
        if let Some(last_validated) = license.last_validated {
            let days_since = (Utc::now() - last_validated).num_days();
            days_since > 0 && days_since <= self.grace_period_days
        } else {
            false
        }
    }

    /// Get remaining grace period days
    pub fn grace_period_remaining(&self, license: &License) -> Option<u32> {
        license.last_validated.map(|last| {
            let days_since = (Utc::now() - last).num_days();
            if days_since < 0 {
                self.grace_period_days as u32
            } else if days_since >= self.grace_period_days {
                0
            } else {
                (self.grace_period_days - days_since) as u32
            }
        })
    }

    /// Validate license with server (async)
    pub async fn validate_online(&self, license: &mut License) -> Result<(), LicenseError> {
        let client = reqwest::Client::new();

        let response = client
            .post(format!("{}/validate", self.server_url))
            .json(&serde_json::json!({
                "license_id": license.id,
                "license_key": license.key,
                "hardware_fingerprint": self.hardware_fingerprint.to_string(),
            }))
            .send()
            .await
            .map_err(|e| LicenseError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            let status = response.status();
            if status.as_u16() == 401 || status.as_u16() == 403 {
                return Err(LicenseError::InvalidKey("License key rejected".into()));
            } else if status.as_u16() == 410 {
                return Err(LicenseError::Revoked);
            }
            return Err(LicenseError::NetworkError(format!(
                "Server returned {}",
                status
            )));
        }

        // Update last validated time
        license.last_validated = Some(Utc::now());

        // Save updated license
        self.save_license(license)?;

        Ok(())
    }

    /// Activate a new license key
    pub async fn activate(&self, license_key: &str) -> Result<License, LicenseError> {
        let client = reqwest::Client::new();

        let response = client
            .post(format!("{}/activate", self.server_url))
            .json(&serde_json::json!({
                "license_key": license_key,
                "hardware_fingerprint": self.hardware_fingerprint.to_string(),
            }))
            .send()
            .await
            .map_err(|e| LicenseError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            return Err(LicenseError::InvalidKey("Failed to activate license".into()));
        }

        let license: License = response
            .json()
            .await
            .map_err(|e| LicenseError::InvalidFormat(e.to_string()))?;

        // Save the new license
        self.save_license(&license)?;

        Ok(license)
    }

    /// Deactivate the current license
    pub async fn deactivate(&self, license: &License) -> Result<(), LicenseError> {
        let client = reqwest::Client::new();

        let _ = client
            .post(format!("{}/deactivate", self.server_url))
            .json(&serde_json::json!({
                "license_id": license.id,
                "license_key": license.key,
                "hardware_fingerprint": self.hardware_fingerprint.to_string(),
            }))
            .send()
            .await
            .map_err(|e| LicenseError::NetworkError(e.to_string()))?;

        // Delete local license file
        self.delete_license()?;

        Ok(())
    }

    /// Get the current hardware fingerprint
    pub fn hardware_fingerprint(&self) -> &HardwareFingerprint {
        &self.hardware_fingerprint
    }
}

impl Default for LicenseValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_license_creation() {
        let license = License::new(
            "test-123".to_string(),
            "user@example.com".to_string(),
            SubscriptionTier::Pro,
            "test-key".to_string(),
            Utc::now() + Duration::days(30),
        );

        assert_eq!(license.tier, SubscriptionTier::Pro);
        assert!(!license.is_expired());
        assert!(license.days_until_expiry() > 0);
    }

    #[test]
    fn test_expired_license() {
        let license = License::new(
            "test-123".to_string(),
            "user@example.com".to_string(),
            SubscriptionTier::Pro,
            "test-key".to_string(),
            Utc::now() - Duration::days(1),
        );

        assert!(license.is_expired());
    }

    #[test]
    fn test_hardware_fingerprint() {
        let fp = HardwareFingerprint::generate();
        assert!(!fp.machine_id.is_empty());
        assert!(!fp.os_id.is_empty());
    }

    #[test]
    fn test_fingerprint_matching() {
        let fp1 = HardwareFingerprint::generate();
        let fp2 = HardwareFingerprint::generate();

        // Same machine should match
        assert!(fp1.matches(&fp2));
    }
}
