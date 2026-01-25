//! Subscription tier definitions and limits
//!
//! CX Terminal is bundled with Cortex Linux subscriptions.
//! Pricing aligns with cortexlinux.com/pricing:
//! - Core (Free): 1 system, basic features
//! - Pro ($19/system): Unlimited systems, commercial use
//! - Team ($49/mo): Cloud AI, team dashboard, 25 systems
//! - Enterprise ($199/mo): SSO, compliance, 100 systems

use serde::{Deserialize, Serialize};

/// Subscription tier levels
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SubscriptionTier {
    /// Free tier - 1 system, basic features
    Core,
    /// Pro tier ($19/system) - unlimited systems, commercial license
    Pro,
    /// Team tier ($49/mo) - cloud AI, team features, 25 systems
    Team,
    /// Enterprise tier ($199/mo) - SSO, compliance, 100 systems
    Enterprise,
}

impl SubscriptionTier {
    /// Get the display name for the tier
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Core => "Core",
            Self::Pro => "Pro",
            Self::Team => "Team",
            Self::Enterprise => "Enterprise",
        }
    }

    /// Get the tier from a string
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "core" | "free" => Some(Self::Core),
            "pro" | "professional" => Some(Self::Pro),
            "team" | "teams" | "business" => Some(Self::Team),
            "enterprise" | "org" | "organization" => Some(Self::Enterprise),
            _ => None,
        }
    }

    /// Get the monthly price in cents
    pub fn price_cents(&self) -> u32 {
        match self {
            Self::Core => 0,
            Self::Pro => 1900,       // $19/system
            Self::Team => 4900,      // $49/mo
            Self::Enterprise => 19900, // $199/mo
        }
    }

    /// Get the monthly price as a string
    pub fn price_display(&self) -> &'static str {
        match self {
            Self::Core => "Free",
            Self::Pro => "$19/system",
            Self::Team => "$49/mo",
            Self::Enterprise => "$199/mo",
        }
    }

    /// Get the number of systems included
    pub fn systems_included(&self) -> usize {
        match self {
            Self::Core => 1,
            Self::Pro => usize::MAX, // Unlimited (per-system pricing)
            Self::Team => 25,
            Self::Enterprise => 100,
        }
    }

    /// Check if this tier includes another tier's features
    pub fn includes(&self, other: &SubscriptionTier) -> bool {
        match (self, other) {
            (Self::Enterprise, _) => true,
            (Self::Team, Self::Core) | (Self::Team, Self::Pro) | (Self::Team, Self::Team) => true,
            (Self::Pro, Self::Core) | (Self::Pro, Self::Pro) => true,
            (Self::Core, Self::Core) => true,
            _ => false,
        }
    }

    /// Get the Stripe price ID for this tier (matches cortexlinux.com)
    pub fn stripe_price_id_monthly(&self) -> Option<&'static str> {
        match self {
            Self::Core => None,
            Self::Pro => Some("price_1SpotMJ4X1wkC4EspVzV5tT6"),
            Self::Team => Some("price_1SpotNJ4X1wkC4EsN13pV2dA"),
            Self::Enterprise => Some("price_1SpotOJ4X1wkC4Es7ZqOzh1H"),
        }
    }

    /// Get the Stripe price ID for annual billing
    pub fn stripe_price_id_annual(&self) -> Option<&'static str> {
        match self {
            Self::Core => None,
            Self::Pro => Some("price_1SpotMJ4X1wkC4Es3tuZGVHY"),
            Self::Team => Some("price_1SpotNJ4X1wkC4Esw5ienNNQ"),
            Self::Enterprise => Some("price_1SpotOJ4X1wkC4EslmMmWWZI"),
        }
    }

    /// Get all available tiers
    pub fn all() -> &'static [Self] {
        &[Self::Core, Self::Pro, Self::Team, Self::Enterprise]
    }
}

impl Default for SubscriptionTier {
    fn default() -> Self {
        Self::Core
    }
}

impl std::fmt::Display for SubscriptionTier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.display_name())
    }
}

/// Limits associated with each subscription tier
#[derive(Debug, Clone)]
pub struct TierLimits {
    /// Maximum number of systems
    pub max_systems: usize,
    /// Maximum number of agents that can be used
    pub max_agents: usize,
    /// Maximum AI queries per day
    pub ai_queries_per_day: usize,
    /// History retention in days
    pub history_days: usize,
    /// Maximum number of workflows
    pub workflows: usize,
    /// Whether custom agents are allowed
    pub custom_agents: bool,
    /// Whether voice input is allowed
    pub voice_input: bool,
    /// Whether offline LLM is allowed
    pub offline_llm: bool,
    /// Whether external APIs (BYOK) are allowed
    pub external_apis: bool,
    /// Whether cloud LLM fallback is available
    pub cloud_llm: bool,
    /// Whether team dashboard is available
    pub team_dashboard: bool,
    /// Whether audit logs are available
    pub audit_logs: bool,
    /// Whether SSO is available
    pub sso: bool,
    /// Whether private agents are available
    pub private_agents: bool,
    /// Maximum team members
    pub max_team_members: usize,
    /// Whether API access is available
    pub api_access: bool,
    /// Priority support
    pub priority_support: bool,
    /// Commercial license
    pub commercial_license: bool,
}

impl TierLimits {
    /// Get limits for a specific tier
    pub fn for_tier(tier: &SubscriptionTier) -> Self {
        match tier {
            SubscriptionTier::Core => Self::core(),
            SubscriptionTier::Pro => Self::pro(),
            SubscriptionTier::Team => Self::team(),
            SubscriptionTier::Enterprise => Self::enterprise(),
        }
    }

    /// Core tier limits (Free - 1 system)
    pub fn core() -> Self {
        Self {
            max_systems: 1,
            max_agents: 3,
            ai_queries_per_day: 50,
            history_days: 7,
            workflows: 5,
            custom_agents: false,
            voice_input: false,
            offline_llm: true,  // Local Ollama always works
            external_apis: false,
            cloud_llm: false,
            team_dashboard: false,
            audit_logs: false,
            sso: false,
            private_agents: false,
            max_team_members: 1,
            api_access: false,
            priority_support: false,
            commercial_license: false,
        }
    }

    /// Pro tier limits ($19/system - unlimited systems)
    pub fn pro() -> Self {
        Self {
            max_systems: usize::MAX,
            max_agents: usize::MAX,
            ai_queries_per_day: usize::MAX,
            history_days: usize::MAX,
            workflows: usize::MAX,
            custom_agents: true,
            voice_input: true,
            offline_llm: true,
            external_apis: true,  // Bring your own API key
            cloud_llm: false,     // No included cloud LLM
            team_dashboard: false,
            audit_logs: false,
            sso: false,
            private_agents: false,
            max_team_members: 1,
            api_access: true,
            priority_support: false,
            commercial_license: true,
        }
    }

    /// Team tier limits ($49/mo - 25 systems)
    pub fn team() -> Self {
        Self {
            max_systems: 25,
            max_agents: usize::MAX,
            ai_queries_per_day: usize::MAX,
            history_days: usize::MAX,
            workflows: usize::MAX,
            custom_agents: true,
            voice_input: true,
            offline_llm: true,
            external_apis: true,
            cloud_llm: true,      // Cloud LLM fallback included
            team_dashboard: true,
            audit_logs: true,
            sso: false,
            private_agents: false,
            max_team_members: 25,
            api_access: true,
            priority_support: false,
            commercial_license: true,
        }
    }

    /// Enterprise tier limits ($199/mo - 100 systems)
    pub fn enterprise() -> Self {
        Self {
            max_systems: 100,
            max_agents: usize::MAX,
            ai_queries_per_day: usize::MAX,
            history_days: usize::MAX,
            workflows: usize::MAX,
            custom_agents: true,
            voice_input: true,
            offline_llm: true,
            external_apis: true,
            cloud_llm: true,
            team_dashboard: true,
            audit_logs: true,
            sso: true,
            private_agents: true,
            max_team_members: usize::MAX,
            api_access: true,
            priority_support: true,
            commercial_license: true,
        }
    }

    /// Check if a specific limit is unlimited
    pub fn is_unlimited(&self, limit_name: &str) -> bool {
        match limit_name {
            "systems" => self.max_systems == usize::MAX,
            "agents" => self.max_agents == usize::MAX,
            "ai_queries" => self.ai_queries_per_day == usize::MAX,
            "history" => self.history_days == usize::MAX,
            "workflows" => self.workflows == usize::MAX,
            "team_members" => self.max_team_members == usize::MAX,
            _ => false,
        }
    }
}

/// Information about a subscription tier for display
#[derive(Debug, Clone)]
pub struct TierInfo {
    /// Tier level
    pub tier: SubscriptionTier,
    /// Display name
    pub name: &'static str,
    /// Short description
    pub description: &'static str,
    /// Price display string
    pub price: &'static str,
    /// Systems included
    pub systems: &'static str,
    /// Feature highlights
    pub highlights: Vec<&'static str>,
    /// Limits
    pub limits: TierLimits,
}

impl TierInfo {
    /// Get tier info for a specific tier
    pub fn for_tier(tier: &SubscriptionTier) -> Self {
        match tier {
            SubscriptionTier::Core => Self::core(),
            SubscriptionTier::Pro => Self::pro(),
            SubscriptionTier::Team => Self::team(),
            SubscriptionTier::Enterprise => Self::enterprise(),
        }
    }

    fn core() -> Self {
        Self {
            tier: SubscriptionTier::Core,
            name: "Core",
            description: "Essential features for personal use",
            price: "Free",
            systems: "1 system",
            highlights: vec![
                "Intelligent blocks UI",
                "3 built-in AI agents",
                "50 AI queries/day",
                "7 days history",
                "5 saved workflows",
                "Local LLM support (Ollama)",
                "Community support",
            ],
            limits: TierLimits::core(),
        }
    }

    fn pro() -> Self {
        Self {
            tier: SubscriptionTier::Pro,
            name: "Pro",
            description: "Unlimited systems for commercial use",
            price: "$19/system",
            systems: "Unlimited",
            highlights: vec![
                "Everything in Core",
                "Unlimited systems",
                "Commercial license",
                "Unlimited AI agents",
                "Unlimited AI queries",
                "Unlimited history",
                "Unlimited workflows",
                "Voice input (Whisper)",
                "Bring your own API key",
                "API access",
            ],
            limits: TierLimits::pro(),
        }
    }

    fn team() -> Self {
        Self {
            tier: SubscriptionTier::Team,
            name: "Team",
            description: "Cloud AI power for teams",
            price: "$49/mo",
            systems: "25 systems included",
            highlights: vec![
                "Everything in Pro",
                "Cloud LLM fallback",
                "Team dashboard",
                "Audit logging",
                "25 team members",
            ],
            limits: TierLimits::team(),
        }
    }

    fn enterprise() -> Self {
        Self {
            tier: SubscriptionTier::Enterprise,
            name: "Enterprise",
            description: "Full compliance & dedicated support",
            price: "$199/mo",
            systems: "100 systems included",
            highlights: vec![
                "Everything in Team",
                "SSO/SAML integration",
                "Compliance reports",
                "Private AI agents",
                "Unlimited team members",
                "Priority support",
                "99.9% SLA",
            ],
            limits: TierLimits::enterprise(),
        }
    }

    /// Get all tier information for comparison
    pub fn all() -> Vec<Self> {
        vec![Self::core(), Self::pro(), Self::team(), Self::enterprise()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tier_includes() {
        assert!(SubscriptionTier::Enterprise.includes(&SubscriptionTier::Team));
        assert!(SubscriptionTier::Enterprise.includes(&SubscriptionTier::Pro));
        assert!(SubscriptionTier::Enterprise.includes(&SubscriptionTier::Core));
        assert!(SubscriptionTier::Team.includes(&SubscriptionTier::Pro));
        assert!(SubscriptionTier::Team.includes(&SubscriptionTier::Core));
        assert!(SubscriptionTier::Pro.includes(&SubscriptionTier::Core));
        assert!(!SubscriptionTier::Core.includes(&SubscriptionTier::Pro));
    }

    #[test]
    fn test_tier_limits() {
        let core = TierLimits::core();
        assert_eq!(core.max_systems, 1);
        assert_eq!(core.max_agents, 3);
        assert_eq!(core.ai_queries_per_day, 50);
        assert!(!core.custom_agents);
        assert!(!core.commercial_license);

        let pro = TierLimits::pro();
        assert_eq!(pro.max_systems, usize::MAX);
        assert!(pro.custom_agents);
        assert!(pro.voice_input);
        assert!(pro.commercial_license);
        assert!(!pro.cloud_llm);

        let team = TierLimits::team();
        assert_eq!(team.max_systems, 25);
        assert!(team.cloud_llm);
        assert!(team.team_dashboard);

        let enterprise = TierLimits::enterprise();
        assert_eq!(enterprise.max_systems, 100);
        assert!(enterprise.sso);
        assert!(enterprise.audit_logs);
        assert!(enterprise.priority_support);
    }

    #[test]
    fn test_tier_from_str() {
        assert_eq!(SubscriptionTier::from_str("core"), Some(SubscriptionTier::Core));
        assert_eq!(SubscriptionTier::from_str("free"), Some(SubscriptionTier::Core));
        assert_eq!(SubscriptionTier::from_str("pro"), Some(SubscriptionTier::Pro));
        assert_eq!(SubscriptionTier::from_str("team"), Some(SubscriptionTier::Team));
        assert_eq!(SubscriptionTier::from_str("enterprise"), Some(SubscriptionTier::Enterprise));
        assert_eq!(SubscriptionTier::from_str("invalid"), None);
    }

    #[test]
    fn test_tier_price() {
        assert_eq!(SubscriptionTier::Core.price_cents(), 0);
        assert_eq!(SubscriptionTier::Pro.price_cents(), 1900);
        assert_eq!(SubscriptionTier::Team.price_cents(), 4900);
        assert_eq!(SubscriptionTier::Enterprise.price_cents(), 19900);
    }

    #[test]
    fn test_systems_included() {
        assert_eq!(SubscriptionTier::Core.systems_included(), 1);
        assert_eq!(SubscriptionTier::Pro.systems_included(), usize::MAX);
        assert_eq!(SubscriptionTier::Team.systems_included(), 25);
        assert_eq!(SubscriptionTier::Enterprise.systems_included(), 100);
    }
}
