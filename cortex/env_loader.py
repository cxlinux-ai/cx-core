"""
Environment Loader for Cortex Linux

Loads environment variables from .env files at application startup.
This module must be imported and load_env() called BEFORE any other
modules that access os.environ for API keys.

Searches for .env files in the following locations (in order of priority):
1. Current working directory (./.env)
2. User's Cortex config directory (~/.cortex/.env)
3. System-wide config (/etc/cortex/.env)

Later files do NOT override earlier ones - the first value found wins.

Issue: https://github.com/cortexlinux/cortex/issues/XXX
"""

import os
from pathlib import Path


def get_env_file_locations() -> list[Path]:
    """
    Get list of .env file locations to check, in priority order.

    Returns:
        List of Path objects for potential .env file locations.
        First location has highest priority.
    """
    locations = []

    # 1. Current working directory (highest priority)
    cwd_env = Path.cwd() / ".env"
    locations.append(cwd_env)

    # 2. User's home directory .cortex folder
    home_cortex_env = Path.home() / ".cortex" / ".env"
    locations.append(home_cortex_env)

    # 3. System-wide config (Linux only)
    if os.name == "posix":
        system_env = Path("/etc/cortex/.env")
        locations.append(system_env)

    return locations


def load_env(override: bool = False, verbose: bool = False) -> list[Path]:
    """
    Load environment variables from .env files.

    This function should be called at the very beginning of the application,
    BEFORE any modules that access os.environ for API keys are imported.

    Args:
        override: If True, .env values will override existing environment
                  variables. Defaults to False (existing env vars take precedence).
        verbose: If True, print which .env files were loaded.

    Returns:
        List of .env file paths that were successfully loaded.

    Example:
        # At the very start of your main entry point:
        from cortex.env_loader import load_env
        load_env()

        # Now API keys from .env files are available
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv not installed, skip silently
        # This allows the application to still run if the dependency is missing
        if verbose:
            print("Warning: python-dotenv not installed, .env files not loaded")
        return []

    loaded_files = []
    locations = get_env_file_locations()

    for env_path in locations:
        if env_path.exists() and env_path.is_file():
            try:
                # load_dotenv with override=False means existing env vars are NOT replaced
                # This respects the priority order: earlier files and existing env vars win
                load_dotenv(dotenv_path=env_path, override=override)
                loaded_files.append(env_path)

                if verbose:
                    print(f"Loaded environment from: {env_path}")

            except Exception as e:
                # Don't fail the application if we can't read a .env file
                if verbose:
                    print(f"Warning: Could not load {env_path}: {e}")

    return loaded_files


def find_env_files() -> list[Path]:
    """
    Find all existing .env files without loading them.

    Useful for debugging or displaying configuration status.

    Returns:
        List of existing .env file paths, in priority order.
    """
    locations = get_env_file_locations()
    return [path for path in locations if path.exists() and path.is_file()]


def get_api_key_sources() -> dict[str, str | None]:
    """
    Check which API keys are configured and their sources.

    Useful for debugging API key configuration issues.

    Returns:
        Dictionary with API key names and their source (.env file path or 'environment').
    """
    sources = {}
    env_files = find_env_files()

    api_keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "MOONSHOT_API_KEY",
        "CORTEX_PROVIDER",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
    ]

    for key in api_keys:
        value = os.environ.get(key)
        if value:
            # Try to determine source
            source = "environment"

            # Check if it came from a .env file
            for env_file in env_files:
                try:
                    content = env_file.read_text()
                    if f"{key}=" in content:
                        source = str(env_file)
                        break
                except Exception:
                    pass

            sources[key] = source
        else:
            sources[key] = None

    return sources
