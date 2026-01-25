//! Subscription tier definitions and limits
//!
//! Defines the three subscription tiers and their associated limits:
//! - Core (Free): Basic functionality
//! - Pro ($10/mo): Full AI and agent capabilities
//! - Enterprise ($25/user/mo): Team and compliance features

use serde::{Deserialize, Serialize};

/// Subscription tier levels
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SubscriptionTier {
    /// Free tier with basic features
    Core,
    /// Pro tier ($10/mo) with full AI capabilities
    Pro,
    /// Enterprise tier ($25/user/mo) with team features
    Enterprise,
}

impl SubscriptionTier {
    /// Get the display name for the tier
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Core => "Core",
            Self::Pro => "Pro",
            Self::Enterprise => "Enterprise",
        }
    }

    /// Get the tier from a string
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "core" | "free" => Some(Self::Core),
            "pro" | "professional" => Some(Self::Pro),
            "enterprise" | "team" | "business" => Some(Self::Enterprise),
            _ => None,
        }
    }

    /// Get the monthly price in cents
    pub fn price_cents(&self) -> u32 {
        match self {
            Self::Core => 0,
            Self::Pro => 1000,        // $10/mo
            Self::Enterprise => 2500, // $25/user/mo
        }
    }

    /// Get the monthly price as a string
    pub fn price_display(&self) -> &'static str {
        match self {
            Self::Core => "Free",
            Self::Pro => "$10/mo",
            Self::Enterprise => "$25/user/mo",
        }
    }

    /// Check if this tier includes another tier's features
    pub fn includes(&self, other: &SubscriptionTier) -> bool {
        match (self, other) {
            (Self::Enterprise, _) => true,
            (Self::Pro, Self::Core) | (Self::Pro, Self::Pro) => true,
            (Self::Core, Self::Core) => true,
            _ => false,
        }
    }

    /// Get the Stripe price ID for this tier
    pub fn stripe_price_id(&self) -> Option<&'static str> {
        match self {
            Self::Core => None,
            Self::Pro => Some("price_cx_terminal_pro_monthly"),
            Self::Enterprise => Some("price_cx_terminal_enterprise_monthly"),
        }
    }

    /// Get all available tiers
    pub fn all() -> &'static [Self] {
        &[Self::Core, Self::Pro, Self::Enterprise]
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
    /// Whether external APIs are allowed
    pub external_apis: bool,
    /// Whether audit logs are available
    pub audit_logs: bool,
    /// Whether SSO is available
    pub sso: bool,
    /// Whether private agents are available
    pub private_agents: bool,
    /// Maximum team members (Enterprise only)
    pub max_team_members: usize,
    /// Whether API access is available
    pub api_access: bool,
    /// Priority support
    pub priority_support: bool,
}

impl TierLimits {
    /// Get limits for a specific tier
    pub fn for_tier(tier: &SubscriptionTier) -> Self {
        match tier {
            SubscriptionTier::Core => Self::core(),
            SubscriptionTier::Pro => Self::pro(),
            SubscriptionTier::Enterprise => Self::enterprise(),
        }
    }

    /// Core tier limits
    pub fn core() -> Self {
        Self {
            max_agents: 3,
            ai_queries_per_day: 50,
            history_days: 7,
            workflows: 5,
            custom_agents: false,
            voice_input: false,
            offline_llm: false,
            external_apis: false,
            audit_logs: false,
            sso: false,
            private_agents: false,
            max_team_members: 1,
            api_access: false,
            priority_support: false,
        }
    }

    /// Pro tier limits
    pub fn pro() -> Self {
        Self {
            max_agents: usize::MAX,
            ai_queries_per_day: usize::MAX,
            history_days: usize::MAX,
            workflows: usize::MAX,
            custom_agents: true,
            voice_input: true,
            offline_llm: true,
            external_apis: true,
            audit_logs: false,
            sso: false,
            private_agents: false,
            max_team_members: 1,
            api_access: true,
            priority_support: false,
        }
    }

    /// Enterprise tier limits
    pub fn enterprise() -> Self {
        Self {
            max_agents: usize::MAX,
            ai_queries_per_day: usize::MAX,
            history_days: usize::MAX,
            workflows: usize::MAX,
            custom_agents: true,
            voice_input: true,
            offline_llm: true,
            external_apis: true,
            audit_logs: true,
            sso: true,
            private_agents: true,
            max_team_members: usize::MAX,
            api_access: true,
            priority_support: true,
        }
    }

    /// Check if a specific limit is unlimited
    pub fn is_unlimited(&self, limit_name: &str) -> bool {
        match limit_name {
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
            SubscriptionTier::Enterprise => Self::enterprise(),
        }
    }

    fn core() -> Self {
        Self {
            tier: SubscriptionTier::Core,
            name: "Core",
            description: "Essential terminal features for individual developers",
            price: "Free",
            highlights: vec![
                "Intelligent blocks UI",
                "3 built-in AI agents",
                "50 AI queries/day",
                "7 days history",
                "5 saved workflows",
                "Community support",
            ],
            limits: TierLimits::core(),
        }
    }

    fn pro() -> Self {
        Self {
            tier: SubscriptionTier::Pro,
            name: "Pro",
            description: "Full AI capabilities for power users",
            price: "$10/mo",
            highlights: vec![
                "Everything in Core",
                "Unlimited AI agents",
                "Unlimited AI queries",
                "Unlimited history",
                "Unlimited workflows",
                "Custom AI agents",
                "Voice input",
                "Offline LLM support",
                "External API access",
                "API access",
            ],
            limits: TierLimits::pro(),
        }
    }

    fn enterprise() -> Self {
        Self {
            tier: SubscriptionTier::Enterprise,
            name: "Enterprise",
            description: "Team features with compliance and security",
            price: "$25/user/mo",
            highlights: vec![
                "Everything in Pro",
                "SSO/SAML authentication",
                "Audit logging",
                "Private AI agents",
                "Team management",
                "Unlimited team members",
                "Priority support",
                "Custom deployment options",
                "SLA guarantee",
            ],
            limits: TierLimits::enterprise(),
        }
    }

    /// Get all tier information for comparison
    pub fn all() -> Vec<Self> {
        vec![Self::core(), Self::pro(), Self::enterprise()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tier_includes() {
        assert!(SubscriptionTier::Enterprise.includes(&SubscriptionTier::Pro));
        assert!(SubscriptionTier::Enterprise.includes(&SubscriptionTier::Core));
        assert!(SubscriptionTier::Pro.includes(&SubscriptionTier::Core));
        assert!(!SubscriptionTier::Core.includes(&SubscriptionTier::Pro));
    }

    #[test]
    fn test_tier_limits() {
        let core = TierLimits::core();
        assert_eq!(core.max_agents, 3);
        assert_eq!(core.ai_queries_per_day, 50);
        assert!(!core.custom_agents);

        let pro = TierLimits::pro();
        assert_eq!(pro.max_agents, usize::MAX);
        assert!(pro.custom_agents);
        assert!(pro.voice_input);

        let enterprise = TierLimits::enterprise();
        assert!(enterprise.sso);
        assert!(enterprise.audit_logs);
    }

    #[test]
    fn test_tier_from_str() {
        assert_eq!(SubscriptionTier::from_str("core"), Some(SubscriptionTier::Core));
        assert_eq!(SubscriptionTier::from_str("free"), Some(SubscriptionTier::Core));
        assert_eq!(SubscriptionTier::from_str("pro"), Some(SubscriptionTier::Pro));
        assert_eq!(SubscriptionTier::from_str("enterprise"), Some(SubscriptionTier::Enterprise));
        assert_eq!(SubscriptionTier::from_str("invalid"), None);
    }

    #[test]
    fn test_tier_price() {
        assert_eq!(SubscriptionTier::Core.price_cents(), 0);
        assert_eq!(SubscriptionTier::Pro.price_cents(), 1000);
        assert_eq!(SubscriptionTier::Enterprise.price_cents(), 2500);
    }
}
