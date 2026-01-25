//! Subscription and Feature Gating for CX Terminal
//!
//! This module handles subscription management and feature gating for CX Terminal.
//!
//! ## Subscription Tiers
//!
//! - **Core (Free)**: Basic terminal with blocks, basic AI (3 agents), limited history
//! - **Pro ($10/mo)**: All agents, custom AI, unlimited history, voice input, offline LLM
//! - **Enterprise ($25/user/mo)**: SSO, audit logs, private agents, team management
//!
//! ## Architecture
//!
//! The subscription system consists of:
//! - `tier`: Subscription tier definitions and limits
//! - `license`: License file management and validation
//! - `features`: Feature gate checking and enforcement
//! - `stripe`: Stripe API integration for payments

mod tier;
mod license;
mod features;
mod stripe;

pub use tier::{SubscriptionTier, TierLimits, TierInfo};
pub use license::{License, LicenseValidator, LicenseError, HardwareFingerprint};
pub use features::{Feature, FeatureGate, FeatureError};
pub use stripe::{StripeClient, StripeConfig, CheckoutSession, SubscriptionStatus};

use std::sync::Arc;
use parking_lot::RwLock;

/// Global subscription manager
static SUBSCRIPTION_MANAGER: once_cell::sync::Lazy<Arc<RwLock<SubscriptionManager>>> =
    once_cell::sync::Lazy::new(|| Arc::new(RwLock::new(SubscriptionManager::new())));

/// Get the global subscription manager
pub fn get_subscription_manager() -> Arc<RwLock<SubscriptionManager>> {
    SUBSCRIPTION_MANAGER.clone()
}

/// Central manager for subscription state
pub struct SubscriptionManager {
    /// Current license
    license: Option<License>,
    /// License validator
    validator: LicenseValidator,
    /// Feature gate based on current tier
    feature_gate: FeatureGate,
    /// Usage tracking
    usage: UsageTracker,
    /// Stripe client for subscription management
    stripe_client: Option<StripeClient>,
}

impl SubscriptionManager {
    /// Create a new subscription manager
    pub fn new() -> Self {
        let validator = LicenseValidator::new();
        let license = validator.load_license().ok();
        let tier = license.as_ref()
            .map(|l| l.tier.clone())
            .unwrap_or(SubscriptionTier::Core);

        Self {
            license,
            validator,
            feature_gate: FeatureGate::new(tier),
            usage: UsageTracker::new(),
            stripe_client: None,
        }
    }

    /// Initialize with Stripe configuration
    pub fn with_stripe(mut self, config: StripeConfig) -> Self {
        self.stripe_client = Some(StripeClient::new(config));
        self
    }

    /// Get current subscription tier
    pub fn tier(&self) -> SubscriptionTier {
        self.feature_gate.tier().clone()
    }

    /// Get tier information
    pub fn tier_info(&self) -> TierInfo {
        TierInfo::for_tier(&self.tier())
    }

    /// Get tier limits
    pub fn limits(&self) -> TierLimits {
        TierLimits::for_tier(&self.tier())
    }

    /// Check if a feature is enabled
    pub fn is_feature_enabled(&self, feature: Feature) -> bool {
        self.feature_gate.is_enabled(feature)
    }

    /// Check feature and return error if not available
    pub fn check_feature(&self, feature: Feature) -> Result<(), FeatureError> {
        self.feature_gate.check(feature)
    }

    /// Get the feature gate for direct access
    pub fn feature_gate(&self) -> &FeatureGate {
        &self.feature_gate
    }

    /// Get current license
    pub fn license(&self) -> Option<&License> {
        self.license.as_ref()
    }

    /// Check if license is valid
    pub fn is_licensed(&self) -> bool {
        self.license.as_ref()
            .map(|l| self.validator.is_valid(l))
            .unwrap_or(false)
    }

    /// Get usage tracker
    pub fn usage(&self) -> &UsageTracker {
        &self.usage
    }

    /// Get mutable usage tracker
    pub fn usage_mut(&mut self) -> &mut UsageTracker {
        &mut self.usage
    }

    /// Validate and update license
    pub fn update_license(&mut self, license: License) -> Result<(), LicenseError> {
        self.validator.validate(&license)?;
        self.feature_gate = FeatureGate::new(license.tier.clone());
        self.license = Some(license);
        Ok(())
    }

    /// Reload license from disk
    pub fn reload_license(&mut self) -> Result<(), LicenseError> {
        let license = self.validator.load_license()?;
        self.update_license(license)
    }

    /// Check if we're in offline grace period
    pub fn is_offline_grace_period(&self) -> bool {
        self.license.as_ref()
            .map(|l| self.validator.is_in_grace_period(l))
            .unwrap_or(false)
    }

    /// Get days remaining in grace period (if applicable)
    pub fn grace_period_days_remaining(&self) -> Option<u32> {
        self.license.as_ref()
            .and_then(|l| self.validator.grace_period_remaining(l))
    }

    /// Create a Stripe checkout session for upgrade
    pub async fn create_checkout_session(&self, target_tier: SubscriptionTier) -> Result<CheckoutSession, StripeError> {
        let client = self.stripe_client.as_ref()
            .ok_or(StripeError::NotConfigured)?;

        client.create_checkout_session(target_tier).await
    }

    /// Get Stripe customer portal URL
    pub async fn get_customer_portal_url(&self) -> Result<String, StripeError> {
        let client = self.stripe_client.as_ref()
            .ok_or(StripeError::NotConfigured)?;

        let customer_id = self.license.as_ref()
            .and_then(|l| l.stripe_customer_id.as_ref())
            .ok_or(StripeError::NoCustomer)?;

        client.create_portal_session(customer_id).await
    }

    /// Track AI query usage
    pub fn track_ai_query(&mut self) -> Result<(), FeatureError> {
        let limits = self.limits();
        if limits.ai_queries_per_day == usize::MAX {
            return Ok(());
        }

        if self.usage.ai_queries_today >= limits.ai_queries_per_day {
            return Err(FeatureError::LimitExceeded {
                feature: Feature::UnlimitedAI,
                limit: limits.ai_queries_per_day,
                current: self.usage.ai_queries_today,
            });
        }

        self.usage.ai_queries_today += 1;
        Ok(())
    }

    /// Track agent usage
    pub fn track_agent_use(&mut self, agent_name: &str) -> Result<(), FeatureError> {
        let limits = self.limits();
        if limits.max_agents == usize::MAX {
            return Ok(());
        }

        if !self.usage.active_agents.contains(&agent_name.to_string()) {
            if self.usage.active_agents.len() >= limits.max_agents {
                return Err(FeatureError::LimitExceeded {
                    feature: Feature::UnlimitedAgents,
                    limit: limits.max_agents,
                    current: self.usage.active_agents.len(),
                });
            }
            self.usage.active_agents.push(agent_name.to_string());
        }
        Ok(())
    }

    /// Track workflow creation
    pub fn track_workflow_creation(&mut self) -> Result<(), FeatureError> {
        let limits = self.limits();
        if limits.workflows == usize::MAX {
            return Ok(());
        }

        if self.usage.workflows_created >= limits.workflows {
            return Err(FeatureError::LimitExceeded {
                feature: Feature::UnlimitedWorkflows,
                limit: limits.workflows,
                current: self.usage.workflows_created,
            });
        }

        self.usage.workflows_created += 1;
        Ok(())
    }

    /// Reset daily usage counters
    pub fn reset_daily_usage(&mut self) {
        self.usage.ai_queries_today = 0;
        self.usage.last_reset = chrono::Utc::now();
    }
}

impl Default for SubscriptionManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Tracks usage for limit enforcement
#[derive(Debug, Clone)]
pub struct UsageTracker {
    /// AI queries made today
    pub ai_queries_today: usize,
    /// Active agents used
    pub active_agents: Vec<String>,
    /// Workflows created
    pub workflows_created: usize,
    /// History days retained
    pub history_days: usize,
    /// Last reset time
    pub last_reset: chrono::DateTime<chrono::Utc>,
}

impl UsageTracker {
    pub fn new() -> Self {
        Self {
            ai_queries_today: 0,
            active_agents: Vec::new(),
            workflows_created: 0,
            history_days: 0,
            last_reset: chrono::Utc::now(),
        }
    }

    /// Check if daily reset is needed
    pub fn needs_daily_reset(&self) -> bool {
        let now = chrono::Utc::now();
        now.date_naive() > self.last_reset.date_naive()
    }
}

impl Default for UsageTracker {
    fn default() -> Self {
        Self::new()
    }
}

/// Stripe-related errors
#[derive(Debug, Clone)]
pub enum StripeError {
    /// Stripe not configured
    NotConfigured,
    /// No customer ID
    NoCustomer,
    /// API error
    ApiError(String),
    /// Network error
    NetworkError(String),
}

impl std::fmt::Display for StripeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotConfigured => write!(f, "Stripe is not configured"),
            Self::NoCustomer => write!(f, "No Stripe customer ID found"),
            Self::ApiError(msg) => write!(f, "Stripe API error: {}", msg),
            Self::NetworkError(msg) => write!(f, "Network error: {}", msg),
        }
    }
}

impl std::error::Error for StripeError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_subscription_manager_creation() {
        let manager = SubscriptionManager::new();
        assert_eq!(manager.tier(), SubscriptionTier::Core);
    }

    #[test]
    fn test_feature_checking() {
        let manager = SubscriptionManager::new();

        // Core tier should not have unlimited agents
        assert!(!manager.is_feature_enabled(Feature::UnlimitedAgents));

        // Core tier should not have voice input
        assert!(!manager.is_feature_enabled(Feature::VoiceInput));
    }

    #[test]
    fn test_usage_tracking() {
        let mut manager = SubscriptionManager::new();

        // Track some AI queries
        for _ in 0..10 {
            let _ = manager.track_ai_query();
        }

        assert_eq!(manager.usage().ai_queries_today, 10);
    }
}
