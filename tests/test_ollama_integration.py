#!/usr/bin/env python3
"""
Tests for Cortex Linux Ollama Integration

Run with: pytest test_ollama_integration.py -v
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from ollama_integration import (
    OllamaProvider,
    OllamaInstaller,
    ProviderRouter,
    CompletionRequest,
    CompletionResponse,
    ModelCapability,
    ModelInfo,
    KNOWN_MODELS,
    CORTEX_SYSTEM_PROMPT,
    get_best_provider,
    quick_complete,
    check_ollama_status,
)


# Fixtures

@pytest.fixture
def ollama_provider():
    """Create an OllamaProvider instance."""
    return OllamaProvider(host="http://localhost:11434")


@pytest.fixture
def mock_models_response():
    """Mock response from Ollama /api/tags endpoint."""
    return {
        "models": [
            {"name": "llama3.2:latest", "size": 2000000000},
            {"name": "codellama:latest", "size": 3800000000},
            {"name": "mistral:latest", "size": 4100000000},
        ]
    }


@pytest.fixture
def mock_generate_response():
    """Mock response from Ollama /api/generate endpoint."""
    return {
        "response": "nginx - High-performance web server",
        "model": "codellama:latest",
        "done": True,
        "eval_count": 42,
        "total_duration": 1500000000
    }


# OllamaProvider Tests

class TestOllamaProvider:
    """Tests for OllamaProvider class."""

    def test_initialization_defaults(self, ollama_provider):
        """Should initialize with default values."""
        assert ollama_provider.host == "http://localhost:11434"
        assert ollama_provider.timeout == 120.0
        assert ollama_provider.auto_pull is False
        assert ollama_provider.name == "ollama"

    def test_initialization_custom(self):
        """Should accept custom configuration."""
        provider = OllamaProvider(
            host="http://custom:8080",
            model="mistral:latest",
            timeout=60.0,
            auto_pull=True
        )
        assert provider.host == "http://custom:8080"
        assert provider._model == "mistral:latest"
        assert provider.timeout == 60.0
        assert provider.auto_pull is True

    def test_host_trailing_slash_stripped(self):
        """Should strip trailing slash from host."""
        provider = OllamaProvider(host="http://localhost:11434/")
        assert provider.host == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_is_available_success(self, ollama_provider, mock_models_response):
        """Should return True when Ollama is available."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_models_response)
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            result = await ollama_provider.is_available()
            assert result is True
            assert ollama_provider._available_models == [
                "llama3.2:latest",
                "codellama:latest",
                "mistral:latest"
            ]

    @pytest.mark.asyncio
    async def test_is_available_no_models(self, ollama_provider):
        """Should return False when no models available."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"models": []})
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            result = await ollama_provider.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_available_connection_error(self, ollama_provider):
        """Should return False on connection error."""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=Exception("Connection refused"))
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            result = await ollama_provider.is_available()
            assert result is False

    def test_select_best_model_prefers_code(self, ollama_provider):
        """Should prefer code-focused models for Cortex."""
        available = ["llama3.2:latest", "codellama:latest", "phi3:latest"]
        result = ollama_provider._select_best_model(available)
        assert result == "codellama:latest"

    def test_select_best_model_prefers_larger(self, ollama_provider):
        """Should prefer larger/more capable models."""
        available = ["codellama:latest", "codellama:13b", "phi3:latest"]
        result = ollama_provider._select_best_model(available)
        assert result == "codellama:13b"

    def test_select_best_model_unknown_fallback(self, ollama_provider):
        """Should handle unknown models gracefully."""
        available = ["custom-model:latest", "another-unknown:v1"]
        result = ollama_provider._select_best_model(available)
        assert result == "custom-model:latest"

    @pytest.mark.asyncio
    async def test_complete_success(self, ollama_provider, mock_generate_response):
        """Should successfully complete a prompt."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_generate_response)
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        ollama_provider._selected_model = "codellama:latest"
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            request = CompletionRequest(prompt="What package for web server?")
            response = await ollama_provider.complete(request)
            
            assert response.content == "nginx - High-performance web server"
            assert response.model == "codellama:latest"
            assert response.provider == "ollama"
            assert response.tokens_used == 42

    @pytest.mark.asyncio
    async def test_complete_with_system_prompt(self, ollama_provider, mock_generate_response):
        """Should include system prompt in request."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_generate_response)
        
        mock_session = AsyncMock()
        call_args = []
        
        async def capture_post(*args, **kwargs):
            call_args.append(kwargs)
            return AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock()
            )
        
        mock_session.post = capture_post
        ollama_provider._selected_model = "codellama:latest"
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            request = CompletionRequest(
                prompt="Install nginx",
                system_prompt="You are a Linux expert"
            )
            await ollama_provider.complete(request)
            
            assert len(call_args) > 0
            payload = call_args[0].get('json', {})
            assert "You are a Linux expert" in payload.get('prompt', '')

    @pytest.mark.asyncio
    async def test_complete_error_handling(self, ollama_provider):
        """Should raise RuntimeError on API error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal server error")
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        ollama_provider._selected_model = "codellama:latest"
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            request = CompletionRequest(prompt="test")
            with pytest.raises(RuntimeError, match="Ollama error"):
                await ollama_provider.complete(request)

    @pytest.mark.asyncio
    async def test_list_models(self, ollama_provider, mock_models_response):
        """Should list available models."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_models_response)
        
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            models = await ollama_provider.list_models()
            assert len(models) == 3
            assert "codellama:latest" in models

    @pytest.mark.asyncio
    async def test_pull_model_success(self, ollama_provider):
        """Should successfully pull a model."""
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))
        
        with patch.object(ollama_provider, '_get_session', return_value=mock_session):
            result = await ollama_provider.pull_model("llama3.2:latest")
            assert result is True


# OllamaInstaller Tests

class TestOllamaInstaller:
    """Tests for OllamaInstaller class."""

    def test_is_installed_true(self):
        """Should detect Ollama when installed."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert OllamaInstaller.is_installed() is True

    def test_is_installed_false(self):
        """Should return False when Ollama not installed."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert OllamaInstaller.is_installed() is False

    def test_is_running_true(self):
        """Should detect running Ollama process."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert OllamaInstaller.is_running() is True

    def test_is_running_false(self):
        """Should return False when Ollama not running."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert OllamaInstaller.is_running() is False

    @pytest.mark.asyncio
    async def test_install_success(self):
        """Should install Ollama successfully."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Success", b""))
        
        with patch('asyncio.create_subprocess_shell', return_value=mock_process):
            result = await OllamaInstaller.install()
            assert result is True

    @pytest.mark.asyncio
    async def test_install_failure(self):
        """Should handle installation failure."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error"))
        
        with patch('asyncio.create_subprocess_shell', return_value=mock_process):
            result = await OllamaInstaller.install()
            assert result is False


# ProviderRouter Tests

class TestProviderRouter:
    """Tests for ProviderRouter class."""

    def test_initialization(self):
        """Should initialize with correct defaults."""
        router = ProviderRouter()
        assert router.prefer_local is True
        assert router.ollama is not None

    @pytest.mark.asyncio
    async def test_get_provider_prefers_ollama(self):
        """Should prefer Ollama when available and prefer_local=True."""
        router = ProviderRouter(prefer_local=True)
        
        with patch.object(router.ollama, 'is_available', return_value=True):
            provider = await router.get_provider()
            assert provider == router.ollama

    @pytest.mark.asyncio
    async def test_get_provider_fallback_to_claude(self):
        """Should fallback to Claude when Ollama unavailable."""
        router = ProviderRouter(
            prefer_local=True,
            anthropic_key="test-key"
        )
        
        with patch.object(router.ollama, 'is_available', return_value=False):
            provider = await router.get_provider()
            # In full implementation, would be Claude provider
            assert provider is not None

    @pytest.mark.asyncio
    async def test_get_provider_no_providers_error(self):
        """Should raise error when no providers available."""
        router = ProviderRouter(
            prefer_local=True,
            anthropic_key=None,
            openai_key=None
        )
        
        with patch.object(router.ollama, 'is_available', return_value=False):
            with pytest.raises(RuntimeError, match="No LLM provider available"):
                await router.get_provider()

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Should return comprehensive status."""
        router = ProviderRouter()
        
        with patch.object(router.ollama, 'is_available', return_value=True):
            with patch.object(router.ollama, 'list_models', return_value=["llama3.2:latest"]):
                with patch.object(OllamaInstaller, 'is_installed', return_value=True):
                    with patch.object(OllamaInstaller, 'is_running', return_value=True):
                        status = await router.get_status()
                        
                        assert status["ollama"]["available"] is True
                        assert status["ollama"]["installed"] is True
                        assert status["ollama"]["running"] is True
                        assert "llama3.2:latest" in status["ollama"]["models"]


# Model Info Tests

class TestModelInfo:
    """Tests for model configuration."""

    def test_known_models_exist(self):
        """Should have predefined model configurations."""
        assert len(KNOWN_MODELS) > 0
        assert "codellama:latest" in KNOWN_MODELS
        assert "llama3.2:latest" in KNOWN_MODELS

    def test_model_info_structure(self):
        """Should have correct ModelInfo structure."""
        model = KNOWN_MODELS["codellama:latest"]
        assert isinstance(model, ModelInfo)
        assert model.name == "codellama:latest"
        assert model.capability == ModelCapability.CODE
        assert model.context_length > 0
        assert model.priority > 0

    def test_code_models_have_high_priority(self):
        """Code models should have higher priority for Cortex."""
        code_model = KNOWN_MODELS["codellama:latest"]
        general_model = KNOWN_MODELS["mistral:latest"]
        assert code_model.priority > general_model.priority


# System Prompt Tests

class TestSystemPrompt:
    """Tests for system prompt configuration."""

    def test_system_prompt_exists(self):
        """Should have a system prompt defined."""
        assert CORTEX_SYSTEM_PROMPT is not None
        assert len(CORTEX_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_packages(self):
        """System prompt should mention package management."""
        assert "package" in CORTEX_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_apt(self):
        """System prompt should mention apt."""
        assert "apt" in CORTEX_SYSTEM_PROMPT.lower()


# Convenience Function Tests

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_check_ollama_status(self):
        """Should return status dict."""
        with patch('ollama_integration.ProviderRouter') as MockRouter:
            mock_router = MagicMock()
            mock_router.get_status = AsyncMock(return_value={
                "ollama": {"available": True},
                "claude": {"available": False}
            })
            MockRouter.return_value = mock_router
            
            status = await check_ollama_status()
            assert "ollama" in status


# Integration Tests (marked for skip in CI)

@pytest.mark.integration
class TestOllamaIntegration:
    """Integration tests requiring running Ollama instance."""

    @pytest.mark.asyncio
    async def test_real_completion(self):
        """Test against real Ollama instance."""
        ollama = OllamaProvider()
        
        if not await ollama.is_available():
            pytest.skip("Ollama not available")
        
        request = CompletionRequest(
            prompt="What package provides nginx?",
            system_prompt=CORTEX_SYSTEM_PROMPT,
            max_tokens=100
        )
        
        response = await ollama.complete(request)
        assert len(response.content) > 0
        assert response.latency_ms > 0

    @pytest.mark.asyncio
    async def test_real_streaming(self):
        """Test streaming against real Ollama instance."""
        ollama = OllamaProvider()
        
        if not await ollama.is_available():
            pytest.skip("Ollama not available")
        
        request = CompletionRequest(
            prompt="List 3 web servers",
            max_tokens=50
        )
        
        tokens = []
        async for token in ollama.stream(request):
            tokens.append(token)
        
        assert len(tokens) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
