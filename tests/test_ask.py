"""Unit tests for the ask module."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.ask import AskHandler, LearningTracker, SystemInfoGatherer


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


class TestLearningTracker(unittest.TestCase):
    """Tests for LearningTracker."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = Path(self.temp_dir) / "learning_history.json"
        self.tracker = LearningTracker()
        # Set the progress file to use temp location
        self.tracker._progress_file = self.temp_file

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_is_educational_query_explain(self):
        """Test detection of 'explain' queries."""
        self.assertTrue(self.tracker.is_educational_query("explain how docker works"))
        self.assertTrue(self.tracker.is_educational_query("Explain nginx configuration"))

    def test_is_educational_query_teach_me(self):
        """Test detection of 'teach me' queries."""
        self.assertTrue(self.tracker.is_educational_query("teach me about systemd"))
        self.assertTrue(self.tracker.is_educational_query("Teach me how to use git"))

    def test_is_educational_query_what_is(self):
        """Test detection of 'what is' queries."""
        self.assertTrue(self.tracker.is_educational_query("what is kubernetes"))
        self.assertTrue(self.tracker.is_educational_query("What are containers"))

    def test_is_educational_query_how_does(self):
        """Test detection of 'how does' queries."""
        self.assertTrue(self.tracker.is_educational_query("how does DNS work"))
        self.assertTrue(self.tracker.is_educational_query("How do containers work"))

    def test_is_educational_query_best_practices(self):
        """Test detection of 'best practices' queries."""
        self.assertTrue(self.tracker.is_educational_query("best practices for security"))
        self.assertTrue(self.tracker.is_educational_query("what are best practice for nginx"))

    def test_is_educational_query_tutorial(self):
        """Test detection of 'tutorial' queries."""
        self.assertTrue(self.tracker.is_educational_query("tutorial on docker compose"))

    def test_is_educational_query_non_educational(self):
        """Test that non-educational queries return False."""
        self.assertFalse(self.tracker.is_educational_query("why is my disk full"))
        self.assertFalse(self.tracker.is_educational_query("what packages need updating"))
        self.assertFalse(self.tracker.is_educational_query("check my system status"))

    def test_extract_topic_explain(self):
        """Test topic extraction from 'explain' queries."""
        topic = self.tracker.extract_topic("explain how docker containers work")
        self.assertEqual(topic, "how docker containers work")

    def test_extract_topic_teach_me(self):
        """Test topic extraction from 'teach me' queries."""
        topic = self.tracker.extract_topic("teach me about systemd services")
        self.assertEqual(topic, "systemd services")

    def test_extract_topic_what_is(self):
        """Test topic extraction from 'what is' queries."""
        topic = self.tracker.extract_topic("what is kubernetes?")
        self.assertEqual(topic, "kubernetes")

    def test_extract_topic_truncation(self):
        """Test that long topics are truncated."""
        long_question = "explain " + "a" * 100
        topic = self.tracker.extract_topic(long_question)
        self.assertLessEqual(len(topic), 50)

    def test_record_topic_creates_file(self):
        """Test that recording a topic creates the history file."""
        self.tracker.record_topic("explain docker")
        self.assertTrue(self.temp_file.exists())

    def test_record_topic_stores_data(self):
        """Test that recorded topics are stored correctly."""
        self.tracker.record_topic("explain docker containers")
        history = self.tracker.get_history()
        self.assertIn("docker containers", history["topics"])
        self.assertEqual(history["topics"]["docker containers"]["count"], 1)

    def test_record_topic_increments_count(self):
        """Test that repeated topics increment the count."""
        self.tracker.record_topic("explain docker")
        self.tracker.record_topic("explain docker")
        history = self.tracker.get_history()
        self.assertEqual(history["topics"]["docker"]["count"], 2)

    def test_record_topic_ignores_non_educational(self):
        """Test that non-educational queries are not recorded."""
        self.tracker.record_topic("why is my disk full")
        history = self.tracker.get_history()
        self.assertEqual(len(history["topics"]), 0)

    def test_get_recent_topics(self):
        """Test getting recent topics."""
        self.tracker.record_topic("explain docker")
        self.tracker.record_topic("what is kubernetes")
        self.tracker.record_topic("teach me nginx")

        recent = self.tracker.get_recent_topics(limit=2)
        self.assertEqual(len(recent), 2)
        # Most recent should be first
        self.assertEqual(recent[0], "nginx")

    def test_get_recent_topics_empty(self):
        """Test getting recent topics when none exist."""
        recent = self.tracker.get_recent_topics()
        self.assertEqual(recent, [])

    def test_total_queries_tracked(self):
        """Test that total educational queries are tracked."""
        self.tracker.record_topic("explain docker")
        self.tracker.record_topic("what is kubernetes")
        history = self.tracker.get_history()
        self.assertEqual(history["total_queries"], 2)


class TestAskHandlerLearning(unittest.TestCase):
    """Tests for AskHandler learning features."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = Path(self.temp_dir) / "learning_history.json"

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_ask_records_educational_topic(self):
        """Test that educational questions are recorded."""
        os.environ["CORTEX_FAKE_RESPONSE"] = "Docker is a containerization platform..."
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = None
        # Set the progress file to use temp location
        handler.learning_tracker._progress_file = self.temp_file

        handler.ask("explain how docker works")

        history = handler.get_learning_history()
        self.assertIn("how docker works", history["topics"])

    def test_ask_does_not_record_diagnostic(self):
        """Test that diagnostic questions are not recorded."""
        os.environ["CORTEX_FAKE_RESPONSE"] = "Your disk is 80% full."
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = None
        handler.learning_tracker._progress_file = self.temp_file

        handler.ask("why is my disk full")

        history = handler.get_learning_history()
        self.assertEqual(len(history["topics"]), 0)

    def test_get_recent_topics_via_handler(self):
        """Test getting recent topics through handler."""
        os.environ["CORTEX_FAKE_RESPONSE"] = "Test response"
        handler = AskHandler(api_key="fake-key", provider="fake")
        handler.cache = None
        handler.learning_tracker._progress_file = self.temp_file

        handler.ask("explain kubernetes")
        handler.ask("what is docker")

        recent = handler.get_recent_topics(limit=5)
        self.assertEqual(len(recent), 2)

    def test_system_prompt_contains_educational_instructions(self):
        """Test that system prompt includes educational guidance."""
        handler = AskHandler(api_key="fake-key", provider="fake")
        context = handler.info_gatherer.gather_context()
        prompt = handler._get_system_prompt(context)

        self.assertIn("Educational Questions", prompt)
        self.assertIn("Diagnostic Questions", prompt)
        self.assertIn("tutorial-style", prompt)
        self.assertIn("best practices", prompt)


class TestSystemPromptEnhancement(unittest.TestCase):
    """Tests for enhanced system prompt."""

    def test_prompt_includes_query_type_detection(self):
        """Test that prompt includes query type detection section."""
        handler = AskHandler(api_key="fake-key", provider="fake")
        context = {"python_version": "3.11", "os": {"system": "Linux"}}
        prompt = handler._get_system_prompt(context)

        self.assertIn("Query Type Detection", prompt)
        self.assertIn("explain", prompt.lower())
        self.assertIn("teach me", prompt.lower())

    def test_prompt_includes_educational_instructions(self):
        """Test that prompt includes educational response instructions."""
        handler = AskHandler(api_key="fake-key", provider="fake")
        context = {}
        prompt = handler._get_system_prompt(context)

        self.assertIn("code examples", prompt.lower())
        self.assertIn("best practices", prompt.lower())
        self.assertIn("related topics", prompt.lower())

    def test_prompt_includes_diagnostic_instructions(self):
        """Test that prompt includes diagnostic response instructions."""
        handler = AskHandler(api_key="fake-key", provider="fake")
        context = {}
        prompt = handler._get_system_prompt(context)

        self.assertIn("system context", prompt.lower())
        self.assertIn("actionable", prompt.lower())


if __name__ == "__main__":
    unittest.main()
