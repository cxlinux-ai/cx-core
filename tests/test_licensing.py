"""Tests for cortex/licensing.py - License management and feature gating."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from cortex.licensing import (
    FeatureTier,
    LicenseInfo,
    FEATURE_REQUIREMENTS,
    FEATURE_NAMES,
    get_license_info,
    get_license_tier,
    check_feature,
    require_feature,
    activate_license,
    show_license_status,
    show_upgrade_prompt,
    FeatureNotAvailableError,
    LICENSE_FILE,
    _get_hostname,
)


class TestFeatureTier:
    """Tests for FeatureTier class."""

    def test_tier_constants(self):
        """Verify tier constant values."""
        assert FeatureTier.COMMUNITY == "community"
        assert FeatureTier.PRO == "pro"
        assert FeatureTier.ENTERPRISE == "enterprise"

    def test_level_community(self):
        """Community tier should be level 0."""
        assert FeatureTier.level(FeatureTier.COMMUNITY) == 0

    def test_level_pro(self):
        """Pro tier should be level 1."""
        assert FeatureTier.level(FeatureTier.PRO) == 1

    def test_level_enterprise(self):
        """Enterprise tier should be level 2."""
        assert FeatureTier.level(FeatureTier.ENTERPRISE) == 2

    def test_level_unknown_returns_zero(self):
        """Unknown tier should return level 0."""
        assert FeatureTier.level("unknown") == 0
        assert FeatureTier.level("") == 0

    def test_tier_ordering(self):
        """Verify tier ordering: community < pro < enterprise."""
        assert FeatureTier.level(FeatureTier.COMMUNITY) < FeatureTier.level(FeatureTier.PRO)
        assert FeatureTier.level(FeatureTier.PRO) < FeatureTier.level(FeatureTier.ENTERPRISE)


class TestLicenseInfo:
    """Tests for LicenseInfo class."""

    def test_default_values(self):
        """Default license should be community tier."""
        info = LicenseInfo()
        assert info.tier == FeatureTier.COMMUNITY
        assert info.valid is True
        assert info.expires is None
        assert info.organization is None
        assert info.email is None

    def test_custom_values(self):
        """LicenseInfo should accept custom values."""
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        info = LicenseInfo(
            tier=FeatureTier.PRO,
            valid=True,
            expires=expires,
            organization="Acme Corp",
            email="admin@acme.com",
        )
        assert info.tier == FeatureTier.PRO
        assert info.organization == "Acme Corp"
        assert info.email == "admin@acme.com"

    def test_is_expired_no_expiry(self):
        """License without expiry should not be expired."""
        info = LicenseInfo(expires=None)
        assert info.is_expired is False

    def test_is_expired_future(self):
        """License expiring in future should not be expired."""
        info = LicenseInfo(expires=datetime.now(timezone.utc) + timedelta(days=30))
        assert info.is_expired is False

    def test_is_expired_past(self):
        """License expiring in past should be expired."""
        info = LicenseInfo(expires=datetime.now(timezone.utc) - timedelta(days=1))
        assert info.is_expired is True

    def test_days_remaining_no_expiry(self):
        """License without expiry should return -1 days."""
        info = LicenseInfo(expires=None)
        assert info.days_remaining == -1

    def test_days_remaining_future(self):
        """Days remaining should be positive for future expiry."""
        info = LicenseInfo(expires=datetime.now(timezone.utc) + timedelta(days=30))
        assert info.days_remaining >= 29  # Allow for timing

    def test_days_remaining_past(self):
        """Days remaining should be 0 for expired license."""
        info = LicenseInfo(expires=datetime.now(timezone.utc) - timedelta(days=5))
        assert info.days_remaining == 0


class TestFeatureRequirements:
    """Tests for feature requirement mappings."""

    def test_pro_features_exist(self):
        """Pro features should be mapped correctly."""
        pro_features = ["cloud_llm", "web_console", "kubernetes", "parallel_ops"]
        for feature in pro_features:
            assert feature in FEATURE_REQUIREMENTS
            assert FEATURE_REQUIREMENTS[feature] == FeatureTier.PRO

    def test_enterprise_features_exist(self):
        """Enterprise features should be mapped correctly."""
        enterprise_features = ["sso", "ldap", "audit_logs", "compliance"]
        for feature in enterprise_features:
            assert feature in FEATURE_REQUIREMENTS
            assert FEATURE_REQUIREMENTS[feature] == FeatureTier.ENTERPRISE

    def test_feature_names_exist(self):
        """All features should have display names."""
        for feature in FEATURE_REQUIREMENTS:
            assert feature in FEATURE_NAMES


class TestGetLicenseInfo:
    """Tests for get_license_info function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset license cache before each test."""
        import cortex.licensing as lic
        lic._cached_license = None
        yield
        lic._cached_license = None

    def test_returns_license_info(self):
        """Should return LicenseInfo object."""
        with patch.object(Path, 'exists', return_value=False):
            info = get_license_info()
            assert isinstance(info, LicenseInfo)

    def test_default_community_tier(self):
        """Should default to community tier when no license file."""
        with patch.object(Path, 'exists', return_value=False):
            info = get_license_info()
            assert info.tier == FeatureTier.COMMUNITY

    def test_reads_license_file(self, tmp_path):
        """Should read license from file."""
        import cortex.licensing as lic

        license_data = {
            "tier": "pro",
            "valid": True,
            "expires": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "organization": "Test Org",
            "email": "test@test.com",
        }

        license_file = tmp_path / "license.key"
        license_file.write_text(json.dumps(license_data))

        with patch.object(lic, 'LICENSE_FILE', license_file):
            info = get_license_info()
            assert info.tier == "pro"
            assert info.organization == "Test Org"

    def test_caches_result(self):
        """Should cache license info."""
        with patch.object(Path, 'exists', return_value=False):
            info1 = get_license_info()
            info2 = get_license_info()
            assert info1 is info2


class TestCheckFeature:
    """Tests for check_feature function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset license cache before each test."""
        import cortex.licensing as lic
        lic._cached_license = None
        yield
        lic._cached_license = None

    def test_community_features_allowed(self):
        """Community tier should access community features."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.COMMUNITY)

        # Unknown features default to community
        assert check_feature("unknown_feature", silent=True) is True

    def test_pro_feature_blocked_for_community(self):
        """Community tier should not access pro features."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.COMMUNITY)

        assert check_feature("cloud_llm", silent=True) is False

    def test_pro_feature_allowed_for_pro(self):
        """Pro tier should access pro features."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.PRO)

        assert check_feature("cloud_llm", silent=True) is True

    def test_enterprise_feature_allowed_for_enterprise(self):
        """Enterprise tier should access all features."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.ENTERPRISE)

        assert check_feature("sso", silent=True) is True
        assert check_feature("cloud_llm", silent=True) is True

    def test_shows_upgrade_prompt(self, capsys):
        """Should show upgrade prompt when feature blocked."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.COMMUNITY)

        check_feature("cloud_llm", silent=False)
        captured = capsys.readouterr()
        assert "UPGRADE" in captured.out


class TestRequireFeatureDecorator:
    """Tests for require_feature decorator."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset license cache before each test."""
        import cortex.licensing as lic
        lic._cached_license = None
        yield
        lic._cached_license = None

    def test_allows_when_feature_available(self):
        """Should allow function call when feature available."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.PRO)

        @require_feature("cloud_llm")
        def test_func():
            return "success"

        assert test_func() == "success"

    def test_raises_when_feature_blocked(self):
        """Should raise FeatureNotAvailableError when feature blocked."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.COMMUNITY)

        @require_feature("cloud_llm")
        def test_func():
            return "success"

        with pytest.raises(FeatureNotAvailableError) as exc_info:
            test_func()

        assert "cloud_llm" in str(exc_info.value)


class TestFeatureNotAvailableError:
    """Tests for FeatureNotAvailableError exception."""

    def test_error_message_contains_feature(self):
        """Error message should contain feature name."""
        error = FeatureNotAvailableError("cloud_llm")
        assert "cloud_llm" in str(error)
        assert error.feature == "cloud_llm"

    def test_error_suggests_upgrade(self):
        """Error message should suggest upgrade."""
        error = FeatureNotAvailableError("sso")
        assert "upgrade" in str(error).lower()


class TestActivateLicense:
    """Tests for activate_license function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset license cache before each test."""
        import cortex.licensing as lic
        lic._cached_license = None
        yield
        lic._cached_license = None

    def test_successful_activation(self, tmp_path):
        """Should save license on successful activation."""
        import cortex.licensing as lic

        license_file = tmp_path / "license.key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "tier": "pro",
            "organization": "Test Org",
        }

        with patch.object(lic, 'LICENSE_FILE', license_file):
            with patch('httpx.post', return_value=mock_response):
                result = activate_license("test-key-123")

        assert result is True
        assert license_file.exists()

    def test_failed_activation(self):
        """Should return False on failed activation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error": "Invalid key",
        }

        with patch('httpx.post', return_value=mock_response):
            result = activate_license("invalid-key")

        assert result is False

    def test_network_error(self):
        """Should handle network errors gracefully."""
        import httpx

        with patch('httpx.post', side_effect=httpx.HTTPError("Network error")):
            result = activate_license("test-key")

        assert result is False


class TestShowLicenseStatus:
    """Tests for show_license_status function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset license cache before each test."""
        import cortex.licensing as lic
        lic._cached_license = None
        yield
        lic._cached_license = None

    def test_shows_community_status(self, capsys):
        """Should show community tier status."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(tier=FeatureTier.COMMUNITY)

        show_license_status()
        captured = capsys.readouterr()

        assert "COMMUNITY" in captured.out
        assert "ACTIVE" in captured.out

    def test_shows_pro_status(self, capsys):
        """Should show pro tier status."""
        import cortex.licensing as lic
        lic._cached_license = LicenseInfo(
            tier=FeatureTier.PRO,
            organization="Test Corp",
            expires=datetime.now(timezone.utc) + timedelta(days=30),
        )

        show_license_status()
        captured = capsys.readouterr()

        assert "PRO" in captured.out


class TestGetHostname:
    """Tests for _get_hostname helper."""

    def test_returns_string(self):
        """Should return hostname as string."""
        hostname = _get_hostname()
        assert isinstance(hostname, str)
        assert len(hostname) > 0


class TestShowUpgradePrompt:
    """Tests for show_upgrade_prompt function."""

    def test_shows_feature_name(self, capsys):
        """Should show feature name in prompt."""
        show_upgrade_prompt("cloud_llm", FeatureTier.PRO)
        captured = capsys.readouterr()

        assert "Cloud LLM" in captured.out or "cloud_llm" in captured.out

    def test_shows_pricing(self, capsys):
        """Should show pricing information."""
        show_upgrade_prompt("cloud_llm", FeatureTier.PRO)
        captured = capsys.readouterr()

        assert "$20" in captured.out

    def test_shows_enterprise_pricing(self, capsys):
        """Should show enterprise pricing for enterprise features."""
        show_upgrade_prompt("sso", FeatureTier.ENTERPRISE)
        captured = capsys.readouterr()

        assert "$99" in captured.out
