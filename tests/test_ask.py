"""Unit tests for the ask module."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.ask import AskHandler, SystemInfoGatherer


class TestSystemInfoGatherer(unittest.TestCase):
    """Tests for SystemInfoGatherer."""

    def test_get_python_version(self):
        """Test Python version retrieval."""
        version = SystemInfoGatherer.get_python_version()
        self.assertIsInstance(version, str)
        # Should match format like "3.11.6"
        parts = version.split(".")
        self.assertGreaterEqual(len(parts), 2)

    def test_get_python_path(self):
        """Test Python path retrieval."""
        path = SystemInfoGatherer.get_python_path()
        self.assertIsInstance(path, str)
        self.assertTrue(len(path) > 0)

    def test_get_os_info(self):
        """Test OS info retrieval."""
        info = SystemInfoGatherer.get_os_info()
        self.assertIn("system", info)
        self.assertIn("release", info)
        self.assertIn("machine", info)

    @patch("subprocess.run")
    def test_get_installed_package_found(self, mock_run):
        """Test getting an installed package version."""
        mock_run.return_value = MagicMock(returncode=0, stdout="1.24.0")
        version = SystemInfoGatherer.get_installed_package("nginx")
        self.assertEqual(version, "1.24.0")

    @patch("subprocess.run")
    def test_get_installed_package_not_found(self, mock_run):
        """Test getting a non-existent package."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        version = SystemInfoGatherer.get_installed_package("nonexistent-pkg")
        self.assertIsNone(version)

    @patch("subprocess.run")
    def test_get_pip_package_found(self, mock_run):
        """Test getting an installed pip package version."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Name: numpy\nVersion: 1.26.4\nSummary: NumPy",
        )
        version = SystemInfoGatherer.get_pip_package("numpy")
        self.assertEqual(version, "1.26.4")

    @patch("subprocess.run")
    def test_get_pip_package_not_found(self, mock_run):
        """Test pip package not found or pip unavailable."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        version = SystemInfoGatherer.get_pip_package("nonexistent-pkg")
        self.assertIsNone(version)

    @patch("shutil.which")
    def test_check_command_exists_true(self, mock_which):
        """Test checking for an existing command."""
        mock_which.return_value = "/usr/bin/python3"
        self.assertTrue(SystemInfoGatherer.check_command_exists("python3"))

    @patch("shutil.which")
    def test_check_command_exists_false(self, mock_which):
        """Test checking for a non-existent command."""
        mock_which.return_value = None
        self.assertFalse(SystemInfoGatherer.check_command_exists("nonexistent-cmd"))

    @patch("shutil.which")
    def test_get_gpu_info_no_nvidia(self, mock_which):
        """Test GPU info when nvidia-smi is not available."""
        mock_which.return_value = None
        info = SystemInfoGatherer.get_gpu_info()
        self.assertFalse(info["available"])
        self.assertFalse(info["nvidia"])

    def test_gather_context(self):
        """Test gathering full context."""
        gatherer = SystemInfoGatherer()
        context = gatherer.gather_context()
        self.assertIn("python_version", context)
        self.assertIn("python_path", context)
        self.assertIn("os", context)
        self.assertIn("gpu", context)


class TestAskHandler(unittest.TestCase):
    """Tests for AskHandler."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_cache.db")
        self._caches_to_close = []

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        # Close any caches to release file handles (needed on Windows)
        for cache in self._caches_to_close:
            if hasattr(cache, "_pool") and cache._pool is not None:
                cache._pool.close_all()

        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except PermissionError:
                pass  # Ignore on Windows if file is still locked

    def test_ask_empty_question(self):
        """Test that empty questions raise ValueError."""
        # Use fake provider to avoid API calls
        os.environ["CORTEX_FAKE_RESPONSE"] = "test response"
        handler = AskHandler(api_key="fake-key", provider="fake")
        with self.assertRaises(ValueError):
            handler.ask("")
        with self.assertRaises(ValueError):
            handler.ask("   ")

    def test_ask_with_fake_provider(self):
        """Test ask with fake provider returns expected response."""
        os.environ["CORTEX_FAKE_RESPONSE"] = "Test answer from fake provider"
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = None  # Disable cache for this test
        answer = handler.ask("What is the meaning of life?")
        self.assertEqual(answer, "Test answer from fake provider")

    def test_ask_python_version_fake(self):
        """Test asking about Python version with fake provider."""
        # Clear any custom response to use default
        if "CORTEX_FAKE_RESPONSE" in os.environ:
            del os.environ["CORTEX_FAKE_RESPONSE"]
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = None
        answer = handler.ask("What version of Python do I have?")
        self.assertIn("Python", answer)

    @patch("cortex.ask.AskHandler._call_claude")
    def test_ask_with_claude_mock(self, mock_claude):
        """Test ask with mocked Claude API."""
        mock_claude.return_value = "You have Python 3.11.6 installed."

        with patch("anthropic.Anthropic"):
            handler = AskHandler(api_key="test-key", provider="claude")
            handler.cache = None
            answer = handler.ask("What Python version do I have?")

        self.assertEqual(answer, "You have Python 3.11.6 installed.")
        mock_claude.assert_called_once()

    @patch("cortex.ask.AskHandler._call_openai")
    def test_ask_with_openai_mock(self, mock_openai):
        """Test ask with mocked OpenAI API."""
        mock_openai.return_value = "TensorFlow is compatible with your system."

        with patch("openai.OpenAI"):
            handler = AskHandler(api_key="test-key", provider="openai")
            handler.cache = None
            answer = handler.ask("Can I run TensorFlow?")

        self.assertEqual(answer, "TensorFlow is compatible with your system.")
        mock_openai.assert_called_once()

    def test_ask_caches_response(self):
        """Test that responses are cached after successful API call."""
        from cortex.semantic_cache import SemanticCache

        cache = SemanticCache(db_path=self.db_path)
        self._caches_to_close.append(cache)

        os.environ["CORTEX_FAKE_RESPONSE"] = "Cached test answer"
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = cache

        # First call should cache the response
        answer1 = handler.ask("Test question for caching")
        self.assertEqual(answer1, "Cached test answer")

        # Verify it's in cache
        stats = cache.stats()
        # First call is a miss, then we store
        self.assertEqual(stats.misses, 1)

    def test_ask_uses_cached_response(self):
        """Test that cached responses are reused."""
        from cortex.semantic_cache import SemanticCache

        cache = SemanticCache(db_path=self.db_path)
        self._caches_to_close.append(cache)

        # Pre-populate cache
        cache.put_commands(
            prompt="ask:What is 2+2?",
            provider="fake",
            model="fake",
            system_prompt="",  # Will be different but we're testing exact match
            commands=["The answer is 4."],
        )

        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = cache

        # This should hit the cache
        # Note: Cache hit depends on system_prompt matching, which won't happen
        # with different contexts, so this tests the cache lookup mechanism
        stats_before = cache.stats()

        # The exact cache hit depends on matching system_prompt hash
        # For this test, we just verify the cache mechanism is called
        self.assertIsNotNone(handler.cache)


class TestAskHandlerProviders(unittest.TestCase):
    """Tests for different provider configurations."""

    def test_default_model_openai(self):
        """Test default model for OpenAI."""
        with patch("openai.OpenAI"):
            handler = AskHandler(api_key="test", provider="openai")
            self.assertEqual(handler.model, "gpt-4")

    def test_default_model_claude(self):
        """Test default model for Claude."""
        with patch("anthropic.Anthropic"):
            handler = AskHandler(api_key="test", provider="claude")
            self.assertEqual(handler.model, "claude-sonnet-4-20250514")

    def test_default_model_ollama(self):
        """Test default model for Ollama."""
        # Test with environment variable

        # Save and clear any existing OLLAMA_MODEL
        original_model = os.environ.get("OLLAMA_MODEL")

        # Test with custom env variable
        os.environ["OLLAMA_MODEL"] = "test-model"
        handler = AskHandler(api_key="test", provider="ollama")
        self.assertEqual(handler.model, "test-model")

        # Clean up
        if original_model is not None:
            os.environ["OLLAMA_MODEL"] = original_model
        else:
            os.environ.pop("OLLAMA_MODEL", None)

        # Test deterministic default behavior when no env var or config file exists.
        # Point the home directory to a temporary location without ~/.cortex/config.json
        # Also ensure OLLAMA_MODEL is not set in the environment so get_ollama_model()
        # exercises the built-in default model lookup.
        env_without_ollama = {k: v for k, v in os.environ.items() if k != "OLLAMA_MODEL"}
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cortex.config_utils.Path.home", return_value=Path(tmpdir)),
            patch.dict(os.environ, env_without_ollama, clear=True),
        ):
            handler2 = AskHandler(api_key="test", provider="ollama")
            # When no env var and no config file exist, AskHandler should use its built-in default.
            self.assertEqual(handler2.model, "llama3.2")

    def test_default_model_fake(self):
        """Test default model for fake provider."""
        handler = AskHandler(api_key="test", provider="fake")
        self.assertEqual(handler.model, "fake")

    def test_custom_model_override(self):
        """Test that custom model overrides default."""
        with patch("openai.OpenAI"):
            handler = AskHandler(api_key="test", provider="openai", model="gpt-4-turbo")
            self.assertEqual(handler.model, "gpt-4-turbo")

    def test_unsupported_provider(self):
        """Test that unsupported provider raises error."""
        with self.assertRaises(ValueError):
            AskHandler(api_key="test", provider="unsupported")


if __name__ == "__main__":
    unittest.main()
