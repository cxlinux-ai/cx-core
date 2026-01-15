"""
Locale-aware formatting for Cortex Linux CLI.

Provides locale-specific formatting for:
- Date and time
- Numbers and currencies
- File sizes
- Durations
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# =============================================================================
# Time Constants
# =============================================================================
# These named constants replace magic numbers for improved readability
# and maintainability. All values are in seconds.

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600  # 60 * 60
SECONDS_PER_DAY = 86400  # 60 * 60 * 24
SECONDS_PER_WEEK = 604800  # 60 * 60 * 24 * 7
SECONDS_PER_MONTH = 2592000  # 60 * 60 * 24 * 30 (approximate)
SECONDS_PER_YEAR = 31536000  # 60 * 60 * 24 * 365 (approximate)

# Language-specific formatting configurations
LOCALE_CONFIGS = {
    "en": {
        "date_format": "%Y-%m-%d",
        "time_format": "%I:%M %p",
        "datetime_format": "%Y-%m-%d %I:%M %p",
        "datetime_full": "%B %d, %Y at %I:%M %p",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "time_ago": {
            "seconds": "{n} seconds ago",
            "second": "1 second ago",
            "minutes": "{n} minutes ago",
            "minute": "1 minute ago",
            "hours": "{n} hours ago",
            "hour": "1 hour ago",
            "days": "{n} days ago",
            "day": "1 day ago",
            "weeks": "{n} weeks ago",
            "week": "1 week ago",
            "months": "{n} months ago",
            "month": "1 month ago",
            "years": "{n} years ago",
            "year": "1 year ago",
            "just_now": "just now",
        },
        "file_size_units": ["B", "KB", "MB", "GB", "TB"],
    },
    "es": {
        "date_format": "%d/%m/%Y",
        "time_format": "%H:%M",
        "datetime_format": "%d/%m/%Y %H:%M",
        "datetime_full": "%d de %B de %Y a las %H:%M",
        "decimal_separator": ",",
        "thousands_separator": ".",
        "time_ago": {
            "seconds": "hace {n} segundos",
            "second": "hace 1 segundo",
            "minutes": "hace {n} minutos",
            "minute": "hace 1 minuto",
            "hours": "hace {n} horas",
            "hour": "hace 1 hora",
            "days": "hace {n} días",
            "day": "hace 1 día",
            "weeks": "hace {n} semanas",
            "week": "hace 1 semana",
            "months": "hace {n} meses",
            "month": "hace 1 mes",
            "years": "hace {n} años",
            "year": "hace 1 año",
            "just_now": "ahora mismo",
        },
        "file_size_units": ["B", "KB", "MB", "GB", "TB"],
    },
    "fr": {
        "date_format": "%d/%m/%Y",
        "time_format": "%H:%M",
        "datetime_format": "%d/%m/%Y %H:%M",
        "datetime_full": "%d %B %Y à %H:%M",
        "decimal_separator": ",",
        "thousands_separator": " ",
        "time_ago": {
            "seconds": "il y a {n} secondes",
            "second": "il y a 1 seconde",
            "minutes": "il y a {n} minutes",
            "minute": "il y a 1 minute",
            "hours": "il y a {n} heures",
            "hour": "il y a 1 heure",
            "days": "il y a {n} jours",
            "day": "il y a 1 jour",
            "weeks": "il y a {n} semaines",
            "week": "il y a 1 semaine",
            "months": "il y a {n} mois",
            "month": "il y a 1 mois",
            "years": "il y a {n} ans",
            "year": "il y a 1 an",
            "just_now": "à l'instant",
        },
        "file_size_units": ["o", "Ko", "Mo", "Go", "To"],
    },
    "de": {
        "date_format": "%d.%m.%Y",
        "time_format": "%H:%M",
        "datetime_format": "%d.%m.%Y %H:%M",
        "datetime_full": "%d. %B %Y um %H:%M",
        "decimal_separator": ",",
        "thousands_separator": ".",
        "time_ago": {
            "seconds": "vor {n} Sekunden",
            "second": "vor 1 Sekunde",
            "minutes": "vor {n} Minuten",
            "minute": "vor 1 Minute",
            "hours": "vor {n} Stunden",
            "hour": "vor 1 Stunde",
            "days": "vor {n} Tagen",
            "day": "vor 1 Tag",
            "weeks": "vor {n} Wochen",
            "week": "vor 1 Woche",
            "months": "vor {n} Monaten",
            "month": "vor 1 Monat",
            "years": "vor {n} Jahren",
            "year": "vor 1 Jahr",
            "just_now": "gerade eben",
        },
        "file_size_units": ["B", "KB", "MB", "GB", "TB"],
    },
    "zh": {
        "date_format": "%Y年%m月%d日",
        "time_format": "%H:%M",
        "datetime_format": "%Y年%m月%d日 %H:%M",
        "datetime_full": "%Y年%m月%d日 %H:%M",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "time_ago": {
            "seconds": "{n}秒前",
            "second": "1秒前",
            "minutes": "{n}分钟前",
            "minute": "1分钟前",
            "hours": "{n}小时前",
            "hour": "1小时前",
            "days": "{n}天前",
            "day": "1天前",
            "weeks": "{n}周前",
            "week": "1周前",
            "months": "{n}个月前",
            "month": "1个月前",
            "years": "{n}年前",
            "year": "1年前",
            "just_now": "刚刚",
        },
        "file_size_units": ["B", "KB", "MB", "GB", "TB"],
    },
}


class LocaleFormatter:
    """
    Provides locale-aware formatting for various data types.

    Automatically uses the current language setting from the i18n module.
    """

    def __init__(self, language: str = "en"):
        """
        Initialize the formatter with a language.

        Args:
            language: Language code (defaults to English)
        """
        self._language = language if language in LOCALE_CONFIGS else "en"

    @property
    def language(self) -> str:
        """Get the current language."""
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        """Set the language."""
        if value in LOCALE_CONFIGS:
            self._language = value
        else:
            self._language = "en"

    def _get_config(self) -> dict[str, Any]:
        """Get the locale configuration for the current language."""
        return LOCALE_CONFIGS.get(self._language, LOCALE_CONFIGS["en"])

    def format_date(self, dt: datetime) -> str:
        """
        Format a date according to locale conventions.

        Args:
            dt: datetime object to format

        Returns:
            Formatted date string
        """
        config = self._get_config()
        return dt.strftime(config["date_format"])

    def format_time(self, dt: datetime) -> str:
        """
        Format a time according to locale conventions.

        Args:
            dt: datetime object to format

        Returns:
            Formatted time string
        """
        config = self._get_config()
        return dt.strftime(config["time_format"])

    def format_datetime(self, dt: datetime, full: bool = False) -> str:
        """
        Format a datetime according to locale conventions.

        Args:
            dt: datetime object to format
            full: Use full format (e.g., "January 15, 2024 at 3:30 PM")

        Returns:
            Formatted datetime string
        """
        config = self._get_config()
        format_key = "datetime_full" if full else "datetime_format"
        return dt.strftime(config[format_key])

    def format_number(self, number: int | float, decimals: int = 0) -> str:
        """
        Format a number according to locale conventions.

        Args:
            number: Number to format
            decimals: Number of decimal places

        Returns:
            Formatted number string
        """
        config = self._get_config()
        decimal_sep = config["decimal_separator"]
        thousands_sep = config["thousands_separator"]

        if decimals > 0:
            formatted = f"{number:,.{decimals}f}"
        else:
            formatted = f"{int(number):,}"

        # Replace separators according to locale
        if decimal_sep != "." or thousands_sep != ",":
            # Use placeholder to avoid replacement conflicts
            formatted = formatted.replace(",", "\x00")
            formatted = formatted.replace(".", decimal_sep)
            formatted = formatted.replace("\x00", thousands_sep)

        return formatted

    def format_file_size(self, size_bytes: int) -> str:
        """
        Format a file size in human-readable form.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted file size (e.g., "1.5 GB")
        """
        config = self._get_config()
        units = config["file_size_units"]

        if size_bytes == 0:
            return f"0 {units[0]}"

        size = float(size_bytes)
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        # Format with appropriate decimals
        if size >= 100:
            formatted_size = self.format_number(size, 0)
        elif size >= 10:
            formatted_size = self.format_number(size, 1)
        else:
            formatted_size = self.format_number(size, 2)

        return f"{formatted_size} {units[unit_index]}"

    def format_time_ago(self, dt: datetime, now: datetime | None = None) -> str:
        """
        Format a datetime as a relative time string.

        Args:
            dt: datetime to format
            now: Current time (defaults to now)

        Returns:
            Relative time string (e.g., "5 minutes ago")
        """
        if now is None:
            now = datetime.now()

        config = self._get_config()
        time_ago = config["time_ago"]

        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 0:
            return time_ago["just_now"]

        if seconds < 5:
            return time_ago["just_now"]
        elif seconds < SECONDS_PER_MINUTE:
            return time_ago["second"] if seconds == 1 else time_ago["seconds"].format(n=seconds)
        elif seconds < SECONDS_PER_HOUR:
            minutes = seconds // SECONDS_PER_MINUTE
            return time_ago["minute"] if minutes == 1 else time_ago["minutes"].format(n=minutes)
        elif seconds < SECONDS_PER_DAY:
            hours = seconds // SECONDS_PER_HOUR
            return time_ago["hour"] if hours == 1 else time_ago["hours"].format(n=hours)
        elif seconds < SECONDS_PER_WEEK:
            days = seconds // SECONDS_PER_DAY
            return time_ago["day"] if days == 1 else time_ago["days"].format(n=days)
        elif seconds < SECONDS_PER_MONTH:
            weeks = seconds // SECONDS_PER_WEEK
            return time_ago["week"] if weeks == 1 else time_ago["weeks"].format(n=weeks)
        elif seconds < SECONDS_PER_YEAR:
            months = seconds // SECONDS_PER_MONTH
            return time_ago["month"] if months == 1 else time_ago["months"].format(n=months)
        else:
            years = seconds // SECONDS_PER_YEAR
            return time_ago["year"] if years == 1 else time_ago["years"].format(n=years)

    def format_duration(self, seconds: float) -> str:
        """
        Format a duration in seconds as a human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration (e.g., "2m 30s")
        """
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        elif seconds < SECONDS_PER_MINUTE:
            return f"{seconds:.1f}s"
        elif seconds < SECONDS_PER_HOUR:
            minutes = int(seconds // SECONDS_PER_MINUTE)
            secs = int(seconds % SECONDS_PER_MINUTE)
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
        else:
            hours = int(seconds // SECONDS_PER_HOUR)
            minutes = int((seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE)
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"


# Global formatter instance
_formatter: LocaleFormatter | None = None


def get_formatter() -> LocaleFormatter:
    """
    Get or create the global formatter instance.

    The formatter is kept in sync with the current application language.
    If the language has changed since the formatter was created, it will
    be updated automatically.

    Returns:
        The global LocaleFormatter instance
    """
    global _formatter
    from cortex.i18n.translator import get_language

    current_language = get_language()

    if _formatter is None:
        # Create new formatter with current language
        _formatter = LocaleFormatter(language=current_language)
    elif _formatter.language != current_language:
        # Language has changed - update the formatter
        _formatter.language = current_language

    return _formatter


def format_date(dt: datetime) -> str:
    """Format a date using the global formatter."""
    return get_formatter().format_date(dt)


def format_time(dt: datetime) -> str:
    """Format a time using the global formatter."""
    return get_formatter().format_time(dt)


def format_datetime(dt: datetime, full: bool = False) -> str:
    """Format a datetime using the global formatter."""
    return get_formatter().format_datetime(dt, full)


def format_number(number: int | float, decimals: int = 0) -> str:
    """Format a number using the global formatter."""
    return get_formatter().format_number(number, decimals)


def format_file_size(size_bytes: int) -> str:
    """Format a file size using the global formatter."""
    return get_formatter().format_file_size(size_bytes)


def format_time_ago(dt: datetime) -> str:
    """Format a relative time using the global formatter."""
    return get_formatter().format_time_ago(dt)


def format_duration(seconds: float) -> str:
    """Format a duration using the global formatter."""
    return get_formatter().format_duration(seconds)
