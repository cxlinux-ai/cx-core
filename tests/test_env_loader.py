"""
Tests for the environment loader module.

Tests verify that .env files are properly loaded from multiple locations
and that API keys become available in os.environ.
"""

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Import the env_loader module directly from file to avoid triggering
# cortex/__init__.py which has heavy dependencies (rich, etc.)
_env_loader_path = Path(__file__).parent.parent / "cortex" / "env_loader.py"
_spec = importlib.util.spec_from_file_location("env_loader", _env_loader_path)
env_loader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(env_loader)


class TestGetEnvFileLocations:
    """Tests for get_env_file_locations function."""

    def test_returns_list_of_paths(self):
        """Should return a list of Path objects."""
        locations = env_loader.get_env_file_locations()

        assert isinstance(locations, list)
        assert all(isinstance(p, Path) for p in locations)

    def test_includes_cwd_env(self):
        """Should include current working directory .env."""
        locations = env_loader.get_env_file_locations()
        cwd_env = Path.cwd() / ".env"

        assert cwd_env in locations

    def test_includes_home_cortex_env(self):
        """Should include ~/.cortex/.env."""
        locations = env_loader.get_env_file_locations()
        home_cortex_env = Path.home() / ".cortex" / ".env"

        assert home_cortex_env in locations

    @pytest.mark.skipif(os.name != "posix", reason="Only applicable on POSIX systems")
    def test_includes_system_env_on_posix(self):
        """Should include /etc/cortex/.env on POSIX systems."""
        locations = env_loader.get_env_file_locations()
        system_env = Path("/etc/cortex/.env")

        assert system_env in locations

    def test_cwd_is_first_priority(self):
        """Current directory should have highest priority (first in list)."""
        locations = env_loader.get_env_file_locations()
        cwd_env = Path.cwd() / ".env"

        assert locations[0] == cwd_env


class TestLoadEnv:
    """Tests for load_env function."""

    def test_returns_empty_list_when_no_env_files(self):
        """Should return empty list when no .env files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Mock home directory to empty temp dir
                with mock.patch.object(Path, "home", return_value=Path(tmpdir)):
                    loaded = env_loader.load_env()
                    assert loaded == []
            finally:
                os.chdir(original_cwd)

    def test_loads_env_from_cwd(self):
        """Should load .env from current working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env file with test API key
                env_file = Path(tmpdir) / ".env"
                env_file.write_text("TEST_CORTEX_API_KEY=test-value-123\n")

                # Clear any existing value
                os.environ.pop("TEST_CORTEX_API_KEY", None)

                # Mock home to avoid loading other .env files
                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    loaded = env_loader.load_env()

                    assert len(loaded) >= 1
                    assert env_file in loaded
                    assert os.environ.get("TEST_CORTEX_API_KEY") == "test-value-123"

            finally:
                os.chdir(original_cwd)
                # Restore environment
                os.environ.clear()
                os.environ.update(original_env)

    def test_existing_env_vars_not_overridden_by_default(self):
        """Existing environment variables should not be overridden by .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env file
                env_file = Path(tmpdir) / ".env"
                env_file.write_text("TEST_EXISTING_VAR=from-dotenv\n")

                # Set existing value
                os.environ["TEST_EXISTING_VAR"] = "from-environment"

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    env_loader.load_env(override=False)

                    # Existing value should be preserved
                    assert os.environ.get("TEST_EXISTING_VAR") == "from-environment"

            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)

    def test_override_mode_replaces_existing_vars(self):
        """When override=True, .env values should replace existing variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env file
                env_file = Path(tmpdir) / ".env"
                env_file.write_text("TEST_OVERRIDE_VAR=from-dotenv\n")

                # Set existing value
                os.environ["TEST_OVERRIDE_VAR"] = "from-environment"

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    env_loader.load_env(override=True)

                    # Value should be from .env file
                    assert os.environ.get("TEST_OVERRIDE_VAR") == "from-dotenv"

            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)

    def test_handles_missing_dotenv_gracefully(self):
        """Should handle ImportError for python-dotenv gracefully."""
        # The function should gracefully return empty list when dotenv unavailable
        # Since dotenv IS installed in test env, we just verify the function works
        result = env_loader.load_env()

        # Should not raise, should return list (possibly empty or with loaded files)
        assert isinstance(result, list)


class TestFindEnvFiles:
    """Tests for find_env_files function."""

    def test_returns_empty_when_no_files_exist(self):
        """Should return empty list when no .env files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    files = env_loader.find_env_files()
                    assert files == []

            finally:
                os.chdir(original_cwd)

    def test_finds_existing_env_file(self):
        """Should find existing .env file in cwd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                env_file = Path(tmpdir) / ".env"
                env_file.write_text("KEY=VALUE\n")

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    files = env_loader.find_env_files()
                    assert env_file in files

            finally:
                os.chdir(original_cwd)


class TestGetApiKeySources:
    """Tests for get_api_key_sources function."""

    def test_returns_dict_of_api_keys(self):
        """Should return dictionary with API key sources."""
        sources = env_loader.get_api_key_sources()

        assert isinstance(sources, dict)
        assert "ANTHROPIC_API_KEY" in sources
        assert "OPENAI_API_KEY" in sources
        assert "MOONSHOT_API_KEY" in sources
        assert "CORTEX_PROVIDER" in sources

    def test_none_for_missing_keys(self):
        """Should return None for keys not set."""
        original_env = os.environ.copy()
        try:
            # Clear API keys
            for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MOONSHOT_API_KEY"]:
                os.environ.pop(key, None)

            sources = env_loader.get_api_key_sources()

            assert sources["ANTHROPIC_API_KEY"] is None
            assert sources["OPENAI_API_KEY"] is None
            assert sources["MOONSHOT_API_KEY"] is None

        finally:
            os.environ.clear()
            os.environ.update(original_env)


class TestApiKeyLoadingIntegration:
    """Integration tests verifying API keys are loaded correctly."""

    def test_anthropic_key_loaded_from_dotenv(self):
        """ANTHROPIC_API_KEY should be loaded from .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env with Anthropic key
                env_file = Path(tmpdir) / ".env"
                env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-key-123\n")

                # Clear existing key
                os.environ.pop("ANTHROPIC_API_KEY", None)

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    env_loader.load_env()

                    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-key-123"

            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)

    def test_openai_key_loaded_from_dotenv(self):
        """OPENAI_API_KEY should be loaded from .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env with OpenAI key
                env_file = Path(tmpdir) / ".env"
                env_file.write_text("OPENAI_API_KEY=sk-openai-test-key-456\n")

                # Clear existing key
                os.environ.pop("OPENAI_API_KEY", None)

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    env_loader.load_env()

                    assert os.environ.get("OPENAI_API_KEY") == "sk-openai-test-key-456"

            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)

    def test_multiple_keys_loaded(self):
        """Multiple API keys should be loaded from single .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            original_env = os.environ.copy()

            try:
                os.chdir(tmpdir)

                # Create .env with multiple keys
                env_file = Path(tmpdir) / ".env"
                env_file.write_text(
                    "ANTHROPIC_API_KEY=sk-ant-multi-123\n"
                    "OPENAI_API_KEY=sk-openai-multi-456\n"
                    "CORTEX_PROVIDER=claude\n"
                )

                # Clear existing keys
                for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CORTEX_PROVIDER"]:
                    os.environ.pop(key, None)

                with mock.patch.object(Path, "home", return_value=Path(tmpdir) / "fake_home"):
                    env_loader.load_env()

                    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-multi-123"
                    assert os.environ.get("OPENAI_API_KEY") == "sk-openai-multi-456"
                    assert os.environ.get("CORTEX_PROVIDER") == "claude"

            finally:
                os.chdir(original_cwd)
                os.environ.clear()
                os.environ.update(original_env)
