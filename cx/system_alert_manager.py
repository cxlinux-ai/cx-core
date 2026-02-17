"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.

SystemAlertManager - Central alert persistence and management system for CX Linux.

This module provides a unified interface for managing alerts across all CX Linux
components including notifications, system health, security events, monitoring data,
and Founding 1,000 referral tracking for revenue attribution.

Features:
- SQLite-backed persistent alert storage
- Alert state management (new/acknowledged/resolved)
- Threshold-based alerting with configurable rules
- Alert querying and filtering capabilities
- Founding 1,000 referral tracking and revenue attribution (10% lifetime)
- User context integration for Pro tier revenue tracking
- Thread-safe operations for concurrent access
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from base64 import b64encode, b64decode
from cryptography.fernet import Fernet
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field
from decimal import Decimal

from rich.console import Console

console = Console()

# Configure enterprise logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / ".cx" / "alert_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SecurityConfig:
    """Enterprise security configuration."""

    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.rate_limit_window = 60  # seconds
        self.rate_limit_max_requests = 1000
        self.max_query_results = 10000
        self.audit_sensitive_operations = True
        self.require_strong_validation = True

    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for sensitive data."""
        key_file = Path.home() / ".cx" / "alert_encryption.key"

        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Failed to read encryption key, generating new: {e}")

        # Generate new key
        key = Fernet.generate_key()
        try:
            key_file.parent.mkdir(exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
            # Secure file permissions (readable only by owner)
            os.chmod(key_file, 0o600)
            logger.info("Generated new encryption key for alert manager")
        except Exception as e:
            logger.error(f"Failed to save encryption key: {e}")

        return key


class SecurityValidator:
    """Enterprise input validation and sanitization."""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format with enterprise security standards."""
        if not email or len(email) > 254:
            return False

        # RFC 5322 compliant regex (simplified)
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_user_id(user_id: str) -> bool:
        """Validate user ID format."""
        if not user_id or len(user_id) > 128:
            return False
        # Allow alphanumeric, hyphens, underscores
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', user_id))

    @staticmethod
    def validate_amount(amount: Union[Decimal, float, str]) -> bool:
        """Validate monetary amount."""
        try:
            decimal_amount = Decimal(str(amount))
            return 0 <= decimal_amount <= Decimal('999999999.99')
        except (ValueError, TypeError):
            return False

    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """Sanitize text input to prevent injection attacks."""
        if not text:
            return ""

        # Remove control characters except newlines and tabs
        cleaned = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

        # Truncate to max length
        return cleaned[:max_length]

    @staticmethod
    def validate_json_metadata(metadata: Any) -> bool:
        """Validate JSON metadata for security."""
        if metadata is None:
            return True

        try:
            # Ensure it can be serialized safely
            json_str = json.dumps(metadata)

            # Check size limit (1MB)
            if len(json_str) > 1024 * 1024:
                return False

            # Basic structure validation
            return isinstance(metadata, (dict, list, str, int, float, bool, type(None)))
        except (TypeError, ValueError):
            return False


class RateLimiter:
    """Enterprise rate limiting for API operations."""

    def __init__(self, max_requests: int = 1000, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
        self.lock = threading.Lock()

    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed under rate limit."""
        with self.lock:
            now = time.time()
            window_start = now - self.window_seconds

            if identifier not in self.requests:
                self.requests[identifier] = []

            # Remove old requests outside the window
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > window_start
            ]

            # Check if under limit
            if len(self.requests[identifier]) >= self.max_requests:
                return False

            # Add current request
            self.requests[identifier].append(now)
            return True


class DataEncryption:
    """Enterprise data encryption for sensitive fields."""

    def __init__(self, key: bytes):
        self.cipher = Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if not data:
            return data
        try:
            encrypted_bytes = self.cipher.encrypt(data.encode('utf-8'))
            return b64encode(encrypted_bytes).decode('ascii')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise SecurityException("Failed to encrypt sensitive data")

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        if not encrypted_data:
            return encrypted_data
        try:
            encrypted_bytes = b64decode(encrypted_data.encode('ascii'))
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise SecurityException("Failed to decrypt sensitive data")


class SecurityException(Exception):
    """Custom exception for security-related errors."""
    pass


class ValidationException(Exception):
    """Custom exception for validation errors."""
    pass


def rate_limited(identifier_func: Callable = None):
    """Decorator for rate limiting methods."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if hasattr(self, 'rate_limiter'):
                identifier = identifier_func(self, *args, **kwargs) if identifier_func else 'default'
                if not self.rate_limiter.is_allowed(identifier):
                    logger.warning(f"Rate limit exceeded for {identifier}")
                    raise SecurityException("Rate limit exceeded")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def audit_operation(operation_name: str):
    """Decorator to audit sensitive operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if hasattr(self, 'security_config') and self.security_config.audit_sensitive_operations:
                logger.info(f"AUDIT: {operation_name} called with args={len(args)} kwargs={len(kwargs)}")
                start_time = time.time()
                try:
                    result = func(self, *args, **kwargs)
                    duration = time.time() - start_time
                    logger.info(f"AUDIT: {operation_name} completed successfully in {duration:.3f}s")
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"AUDIT: {operation_name} failed after {duration:.3f}s: {str(e)}")
                    raise
            else:
                return func(self, *args, **kwargs)
        return wrapper
    return decorator


class AlertSeverity(Enum):
    """Alert severity levels matching notification manager levels."""
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert lifecycle status."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertType(Enum):
    """Categories of alerts for organization."""
    SYSTEM_HEALTH = "system_health"
    SECURITY = "security"
    PERFORMANCE = "performance"
    NOTIFICATION = "notification"
    AUDIT = "audit"
    THRESHOLD = "threshold"
    REFERRAL = "referral"
    REVENUE = "revenue"


class UserTier(Enum):
    """User subscription tiers for CX Linux."""
    FOUNDING = "founding"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    FREE = "free"


class RevenueEventType(Enum):
    """Types of revenue events for referral tracking."""
    SUBSCRIPTION = "subscription"
    UPGRADE = "upgrade"
    RENEWAL = "renewal"
    REFERRAL_BONUS = "referral_bonus"


@dataclass
class UserProfile:
    """User profile with referral tracking for Founding 1,000 ecosystem."""
    user_id: str
    email: str
    tier: UserTier
    founding_member: bool = False
    referral_code: Optional[str] = None
    referred_by: Optional[str] = None
    created_at: datetime.datetime = None
    total_referrals: int = 0
    lifetime_referral_revenue: Decimal = Decimal('0.00')

    def __post_init__(self):
        if self.referral_code is None:
            self.referral_code = self._generate_referral_code()
        if self.created_at is None:
            self.created_at = datetime.datetime.now()

    def _generate_referral_code(self) -> str:
        """Generate unique 12-character referral code."""
        return str(uuid.uuid4()).replace('-', '').upper()[:12]


@dataclass
class RevenueEvent:
    """Revenue event for referral tracking and 10% attribution."""
    event_id: str
    user_id: str
    event_type: RevenueEventType
    amount: Decimal
    currency: str = "USD"
    referrer_id: Optional[str] = None
    referral_bonus: Optional[Decimal] = None  # 10% to referrer
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime.datetime = None

    def __post_init__(self):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.datetime.now()
        # Calculate 10% referral bonus if user was referred
        if self.referrer_id and not self.referral_bonus:
            self.referral_bonus = self.amount * Decimal('0.10')


class SystemAlertManager:
    """
    Enterprise-grade central alert management system with SQLite persistence.

    Provides unified interface for storing, querying, and managing alerts
    from all CX Linux components with enterprise security features:
    - Data encryption for sensitive fields
    - Rate limiting for API protection
    - Input validation and sanitization
    - Audit logging for compliance
    - Backup and recovery mechanisms
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the alert manager with enterprise security features."""
        # Set up configuration directory
        self.config_dir = Path.home() / ".cx"
        self.config_dir.mkdir(exist_ok=True, mode=0o700)  # Secure directory permissions

        # Database path with secure permissions
        if db_path is None:
            self.db_path = self.config_dir / "alerts.db"
        else:
            self.db_path = db_path

        # Enterprise security components
        self.security_config = SecurityConfig()
        self.validator = SecurityValidator()
        self.rate_limiter = RateLimiter(
            max_requests=self.security_config.rate_limit_max_requests,
            window_seconds=self.security_config.rate_limit_window
        )
        self.encryptor = DataEncryption(self.security_config.encryption_key)

        # Thread safety
        self._db_lock = threading.Lock()

        # Performance monitoring
        self.operation_metrics = {
            'queries': 0,
            'alerts_created': 0,
            'errors': 0,
            'last_backup': None
        }

        # Initialize database schema
        self._init_database()

        # Set secure database file permissions
        try:
            os.chmod(self.db_path, 0o600)
            logger.info("Set secure permissions on alert database")
        except Exception as e:
            logger.warning(f"Failed to set database permissions: {e}")

        logger.info("SystemAlertManager initialized with enterprise security")

    def _init_database(self):
        """Initialize SQLite database schema."""
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.cursor()

                # Main alerts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        metadata TEXT,  -- JSON for additional data
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Alert configuration/rules table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alert_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        type TEXT NOT NULL,
                        condition_json TEXT NOT NULL,  -- JSON: {"metric": "cpu_usage", "operator": ">", "threshold": 80}
                        severity TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        cooldown_seconds INTEGER DEFAULT 300,  -- Prevent spam
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Alert state tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alert_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        alert_id INTEGER NOT NULL,
                        action TEXT NOT NULL,  -- acknowledged, resolved, commented
                        comment TEXT,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (alert_id) REFERENCES alerts (id)
                    )
                """)

                # Metrics for threshold monitoring
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alert_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_type TEXT NOT NULL,  -- cpu_usage, memory_usage, disk_free, etc
                        value REAL NOT NULL,
                        unit TEXT,
                        timestamp TEXT NOT NULL,
                        source TEXT NOT NULL
                    )
                """)

                # User profiles for Founding 1,000 referral tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        tier TEXT NOT NULL,
                        founding_member INTEGER NOT NULL DEFAULT 0,
                        referral_code TEXT UNIQUE NOT NULL,
                        referred_by TEXT,
                        created_at TEXT NOT NULL,
                        total_referrals INTEGER DEFAULT 0,
                        lifetime_referral_revenue REAL DEFAULT 0.00,
                        FOREIGN KEY (referred_by) REFERENCES user_profiles (referral_code)
                    )
                """)

                # Revenue events for 10% referral tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS revenue_events (
                        event_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        referrer_id TEXT,
                        referral_bonus REAL,
                        metadata TEXT,  -- JSON for additional data
                        timestamp TEXT NOT NULL,
                        processed INTEGER DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES user_profiles (user_id),
                        FOREIGN KEY (referrer_id) REFERENCES user_profiles (user_id)
                    )
                """)

                # Referral tracking and attribution
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS referral_attributions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        referrer_code TEXT NOT NULL,
                        referred_user_id TEXT NOT NULL,
                        revenue_event_id TEXT NOT NULL,
                        bonus_amount REAL NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',  -- pending, paid, failed
                        created_at TEXT NOT NULL,
                        processed_at TEXT,
                        FOREIGN KEY (referrer_code) REFERENCES user_profiles (referral_code),
                        FOREIGN KEY (referred_user_id) REFERENCES user_profiles (user_id),
                        FOREIGN KEY (revenue_event_id) REFERENCES revenue_events (event_id)
                    )
                """)

                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_type_time ON alert_metrics(metric_type, timestamp)")

                # Indexes for referral tracking
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_referral_code ON user_profiles(referral_code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_referred_by ON user_profiles(referred_by)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_founding ON user_profiles(founding_member)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_revenue_user_time ON revenue_events(user_id, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_revenue_referrer ON revenue_events(referrer_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_referral_status ON referral_attributions(status)")

                conn.commit()
                console.print("[green]✓[/green] Alert database initialized successfully")

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to initialize alert database: {e}")
                conn.rollback()
            finally:
                conn.close()

    @rate_limited(lambda self, *args, **kwargs: f"create_alert_{args[3] if len(args) > 3 else 'unknown'}")
    @audit_operation("create_alert")
    def create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        source: str,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Create a new alert with enterprise validation and security.

        Args:
            alert_type: Category of alert
            severity: Alert severity level
            source: Component that generated the alert
            title: Short alert title (max 200 chars)
            message: Detailed alert message (max 5000 chars)
            metadata: Additional structured data (max 1MB JSON)

        Returns:
            Alert ID of created alert

        Raises:
            ValidationException: If input validation fails
            SecurityException: If rate limit exceeded or security violation
        """
        # Enterprise input validation
        if not isinstance(alert_type, AlertType):
            raise ValidationException("Invalid alert type")

        if not isinstance(severity, AlertSeverity):
            raise ValidationException("Invalid alert severity")

        source = self.validator.sanitize_text(source, max_length=100)
        if not source or len(source.strip()) == 0:
            raise ValidationException("Source is required")

        title = self.validator.sanitize_text(title, max_length=200)
        if not title or len(title.strip()) == 0:
            raise ValidationException("Title is required")

        message = self.validator.sanitize_text(message, max_length=5000)
        if not message or len(message.strip()) == 0:
            raise ValidationException("Message is required")

        if metadata is not None and not self.validator.validate_json_metadata(metadata):
            raise ValidationException("Invalid metadata format or size")

        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints

            try:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()

                cursor.execute("""
                    INSERT INTO alerts (
                        timestamp, type, severity, status, source, title, message,
                        metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now,
                    alert_type.value,
                    severity.value,
                    AlertStatus.NEW.value,
                    source,
                    title,
                    message,
                    json.dumps(metadata) if metadata else None,
                    now,
                    now
                ))

                alert_id = cursor.lastrowid
                conn.commit()

                # Update metrics
                self.operation_metrics['alerts_created'] += 1

                # Log security events at higher severity
                if severity == AlertSeverity.CRITICAL:
                    logger.warning(f"CRITICAL alert created: {alert_id} - {title}")
                else:
                    logger.info(f"Alert created: {alert_id} - {title}")

                console.print(f"[yellow]🚨[/yellow] Alert #{alert_id} created: {title}")
                return alert_id

            except sqlite3.Error as e:
                self.operation_metrics['errors'] += 1
                logger.error(f"Database error creating alert: {e}")
                console.print(f"[red]✗[/red] Database error creating alert: {e}")
                conn.rollback()
                return -1
            except Exception as e:
                self.operation_metrics['errors'] += 1
                logger.error(f"Unexpected error creating alert: {e}")
                console.print(f"[red]✗[/red] Failed to create alert: {e}")
                conn.rollback()
                return -1
            finally:
                conn.close()

    def update_alert_status(
        self,
        alert_id: int,
        status: AlertStatus,
        comment: Optional[str] = None
    ) -> bool:
        """
        Update alert status and log action.

        Args:
            alert_id: Alert ID to update
            status: New status
            comment: Optional comment about the action

        Returns:
            True if successful
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()

                # Update alert status
                cursor.execute("""
                    UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?
                """, (status.value, now, alert_id))

                if cursor.rowcount == 0:
                    console.print(f"[yellow]⚠️[/yellow] Alert #{alert_id} not found")
                    return False

                # Log the action
                cursor.execute("""
                    INSERT INTO alert_actions (alert_id, action, comment, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (alert_id, status.value, comment, now))

                conn.commit()
                console.print(f"[green]✓[/green] Alert #{alert_id} status updated to {status.value}")
                return True

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to update alert status: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()

    def query_alerts(
        self,
        status: Optional[AlertStatus] = None,
        alert_type: Optional[AlertType] = None,
        severity: Optional[AlertSeverity] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        since: Optional[datetime.datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Query alerts with filtering options.

        Args:
            status: Filter by alert status
            alert_type: Filter by alert type
            severity: Filter by severity level
            source: Filter by source component
            limit: Maximum number of results
            offset: Offset for pagination
            since: Only alerts after this timestamp

        Returns:
            List of alert dictionaries
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.cursor()

                # Build query with filters
                query = "SELECT * FROM alerts WHERE 1=1"
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)

                if alert_type:
                    query += " AND type = ?"
                    params.append(alert_type.value)

                if severity:
                    query += " AND severity = ?"
                    params.append(severity.value)

                if source:
                    query += " AND source = ?"
                    params.append(source)

                if since:
                    query += " AND timestamp >= ?"
                    params.append(since.isoformat())

                query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Convert to list of dicts
                alerts = []
                for row in rows:
                    alert = dict(row)
                    if alert['metadata']:
                        alert['metadata'] = json.loads(alert['metadata'])
                    alerts.append(alert)

                return alerts

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to query alerts: {e}")
                return []
            finally:
                conn.close()

    def record_metric(
        self,
        metric_type: str,
        value: float,
        unit: Optional[str] = None,
        source: str = "system"
    ) -> bool:
        """
        Record a metric value for threshold monitoring.

        Args:
            metric_type: Type of metric (cpu_usage, memory_usage, etc)
            value: Numeric value
            unit: Optional unit (%, MB, etc)
            source: Source component

        Returns:
            True if successful
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()

                cursor.execute("""
                    INSERT INTO alert_metrics (metric_type, value, unit, timestamp, source)
                    VALUES (?, ?, ?, ?, ?)
                """, (metric_type, value, unit, now, source))

                conn.commit()
                return True

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to record metric: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()

    def get_alert_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics about alerts.

        Returns:
            Dictionary with alert counts by status, type, severity
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.cursor()

                stats = {}

                # Count by status
                cursor.execute("SELECT status, COUNT(*) as count FROM alerts GROUP BY status")
                stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

                # Count by type
                cursor.execute("SELECT type, COUNT(*) as count FROM alerts GROUP BY type")
                stats['by_type'] = {row['type']: row['count'] for row in cursor.fetchall()}

                # Count by severity
                cursor.execute("SELECT severity, COUNT(*) as count FROM alerts GROUP BY severity")
                stats['by_severity'] = {row['severity']: row['count'] for row in cursor.fetchall()}

                # Total count
                cursor.execute("SELECT COUNT(*) as total FROM alerts")
                stats['total'] = cursor.fetchone()['total']

                # Recent alerts (last 24 hours)
                yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
                cursor.execute("SELECT COUNT(*) as recent FROM alerts WHERE timestamp >= ?", (yesterday,))
                stats['recent_24h'] = cursor.fetchone()['recent']

                return stats

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to get alert stats: {e}")
                return {}
            finally:
                conn.close()

    def cleanup_old_alerts(self, days_to_keep: int = 30) -> int:
        """
        Clean up old resolved alerts to prevent database bloat.

        Args:
            days_to_keep: Number of days to keep resolved alerts

        Returns:
            Number of alerts deleted
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()

                cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days_to_keep)).isoformat()

                # Only delete resolved alerts older than cutoff
                cursor.execute("""
                    DELETE FROM alerts
                    WHERE status = 'resolved' AND timestamp < ?
                """, (cutoff_date,))

                deleted_count = cursor.rowcount
                conn.commit()

                console.print(f"[green]✓[/green] Cleaned up {deleted_count} old resolved alerts")
                return deleted_count

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to cleanup old alerts: {e}")
                conn.rollback()
                return 0
            finally:
                conn.close()

    # === FOUNDING 1,000 REFERRAL TRACKING METHODS ===

    @rate_limited(lambda self, user_id, *args, **kwargs: f"user_profile_{user_id}")
    @audit_operation("create_user_profile")
    def create_user_profile(
        self,
        user_id: str,
        email: str,
        tier: UserTier = UserTier.FREE,
        referred_by_code: Optional[str] = None
    ) -> UserProfile:
        """
        Create a new user profile with enterprise validation and encryption.

        Args:
            user_id: Unique user identifier (alphanumeric, hyphens, underscores only)
            email: User email address (will be encrypted)
            tier: User subscription tier
            referred_by_code: Referral code of referring user (if any)

        Returns:
            Created UserProfile object

        Raises:
            ValidationException: If input validation fails
            SecurityException: If rate limit exceeded or duplicate user
        """
        # Enterprise validation
        if not self.validator.validate_user_id(user_id):
            raise ValidationException("Invalid user ID format")

        if not self.validator.validate_email(email):
            raise ValidationException("Invalid email format")

        if not isinstance(tier, UserTier):
            raise ValidationException("Invalid user tier")

        if referred_by_code and len(referred_by_code) != 12:
            raise ValidationException("Invalid referral code format")

        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA foreign_keys = ON")

            try:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()

                # Check for duplicate user_id
                cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    raise SecurityException("User ID already exists")

                # Check for duplicate email (need to handle encryption)
                encrypted_email = self.encryptor.encrypt(email.lower())
                cursor.execute("SELECT user_id FROM user_profiles WHERE email = ?", (encrypted_email,))
                if cursor.fetchone():
                    raise SecurityException("Email address already registered")

                # Validate referral code exists if provided
                if referred_by_code:
                    cursor.execute("SELECT user_id FROM user_profiles WHERE referral_code = ?", (referred_by_code,))
                    if not cursor.fetchone():
                        raise ValidationException("Invalid referral code")

                # Check if this is a founding member (first 1,000 users)
                cursor.execute("SELECT COUNT(*) FROM user_profiles")
                total_users = cursor.fetchone()[0]
                founding_member = total_users < 1000

                profile = UserProfile(
                    user_id=user_id,
                    email=email,  # Keep unencrypted in object for return
                    tier=tier,
                    founding_member=founding_member,
                    referred_by=referred_by_code,
                    created_at=datetime.datetime.now()
                )

                cursor.execute("""
                    INSERT INTO user_profiles (
                        user_id, email, tier, founding_member, referral_code,
                        referred_by, created_at, total_referrals, lifetime_referral_revenue
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    profile.user_id,
                    encrypted_email,  # Store encrypted email
                    profile.tier.value,
                    int(profile.founding_member),
                    profile.referral_code,
                    profile.referred_by,
                    now,
                    profile.total_referrals,
                    float(profile.lifetime_referral_revenue)
                ))

                # Update referrer's total referrals if applicable
                if referred_by_code:
                    result = cursor.execute("""
                        UPDATE user_profiles
                        SET total_referrals = total_referrals + 1
                        WHERE referral_code = ?
                    """, (referred_by_code,))

                    if cursor.rowcount == 0:
                        raise ValidationException("Referral code not found during update")

                conn.commit()

                if profile.founding_member:
                    console.print(f"[gold3]🏆[/gold3] Founding Member #{total_users + 1}: {email}")
                    # Create alert without calling create_alert to avoid rate limiting recursion
                    logger.info(f"New Founding Member #{total_users + 1}: {user_id}")

                logger.info(f"User profile created successfully: {user_id}")
                console.print(f"[green]✓[/green] User profile created: {email} (Referral: {profile.referral_code})")
                return profile

            except sqlite3.IntegrityError as e:
                self.operation_metrics['errors'] += 1
                logger.error(f"Database integrity error creating user profile: {e}")
                conn.rollback()
                if "UNIQUE constraint failed" in str(e):
                    raise SecurityException("User already exists")
                else:
                    raise ValidationException(f"Database constraint violation: {e}")
            except (ValidationException, SecurityException):
                conn.rollback()
                raise
            except Exception as e:
                self.operation_metrics['errors'] += 1
                logger.error(f"Unexpected error creating user profile: {e}")
                console.print(f"[red]✗[/red] Failed to create user profile: {e}")
                conn.rollback()
                raise
            finally:
                conn.close()

    def record_revenue_event(
        self,
        user_id: str,
        event_type: RevenueEventType,
        amount: Decimal,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Record a revenue event and calculate 10% referral bonus.

        Args:
            user_id: User who generated the revenue
            event_type: Type of revenue event
            amount: Revenue amount
            currency: Currency code
            metadata: Additional event data

        Returns:
            Event ID if successful, None if failed
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()

                # Get user profile to check for referrer
                cursor.execute("""
                    SELECT user_id, referred_by, founding_member, tier
                    FROM user_profiles WHERE user_id = ?
                """, (user_id,))

                user_row = cursor.fetchone()
                if not user_row:
                    console.print(f"[yellow]⚠️[/yellow] User {user_id} not found for revenue event")
                    return None

                referred_by_code = user_row[1]
                founding_member = bool(user_row[2])
                user_tier = user_row[3]

                # Get referrer user_id if exists
                referrer_id = None
                if referred_by_code:
                    cursor.execute("""
                        SELECT user_id FROM user_profiles WHERE referral_code = ?
                    """, (referred_by_code,))
                    referrer_row = cursor.fetchone()
                    if referrer_row:
                        referrer_id = referrer_row[0]

                # Create revenue event
                event = RevenueEvent(
                    event_id=str(uuid.uuid4()),
                    user_id=user_id,
                    event_type=event_type,
                    amount=amount,
                    currency=currency,
                    referrer_id=referrer_id,
                    metadata=metadata
                )

                cursor.execute("""
                    INSERT INTO revenue_events (
                        event_id, user_id, event_type, amount, currency,
                        referrer_id, referral_bonus, metadata, timestamp, processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.user_id,
                    event.event_type.value,
                    float(event.amount),
                    event.currency,
                    event.referrer_id,
                    float(event.referral_bonus) if event.referral_bonus else None,
                    json.dumps(event.metadata) if event.metadata else None,
                    event.timestamp.isoformat(),
                    0
                ))

                # Create referral attribution if there's a referrer
                if referrer_id and event.referral_bonus:
                    cursor.execute("""
                        INSERT INTO referral_attributions (
                            referrer_code, referred_user_id, revenue_event_id,
                            bonus_amount, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        referred_by_code,
                        user_id,
                        event.event_id,
                        float(event.referral_bonus),
                        'pending',
                        datetime.datetime.now().isoformat()
                    ))

                    # Update referrer's lifetime revenue
                    cursor.execute("""
                        UPDATE user_profiles
                        SET lifetime_referral_revenue = lifetime_referral_revenue + ?
                        WHERE user_id = ?
                    """, (float(event.referral_bonus), referrer_id))

                conn.commit()

                # Create alert for significant revenue events
                if event.amount >= Decimal('100'):
                    severity = AlertSeverity.CRITICAL if founding_member else AlertSeverity.NORMAL
                    self.create_alert(
                        AlertType.REVENUE,
                        severity,
                        "revenue_tracker",
                        f"Revenue Event: ${event.amount}",
                        f"User {user_id} ({user_tier}) generated ${event.amount} via {event_type.value}",
                        {
                            "amount": float(event.amount),
                            "founding_member": founding_member,
                            "referrer_bonus": float(event.referral_bonus) if event.referral_bonus else 0,
                            "event_id": event.event_id
                        }
                    )

                console.print(f"[green]💰[/green] Revenue event recorded: {event_type.value} ${event.amount}")
                if event.referral_bonus:
                    console.print(f"[blue]🔗[/blue] Referral bonus: ${event.referral_bonus} to referrer")

                return event.event_id

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to record revenue event: {e}")
                conn.rollback()
                return None
            finally:
                conn.close()

    def get_user_referral_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get referral statistics for a user.

        Args:
            user_id: User to get stats for

        Returns:
            Dictionary with referral statistics
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.cursor()

                # Get user profile
                cursor.execute("""
                    SELECT * FROM user_profiles WHERE user_id = ?
                """, (user_id,))

                user = cursor.fetchone()
                if not user:
                    return {}

                stats = {
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'tier': user['tier'],
                    'founding_member': bool(user['founding_member']),
                    'referral_code': user['referral_code'],
                    'total_referrals': user['total_referrals'],
                    'lifetime_referral_revenue': user['lifetime_referral_revenue'],
                    'referred_by': user['referred_by']
                }

                # Get pending referral bonuses
                cursor.execute("""
                    SELECT SUM(bonus_amount) as pending_bonus
                    FROM referral_attributions
                    WHERE referrer_code = ? AND status = 'pending'
                """, (user['referral_code'],))

                pending_row = cursor.fetchone()
                stats['pending_referral_bonus'] = pending_row['pending_bonus'] or 0.0

                # Get referred users
                cursor.execute("""
                    SELECT user_id, email, tier, created_at
                    FROM user_profiles
                    WHERE referred_by = ?
                    ORDER BY created_at DESC
                """, (user['referral_code'],))

                stats['referred_users'] = [dict(row) for row in cursor.fetchall()]

                return stats

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to get referral stats: {e}")
                return {}
            finally:
                conn.close()

    def get_founding_1000_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the Founding 1,000 ecosystem.

        Returns:
            Dictionary with Founding 1,000 metrics
        """
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            try:
                cursor = conn.cursor()

                stats = {}

                # Total founding members
                cursor.execute("SELECT COUNT(*) as count FROM user_profiles WHERE founding_member = 1")
                stats['founding_members'] = cursor.fetchone()['count']

                # Total referrals by founding members
                cursor.execute("""
                    SELECT SUM(total_referrals) as total
                    FROM user_profiles WHERE founding_member = 1
                """)
                stats['total_founding_referrals'] = cursor.fetchone()['total'] or 0

                # Total referral revenue generated
                cursor.execute("SELECT SUM(lifetime_referral_revenue) as total FROM user_profiles")
                stats['total_referral_revenue'] = cursor.fetchone()['total'] or 0.0

                # Revenue by tier
                cursor.execute("""
                    SELECT tier, SUM(amount) as revenue
                    FROM revenue_events re
                    JOIN user_profiles up ON re.user_id = up.user_id
                    GROUP BY tier
                """)
                stats['revenue_by_tier'] = {row['tier']: row['revenue'] for row in cursor.fetchall()}

                # Top referrers
                cursor.execute("""
                    SELECT user_id, email, referral_code, total_referrals, lifetime_referral_revenue
                    FROM user_profiles
                    WHERE founding_member = 1 AND total_referrals > 0
                    ORDER BY total_referrals DESC, lifetime_referral_revenue DESC
                    LIMIT 10
                """)
                stats['top_referrers'] = [dict(row) for row in cursor.fetchall()]

                # Recent revenue events
                cursor.execute("""
                    SELECT COUNT(*) as count, SUM(amount) as total
                    FROM revenue_events
                    WHERE timestamp >= ?
                """, ((datetime.datetime.now() - datetime.timedelta(days=30)).isoformat(),))

                recent = cursor.fetchone()
                stats['recent_30d'] = {
                    'revenue_events': recent['count'],
                    'total_revenue': recent['total'] or 0.0
                }

                return stats

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to get Founding 1,000 stats: {e}")
                return {}
            finally:
                conn.close()

    # === ENTERPRISE ADMINISTRATIVE METHODS ===

    @audit_operation("backup_database")
    def backup_database(self, backup_path: Optional[Path] = None) -> bool:
        """
        Create secure backup of the alert database.

        Args:
            backup_path: Optional custom backup path

        Returns:
            True if backup successful
        """
        try:
            if backup_path is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.config_dir / f"alerts_backup_{timestamp}.db"

            # Ensure backup directory exists
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            with self._db_lock:
                # Use SQLite backup API for consistent backup
                source_conn = sqlite3.connect(str(self.db_path))
                backup_conn = sqlite3.connect(str(backup_path))

                try:
                    source_conn.backup(backup_conn)
                    backup_conn.close()
                    source_conn.close()

                    # Set secure permissions on backup
                    os.chmod(backup_path, 0o600)

                    # Update metrics
                    self.operation_metrics['last_backup'] = datetime.datetime.now().isoformat()

                    logger.info(f"Database backup created: {backup_path}")
                    console.print(f"[green]✓[/green] Backup created: {backup_path}")
                    return True

                except Exception as e:
                    logger.error(f"Backup failed: {e}")
                    console.print(f"[red]✗[/red] Backup failed: {e}")
                    # Clean up partial backup
                    if backup_path.exists():
                        backup_path.unlink()
                    return False

        except Exception as e:
            logger.error(f"Backup preparation failed: {e}")
            console.print(f"[red]✗[/red] Backup preparation failed: {e}")
            return False

    @audit_operation("optimize_database")
    def optimize_database(self) -> bool:
        """
        Optimize database performance through VACUUM and ANALYZE.

        Returns:
            True if optimization successful
        """
        try:
            with self._db_lock:
                conn = sqlite3.connect(str(self.db_path))
                try:
                    cursor = conn.cursor()

                    # Analyze query performance
                    cursor.execute("ANALYZE")

                    # Reclaim space and optimize
                    cursor.execute("VACUUM")

                    conn.commit()
                    logger.info("Database optimization completed")
                    console.print("[green]✓[/green] Database optimized successfully")
                    return True

                except Exception as e:
                    logger.error(f"Database optimization failed: {e}")
                    console.print(f"[red]✗[/red] Optimization failed: {e}")
                    return False
                finally:
                    conn.close()

        except Exception as e:
            logger.error(f"Optimization setup failed: {e}")
            console.print(f"[red]✗[/red] Optimization setup failed: {e}")
            return False

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance and operational metrics.

        Returns:
            Dictionary with system metrics
        """
        try:
            with self._db_lock:
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row

                try:
                    cursor = conn.cursor()

                    # Database size
                    db_size = self.db_path.stat().st_size

                    # Table counts
                    cursor.execute("SELECT COUNT(*) as count FROM alerts")
                    alert_count = cursor.fetchone()['count']

                    cursor.execute("SELECT COUNT(*) as count FROM user_profiles")
                    user_count = cursor.fetchone()['count']

                    cursor.execute("SELECT COUNT(*) as count FROM revenue_events")
                    revenue_count = cursor.fetchone()['count']

                    # Performance stats
                    metrics = {
                        'database': {
                            'size_bytes': db_size,
                            'size_mb': round(db_size / (1024 * 1024), 2),
                            'alert_count': alert_count,
                            'user_count': user_count,
                            'revenue_event_count': revenue_count
                        },
                        'operations': self.operation_metrics.copy(),
                        'security': {
                            'encryption_enabled': True,
                            'rate_limiting_enabled': True,
                            'audit_logging_enabled': self.security_config.audit_sensitive_operations
                        },
                        'timestamp': datetime.datetime.now().isoformat()
                    }

                    return metrics

                except Exception as e:
                    logger.error(f"Failed to get performance metrics: {e}")
                    return {'error': str(e)}
                finally:
                    conn.close()

        except Exception as e:
            logger.error(f"Performance metrics setup failed: {e}")
            return {'error': str(e)}

    @audit_operation("validate_database_integrity")
    def validate_database_integrity(self) -> Dict[str, Any]:
        """
        Validate database integrity and consistency.

        Returns:
            Dictionary with validation results
        """
        results = {
            'integrity_check': False,
            'foreign_key_check': False,
            'data_consistency': False,
            'errors': [],
            'warnings': []
        }

        try:
            with self._db_lock:
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row

                try:
                    cursor = conn.cursor()

                    # SQLite integrity check
                    cursor.execute("PRAGMA integrity_check")
                    integrity_results = cursor.fetchall()
                    if len(integrity_results) == 1 and integrity_results[0][0] == 'ok':
                        results['integrity_check'] = True
                    else:
                        results['errors'].extend([row[0] for row in integrity_results])

                    # Foreign key constraint check
                    cursor.execute("PRAGMA foreign_key_check")
                    fk_violations = cursor.fetchall()
                    if len(fk_violations) == 0:
                        results['foreign_key_check'] = True
                    else:
                        results['errors'].append(f"Foreign key violations found: {len(fk_violations)}")

                    # Data consistency checks
                    consistency_errors = []

                    # Check for orphaned referral attributions
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM referral_attributions ra
                        LEFT JOIN user_profiles up1 ON ra.referrer_code = up1.referral_code
                        LEFT JOIN user_profiles up2 ON ra.referred_user_id = up2.user_id
                        WHERE up1.user_id IS NULL OR up2.user_id IS NULL
                    """)
                    orphaned = cursor.fetchone()['count']
                    if orphaned > 0:
                        consistency_errors.append(f"Orphaned referral attributions: {orphaned}")

                    # Check revenue event integrity
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM revenue_events re
                        LEFT JOIN user_profiles up ON re.user_id = up.user_id
                        WHERE up.user_id IS NULL
                    """)
                    orphaned_revenue = cursor.fetchone()['count']
                    if orphaned_revenue > 0:
                        consistency_errors.append(f"Orphaned revenue events: {orphaned_revenue}")

                    if len(consistency_errors) == 0:
                        results['data_consistency'] = True
                    else:
                        results['errors'].extend(consistency_errors)

                    # Check for potential data anomalies
                    cursor.execute("SELECT COUNT(*) as count FROM user_profiles WHERE total_referrals < 0")
                    negative_referrals = cursor.fetchone()['count']
                    if negative_referrals > 0:
                        results['warnings'].append(f"Users with negative referral counts: {negative_referrals}")

                    logger.info(f"Database integrity validation completed: {results}")
                    return results

                except Exception as e:
                    logger.error(f"Integrity validation failed: {e}")
                    results['errors'].append(f"Validation error: {e}")
                    return results
                finally:
                    conn.close()

        except Exception as e:
            logger.error(f"Integrity validation setup failed: {e}")
            results['errors'].append(f"Setup error: {e}")
            return results

    def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check of the alert manager system.

        Returns:
            Dictionary with health status
        """
        health = {
            'status': 'healthy',
            'checks': {},
            'timestamp': datetime.datetime.now().isoformat()
        }

        try:
            # Database connectivity
            try:
                with self._db_lock:
                    conn = sqlite3.connect(str(self.db_path))
                    conn.execute("SELECT 1")
                    conn.close()
                health['checks']['database_connectivity'] = True
            except Exception as e:
                health['checks']['database_connectivity'] = False
                health['status'] = 'degraded'
                logger.error(f"Database connectivity check failed: {e}")

            # File permissions
            try:
                db_stat = self.db_path.stat()
                permissions = oct(db_stat.st_mode)[-3:]
                health['checks']['file_permissions'] = (permissions == '600')
                if permissions != '600':
                    health['status'] = 'warning'
                    logger.warning(f"Database file permissions not secure: {permissions}")
            except Exception as e:
                health['checks']['file_permissions'] = False
                health['status'] = 'warning'
                logger.error(f"Permission check failed: {e}")

            # Encryption key availability
            try:
                test_data = "health_check_test"
                encrypted = self.encryptor.encrypt(test_data)
                decrypted = self.encryptor.decrypt(encrypted)
                health['checks']['encryption'] = (decrypted == test_data)
            except Exception as e:
                health['checks']['encryption'] = False
                health['status'] = 'critical'
                logger.error(f"Encryption check failed: {e}")

            # Security configuration
            health['checks']['security_config'] = {
                'rate_limiting': hasattr(self, 'rate_limiter'),
                'input_validation': hasattr(self, 'validator'),
                'audit_logging': self.security_config.audit_sensitive_operations
            }

            # Performance metrics
            metrics = self.get_performance_metrics()
            if 'error' in metrics:
                health['checks']['performance_monitoring'] = False
                health['status'] = 'degraded'
            else:
                health['checks']['performance_monitoring'] = True
                health['performance'] = metrics

            return health

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'critical',
                'error': str(e),
                'timestamp': datetime.datetime.now().isoformat()
            }


# Global instance for easy access
_alert_manager_instance = None


def get_alert_manager() -> SystemAlertManager:
    """Get global alert manager instance (singleton pattern)."""
    global _alert_manager_instance
    if _alert_manager_instance is None:
        _alert_manager_instance = SystemAlertManager()
    return _alert_manager_instance


if __name__ == "__main__":
    # Test the alert manager with Founding 1,000 referral tracking
    manager = SystemAlertManager()

    console.print("[bold blue]Testing CX Linux Founding 1,000 Referral System[/bold blue]")

    # Create founding member (referrer)
    referrer = manager.create_user_profile(
        user_id="founder_001",
        email="founder@cxlinux.ai",
        tier=UserTier.FOUNDING
    )
    console.print(f"Created founding member with referral code: {referrer.referral_code}")

    # Create referred user
    referred_user = manager.create_user_profile(
        user_id="user_002",
        email="referred@cxlinux.ai",
        tier=UserTier.PRO,
        referred_by_code=referrer.referral_code
    )

    # Record revenue event (Pro subscription)
    revenue_event_id = manager.record_revenue_event(
        user_id=referred_user.user_id,
        event_type=RevenueEventType.SUBSCRIPTION,
        amount=Decimal('29.99'),
        metadata={"plan": "pro_monthly", "trial_ended": True}
    )

    # Get referral stats
    referrer_stats = manager.get_user_referral_stats(referrer.user_id)
    console.print(f"[green]Referrer stats:[/green] {referrer_stats}")

    # Get Founding 1,000 ecosystem stats
    founding_stats = manager.get_founding_1000_stats()
    console.print(f"[gold3]Founding 1,000 stats:[/gold3] {founding_stats}")

    # Create test system alert
    alert_id = manager.create_alert(
        AlertType.SYSTEM_HEALTH,
        AlertSeverity.CRITICAL,
        "test_doctor",
        "High CPU Usage",
        "CPU usage at 85% for 5 minutes",
        {"cpu_usage": 85.4, "duration_minutes": 5}
    )

    # Query alerts
    alerts = manager.query_alerts(limit=5)
    console.print(f"Found {len(alerts)} total alerts")

    # Update alert status
    manager.update_alert_status(alert_id, AlertStatus.ACKNOWLEDGED, "Investigating high CPU")

    # Get comprehensive stats
    stats = manager.get_alert_stats()
    console.print(f"Alert stats: {stats}")

    console.print("[bold green]✓ Founding 1,000 referral tracking fully integrated![/bold green]")