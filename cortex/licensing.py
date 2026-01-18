"""Cortex Linux licensing and feature gating."""

import json
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

LICENSE_FILE = Path.home() / ".cortex" / "license.key"
LICENSE_SERVER = "https://api.cortexlinux.com/v1/license"
PRICING_URL = "https://cortexlinux.com/pricing"
UPGRADE_URL = "https://cortexlinux.com/upgrade"


class FeatureTier:
    """Subscription tier levels."""

    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    @staticmethod
    def level(tier: str) -> int:
        """Get numeric level for tier comparison."""
        levels = {
            FeatureTier.COMMUNITY: 0,
            FeatureTier.PRO: 1,
            FeatureTier.ENTERPRISE: 2,
        }
        return levels.get(tier, 0)


# Feature to tier mapping
FEATURE_REQUIREMENTS = {
    # Pro features ($20/month)
    "cloud_llm": FeatureTier.PRO,
    "web_console": FeatureTier.PRO,
    "kubernetes": FeatureTier.PRO,
    "complex_stacks": FeatureTier.PRO,
    "ai_diagnosis": FeatureTier.PRO,
    "parallel_ops": FeatureTier.PRO,
    "priority_support": FeatureTier.PRO,
    "usage_analytics": FeatureTier.PRO,
    # Enterprise features ($99/month)
    "sso": FeatureTier.ENTERPRISE,
    "ldap": FeatureTier.ENTERPRISE,
    "audit_logs": FeatureTier.ENTERPRISE,
    "compliance": FeatureTier.ENTERPRISE,
    "custom_branding": FeatureTier.ENTERPRISE,
    "multi_tenant": FeatureTier.ENTERPRISE,
    "sla": FeatureTier.ENTERPRISE,
}

# User-friendly feature names
FEATURE_NAMES = {
    "cloud_llm": "Cloud LLM Connectors",
    "web_console": "Web Console",
    "kubernetes": "Kubernetes Deployment",
    "complex_stacks": "Complex Stack Deployment",
    "ai_diagnosis": "AI-Powered Diagnostics",
    "parallel_ops": "Parallel Operations",
    "priority_support": "Priority Support",
    "usage_analytics": "Usage Analytics",
    "sso": "Single Sign-On (SSO)",
    "ldap": "LDAP/Active Directory",
    "audit_logs": "Audit Logging",
    "compliance": "Compliance Reports",
    "custom_branding": "Custom Branding",
    "multi_tenant": "Multi-Tenant Support",
    "sla": "SLA Guarantee",
}


class LicenseInfo:
    """License information."""

    def __init__(
        self,
        tier: str = FeatureTier.COMMUNITY,
        valid: bool = True,
        expires: datetime | None = None,
        organization: str | None = None,
        email: str | None = None,
    ):
        self.tier = tier
        self.valid = valid
        self.expires = expires
        self.organization = organization
        self.email = email

    @property
    def is_expired(self) -> bool:
        """Check if license is expired."""
        if not self.expires:
            return False
        return datetime.now(timezone.utc) > self.expires

    @property
    def days_remaining(self) -> int:
        """Days until expiration."""
        if not self.expires:
            return -1  # Never expires (community)
        delta = self.expires - datetime.now(timezone.utc)
        return max(0, delta.days)


_cached_license: LicenseInfo | None = None


def get_license_info() -> LicenseInfo:
    """Get current license information."""
    global _cached_license

    if _cached_license:
        return _cached_license

    # Check local license file
    if LICENSE_FILE.exists():
        try:
            data = json.loads(LICENSE_FILE.read_text())
            _cached_license = LicenseInfo(
                tier=data.get("tier", FeatureTier.COMMUNITY),
                valid=data.get("valid", True),
                expires=datetime.fromisoformat(data["expires"]) if data.get("expires") else None,
                organization=data.get("organization"),
                email=data.get("email"),
            )

            # Check expiration
            if _cached_license.is_expired:
                _cached_license.tier = FeatureTier.COMMUNITY
                _cached_license.valid = False

            return _cached_license
        except (json.JSONDecodeError, KeyError):
            pass

    # Default to community
    _cached_license = LicenseInfo()
    return _cached_license


def get_license_tier() -> str:
    """Get current license tier."""
    return get_license_info().tier


def check_feature(feature_name: str, silent: bool = False) -> bool:
    """Check if user's license allows this feature.

    Args:
        feature_name: Feature identifier
        silent: If True, don't show upgrade prompt

    Returns:
        True if feature is available
    """
    license_info = get_license_info()
    required_tier = FEATURE_REQUIREMENTS.get(feature_name, FeatureTier.COMMUNITY)

    user_level = FeatureTier.level(license_info.tier)
    required_level = FeatureTier.level(required_tier)

    if user_level >= required_level:
        return True

    # Show upgrade prompt
    if not silent:
        show_upgrade_prompt(feature_name, required_tier)

    return False


def require_feature(feature_name: str):
    """Decorator to require a feature for a function.

    Args:
        feature_name: Required feature identifier

    Raises:
        FeatureNotAvailableError: If feature not available
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            if not check_feature(feature_name):
                raise FeatureNotAvailableError(feature_name)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def show_upgrade_prompt(feature: str, required_tier: str) -> None:
    """Show compelling upgrade message."""
    feature_display = FEATURE_NAMES.get(feature, feature)
    tier_display = required_tier.title()

    price = "$20" if required_tier == FeatureTier.PRO else "$99"

    print(f"""
┌─────────────────────────────────────────────────────────┐
│  ⚡ UPGRADE REQUIRED                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  '{feature_display}' requires Cortex {tier_display}
│                                                         │
│  ✅ Upgrade now:  cortex upgrade                        │
│                                                         │
│  Plans start at {price}/month with 14-day free trial.
│                                                         │
│  🌐 {PRICING_URL}
│                                                         │
└─────────────────────────────────────────────────────────┘
""")


def show_license_status() -> None:
    """Display current license status."""
    info = get_license_info()

    tier_colors = {
        FeatureTier.COMMUNITY: "dim",
        FeatureTier.PRO: "cyan",
        FeatureTier.ENTERPRISE: "yellow",
    }

    print(f"""
┌─────────────────────────────────────────────────────────┐
│  CORTEX LICENSE STATUS                                  │
├─────────────────────────────────────────────────────────┤
│  Tier:         {info.tier.upper():12}                          │
│  Status:       {"ACTIVE" if info.valid else "EXPIRED":12}                          │""")

    if info.organization:
        print(f"│  Organization: {info.organization[:12]:12}                          │")

    if info.expires:
        print(f"│  Expires:      {info.expires.strftime('%Y-%m-%d'):12}                          │")
        print(f"│  Days Left:    {info.days_remaining:<12}                          │")

    print("└─────────────────────────────────────────────────────────┘")

    # Show available features
    print("\n  Available Features:")
    for feature, required in FEATURE_REQUIREMENTS.items():
        available = FeatureTier.level(info.tier) >= FeatureTier.level(required)
        icon = "✅" if available else "🔒"
        name = FEATURE_NAMES.get(feature, feature)
        print(f"    {icon} {name}")

    if info.tier == FeatureTier.COMMUNITY:
        print("\n  💡 Upgrade to Pro for just $20/month: cortex upgrade")


def activate_license(license_key: str) -> bool:
    """Activate a license key.

    Args:
        license_key: License key to activate

    Returns:
        True if activation successful
    """
    global _cached_license

    try:
        response = httpx.post(
            f"{LICENSE_SERVER}/activate",
            json={
                "license_key": license_key,
                "hostname": _get_hostname(),
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            # Save license locally
            LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
            LICENSE_FILE.write_text(
                json.dumps(
                    {
                        "key": license_key,
                        "tier": data["tier"],
                        "valid": True,
                        "expires": data.get("expires"),
                        "organization": data.get("organization"),
                        "email": data.get("email"),
                    }
                )
            )

            # Clear cache
            _cached_license = None

            print("\n  ✅ License activated successfully!")
            print(f"     Tier: {data['tier'].upper()}")
            if data.get("organization"):
                print(f"     Organization: {data['organization']}")

            return True
        else:
            print(f"\n  ❌ Activation failed: {data.get('error', 'Unknown error')}")
            return False

    except httpx.HTTPError as e:
        print("\n  ❌ Activation failed: Could not reach license server")
        return False


def open_upgrade_page() -> None:
    """Open the upgrade page in browser."""
    print(f"\n  🌐 Opening {UPGRADE_URL}")
    webbrowser.open(UPGRADE_URL)


def _get_hostname() -> str:
    """Get system hostname."""
    import platform

    return platform.node()


class FeatureNotAvailableError(Exception):
    """Raised when accessing a feature not available in current tier."""

    def __init__(self, feature: str):
        self.feature = feature
        required = FEATURE_REQUIREMENTS.get(feature, FeatureTier.COMMUNITY)
        super().__init__(
            f"Feature '{feature}' requires {required.title()} tier. "
            f"Run 'cortex upgrade' to unlock."
        )
