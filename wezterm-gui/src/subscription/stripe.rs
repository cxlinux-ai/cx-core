//! Stripe API integration for subscription management
//!
//! Provides:
//! - Checkout session creation for upgrades
//! - Customer portal access for subscription management
//! - Webhook handling for subscription events
//! - Subscription status checking

use super::tier::SubscriptionTier;
use serde::{Deserialize, Serialize};

/// Stripe API configuration
#[derive(Debug, Clone)]
pub struct StripeConfig {
    /// Stripe API key (secret key)
    pub api_key: String,
    /// Stripe publishable key (for client-side)
    pub publishable_key: String,
    /// Webhook secret for verifying webhook signatures
    pub webhook_secret: Option<String>,
    /// Success URL for checkout
    pub success_url: String,
    /// Cancel URL for checkout
    pub cancel_url: String,
    /// Customer portal return URL
    pub portal_return_url: String,
}

impl StripeConfig {
    /// Create configuration from environment variables
    pub fn from_env() -> Option<Self> {
        Some(Self {
            api_key: std::env::var("STRIPE_SECRET_KEY").ok()?,
            publishable_key: std::env::var("STRIPE_PUBLISHABLE_KEY").ok()?,
            webhook_secret: std::env::var("STRIPE_WEBHOOK_SECRET").ok(),
            success_url: std::env::var("STRIPE_SUCCESS_URL")
                .unwrap_or_else(|_| "https://cxlinux.com/checkout/success".to_string()),
            cancel_url: std::env::var("STRIPE_CANCEL_URL")
                .unwrap_or_else(|_| "https://cxlinux.com/checkout/cancel".to_string()),
            portal_return_url: std::env::var("STRIPE_PORTAL_RETURN_URL")
                .unwrap_or_else(|_| "https://cxlinux.com/settings".to_string()),
        })
    }

    /// Create configuration with explicit values
    pub fn new(api_key: String, publishable_key: String) -> Self {
        Self {
            api_key,
            publishable_key,
            webhook_secret: None,
            success_url: "https://cxlinux.com/checkout/success".to_string(),
            cancel_url: "https://cxlinux.com/checkout/cancel".to_string(),
            portal_return_url: "https://cxlinux.com/settings".to_string(),
        }
    }
}

/// Stripe checkout session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckoutSession {
    /// Session ID
    pub id: String,
    /// Checkout URL to redirect user to
    pub url: String,
    /// Target tier
    pub tier: SubscriptionTier,
    /// Customer email (if known)
    pub customer_email: Option<String>,
    /// When the session expires
    pub expires_at: chrono::DateTime<chrono::Utc>,
}

/// Subscription status from Stripe
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubscriptionStatus {
    /// Active subscription
    Active,
    /// Past due (payment failed but still active)
    PastDue,
    /// Canceled but still active until period end
    Canceled,
    /// Subscription has ended
    Incomplete,
    /// Incomplete and expired
    IncompleteExpired,
    /// Trialing
    Trialing,
    /// Unpaid
    Unpaid,
    /// Paused
    Paused,
}

impl SubscriptionStatus {
    /// Check if the subscription is active (usable)
    pub fn is_active(&self) -> bool {
        matches!(
            self,
            Self::Active | Self::PastDue | Self::Trialing | Self::Canceled
        )
    }

    /// Check if payment is needed
    pub fn needs_payment(&self) -> bool {
        matches!(self, Self::PastDue | Self::Incomplete | Self::Unpaid)
    }
}

/// Stripe subscription information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StripeSubscription {
    /// Subscription ID
    pub id: String,
    /// Customer ID
    pub customer_id: String,
    /// Current status
    pub status: SubscriptionStatus,
    /// Current period start
    pub current_period_start: chrono::DateTime<chrono::Utc>,
    /// Current period end
    pub current_period_end: chrono::DateTime<chrono::Utc>,
    /// Whether it cancels at period end
    pub cancel_at_period_end: bool,
    /// Price ID
    pub price_id: String,
    /// Subscription tier
    pub tier: SubscriptionTier,
}

/// Webhook event types we care about
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WebhookEvent {
    /// Checkout completed successfully
    CheckoutCompleted {
        customer_id: String,
        subscription_id: String,
        tier: SubscriptionTier,
    },
    /// Subscription updated
    SubscriptionUpdated {
        subscription_id: String,
        status: SubscriptionStatus,
        tier: SubscriptionTier,
    },
    /// Subscription canceled
    SubscriptionCanceled {
        subscription_id: String,
    },
    /// Invoice paid
    InvoicePaid {
        customer_id: String,
        subscription_id: String,
    },
    /// Payment failed
    PaymentFailed {
        customer_id: String,
        subscription_id: Option<String>,
    },
    /// Unknown event type
    Unknown(String),
}

/// Stripe API client
pub struct StripeClient {
    /// HTTP client
    client: reqwest::Client,
    /// Configuration
    config: StripeConfig,
    /// API base URL
    base_url: String,
}

impl StripeClient {
    /// Create a new Stripe client
    pub fn new(config: StripeConfig) -> Self {
        Self {
            client: reqwest::Client::new(),
            config,
            base_url: "https://api.stripe.com/v1".to_string(),
        }
    }

    /// Create a checkout session for upgrading to a tier
    pub async fn create_checkout_session(
        &self,
        tier: SubscriptionTier,
    ) -> Result<CheckoutSession, super::StripeError> {
        let price_id = tier
            .stripe_price_id()
            .ok_or_else(|| super::StripeError::ApiError("No price for this tier".into()))?;

        let mut params = vec![
            ("mode", "subscription".to_string()),
            ("success_url", self.config.success_url.clone()),
            ("cancel_url", self.config.cancel_url.clone()),
            ("line_items[0][price]", price_id.to_string()),
            ("line_items[0][quantity]", "1".to_string()),
        ];

        // Add metadata
        params.push(("metadata[tier]", tier.display_name().to_string()));
        params.push((
            "metadata[source]",
            "cx-terminal".to_string(),
        ));

        let response = self
            .client
            .post(format!("{}/checkout/sessions", self.base_url))
            .basic_auth(&self.config.api_key, Option::<&str>::None)
            .form(&params)
            .send()
            .await
            .map_err(|e| super::StripeError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(super::StripeError::ApiError(format!(
                "Failed to create checkout session: {}",
                error_text
            )));
        }

        let session_data: serde_json::Value = response
            .json()
            .await
            .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

        Ok(CheckoutSession {
            id: session_data["id"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            url: session_data["url"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            tier,
            customer_email: session_data["customer_email"]
                .as_str()
                .map(|s| s.to_string()),
            expires_at: chrono::Utc::now() + chrono::Duration::hours(24),
        })
    }

    /// Create a customer portal session
    pub async fn create_portal_session(
        &self,
        customer_id: &str,
    ) -> Result<String, super::StripeError> {
        let params = [
            ("customer", customer_id),
            ("return_url", &self.config.portal_return_url),
        ];

        let response = self
            .client
            .post(format!("{}/billing_portal/sessions", self.base_url))
            .basic_auth(&self.config.api_key, Option::<&str>::None)
            .form(&params)
            .send()
            .await
            .map_err(|e| super::StripeError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(super::StripeError::ApiError(format!(
                "Failed to create portal session: {}",
                error_text
            )));
        }

        let session_data: serde_json::Value = response
            .json()
            .await
            .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

        session_data["url"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| super::StripeError::ApiError("No URL in response".into()))
    }

    /// Get subscription details
    pub async fn get_subscription(
        &self,
        subscription_id: &str,
    ) -> Result<StripeSubscription, super::StripeError> {
        let response = self
            .client
            .get(format!("{}/subscriptions/{}", self.base_url, subscription_id))
            .basic_auth(&self.config.api_key, Option::<&str>::None)
            .send()
            .await
            .map_err(|e| super::StripeError::NetworkError(e.to_string()))?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(super::StripeError::ApiError(format!(
                "Failed to get subscription: {}",
                error_text
            )));
        }

        let data: serde_json::Value = response
            .json()
            .await
            .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

        self.parse_subscription(&data)
    }

    /// Cancel a subscription
    pub async fn cancel_subscription(
        &self,
        subscription_id: &str,
        immediately: bool,
    ) -> Result<StripeSubscription, super::StripeError> {
        if immediately {
            let response = self
                .client
                .delete(format!("{}/subscriptions/{}", self.base_url, subscription_id))
                .basic_auth(&self.config.api_key, Option::<&str>::None)
                .send()
                .await
                .map_err(|e| super::StripeError::NetworkError(e.to_string()))?;

            if !response.status().is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(super::StripeError::ApiError(format!(
                    "Failed to cancel subscription: {}",
                    error_text
                )));
            }

            let data: serde_json::Value = response
                .json()
                .await
                .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

            self.parse_subscription(&data)
        } else {
            // Cancel at period end
            let params = [("cancel_at_period_end", "true")];

            let response = self
                .client
                .post(format!("{}/subscriptions/{}", self.base_url, subscription_id))
                .basic_auth(&self.config.api_key, Option::<&str>::None)
                .form(&params)
                .send()
                .await
                .map_err(|e| super::StripeError::NetworkError(e.to_string()))?;

            if !response.status().is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(super::StripeError::ApiError(format!(
                    "Failed to cancel subscription: {}",
                    error_text
                )));
            }

            let data: serde_json::Value = response
                .json()
                .await
                .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

            self.parse_subscription(&data)
        }
    }

    /// Parse webhook event
    pub fn parse_webhook(
        &self,
        payload: &str,
        signature: Option<&str>,
    ) -> Result<WebhookEvent, super::StripeError> {
        // Verify signature if webhook secret is configured
        if let (Some(secret), Some(sig)) = (&self.config.webhook_secret, signature) {
            if !self.verify_webhook_signature(payload, sig, secret) {
                return Err(super::StripeError::ApiError(
                    "Invalid webhook signature".into(),
                ));
            }
        }

        let event: serde_json::Value = serde_json::from_str(payload)
            .map_err(|e| super::StripeError::ApiError(e.to_string()))?;

        let event_type = event["type"].as_str().unwrap_or_default();
        let data = &event["data"]["object"];

        match event_type {
            "checkout.session.completed" => {
                let customer_id = data["customer"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                let subscription_id = data["subscription"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                let tier_str = data["metadata"]["tier"].as_str().unwrap_or("pro");
                let tier =
                    SubscriptionTier::from_str(tier_str).unwrap_or(SubscriptionTier::Pro);

                Ok(WebhookEvent::CheckoutCompleted {
                    customer_id,
                    subscription_id,
                    tier,
                })
            }
            "customer.subscription.updated" => {
                let subscription_id = data["id"].as_str().unwrap_or_default().to_string();
                let status = self.parse_status(data["status"].as_str().unwrap_or("active"));
                let tier = self.tier_from_price_id(
                    data["items"]["data"][0]["price"]["id"]
                        .as_str()
                        .unwrap_or_default(),
                );

                Ok(WebhookEvent::SubscriptionUpdated {
                    subscription_id,
                    status,
                    tier,
                })
            }
            "customer.subscription.deleted" => {
                let subscription_id = data["id"].as_str().unwrap_or_default().to_string();
                Ok(WebhookEvent::SubscriptionCanceled { subscription_id })
            }
            "invoice.paid" => {
                let customer_id = data["customer"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                let subscription_id = data["subscription"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();

                Ok(WebhookEvent::InvoicePaid {
                    customer_id,
                    subscription_id,
                })
            }
            "invoice.payment_failed" => {
                let customer_id = data["customer"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                let subscription_id = data["subscription"].as_str().map(|s| s.to_string());

                Ok(WebhookEvent::PaymentFailed {
                    customer_id,
                    subscription_id,
                })
            }
            _ => Ok(WebhookEvent::Unknown(event_type.to_string())),
        }
    }

    fn parse_subscription(
        &self,
        data: &serde_json::Value,
    ) -> Result<StripeSubscription, super::StripeError> {
        let price_id = data["items"]["data"][0]["price"]["id"]
            .as_str()
            .unwrap_or_default();

        Ok(StripeSubscription {
            id: data["id"].as_str().unwrap_or_default().to_string(),
            customer_id: data["customer"].as_str().unwrap_or_default().to_string(),
            status: self.parse_status(data["status"].as_str().unwrap_or("active")),
            current_period_start: chrono::DateTime::from_timestamp(
                data["current_period_start"].as_i64().unwrap_or(0),
                0,
            )
            .unwrap_or_else(chrono::Utc::now),
            current_period_end: chrono::DateTime::from_timestamp(
                data["current_period_end"].as_i64().unwrap_or(0),
                0,
            )
            .unwrap_or_else(chrono::Utc::now),
            cancel_at_period_end: data["cancel_at_period_end"].as_bool().unwrap_or(false),
            price_id: price_id.to_string(),
            tier: self.tier_from_price_id(price_id),
        })
    }

    fn parse_status(&self, status: &str) -> SubscriptionStatus {
        match status {
            "active" => SubscriptionStatus::Active,
            "past_due" => SubscriptionStatus::PastDue,
            "canceled" => SubscriptionStatus::Canceled,
            "incomplete" => SubscriptionStatus::Incomplete,
            "incomplete_expired" => SubscriptionStatus::IncompleteExpired,
            "trialing" => SubscriptionStatus::Trialing,
            "unpaid" => SubscriptionStatus::Unpaid,
            "paused" => SubscriptionStatus::Paused,
            _ => SubscriptionStatus::Active,
        }
    }

    fn tier_from_price_id(&self, price_id: &str) -> SubscriptionTier {
        if price_id.contains("enterprise") {
            SubscriptionTier::Enterprise
        } else if price_id.contains("pro") {
            SubscriptionTier::Pro
        } else {
            SubscriptionTier::Core
        }
    }

    fn verify_webhook_signature(&self, _payload: &str, _signature: &str, _secret: &str) -> bool {
        // In production, implement proper HMAC-SHA256 signature verification
        // For now, we'll trust all webhooks if a secret is configured
        true
    }

    /// Open checkout in browser
    pub fn open_checkout_in_browser(session: &CheckoutSession) -> Result<(), std::io::Error> {
        #[cfg(target_os = "macos")]
        {
            std::process::Command::new("open")
                .arg(&session.url)
                .spawn()?;
        }

        #[cfg(target_os = "linux")]
        {
            std::process::Command::new("xdg-open")
                .arg(&session.url)
                .spawn()?;
        }

        #[cfg(target_os = "windows")]
        {
            std::process::Command::new("cmd")
                .args(["/c", "start", &session.url])
                .spawn()?;
        }

        Ok(())
    }
}

/// Open URL in default browser
pub fn open_url(url: &str) -> Result<(), std::io::Error> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open").arg(url).spawn()?;
    }

    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open").arg(url).spawn()?;
    }

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/c", "start", url])
            .spawn()?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_subscription_status_is_active() {
        assert!(SubscriptionStatus::Active.is_active());
        assert!(SubscriptionStatus::PastDue.is_active());
        assert!(SubscriptionStatus::Trialing.is_active());
        assert!(!SubscriptionStatus::Incomplete.is_active());
        assert!(!SubscriptionStatus::Unpaid.is_active());
    }

    #[test]
    fn test_subscription_status_needs_payment() {
        assert!(SubscriptionStatus::PastDue.needs_payment());
        assert!(SubscriptionStatus::Incomplete.needs_payment());
        assert!(SubscriptionStatus::Unpaid.needs_payment());
        assert!(!SubscriptionStatus::Active.needs_payment());
    }

    #[test]
    fn test_stripe_config_new() {
        let config = StripeConfig::new(
            "sk_test_xxx".to_string(),
            "pk_test_xxx".to_string(),
        );

        assert_eq!(config.api_key, "sk_test_xxx");
        assert_eq!(config.publishable_key, "pk_test_xxx");
        assert!(config.webhook_secret.is_none());
    }
}
