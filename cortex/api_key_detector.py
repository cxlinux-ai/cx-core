"""
API Key Auto-Detection Module

Automatically detects API keys and provider preferences from common locations
without requiring user to manually set environment variables.

Detection order (highest priority first):
1. CORTEX_PROVIDER=ollama environment variable (for explicit Ollama mode)
2. API key environment variables: ANTHROPIC_API_KEY, OPENAI_API_KEY
3. Cached key location (~/.cortex/.api_key_cache)
4. Saved Ollama provider preference in ~/.cortex/.env (CORTEX_PROVIDER=ollama)
5. API keys in ~/.cortex/.env
6. ~/.config/anthropic/credentials.json (Claude CLI location)
7. ~/.config/openai/credentials.json
8. .env in current directory

Implements caching to avoid repeated file checks, file locking for safe
concurrent access, and supports manual entry with optional saving to
~/.cortex/.env.

"""

import fcntl
import json
import os
import re
from pathlib import Path
from typing import Optional

from cortex.branding import console, cx_print

# Constants
CORTEX_DIR = ".cortex"
CORTEX_ENV_FILE = ".env"
CORTEX_CACHE_FILE = ".api_key_cache"

# Supported API key prefixes
KEY_PATTERNS = {
    "sk-ant-": "anthropic",
    "sk-": "openai",
}

# Environment variable mappings
ENV_VAR_PROVIDERS = {
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
}

# JSON field names to search for API keys
API_KEY_FIELD_NAMES = ["api_key", "apiKey", "key"]

# Provider display names for brand consistency
PROVIDER_DISPLAY_NAMES = {"anthropic": "Claude (Anthropic)", "openai": "OpenAI", "ollama": "Ollama"}

# Menu choice mappings for provider selection
PROVIDER_MENU_CHOICES = {"anthropic": "1", "openai": "2", "ollama": "3"}


class APIKeyDetector:
    """Detects and caches API keys from multiple sources."""

    def __init__(self, cache_dir: Path | None = None):
        """
        Initialize the API key detector.

        Args:
            cache_dir: Directory for caching key location info.
                      Defaults to ~/.cortex
        """
        self.cache_dir = cache_dir or (Path.home() / CORTEX_DIR)
        self.cache_file = self.cache_dir / CORTEX_CACHE_FILE

    def detect(self) -> tuple[bool, str | None, str | None, str | None]:
        """
        Auto-detect API key from common locations.

        Returns:
            Tuple of (found, key, provider, source)
            - found: True if key was found
            - key: The API key (or None)
            - provider: "anthropic" or "openai" (or None)
            - source: Where the key was found (or None)
        """
        # Check for explicit CORTEX_PROVIDER=ollama in environment variable first
        if os.environ.get("CORTEX_PROVIDER", "").lower() == "ollama":
            return (True, "ollama-local", "ollama", "environment")

        # Check for API keys in environment variables (highest priority)
        result = self._check_environment_api_keys()
        if result:
            return result

        # Check cached location
        result = self._check_cached_key()
        if result:
            return result

        # Check for saved Ollama provider preference in config file
        # (only if no API keys found in environment)
        result = self._check_saved_ollama_provider()
        if result:
            return result

        # Check other locations for API keys
        result = self._check_all_locations()
        return result or (False, None, None, None)

    def _check_environment_api_keys(self) -> tuple[bool, str, str, str] | None:
        """Check for API keys in environment variables."""
        for env_var, provider in ENV_VAR_PROVIDERS.items():
            value = os.environ.get(env_var)
            if value:
                return (True, value, provider, "environment")
        return None

    def _check_saved_ollama_provider(self) -> tuple[bool, str, str, str] | None:
        """Check if Ollama was previously selected as the provider in config file."""
        env_file = Path.home() / CORTEX_DIR / CORTEX_ENV_FILE
        if env_file.exists():
            try:
                content = env_file.read_text()
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("CORTEX_PROVIDER="):
                        value = line.split("=", 1)[1].strip().strip("\"'").lower()
                        if value == "ollama":
                            return (True, "ollama-local", "ollama", str(env_file))
            except OSError:
                # Ignore errors reading env file; treat as no configured provider
                pass
        return None

    def _check_cached_key(self) -> tuple[bool, str | None, str | None, str | None] | None:
        """Check if we have a cached key that still works."""
        cached = self._get_cached_key()
        if not cached:
            return None

        provider, source = cached
        return self._validate_cached_key(provider, source)

    def _validate_cached_key(
        self, provider: str, source: str
    ) -> tuple[bool, str | None, str | None, str | None] | None:
        """Validate that a cached key still works."""
        env_var = self._get_env_var_name(provider)

        if source == "environment":
            value = os.environ.get(env_var)
            return (True, value, provider, source) if value else None
        else:
            key = self._extract_key_from_file(Path(source), env_var)
            if key:
                os.environ[env_var] = key
                return (True, key, provider, source)
            return None

    def _check_all_locations(self) -> tuple[bool, str | None, str | None, str | None] | None:
        """Check all locations in priority order for API keys."""
        locations = self._get_check_locations()

        for source, env_vars in locations:
            result = self._check_location(source, env_vars)
            if result:
                return result

        return None

    def _check_location(
        self, source: str | Path, env_vars: list[str]
    ) -> tuple[bool, str | None, str | None, str | None] | None:
        """Check a specific location for API keys."""
        for env_var in env_vars:
            if source == "environment":
                result = self._check_environment_variable(env_var)
            elif isinstance(source, Path):
                result = self._check_file_location(source, env_var)
            else:
                continue

            if result:
                return result

        return None

    def _check_environment_variable(
        self, env_var: str
    ) -> tuple[bool, str | None, str | None, str | None] | None:
        """Check if an environment variable contains a valid API key."""
        value = os.environ.get(env_var)
        if value:
            provider = self._get_provider_from_var(env_var)
            self._cache_key_location(value, provider, "environment")
            return (True, value, provider, "environment")
        return None

    def _check_file_location(
        self, source: Path, env_var: str
    ) -> tuple[bool, str | None, str | None, str | None] | None:
        """Check if a file contains a valid API key."""
        key = self._extract_key_from_file(source, env_var)
        if key:
            provider = self._get_provider_from_var(env_var)
            self._cache_key_location(key, provider, str(source))
            # Set in environment for this session
            os.environ[env_var] = key
            return (True, key, provider, str(source))
        return None

    def prompt_for_key(self) -> tuple[bool, str | None, str | None]:
        """
        Prompt user to select a provider and enter an API key if needed.

        Returns:
            Tuple of (entered, key, provider)
        """
        provider = self._get_provider_choice()
        if not provider:
            return (False, None, None)

        if provider == "ollama":
            self._ask_to_save_ollama_preference()
            return (True, "ollama-local", "ollama")

        key = self._get_and_validate_key(provider)
        if not key:
            return (False, None, None)

        self._ask_to_save_key(key, provider)
        return (True, key, provider)

    def _ask_to_save_ollama_preference(self) -> None:
        """Ask user if they want to save Ollama as their default provider."""
        print(
            f"\nSave Ollama as default provider to ~/{CORTEX_DIR}/{CORTEX_ENV_FILE}? [Y/n] ", end=""
        )
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"

        if response != "n":
            self._save_provider_to_env("ollama")
            cx_print(f"✓ Provider preference saved to ~/{CORTEX_DIR}/{CORTEX_ENV_FILE}", "success")

    def _save_provider_to_env(self, provider: str) -> None:
        """Save provider preference to ~/.cortex/.env with file locking."""
        try:
            env_file = Path.home() / CORTEX_DIR / CORTEX_ENV_FILE
            self._locked_read_modify_write(
                env_file, self._update_or_append_key, "CORTEX_PROVIDER", provider
            )
        except Exception as e:
            cx_print(f"Warning: Could not save provider to ~/.cortex/.env: {e}", "warning")

    def _get_provider_choice(self) -> str | None:
        """Get user's provider choice."""
        cx_print("No API key found. Select a provider:", "warning")
        console.print("  [bold]1.[/bold] Claude (Anthropic)")
        console.print("  [bold]2.[/bold] OpenAI")
        console.print("  [bold]3.[/bold] Ollama (local, no key needed)")

        while True:
            try:
                choice = input("\nEnter choice [1/2/3]: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None

            if choice == "3":
                cx_print("✓ Using Ollama (local mode)", "success")
                return "ollama"

            if choice == "1":
                return "anthropic"
            elif choice == "2":
                return "openai"
            else:
                cx_print("Invalid choice. Please enter 1, 2, or 3.", "warning")

    def _get_and_validate_key(self, provider: str) -> str | None:
        """Get and validate API key from user."""
        provider_name = "Anthropic" if provider == "anthropic" else "OpenAI"
        prefix_hint = "sk-ant-" if provider == "anthropic" else "sk-"
        cx_print(f"Enter your {provider_name} API key (starts with '{prefix_hint}'):", "info")

        try:
            key = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not key:
            cx_print("Cancelled.", "info")
            return None

        # Validate format
        detected = self._get_provider_from_key(key)
        if detected != provider:
            cx_print(f"⚠️  Key doesn't match expected {provider_name} format", "warning")
            return None

        return key

    def _ask_to_save_key(self, key: str, provider: str) -> None:
        """Ask user if they want to save the key."""
        print(f"\nSave to ~/{CORTEX_DIR}/{CORTEX_ENV_FILE}? [Y/n] ", end="")
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"

        if response != "n":
            self._save_key_to_env(key, provider)
            # Update cache to point to the default location
            target_env = Path.home() / CORTEX_DIR / CORTEX_ENV_FILE
            self._cache_key_location(key, provider, str(target_env))
            cx_print(f"✓ Key saved to ~/{CORTEX_DIR}/{CORTEX_ENV_FILE}", "success")

    def _maybe_save_found_key(self, key: str, provider: str, source: str) -> None:
        """Offer to save a detected key to ~/.cortex/.env."""
        # Skip prompting for environment variables - they're already properly configured
        if source == "environment":
            return

        target_env = Path.home() / CORTEX_DIR / CORTEX_ENV_FILE
        try:
            source_path = Path(source).expanduser()
            if source_path.exists() and source_path.resolve() == target_env.resolve():
                return
        except (OSError, ValueError):
            # If source is not a valid path, continue prompting for file-based sources
            pass

        cx_print("API key found at following location", "info")
        console.print(f"{source}")
        print(f"\nSave to ~/{CORTEX_DIR}/{CORTEX_ENV_FILE}? [Y/n] ", end="")

        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"

        if response != "n":
            self._save_key_to_env(key, provider)
            # Update cache to point to the new default location
            self._cache_key_location(key, provider, str(target_env))
            cx_print("✓ Key saved to ~/.cortex/.env", "success")

    def _get_check_locations(self) -> list[tuple]:
        """
        Get locations to check in priority order.

        Returns:
            List of (source, env_vars) tuples
        """
        return [
            ("environment", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]),
            (Path.home() / CORTEX_DIR / CORTEX_ENV_FILE, ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]),
            (Path.home() / ".config" / "anthropic" / "credentials.json", ["ANTHROPIC_API_KEY"]),
            (Path.home() / ".config" / "openai" / "credentials.json", ["OPENAI_API_KEY"]),
            (Path.cwd() / ".env", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]),
        ]

    def _extract_key_from_file(self, file_path: Path, env_var: str) -> str | None:
        """
        Extract API key from a file.

        Supports both simple KEY=value format and JSON files.

        Args:
            file_path: Path to file to check
            env_var: Environment variable name to look for

        Returns:
            The API key value or None
        """
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text().strip()

            # Try extraction methods in order
            key = self._extract_from_json(content, env_var)
            if key:
                return key

            key = self._extract_from_env_format(content, env_var)
            if key:
                return key

            return self._extract_raw_key(content)

        except Exception:
            # Silently ignore read errors
            pass

        return None

    def _extract_from_json(self, content: str, env_var: str) -> str | None:
        """Extract API key from JSON content."""
        try:
            data = json.loads(content)
            # Look for key in common locations
            for key_field in API_KEY_FIELD_NAMES + [env_var]:
                if key_field in data:
                    return data[key_field]
        except json.JSONDecodeError:
            # Content is not valid JSON; indicate no key found from JSON and let callers try other formats.
            return None

    def _extract_from_env_format(self, content: str, env_var: str) -> str | None:
        """Extract API key from KEY=value format."""
        pattern = rf"^{env_var}\s*=\s*(.+?)(?:\s*#.*)?$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.group(1).strip("\"'")
        return None

    def _extract_raw_key(self, content: str) -> str | None:
        """Extract raw API key from content (handles single-line files)."""
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check if line is just the key
            if self._is_valid_key(line):
                return line

            # Check if line is KEY=VALUE format
            if "=" in line:
                _, value = line.split("=", 1)
                value = value.strip("\"'").strip()
                if self._is_valid_key(value):
                    return value

        return None

    def _is_valid_key(self, value: str) -> bool:
        """Check if a value matches known API key patterns.

        More specific (longer) prefixes are checked first to avoid ambiguity
        when prefixes overlap (e.g., "sk-ant-" vs "sk-").
        """
        for prefix in sorted(KEY_PATTERNS.keys(), key=len, reverse=True):
            if value.startswith(prefix):
                return True
        return False

    def _get_provider_from_var(self, env_var: str) -> str:
        """Get provider name from environment variable name."""
        return ENV_VAR_PROVIDERS.get(env_var, "unknown")

    def _get_provider_from_key(self, key: str) -> str | None:
        """Get provider name from API key format.

        More specific (longer) prefixes are checked first to ensure that
        overlapping prefixes resolve to the most specific provider.
        """
        for prefix, provider in sorted(
            KEY_PATTERNS.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if key.startswith(prefix):
                return provider
        return None

    def _atomic_write(self, target_file: Path, content: str) -> None:
        """
        Atomically write content to a file to prevent corruption from concurrent access.

        Args:
            target_file: The file to write to
            content: The content to write
        """
        temp_file = target_file.with_suffix(".tmp")
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file.write_text(content)
        temp_file.chmod(0o600)
        temp_file.replace(target_file)

    def _locked_read_modify_write(self, env_file: Path, modifier_func: callable, *args) -> None:
        """
        Perform a locked read-modify-write operation on a file.

        Uses file locking to prevent race conditions when multiple processes
        try to modify the same file concurrently.

        Args:
            env_file: The file to modify
            modifier_func: Function that takes (existing_content, *args) and returns new content
            *args: Additional arguments to pass to modifier_func
        """
        env_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = env_file.with_suffix(".lock")

        # Create lock file if it doesn't exist
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r+") as lock_fd:
            # Acquire exclusive lock (blocks until available)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                # Read current content
                existing = env_file.read_text() if env_file.exists() else ""

                # Apply modification
                updated = modifier_func(existing, *args)

                # Write atomically
                self._atomic_write(env_file, updated)
            finally:
                # Release lock
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def _cache_key_location(self, key: str, provider: str, source: str):
        """
        Cache the location where a key was found.

        Uses atomic write operations to prevent corruption from concurrent access.

        Args:
            key: The API key
            provider: Provider name
            source: Where the key was found
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "provider": provider,
                "source": source,
                "key_hint": key[:10] + "..." if len(key) > 10 else key,
            }

            self._atomic_write(self.cache_file, json.dumps(cache_data, indent=2))

        except Exception:
            # Silently ignore cache errors
            pass

    def _get_cached_key(self) -> tuple[str, str] | None:
        """
        Retrieve cached key location info.

        Returns:
            Tuple of (provider, source) or None
        """
        if not self.cache_file.exists():
            return None

        try:
            data = json.loads(self.cache_file.read_text())
            # Check if the source still has a valid key
            provider = data.get("provider")
            source = data.get("source")

            # Return cached info (caller will validate key still exists)
            if provider and source:
                return (provider, source)
        except Exception:
            return None

        return None

    def _get_env_var_name(self, provider: str) -> str:
        """Get environment variable name from provider name."""
        reverse_mapping = {v: k for k, v in ENV_VAR_PROVIDERS.items()}
        return reverse_mapping.get(provider, "UNKNOWN_API_KEY")

    def _read_env_file(self, env_file: Path) -> str:
        """Read .env file content, return empty string if not exists."""
        return env_file.read_text() if env_file.exists() else ""

    def _write_env_file(self, env_file: Path, content: str) -> None:
        """Write .env file with secure permissions."""
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(content)
        env_file.chmod(0o600)

    def _update_or_append_key(self, existing: str, var_name: str, key: str) -> str:
        """Update existing key or append new one to file content."""
        if f"{var_name}=" in existing:
            # Replace existing
            pattern = rf"^{var_name}=.*$"
            return re.sub(pattern, f"{var_name}={key}", existing, flags=re.MULTILINE)
        else:
            # Append
            if existing and not existing.endswith("\n"):
                existing += "\n"
            return existing + f"{var_name}={key}\n"

    def _save_key_to_env(self, key: str, provider: str):
        """
        Save API key to ~/.cortex/.env.

        Uses file locking and atomic write operations to prevent corruption
        and lost updates from concurrent access.

        Args:
            key: The API key to save
            provider: Provider name
        """
        try:
            env_file = Path.home() / CORTEX_DIR / CORTEX_ENV_FILE
            var_name = self._get_env_var_name(provider)
            self._locked_read_modify_write(env_file, self._update_or_append_key, var_name, key)

        except Exception as e:
            # If save fails, print warning but don't crash
            cx_print(f"Warning: Could not save key to ~/.cortex/.env: {e}", "warning")


def auto_detect_api_key() -> tuple[bool, str | None, str | None, str | None]:
    """
    Convenience function to auto-detect API key.

    Returns:
        Tuple of (found, key, provider, source)
    """
    detector = APIKeyDetector()
    return detector.detect()


def setup_api_key() -> tuple[bool, str | None, str | None]:
    """
    Setup API key by auto-detecting or prompting user.

    Returns:
        Tuple of (success, key, provider)
    """
    detector = APIKeyDetector()

    # Try auto-detection first
    found, key, provider, source = detector.detect()
    if found:
        # Only show "Found" message for non-default locations
        # ~/.cortex/.env is our canonical location, so no need to announce it
        default_location = str(Path.home() / CORTEX_DIR / CORTEX_ENV_FILE)
        if source != default_location:
            display_name = PROVIDER_DISPLAY_NAMES.get(provider, provider.upper())
            cx_print(f"🔑 Found {display_name} API key in {source}", "success")
        detector._maybe_save_found_key(key, provider, source)
        return (True, key, provider)

    # Prompt for manual entry
    entered, key, provider = detector.prompt_for_key()
    if entered:
        return (True, key, provider)

    return (False, None, None)
