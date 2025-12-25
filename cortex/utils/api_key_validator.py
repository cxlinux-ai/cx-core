"""
API Key Validation Utilities

Validates API keys for various LLM providers.
"""

import requests


def validate_anthropic_api_key(api_key: str) -> bool:
    """Validate Anthropic (Claude) API key by making a minimal request."""
    try:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        data = {
            "model": "claude-3-opus-20240229",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "Hello"}],
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False





def validate_openai_api_key(api_key: str) -> bool:
    """Validate OpenAI API key by making a minimal request."""
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1,
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False
