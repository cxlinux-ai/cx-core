#!/usr/bin/env python3
"""
Test suite for Ollama integration.

Tests:
- Ollama provider initialization
- Model management
- LLM router integration
- Fallback logic

Author: Cortex Linux Team
License: Apache 2.0
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.llm_router import LLMProvider, LLMRouter, TaskType
from cortex.providers.ollama_provider import OllamaProvider


class TestOllamaProvider(unittest.TestCase):
    """Test Ollama provider functionality."""

    @patch("cortex.providers.ollama_provider.shutil.which")
    def test_is_installed(self, mock_which):
        """Test Ollama installation detection."""
        # Test when installed
        mock_which.return_value = "/usr/bin/ollama"
        self.assertTrue(OllamaProvider.is_installed())

        # Test when not installed
        mock_which.return_value = None
        self.assertFalse(OllamaProvider.is_installed())

    @patch("cortex.providers.ollama_provider.requests.get")
    def test_is_running(self, mock_get):
        """Test Ollama service detection."""
        # Test when running
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_get.side_effect = None  # Clear any side effects

        provider = OllamaProvider()
        self.assertTrue(provider.is_running())

        # Test when not running - use RequestException
        from requests.exceptions import ConnectionError

        mock_get.side_effect = ConnectionError("Connection refused")

        provider2 = OllamaProvider()
        self.assertFalse(provider2.is_running())

    @patch("cortex.providers.ollama_provider.requests.get")
    def test_get_available_models(self, mock_get):
        """Test model listing."""
        provider = OllamaProvider()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b"},
                {"name": "phi3:mini"},
            ]
        }
        mock_get.return_value = mock_response

        models = provider.get_available_models()
        self.assertEqual(len(models), 2)
        self.assertIn("llama3:8b", models)
        self.assertIn("phi3:mini", models)

    @patch("cortex.providers.ollama_provider.requests.get")
    def test_select_best_model(self, mock_get):
        """Test model selection logic."""
        provider = OllamaProvider()

        # Mock available models
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:8b"},
                {"name": "codellama:13b"},
            ]
        }
        mock_get.return_value = mock_response

        # Should prefer codellama (code-focused)
        selected = provider.select_best_model()
        self.assertEqual(selected, "codellama:13b")

    @patch("cortex.providers.ollama_provider.requests.post")
    def test_pull_model(self, mock_post):
        """Test model pulling."""
        provider = OllamaProvider()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b'{"status": "pulling"}',
            b'{"status": "done"}',
        ]
        mock_post.return_value = mock_response

        result = provider.pull_model("phi3:mini")
        self.assertTrue(result)


class TestLLMRouter(unittest.TestCase):
    """Test LLM router with Ollama integration."""

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    @patch("cortex.llm_router.OllamaProvider")
    def test_router_initialization(self, mock_ollama_class, mock_openai, mock_anthropic):
        """Test router initializes with Ollama."""
        mock_ollama = Mock()
        mock_ollama.is_installed.return_value = True
        mock_ollama.is_running.return_value = True
        mock_ollama.has_models.return_value = True
        mock_ollama.select_best_model.return_value = "llama3:8b"
        mock_ollama_class.return_value = mock_ollama

        # Initialize router without API keys (relies on mocked Ollama)
        router = LLMRouter()

        self.assertIsNotNone(router.ollama_client)
        self.assertTrue(router.ollama_has_models)
        self.assertEqual(router.default_provider, LLMProvider.OLLAMA)

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    @patch("cortex.llm_router.OllamaProvider")
    def test_routing_to_ollama(self, mock_ollama_class, mock_openai, mock_anthropic):
        """Test routing prefers Ollama."""
        mock_ollama = Mock()
        mock_ollama.is_installed.return_value = True
        mock_ollama.is_running.return_value = True
        mock_ollama.has_models.return_value = True
        mock_ollama.select_best_model.return_value = "llama3:8b"
        mock_ollama_class.return_value = mock_ollama

        router = LLMRouter()
        router.ollama_client = mock_ollama

        # Should route to Ollama by default
        routing = router.route_task(TaskType.SYSTEM_OPERATION)
        self.assertEqual(routing.provider, LLMProvider.OLLAMA)

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    @patch("cortex.providers.ollama_provider.OllamaProvider")
    def test_fallback_to_cloud(self, mock_ollama_class, mock_openai, mock_anthropic):
        """Test fallback when Ollama unavailable."""
        # Mock Ollama as unavailable
        mock_ollama = Mock()
        mock_ollama.is_running.return_value = False
        mock_ollama_class.return_value = mock_ollama

        # Mock Claude client
        mock_claude_client = Mock()
        mock_anthropic.return_value = mock_claude_client

        # Initialize router with API keys to enable cloud fallback
        router = LLMRouter(claude_api_key="test-claude-key")
        router.ollama_client = None  # Simulate Ollama unavailable
        router.claude_client = mock_claude_client

        # Should fallback to Claude
        routing = router.route_task(TaskType.SYSTEM_OPERATION)
        self.assertIn(routing.provider, [LLMProvider.CLAUDE, LLMProvider.KIMI_K2])

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    @patch("cortex.llm_router.OllamaProvider")
    @patch("cortex.providers.ollama_provider.requests.post")
    def test_complete_with_ollama(self, mock_post, mock_ollama_class, mock_openai, mock_anthropic):
        """Test completion using Ollama."""
        mock_ollama = Mock()
        mock_ollama.is_installed.return_value = True
        mock_ollama.is_running.return_value = True
        mock_ollama.has_models.return_value = True
        mock_ollama.select_best_model.return_value = "llama3:8b"
        mock_ollama.complete.return_value = {
            "response": "Install nginx using apt-get",
            "model": "llama3:8b",
        }
        mock_ollama_class.return_value = mock_ollama

        router = LLMRouter()

        messages = [{"role": "user", "content": "How to install nginx?"}]
        response = router.complete(
            messages=messages,
            task_type=TaskType.SYSTEM_OPERATION,
            force_provider=LLMProvider.OLLAMA,
        )

        self.assertEqual(response.provider, LLMProvider.OLLAMA)
        # Check that complete was called on the mock
        mock_ollama.complete.assert_called_once()
        self.assertIn("nginx", response.content.lower())


class TestOllamaSetup(unittest.TestCase):
    """Test Ollama setup script."""

    @patch("scripts.setup_ollama.is_ollama_installed")
    @patch("subprocess.Popen")
    def test_install_ollama_success(self, mock_popen, mock_is_installed):
        """Test successful Ollama installation."""
        from scripts.setup_ollama import install_ollama

        # Not installed initially, then installed after
        mock_is_installed.side_effect = [False, True]

        # Mock successful installation process
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = iter(
            [
                ">>> Installing ollama to /usr/local\n",
                ">>> Downloading Linux amd64 bundle\n",
                ">>> Creating ollama user...\n",
                ">>> Enabling and starting ollama service...\n",
            ]
        )
        mock_popen.return_value = mock_process

        result = install_ollama()
        self.assertTrue(result)

        # Verify it used the curl | sh command
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        self.assertEqual(call_args[0], "sh")
        self.assertEqual(call_args[1], "-c")
        self.assertIn("curl -fsSL https://ollama.com/install.sh | sh", call_args[2])

    @patch("scripts.setup_ollama.is_ollama_installed")
    def test_install_ollama_already_installed(self, mock_is_installed):
        """Test that installation is skipped when already installed."""
        from scripts.setup_ollama import install_ollama

        # Already installed
        mock_is_installed.return_value = True

        result = install_ollama()
        self.assertTrue(result)

    @patch("scripts.setup_ollama.is_ollama_installed")
    @patch("subprocess.Popen")
    def test_install_ollama_failure(self, mock_popen, mock_is_installed):
        """Test Ollama installation failure."""
        from scripts.setup_ollama import install_ollama

        # Not installed before or after
        mock_is_installed.return_value = False

        # Mock failed installation
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.stdout = iter([])
        mock_popen.return_value = mock_process

        result = install_ollama()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
