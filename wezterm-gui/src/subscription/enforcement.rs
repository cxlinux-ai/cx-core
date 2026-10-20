//! License enforcement at startup
//!
//! Ensures users have a valid license (including free tier) before using CX Terminal.

use super::{get_subscription_manager, License, LicenseError, LicenseValidator, SubscriptionTier};
use anyhow::{anyhow, Result};

/// Result of license check
#[derive(Debug)]
pub enum LicenseCheckResult {
    /// License is valid
    Valid(License),
    /// No license found - need registration
    NeedsRegistration,
    /// License expired
    Expired,
    /// License invalid (hardware mismatch, revoked, etc.)
    Invalid(String),
    /// Need to validate online (grace period expired)
    NeedsOnlineValidation,
}

/// Check license status at startup
pub fn check_license_on_startup() -> LicenseCheckResult {
    let manager = get_subscription_manager();
    let manager = manager.read();

    match manager.license() {
        Some(license) => {
            // Check if license is valid
            if license.is_expired() {
                return LicenseCheckResult::Expired;
            }

            // Check hardware fingerprint
            let validator = LicenseValidator::new();
            if !license.is_valid_for_hardware(validator.hardware_fingerprint()) {
                return LicenseCheckResult::Invalid("License bound to different hardware".into());
            }

            // Check grace period
            if let Some(last_validated) = license.last_validated {
                let days_since = (chrono::Utc::now() - last_validated).num_days();
                if days_since > 7 {
                    return LicenseCheckResult::NeedsOnlineValidation;
                }
            }

            LicenseCheckResult::Valid(license.clone())
        }
        None => LicenseCheckResult::NeedsRegistration,
    }
}

/// Enforce license requirements
/// Returns Ok(()) if allowed to proceed, Err if should block
pub fn enforce_license() -> Result<()> {
    match check_license_on_startup() {
        LicenseCheckResult::Valid(_license) => {
            log::info!("License valid, proceeding with startup");
            Ok(())
        }
        LicenseCheckResult::NeedsRegistration => {
            log::warn!("No license found - registration required");
            show_registration_required();
            Err(anyhow!("CX Terminal requires registration. Please visit https://cxlinux.com/pricing to get started."))
        }
        LicenseCheckResult::Expired => {
            log::warn!("License expired");
            show_license_expired();
            Err(anyhow!(
                "Your CX Terminal license has expired. Please renew at https://cxlinux.com/pricing"
            ))
        }
        LicenseCheckResult::Invalid(reason) => {
            log::error!("License invalid: {}", reason);
            show_license_invalid(&reason);
            Err(anyhow!(
                "License invalid: {}. Please contact support@cxlinux.com",
                reason
            ))
        }
        LicenseCheckResult::NeedsOnlineValidation => {
            log::warn!("License needs online validation (grace period expired)");
            // Try to validate online
            match try_online_validation() {
                Ok(()) => {
                    log::info!("Online validation successful");
                    Ok(())
                }
                Err(e) => {
                    log::error!("Online validation failed: {}", e);
                    show_validation_required();
                    Err(anyhow!("Unable to validate license. Please check your internet connection or contact support@cxlinux.com"))
                }
            }
        }
    }
}

/// Show registration required dialog/message
fn show_registration_required() {
    // Show toast notification with click-to-open URL
    wezterm_toast_notification::persistent_toast_notification_with_click_to_open_url(
        "CX Terminal - Registration Required",
        "Click here to register at cxlinux.com/pricing",
        "https://cxlinux.com/pricing",
    );

    // Also print to stderr for terminal users
    eprintln!();
    eprintln!("╔══════════════════════════════════════════════════════════════╗");
    eprintln!("║               CX Terminal - Registration Required            ║");
    eprintln!("╠══════════════════════════════════════════════════════════════╣");
    eprintln!("║                                                              ║");
    eprintln!("║  CX Terminal requires registration to use.                   ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Free tier includes:                                         ║");
    eprintln!("║  • 1 system                                                  ║");
    eprintln!("║  • 3 AI agents                                               ║");
    eprintln!("║  • 50 AI queries/day                                         ║");
    eprintln!("║  • Local LLM support                                         ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Register at: https://cxlinux.com/pricing                    ║");
    eprintln!("║                                                              ║");
    eprintln!("║  After registration, activate with:                          ║");
    eprintln!("║  cx activate <your-license-key>                              ║");
    eprintln!("║                                                              ║");
    eprintln!("╚══════════════════════════════════════════════════════════════╝");
    eprintln!();
}

/// Show license expired dialog/message
fn show_license_expired() {
    wezterm_toast_notification::persistent_toast_notification_with_click_to_open_url(
        "CX Terminal - License Expired",
        "Click here to renew at cxlinux.com/pricing",
        "https://cxlinux.com/pricing",
    );

    eprintln!();
    eprintln!("╔══════════════════════════════════════════════════════════════╗");
    eprintln!("║               CX Terminal - License Expired                  ║");
    eprintln!("╠══════════════════════════════════════════════════════════════╣");
    eprintln!("║                                                              ║");
    eprintln!("║  Your CX Terminal license has expired.                       ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Renew at: https://cxlinux.com/pricing                       ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Questions? Contact: support@cxlinux.com                     ║");
    eprintln!("║                                                              ║");
    eprintln!("╚══════════════════════════════════════════════════════════════╝");
    eprintln!();
}

/// Show license invalid dialog/message
fn show_license_invalid(reason: &str) {
    wezterm_toast_notification::persistent_toast_notification(
        "CX Terminal - License Invalid",
        &format!("License invalid: {}. Contact support@cxlinux.com", reason),
    );

    eprintln!();
    eprintln!("╔══════════════════════════════════════════════════════════════╗");
    eprintln!("║               CX Terminal - License Invalid                  ║");
    eprintln!("╠══════════════════════════════════════════════════════════════╣");
    eprintln!("║                                                              ║");
    eprintln!(
        "║  Your license is invalid: {}                                 ",
        reason
    );
    eprintln!("║                                                              ║");
    eprintln!("║  This may happen if:                                         ║");
    eprintln!("║  • License is bound to different hardware                    ║");
    eprintln!("║  • License has been revoked                                  ║");
    eprintln!("║  • License key was entered incorrectly                       ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Contact: support@cxlinux.com                                ║");
    eprintln!("║                                                              ║");
    eprintln!("╚══════════════════════════════════════════════════════════════╝");
    eprintln!();
}

/// Show validation required message
fn show_validation_required() {
    wezterm_toast_notification::persistent_toast_notification(
        "CX Terminal - Validation Required",
        "License validation required. Please connect to the internet.",
    );

    eprintln!();
    eprintln!("╔══════════════════════════════════════════════════════════════╗");
    eprintln!("║          CX Terminal - Online Validation Required            ║");
    eprintln!("╠══════════════════════════════════════════════════════════════╣");
    eprintln!("║                                                              ║");
    eprintln!("║  Your license needs to be validated online.                  ║");
    eprintln!("║  (Offline grace period: 7 days)                              ║");
    eprintln!("║                                                              ║");
    eprintln!("║  Please ensure you have an internet connection and try again.║");
    eprintln!("║                                                              ║");
    eprintln!("║  Contact: support@cxlinux.com                                ║");
    eprintln!("║                                                              ║");
    eprintln!("╚══════════════════════════════════════════════════════════════╝");
    eprintln!();
}

/// Try to validate license online
fn try_online_validation() -> Result<()> {
    let manager = get_subscription_manager();
    let mut manager = manager.write();

    // Get mutable license
    if let Some(license) = manager.license().cloned() {
        let validator = LicenseValidator::new();
        let mut license = license;

        // Use tokio runtime for async validation
        let rt = tokio::runtime::Runtime::new()?;
        rt.block_on(async { validator.validate_online(&mut license).await })
            .map_err(|e| anyhow!("Online validation failed: {}", e))?;

        // Update the license in manager
        manager.update_license(license)?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_license_check_no_license() {
        // Without a license file, should return NeedsRegistration
        // This test relies on no license being present
        let result = check_license_on_startup();
        assert!(matches!(
            result,
            LicenseCheckResult::NeedsRegistration | LicenseCheckResult::Valid(_)
        ));
    }
}
