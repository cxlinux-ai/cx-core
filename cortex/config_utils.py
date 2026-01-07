"""Configuration utilities for Cortex.

This module provides shared configuration helpers used across the codebase.
"""

import json
import os
from pathlib import Path


def get_ollama_model() -> str:
    """Determine which Ollama model to use.

    The model name is resolved using the following precedence:

    1. If the ``OLLAMA_MODEL`` environment variable is set, its value is
       returned.
    2. Otherwise, if ``~/.cortex/config.json`` exists and contains an
       ``"ollama_model"`` key, that value is returned.
    3. If neither of the above sources provides a model name, the
       hard-coded default ``"llama3.2"`` is used.

    Any errors encountered while reading or parsing the configuration
    file are silently ignored, and the resolution continues to the next
    step in the precedence chain.

    Returns:
        The Ollama model name to use.
    """
    # Try environment variable first
    env_model = os.environ.get("OLLAMA_MODEL")
    if env_model:
        return env_model

    # Try config file
    try:
        config_file = Path.home() / ".cortex" / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
                model = config.get("ollama_model")
                if model:
                    return model
    except (OSError, json.JSONDecodeError):
        pass  # Ignore file/parse errors

    # Default to llama3.2
    return "llama3.2"
