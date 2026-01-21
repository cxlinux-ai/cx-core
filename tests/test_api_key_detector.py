"""
Tests for API Key Auto-Detection Module

Tests the APIKeyDetector class for auto-detecting API keys from
various common locations.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.api_key_detector import APIKeyDetector, auto_detect_api_key, setup_api_key


class TestAPIKeyDetector:
    """Test the APIKeyDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a detector with a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = APIKeyDetector(cache_dir=Path(tmpdir))
            yield detector

    @pytest.fixture
    def temp_home(self):
        """Create a temporary home directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _setup_detector_with_home(self, temp_home, cortex_env_content=None):
        """Helper to create detector with mocked home directory."""
        if cortex_env_content:
            cortex_dir = temp_home / ".cortex"
            cortex_dir.mkdir()
            (cortex_dir / ".env").write_text(cortex_env_content)

        detector = APIKeyDetector(cache_dir=temp_home / ".cortex")
        return detector

    def _setup_config_file(self, temp_home, config_path_parts, content):
        """Helper to create a config file with content."""
        config_path = temp_home / Path(*config_path_parts)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(content)

    def _detect_with_mocked_home(self, detector, temp_home):
        """Helper to run detect with mocked home directory."""
        with patch("pathlib.Path.home", return_value=temp_home):
            with patch.dict(os.environ, {}, clear=True):
                return detector.detect()

    def _assert_found_key(self, result, expected_key, expected_provider):
        """Helper to assert successful key detection."""
        found, key, provider, _ = result
        assert found is True
        assert key == expected_key
        assert provider == expected_provider

    def _assert_env_contains(self, temp_home, expected_lines, unexpected_lines=None):
        """Helper to assert .env file content."""
        content = (temp_home / ".cortex" / ".env").read_text()
        for line in expected_lines:
            assert line in content
        if unexpected_lines:
            for line in unexpected_lines:
                assert line not in content

    def test_detect_from_environment(self, detector):
        """Test detection from environment variables."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123"}, clear=True):
            found, key, provider, source = detector.detect()
            assert found is True
            assert key == "sk-ant-test123"
            assert provider == "anthropic"
            assert source == "environment"

    def test_detect_openai_from_environment(self, detector):
        """Test detection of OpenAI key from environment."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}, clear=True):
            found, key, provider, source = detector.detect()
            assert found is True
            assert key == "sk-test123"
            assert provider == "openai"
            assert source == "environment"

    def test_detect_from_cortex_env_file(self, temp_home):
        """Test detection from ~/.cortex/.env file."""
        detector = self._setup_detector_with_home(
            temp_home, "ANTHROPIC_API_KEY=sk-ant-fromfile123\n"
        )

        with patch("pathlib.Path.home", return_value=temp_home):
            result = self._detect_with_mocked_home(detector, temp_home)
            self._assert_found_key(result, "sk-ant-fromfile123", "anthropic")

    def test_detect_from_anthropic_config(self, temp_home):
        """Test detection from ~/.config/anthropic (Claude CLI location)."""
        detector = self._setup_detector_with_home(temp_home)
        self._setup_config_file(
            temp_home,
            (".config", "anthropic", "credentials.json"),
            json.dumps({"key": "sk-ant-config123"}),
        )

        with patch("pathlib.Path.home", return_value=temp_home):
            result = self._detect_with_mocked_home(detector, temp_home)
            self._assert_found_key(result, "sk-ant-config123", "anthropic")

    def test_detect_from_openai_config(self, temp_home):
        """Test detection from ~/.config/openai."""
        detector = self._setup_detector_with_home(temp_home)
        self._setup_config_file(
            temp_home,
            (".config", "openai", "credentials.json"),
            json.dumps({"key": "sk-openai123"}),
        )

        with patch("pathlib.Path.home", return_value=temp_home):
            result = self._detect_with_mocked_home(detector, temp_home)
            self._assert_found_key(result, "sk-openai123", "openai")

    def test_detect_from_current_dir(self, detector):
        """Test detection from .env in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("ANTHROPIC_API_KEY=sk-ant-cwd123\n")

            with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                # Also need to mock home so it doesn't find other keys
                with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                    test_detector = APIKeyDetector(cache_dir=Path(tmpdir) / ".cortex")
                    with patch.dict(os.environ, {}, clear=True):
                        found, key, provider, _ = test_detector.detect()
                        assert found is True
                        assert key == "sk-ant-cwd123"
                        assert provider == "anthropic"

    def test_priority_order(self, temp_home):
        """Test that detection respects priority order."""
        # Create keys in multiple locations
        detector = self._setup_detector_with_home(temp_home, "ANTHROPIC_API_KEY=sk-ant-cortex\n")
        self._setup_config_file(
            temp_home,
            (".config", "anthropic", "credentials.json"),
            json.dumps({"key": "sk-ant-config"}),
        )

        with patch("pathlib.Path.home", return_value=temp_home):
            # Should find cortex/.env first (higher priority)
            result = self._detect_with_mocked_home(detector, temp_home)
            self._assert_found_key(result, "sk-ant-cortex", "anthropic")

    def test_no_key_found(self, detector):
        """Test when no key is found."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.home", return_value=Path("/nonexistent")):
                with patch("pathlib.Path.cwd", return_value=Path("/nonexistent")):
                    found, key, provider, _ = detector.detect()
                    assert found is False
                    assert key is None
                    assert provider is None

    def test_extract_key_from_env_file(self, detector):
        """Test extracting key from .env format file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=sk-ant-test123\n")
            f.write("OTHER_VAR=value\n")
            f.flush()

            try:
                key = detector._extract_key_from_file(Path(f.name), "ANTHROPIC_API_KEY")
                assert key == "sk-ant-test123"
            finally:
                os.unlink(f.name)

    def test_extract_key_from_json(self, detector):
        """Test extracting key from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "sk-ant-json123"}, f)
            f.flush()

            try:
                key = detector._extract_key_from_file(Path(f.name), "ANTHROPIC_API_KEY")
                assert key == "sk-ant-json123"
            finally:
                os.unlink(f.name)

    def test_cache_key_location(self, detector):
        """Test caching key location information."""
        detector._cache_key_location("sk-ant-test", "anthropic", "test/location")

        assert detector.cache_file.exists()
        data = json.loads(detector.cache_file.read_text())
        assert data["provider"] == "anthropic"
        assert data["source"] == "test/location"

    def test_cache_file_permissions(self, detector):
        """Test that cache file has secure permissions."""
        detector._cache_key_location("sk-ant-test", "anthropic", "test/location")

        # Check file permissions (should be 600 = user read/write only)
        mode = detector.cache_file.stat().st_mode
        # Extract permission bits
        perms = mode & 0o777
        assert perms == 0o600

    def _setup_detector_with_env_file(self, temp_home, existing_content=""):
        """Helper to setup detector with existing .env file."""
        cortex_dir = temp_home / ".cortex"
        cortex_dir.mkdir(parents=True, exist_ok=True)
        env_file = cortex_dir / ".env"
        if existing_content:
            env_file.write_text(existing_content)
        return APIKeyDetector(cache_dir=cortex_dir)

    def test_save_key_to_env_file(self, temp_home):
        """Test saving key to ~/.cortex/.env."""
        detector = self._setup_detector_with_env_file(temp_home)

        with patch("pathlib.Path.home", return_value=temp_home):
            detector._save_key_to_env("sk-ant-saved", "anthropic")
            self._assert_env_contains(temp_home, ["ANTHROPIC_API_KEY=sk-ant-saved"])

    def test_save_key_appends_to_existing(self, temp_home):
        """Test that save appends to existing .env file."""
        detector = self._setup_detector_with_env_file(temp_home, "OTHER_VAR=value\n")

        with patch("pathlib.Path.home", return_value=temp_home):
            detector._save_key_to_env("sk-ant-saved", "anthropic")
            self._assert_env_contains(
                temp_home, ["OTHER_VAR=value", "ANTHROPIC_API_KEY=sk-ant-saved"]
            )

    def test_save_key_replaces_existing(self, temp_home):
        """Test that save replaces existing key in .env file."""
        detector = self._setup_detector_with_env_file(temp_home, "ANTHROPIC_API_KEY=sk-ant-old\n")

        with patch("pathlib.Path.home", return_value=temp_home):
            detector._save_key_to_env("sk-ant-new", "anthropic")
            self._assert_env_contains(
                temp_home, ["ANTHROPIC_API_KEY=sk-ant-new"], unexpected_lines=["sk-ant-old"]
            )

    @patch("builtins.input", return_value="y")
    def test_maybe_save_found_key_prompts_and_saves(self, mock_input, temp_home):
        """Detected key from file should prompt to save and persist when accepted."""
        detector = self._setup_detector_with_home(temp_home)

        with patch("pathlib.Path.home", return_value=temp_home):
            with patch.object(detector, "_save_key_to_env") as mock_save:
                # Use a file source (not environment) to test prompting
                detector._maybe_save_found_key(
                    "sk-ant-found", "anthropic", "~/.config/anthropic/credentials.json"
                )
                mock_save.assert_called_once_with("sk-ant-found", "anthropic")

    @patch("builtins.input")
    def test_maybe_save_found_key_skips_when_already_saved(self, mock_input, temp_home):
        """Skip save prompt when key already lives in ~/.cortex/.env."""
        detector = self._setup_detector_with_home(temp_home, "ANTHROPIC_API_KEY=sk-ant-existing\n")
        source = str(temp_home / ".cortex" / ".env")

        with patch("pathlib.Path.home", return_value=temp_home):
            with patch.object(detector, "_save_key_to_env") as mock_save:
                detector._maybe_save_found_key("sk-ant-existing", "anthropic", source)
                mock_input.assert_not_called()
                mock_save.assert_not_called()

    def test_provider_detection_from_key_format(self, detector):
        """Test provider detection based on key format."""
        assert detector._get_provider_from_var("ANTHROPIC_API_KEY") == "anthropic"
        assert detector._get_provider_from_var("OPENAI_API_KEY") == "openai"

    @patch("cortex.api_key_detector.cx_print")
    def test_prompt_for_key_user_input(self, mock_print, detector):
        """Test prompting user for key input."""
        # New flow: choice 1 (Claude), then key, then y to save
        with patch("builtins.input", side_effect=["1", "sk-ant-manual", "y"]):
            entered, key, provider = detector.prompt_for_key()
            assert entered is True
            assert key == "sk-ant-manual"
            assert provider == "anthropic"

    @patch("cortex.api_key_detector.cx_print")
    def test_prompt_for_key_invalid_format(self, mock_print, detector):
        """Test prompting with invalid key format."""
        # Choice 1 (Claude), but enter an invalid key
        with patch("builtins.input", side_effect=["1", "invalid-key"]):
            entered, _, _ = detector.prompt_for_key()
            assert entered is False

    @patch("cortex.api_key_detector.cx_print")
    def test_prompt_cancelled(self, mock_print, detector):
        """Test when user cancels prompt."""
        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            entered, _, _ = detector.prompt_for_key()
            assert entered is False

    @patch("cortex.api_key_detector.cx_print")
    def test_prompt_empty_input(self, mock_print, detector):
        """Test when user provides empty input."""
        # Choice 1 (Claude), but enter empty key
        with patch("builtins.input", side_effect=["1", ""]):
            entered, _, _ = detector.prompt_for_key()
            assert entered is False


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_auto_detect_api_key(self):
        """Test auto_detect_api_key function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use fresh detector with isolated cache
            def mock_detector_init(self, cache_dir=None):
                """Mock APIKeyDetector.__init__ to use temporary cache directory."""
                self.cache_dir = Path(tmpdir)
                self.cache_file = Path(tmpdir) / ".api_key_cache"

            with patch("cortex.api_key_detector.APIKeyDetector.__init__", mock_detector_init):
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True):
                    found, key, provider, _ = auto_detect_api_key()
                    assert found is True
                    assert key == "sk-ant-test"
                    assert provider == "anthropic"

    @patch("cortex.api_key_detector.APIKeyDetector._maybe_save_found_key")
    @patch("cortex.api_key_detector.APIKeyDetector.detect")
    @patch("cortex.api_key_detector.APIKeyDetector.prompt_for_key")
    def test_setup_api_key_auto_detect(self, mock_prompt, mock_detect, mock_save):
        """Test setup_api_key with auto-detection."""
        mock_detect.return_value = (True, "sk-ant-test", "anthropic", "env")

        success, key, provider = setup_api_key()
        assert success is True
        assert key == "sk-ant-test"
        assert provider == "anthropic"
        mock_save.assert_called_once_with("sk-ant-test", "anthropic", "env")

    @patch("cortex.api_key_detector.APIKeyDetector._maybe_save_found_key")
    @patch("cortex.api_key_detector.APIKeyDetector.detect")
    @patch("cortex.api_key_detector.APIKeyDetector.prompt_for_key")
    def test_setup_api_key_fallback_to_prompt(self, mock_prompt, mock_detect, mock_save):
        """Test setup_api_key falls back to prompt."""
        mock_detect.return_value = (False, None, None, None)
        mock_prompt.return_value = (True, "sk-ant-manual", "anthropic")

        success, key, provider = setup_api_key()
        assert success is True
        assert key == "sk-ant-manual"
        assert provider == "anthropic"
        mock_save.assert_not_called()

    @patch("cortex.api_key_detector.APIKeyDetector._maybe_save_found_key")
    @patch("cortex.api_key_detector.APIKeyDetector.detect")
    @patch("cortex.api_key_detector.APIKeyDetector.prompt_for_key")
    def test_setup_api_key_failure(self, mock_prompt, mock_detect, mock_save):
        """Test setup_api_key when both detection and prompt fail."""
        mock_detect.return_value = (False, None, None, None)
        mock_prompt.return_value = (False, None, None)

        success, key, provider = setup_api_key()
        assert success is False
        assert key is None
        assert provider is None
        mock_save.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
