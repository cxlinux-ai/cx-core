//! Feature definitions and gating
//!
//! Defines all gated features and provides the FeatureGate for checking
//! whether features are available based on subscription tier.

use super::tier::{SubscriptionTier, TierLimits};
use serde::{Deserialize, Serialize};

/// Features that can be gated by subscription tier
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Feature {
    // Pro Features
    /// Use more than 3 agents
    UnlimitedAgents,
    /// Create custom AI agents
    CustomAI,
    /// Voice input for commands
    VoiceInput,
    /// Use local/offline LLM
    OfflineLLM,
    /// Access external APIs from agents
    ExternalAPIs,
    /// Create unlimited workflows
    UnlimitedWorkflows,
    /// Unlimited AI queries
    UnlimitedAI,
    /// Unlimited history retention
    UnlimitedHistory,
    /// API access for automation
    ApiAccess,

    // Enterprise Features
    /// Audit logging
    AuditLogs,
    /// Single sign-on
    SSO,
    /// Private/custom agents for organization
    PrivateAgents,
    /// Team management
    TeamManagement,
    /// Priority support
    PrioritySupport,
}

impl Feature {
    /// Get the display name for the feature
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::UnlimitedAgents => "Unlimited Agents",
            Self::CustomAI => "Custom AI Agents",
            Self::VoiceInput => "Voice Input",
            Self::OfflineLLM => "Offline LLM",
            Self::ExternalAPIs => "External APIs",
            Self::UnlimitedWorkflows => "Unlimited Workflows",
            Self::UnlimitedAI => "Unlimited AI Queries",
            Self::UnlimitedHistory => "Unlimited History",
            Self::ApiAccess => "API Access",
            Self::AuditLogs => "Audit Logs",
            Self::SSO => "Single Sign-On",
            Self::PrivateAgents => "Private Agents",
            Self::TeamManagement => "Team Management",
            Self::PrioritySupport => "Priority Support",
        }
    }

    /// Get a description of the feature
    pub fn description(&self) -> &'static str {
        match self {
            Self::UnlimitedAgents => "Use all available AI agents without limits",
            Self::CustomAI => "Create and configure custom AI agents",
            Self::VoiceInput => "Use voice commands to interact with the terminal",
            Self::OfflineLLM => "Run AI locally without internet connection",
            Self::ExternalAPIs => "Connect agents to external services and APIs",
            Self::UnlimitedWorkflows => "Create as many saved workflows as you need",
            Self::UnlimitedAI => "No daily limit on AI queries",
            Self::UnlimitedHistory => "Keep command history indefinitely",
            Self::ApiAccess => "Access CX Terminal programmatically via API",
            Self::AuditLogs => "Track all actions for compliance and security",
            Self::SSO => "Use your organization's identity provider",
            Self::PrivateAgents => "Create agents only visible to your organization",
            Self::TeamManagement => "Manage team members and permissions",
            Self::PrioritySupport => "Get faster response times from support",
        }
    }

    /// Get the minimum tier required for this feature
    pub fn minimum_tier(&self) -> SubscriptionTier {
        match self {
            Self::UnlimitedAgents
            | Self::CustomAI
            | Self::VoiceInput
            | Self::OfflineLLM
            | Self::ExternalAPIs
            | Self::UnlimitedWorkflows
            | Self::UnlimitedAI
            | Self::UnlimitedHistory
            | Self::ApiAccess => SubscriptionTier::Pro,

            Self::AuditLogs
            | Self::SSO
            | Self::PrivateAgents
            | Self::TeamManagement
            | Self::PrioritySupport => SubscriptionTier::Enterprise,
        }
    }

    /// Get the icon for this feature
    pub fn icon(&self) -> &'static str {
        match self {
            Self::UnlimitedAgents => "󰚩",      // nf-md-robot
            Self::CustomAI => "󰛓",             // nf-md-robot_outline
            Self::VoiceInput => "󰍬",           // nf-md-microphone
            Self::OfflineLLM => "󰖟",           // nf-md-wifi_off
            Self::ExternalAPIs => "󰒍",         // nf-md-api
            Self::UnlimitedWorkflows => "󰓦",   // nf-md-workflow
            Self::UnlimitedAI => "󰧞",          // nf-md-infinity
            Self::UnlimitedHistory => "󰋚",     // nf-md-history
            Self::ApiAccess => "󰅩",            // nf-md-code_braces
            Self::AuditLogs => "󰂵",            // nf-md-file_document
            Self::SSO => "󰯄",                  // nf-md-account_key
            Self::PrivateAgents => "󰦝",        // nf-md-lock
            Self::TeamManagement => "󰡉",       // nf-md-account_group
            Self::PrioritySupport => "󱐋",      // nf-md-star_circle
        }
    }

    /// Get all Pro features
    pub fn pro_features() -> &'static [Self] {
        &[
            Self::UnlimitedAgents,
            Self::CustomAI,
            Self::VoiceInput,
            Self::OfflineLLM,
            Self::ExternalAPIs,
            Self::UnlimitedWorkflows,
            Self::UnlimitedAI,
            Self::UnlimitedHistory,
            Self::ApiAccess,
        ]
    }

    /// Get all Enterprise features
    pub fn enterprise_features() -> &'static [Self] {
        &[
            Self::AuditLogs,
            Self::SSO,
            Self::PrivateAgents,
            Self::TeamManagement,
            Self::PrioritySupport,
        ]
    }

    /// Get all features
    pub fn all() -> &'static [Self] {
        &[
            Self::UnlimitedAgents,
            Self::CustomAI,
            Self::VoiceInput,
            Self::OfflineLLM,
            Self::ExternalAPIs,
            Self::UnlimitedWorkflows,
            Self::UnlimitedAI,
            Self::UnlimitedHistory,
            Self::ApiAccess,
            Self::AuditLogs,
            Self::SSO,
            Self::PrivateAgents,
            Self::TeamManagement,
            Self::PrioritySupport,
        ]
    }
}

/// Errors related to feature gating
#[derive(Debug, Clone)]
pub enum FeatureError {
    /// Feature requires a higher tier
    TierRequired {
        feature: Feature,
        required_tier: SubscriptionTier,
        current_tier: SubscriptionTier,
    },
    /// Usage limit exceeded
    LimitExceeded {
        feature: Feature,
        limit: usize,
        current: usize,
    },
    /// Feature is disabled
    Disabled(Feature),
}

impl std::fmt::Display for FeatureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::TierRequired {
                feature,
                required_tier,
                current_tier,
            } => write!(
                f,
                "{} requires {} (you have {})",
                feature.display_name(),
                required_tier.display_name(),
                current_tier.display_name()
            ),
            Self::LimitExceeded {
                feature,
                limit,
                current,
            } => write!(
                f,
                "{} limit reached: {}/{} (upgrade for unlimited)",
                feature.display_name(),
                current,
                limit
            ),
            Self::Disabled(feature) => write!(f, "{} is disabled", feature.display_name()),
        }
    }
}

impl std::error::Error for FeatureError {}

impl FeatureError {
    /// Get the feature associated with this error
    pub fn feature(&self) -> Feature {
        match self {
            Self::TierRequired { feature, .. } => *feature,
            Self::LimitExceeded { feature, .. } => *feature,
            Self::Disabled(feature) => *feature,
        }
    }

    /// Get the required tier to unlock this feature
    pub fn required_tier(&self) -> SubscriptionTier {
        match self {
            Self::TierRequired { required_tier, .. } => *required_tier,
            Self::LimitExceeded { feature, .. } => feature.minimum_tier(),
            Self::Disabled(feature) => feature.minimum_tier(),
        }
    }

    /// Get the upgrade message
    pub fn upgrade_message(&self) -> String {
        let tier = self.required_tier();
        format!(
            "Upgrade to {} ({}) to unlock {}",
            tier.display_name(),
            tier.price_display(),
            self.feature().display_name()
        )
    }
}

/// Feature gate for checking feature availability
#[derive(Debug, Clone)]
pub struct FeatureGate {
    /// Current subscription tier
    tier: SubscriptionTier,
    /// Tier limits
    limits: TierLimits,
    /// Explicitly disabled features (for testing or admin override)
    disabled_features: Vec<Feature>,
}

impl FeatureGate {
    /// Create a new feature gate for a tier
    pub fn new(tier: SubscriptionTier) -> Self {
        Self {
            limits: TierLimits::for_tier(&tier),
            tier,
            disabled_features: Vec::new(),
        }
    }

    /// Get the current tier
    pub fn tier(&self) -> &SubscriptionTier {
        &self.tier
    }

    /// Get the tier limits
    pub fn limits(&self) -> &TierLimits {
        &self.limits
    }

    /// Check if a feature is enabled
    pub fn is_enabled(&self, feature: Feature) -> bool {
        if self.disabled_features.contains(&feature) {
            return false;
        }

        self.tier.includes(&feature.minimum_tier())
    }

    /// Check a feature and return an error if not available
    pub fn check(&self, feature: Feature) -> Result<(), FeatureError> {
        if self.disabled_features.contains(&feature) {
            return Err(FeatureError::Disabled(feature));
        }

        if !self.tier.includes(&feature.minimum_tier()) {
            return Err(FeatureError::TierRequired {
                feature,
                required_tier: feature.minimum_tier(),
                current_tier: self.tier.clone(),
            });
        }

        Ok(())
    }

    /// Disable a feature explicitly
    pub fn disable_feature(&mut self, feature: Feature) {
        if !self.disabled_features.contains(&feature) {
            self.disabled_features.push(feature);
        }
    }

    /// Enable a previously disabled feature
    pub fn enable_feature(&mut self, feature: Feature) {
        self.disabled_features.retain(|f| f != &feature);
    }

    /// Get all available features for current tier
    pub fn available_features(&self) -> Vec<Feature> {
        Feature::all()
            .iter()
            .filter(|f| self.is_enabled(**f))
            .copied()
            .collect()
    }

    /// Get features that require upgrade
    pub fn locked_features(&self) -> Vec<Feature> {
        Feature::all()
            .iter()
            .filter(|f| !self.is_enabled(**f))
            .copied()
            .collect()
    }

    /// Get the upgrade prompt for a blocked feature
    pub fn show_upgrade_prompt(&self, feature: Feature) -> UpgradePrompt {
        let required_tier = feature.minimum_tier();

        UpgradePrompt {
            feature,
            current_tier: self.tier.clone(),
            required_tier,
            title: format!("Upgrade to {}", required_tier.display_name()),
            message: format!(
                "{} requires a {} subscription.",
                feature.display_name(),
                required_tier.display_name()
            ),
            benefits: self.get_tier_benefits(&required_tier),
            price: required_tier.price_display().to_string(),
            cta: format!("Upgrade to {}", required_tier.display_name()),
        }
    }

    fn get_tier_benefits(&self, tier: &SubscriptionTier) -> Vec<String> {
        match tier {
            SubscriptionTier::Pro => Feature::pro_features()
                .iter()
                .map(|f| format!("{} {}", f.icon(), f.display_name()))
                .collect(),
            SubscriptionTier::Enterprise => {
                let mut benefits: Vec<String> = Feature::pro_features()
                    .iter()
                    .map(|f| format!("{} {}", f.icon(), f.display_name()))
                    .collect();
                benefits.extend(
                    Feature::enterprise_features()
                        .iter()
                        .map(|f| format!("{} {}", f.icon(), f.display_name())),
                );
                benefits
            }
            SubscriptionTier::Core => vec![],
        }
    }

    /// Update tier (e.g., after upgrade)
    pub fn update_tier(&mut self, tier: SubscriptionTier) {
        self.tier = tier.clone();
        self.limits = TierLimits::for_tier(&tier);
    }
}

impl Default for FeatureGate {
    fn default() -> Self {
        Self::new(SubscriptionTier::Core)
    }
}

/// Information for showing an upgrade prompt
#[derive(Debug, Clone)]
pub struct UpgradePrompt {
    /// The feature that triggered the prompt
    pub feature: Feature,
    /// Current subscription tier
    pub current_tier: SubscriptionTier,
    /// Required tier for the feature
    pub required_tier: SubscriptionTier,
    /// Prompt title
    pub title: String,
    /// Prompt message
    pub message: String,
    /// List of benefits
    pub benefits: Vec<String>,
    /// Price string
    pub price: String,
    /// Call to action text
    pub cta: String,
}

impl UpgradePrompt {
    /// Get the Stripe checkout URL
    pub fn checkout_url(&self) -> String {
        format!(
            "https://cxlinux.com/checkout?tier={}",
            self.required_tier.display_name().to_lowercase()
        )
    }
}

/// Helper macro for checking features
#[macro_export]
macro_rules! require_feature {
    ($gate:expr, $feature:expr) => {
        if let Err(e) = $gate.check($feature) {
            return Err(e.into());
        }
    };
}

/// Helper macro for checking features with custom error handling
#[macro_export]
macro_rules! check_feature {
    ($gate:expr, $feature:expr, $on_blocked:expr) => {
        if !$gate.is_enabled($feature) {
            $on_blocked;
        }
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_feature_gate_core() {
        let gate = FeatureGate::new(SubscriptionTier::Core);

        // Core should not have Pro features
        assert!(!gate.is_enabled(Feature::UnlimitedAgents));
        assert!(!gate.is_enabled(Feature::VoiceInput));
        assert!(!gate.is_enabled(Feature::CustomAI));

        // Enterprise features should be blocked
        assert!(!gate.is_enabled(Feature::SSO));
        assert!(!gate.is_enabled(Feature::AuditLogs));
    }

    #[test]
    fn test_feature_gate_pro() {
        let gate = FeatureGate::new(SubscriptionTier::Pro);

        // Pro should have Pro features
        assert!(gate.is_enabled(Feature::UnlimitedAgents));
        assert!(gate.is_enabled(Feature::VoiceInput));
        assert!(gate.is_enabled(Feature::CustomAI));

        // Enterprise features should still be blocked
        assert!(!gate.is_enabled(Feature::SSO));
        assert!(!gate.is_enabled(Feature::AuditLogs));
    }

    #[test]
    fn test_feature_gate_enterprise() {
        let gate = FeatureGate::new(SubscriptionTier::Enterprise);

        // Enterprise should have all features
        assert!(gate.is_enabled(Feature::UnlimitedAgents));
        assert!(gate.is_enabled(Feature::SSO));
        assert!(gate.is_enabled(Feature::AuditLogs));
    }

    #[test]
    fn test_feature_check_error() {
        let gate = FeatureGate::new(SubscriptionTier::Core);

        let result = gate.check(Feature::UnlimitedAgents);
        assert!(result.is_err());

        if let Err(FeatureError::TierRequired {
            required_tier,
            current_tier,
            ..
        }) = result
        {
            assert_eq!(required_tier, SubscriptionTier::Pro);
            assert_eq!(current_tier, SubscriptionTier::Core);
        } else {
            panic!("Expected TierRequired error");
        }
    }

    #[test]
    fn test_disabled_feature() {
        let mut gate = FeatureGate::new(SubscriptionTier::Pro);

        assert!(gate.is_enabled(Feature::VoiceInput));

        gate.disable_feature(Feature::VoiceInput);
        assert!(!gate.is_enabled(Feature::VoiceInput));

        gate.enable_feature(Feature::VoiceInput);
        assert!(gate.is_enabled(Feature::VoiceInput));
    }

    #[test]
    fn test_upgrade_prompt() {
        let gate = FeatureGate::new(SubscriptionTier::Core);
        let prompt = gate.show_upgrade_prompt(Feature::UnlimitedAgents);

        assert_eq!(prompt.required_tier, SubscriptionTier::Pro);
        assert!(prompt.benefits.len() > 0);
        assert!(prompt.cta.contains("Pro"));
    }
}
