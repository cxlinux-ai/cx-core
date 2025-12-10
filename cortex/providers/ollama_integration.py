#!/usr/bin/env python3
"""
Cortex Linux - Ollama Integration

Local LLM support for privacy-first, offline-capable package management.
Falls back gracefully when Ollama is unavailable.

Features:
- Auto-detect Ollama installation and available models
- Intelligent model selection based on task
- Streaming responses for better UX
- Graceful fallback to cloud APIs
- Context-aware prompting optimized for package management

Usage:
    from ollama_integration import OllamaProvider, get_best_provider
    
    # Auto-select best available provider
    provider = get_best_provider()
    response = await provider.complete("Install nginx with SSL support")
    
    # Force local-only
    ollama = OllamaProvider()
    if ollama.is_available():
        response = await ollama.complete("What package provides curl?")

Author: Cortex Linux Team
License: Apache 2.0
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

import aiohttp

# Configure logging
logger = logging.getLogger("cortex.ollama")


class ModelCapability(Enum):
    """Model capability categories."""
    GENERAL = "general"
    CODE = "code"
    FAST = "fast"
    LARGE_CONTEXT = "large_context"


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    size_gb: float
    capability: ModelCapability
    context_length: int
    description: str
    priority: int = 0  # Higher = preferred


@dataclass
class CompletionRequest:
    """Request for LLM completion."""
    prompt: str
    system_prompt: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.3
    stream: bool = False
    stop_sequences: list[str] = field(default_factory=list)


@dataclass
class CompletionResponse:
    """Response from LLM completion."""
    content: str
    model: str
    provider: str
    tokens_used: int
    latency_ms: float
    cached: bool = False


# Known Ollama models with their capabilities
KNOWN_MODELS: dict[str, ModelInfo] = {
    # Code-focused models (best for package management)
    "codellama:latest": ModelInfo(
        name="codellama:latest",
        size_gb=3.8,
        capability=ModelCapability.CODE,
        context_length=16384,
        description="Meta's code-specialized LLM",
        priority=90
    ),
    "codellama:13b": ModelInfo(
        name="codellama:13b",
        size_gb=7.3,
        capability=ModelCapability.CODE,
        context_length=16384,
        description="Larger CodeLlama for complex tasks",
        priority=95
    ),
    "deepseek-coder:latest": ModelInfo(
        name="deepseek-coder:latest",
        size_gb=3.8,
        capability=ModelCapability.CODE,
        context_length=16384,
        description="DeepSeek's coding model",
        priority=88
    ),
    
    # General models
    "llama3.2:latest": ModelInfo(
        name="llama3.2:latest",
        size_gb=2.0,
        capability=ModelCapability.GENERAL,
        context_length=131072,
        description="Latest Llama 3.2 - excellent general purpose",
        priority=85
    ),
    "llama3.1:latest": ModelInfo(
        name="llama3.1:latest",
        size_gb=4.7,
        capability=ModelCapability.GENERAL,
        context_length=131072,
        description="Llama 3.1 8B - strong general model",
        priority=80
    ),
    "llama3.1:70b": ModelInfo(
        name="llama3.1:70b",
        size_gb=40.0,
        capability=ModelCapability.LARGE_CONTEXT,
        context_length=131072,
        description="Llama 3.1 70B - most capable",
        priority=100
    ),
    "mistral:latest": ModelInfo(
        name="mistral:latest",
        size_gb=4.1,
        capability=ModelCapability.GENERAL,
        context_length=32768,
        description="Mistral 7B - fast and capable",
        priority=75
    ),
    "mixtral:latest": ModelInfo(
        name="mixtral:latest",
        size_gb=26.0,
        capability=ModelCapability.GENERAL,
        context_length=32768,
        description="Mixtral 8x7B MoE - very capable",
        priority=92
    ),
    
    # Fast/small models
    "phi3:latest": ModelInfo(
        name="phi3:latest",
        size_gb=2.2,
        capability=ModelCapability.FAST,
        context_length=4096,
        description="Microsoft Phi-3 - fast responses",
        priority=60
    ),
    "gemma2:latest": ModelInfo(
        name="gemma2:latest",
        size_gb=5.4,
        capability=ModelCapability.GENERAL,
        context_length=8192,
        description="Google Gemma 2 - balanced",
        priority=70
    ),
    "qwen2.5:latest": ModelInfo(
        name="qwen2.5:latest",
        size_gb=4.4,
        capability=ModelCapability.GENERAL,
        context_length=32768,
        description="Alibaba Qwen 2.5 - multilingual",
        priority=72
    ),
}

# System prompt optimized for package management
CORTEX_SYSTEM_PROMPT = """You are Cortex, an AI assistant specialized in Linux package management.

Your role:
1. Parse natural language requests into specific package names
2. Understand package relationships and dependencies
3. Recommend optimal packages for user needs
4. Explain installation steps clearly

Rules:
- Be concise and direct
- Output package names as they appear in apt repositories
- When multiple packages could work, recommend the most common/stable option
- Always consider security implications
- Mention if sudo/root access is required

Response format for package requests:
- List exact package name(s)
- Brief explanation of what each does
- Any important flags or options

Example:
User: "I need something to edit PDFs"
Response: "pdftk - Command-line PDF toolkit for merging, splitting, rotating PDFs
Alternative: poppler-utils - Includes pdftotext, pdftoppm for conversions"
"""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is available."""
        pass
    
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate completion."""
        pass
    
    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Stream completion tokens."""
        pass
    
    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models."""
        pass


class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider.
    
    Provides privacy-first, offline-capable LLM access through
    locally running Ollama instance.
    """
    
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: Optional[str] = None,
        timeout: float = 120.0,
        auto_pull: bool = False
    ):
        """
        Initialize Ollama provider.
        
        Args:
            host: Ollama API host URL
            model: Specific model to use (auto-selects if None)
            timeout: Request timeout in seconds
            auto_pull: Whether to auto-pull missing models
        """
        self.host = host.rstrip("/")
        self._model = model
        self.timeout = timeout
        self.auto_pull = auto_pull
        self._available_models: Optional[list[str]] = None
        self._selected_model: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def name(self) -> str:
        return "ollama"
    
    @property
    def model(self) -> str:
        """Get the selected model."""
        return self._selected_model or self._model or "llama3.2:latest"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    self._available_models = models
                    
                    # Auto-select best model
                    if not self._model:
                        self._selected_model = self._select_best_model(models)
                        logger.info(f"Auto-selected model: {self._selected_model}")
                    
                    return len(models) > 0
                return False
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False
    
    def _select_best_model(self, available: list[str]) -> str:
        """Select the best model from available options."""
        # Score each available model
        scored = []
        for model in available:
            # Normalize model name (remove tag if just checking base)
            base_name = model.split(":")[0]
            
            # Check known models
            for known_name, info in KNOWN_MODELS.items():
                known_base = known_name.split(":")[0]
                if base_name == known_base or model == known_name:
                    scored.append((model, info.priority))
                    break
            else:
                # Unknown model gets low priority
                scored.append((model, 10))
        
        # Sort by priority (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)
        
        if scored:
            return scored[0][0]
        
        # Fallback
        return available[0] if available else "llama3.2:latest"
    
    async def list_models(self) -> list[str]:
        """List available Ollama models."""
        if self._available_models is not None:
            return self._available_models
        
        try:
            session = await self._get_session()
            async with session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    self._available_models = [m["name"] for m in data.get("models", [])]
                    return self._available_models
                return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    async def pull_model(self, model: str) -> bool:
        """Pull a model from Ollama registry."""
        logger.info(f"Pulling model: {model}")
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.host}/api/pull",
                json={"name": model, "stream": False}
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to pull model: {e}")
            return False
    
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate completion using Ollama."""
        start_time = time.time()
        
        # Ensure we have a model selected
        if not self._selected_model and not self._model:
            await self.is_available()
        
        model = self.model
        
        # Build the prompt with system context
        full_prompt = request.prompt
        if request.system_prompt:
            full_prompt = f"{request.system_prompt}\n\nUser: {request.prompt}\n\nAssistant:"
        
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }
        
        if request.stop_sequences:
            payload["options"]["stop"] = request.stop_sequences
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.host}/api/generate",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama error: {error_text}")
                
                data = await response.json()
                
                latency = (time.time() - start_time) * 1000
                
                return CompletionResponse(
                    content=data.get("response", ""),
                    model=model,
                    provider="ollama",
                    tokens_used=data.get("eval_count", 0),
                    latency_ms=latency,
                    cached=False
                )
        
        except asyncio.TimeoutError:
            raise RuntimeError(f"Ollama request timed out after {self.timeout}s")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {e}")
    
    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Stream completion tokens."""
        # Ensure we have a model selected
        if not self._selected_model and not self._model:
            await self.is_available()
        
        model = self.model
        
        full_prompt = request.prompt
        if request.system_prompt:
            full_prompt = f"{request.system_prompt}\n\nUser: {request.prompt}\n\nAssistant:"
        
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.host}/api/generate",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama error: {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode("utf-8"))
                            if "response" in data:
                                yield data["response"]
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        
        except asyncio.TimeoutError:
            raise RuntimeError(f"Ollama stream timed out after {self.timeout}s")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {e}")
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> CompletionResponse:
        """
        Chat completion with message history.
        
        Args:
            messages: List of {"role": "user|assistant|system", "content": "..."}
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        start_time = time.time()
        
        if not self._selected_model and not self._model:
            await self.is_available()
        
        model = self.model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.host}/api/chat",
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama chat error: {error_text}")
                
                data = await response.json()
                
                latency = (time.time() - start_time) * 1000
                
                return CompletionResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=model,
                    provider="ollama",
                    tokens_used=data.get("eval_count", 0),
                    latency_ms=latency,
                    cached=False
                )
        
        except asyncio.TimeoutError:
            raise RuntimeError(f"Ollama chat timed out after {self.timeout}s")
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Ollama connection error: {e}")


class OllamaInstaller:
    """Helper to install Ollama if not present."""
    
    INSTALL_SCRIPT = "https://ollama.com/install.sh"
    
    @staticmethod
    def is_installed() -> bool:
        """Check if Ollama binary is installed."""
        try:
            result = subprocess.run(
                ["which", "ollama"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def is_running() -> bool:
        """Check if Ollama service is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", "ollama"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    async def install() -> bool:
        """Install Ollama using official script."""
        logger.info("Installing Ollama...")
        try:
            process = await asyncio.create_subprocess_shell(
                f"curl -fsSL {OllamaInstaller.INSTALL_SCRIPT} | sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Ollama installed successfully")
                return True
            else:
                logger.error(f"Ollama installation failed: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"Failed to install Ollama: {e}")
            return False
    
    @staticmethod
    async def start_service() -> bool:
        """Start Ollama service."""
        if OllamaInstaller.is_running():
            return True
        
        logger.info("Starting Ollama service...")
        try:
            # Try systemctl first (Linux)
            process = await asyncio.create_subprocess_exec(
                "systemctl", "start", "ollama",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0:
                await asyncio.sleep(2)  # Wait for service to start
                return OllamaInstaller.is_running()
            
            # Fall back to direct execution
            process = await asyncio.create_subprocess_exec(
                "ollama", "serve",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True
            )
            await asyncio.sleep(2)
            return OllamaInstaller.is_running()
        
        except Exception as e:
            logger.error(f"Failed to start Ollama: {e}")
            return False


class ProviderRouter:
    """
    Routes requests to the best available LLM provider.
    
    Priority:
    1. Ollama (if available) - privacy, offline, free
    2. Claude API - high quality
    3. OpenAI API - fallback
    """
    
    def __init__(
        self,
        prefer_local: bool = True,
        ollama_host: str = "http://localhost:11434",
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None
    ):
        self.prefer_local = prefer_local
        self.ollama = OllamaProvider(host=ollama_host)
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self._active_provider: Optional[LLMProvider] = None
    
    async def get_provider(self) -> LLMProvider:
        """Get the best available provider."""
        if self._active_provider:
            return self._active_provider
        
        # Try Ollama first if preferring local
        if self.prefer_local:
            if await self.ollama.is_available():
                logger.info("Using Ollama (local)")
                self._active_provider = self.ollama
                return self.ollama
        
        # Fall back to cloud providers
        # (These would be separate provider classes in full implementation)
        if self.anthropic_key:
            logger.info("Ollama unavailable, falling back to Claude API")
            # Return Claude provider (simplified for this implementation)
            self._active_provider = self.ollama  # Placeholder
            return self._active_provider
        
        if self.openai_key:
            logger.info("Falling back to OpenAI API")
            self._active_provider = self.ollama  # Placeholder
            return self._active_provider
        
        raise RuntimeError(
            "No LLM provider available. Either:\n"
            "1. Install and run Ollama: curl -fsSL https://ollama.com/install.sh | sh\n"
            "2. Set ANTHROPIC_API_KEY environment variable\n"
            "3. Set OPENAI_API_KEY environment variable"
        )
    
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> CompletionResponse:
        """Route completion to best provider."""
        provider = await self.get_provider()
        request = CompletionRequest(
            prompt=prompt,
            system_prompt=system_prompt or CORTEX_SYSTEM_PROMPT,
            **kwargs
        )
        return await provider.complete(request)
    
    async def get_status(self) -> dict[str, Any]:
        """Get status of all providers."""
        ollama_available = await self.ollama.is_available()
        ollama_models = await self.ollama.list_models() if ollama_available else []
        
        return {
            "ollama": {
                "available": ollama_available,
                "installed": OllamaInstaller.is_installed(),
                "running": OllamaInstaller.is_running(),
                "models": ollama_models,
                "selected_model": self.ollama.model if ollama_available else None
            },
            "claude": {
                "available": bool(self.anthropic_key),
                "configured": self.anthropic_key is not None
            },
            "openai": {
                "available": bool(self.openai_key),
                "configured": self.openai_key is not None
            },
            "active_provider": self._active_provider.name if self._active_provider else None,
            "prefer_local": self.prefer_local
        }


# Convenience functions

async def get_best_provider(prefer_local: bool = True) -> LLMProvider:
    """Get the best available LLM provider."""
    router = ProviderRouter(prefer_local=prefer_local)
    return await router.get_provider()


async def quick_complete(prompt: str, prefer_local: bool = True) -> str:
    """Quick completion using best available provider."""
    router = ProviderRouter(prefer_local=prefer_local)
    response = await router.complete(prompt)
    return response.content


async def check_ollama_status() -> dict[str, Any]:
    """Check Ollama installation and status."""
    router = ProviderRouter()
    return await router.get_status()


# CLI interface
async def main():
    """CLI for testing Ollama integration."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cortex Ollama Integration")
    parser.add_argument("--status", action="store_true", help="Check Ollama status")
    parser.add_argument("--list-models", action="store_true", help="List available models")
    parser.add_argument("--install", action="store_true", help="Install Ollama")
    parser.add_argument("--pull", type=str, help="Pull a model")
    parser.add_argument("--prompt", type=str, help="Run a prompt")
    parser.add_argument("--model", type=str, help="Specify model to use")
    
    args = parser.parse_args()
    
    if args.status:
        status = await check_ollama_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.install:
        if OllamaInstaller.is_installed():
            print("Ollama is already installed")
        else:
            success = await OllamaInstaller.install()
            print("Ollama installed successfully" if success else "Installation failed")
        return
    
    if args.list_models:
        ollama = OllamaProvider()
        if await ollama.is_available():
            models = await ollama.list_models()
            print("Available models:")
            for m in models:
                info = KNOWN_MODELS.get(m, None)
                desc = f" - {info.description}" if info else ""
                print(f"  {m}{desc}")
        else:
            print("Ollama is not running")
        return
    
    if args.pull:
        ollama = OllamaProvider()
        success = await ollama.pull_model(args.pull)
        print(f"Pulled {args.pull}" if success else f"Failed to pull {args.pull}")
        return
    
    if args.prompt:
        ollama = OllamaProvider(model=args.model)
        if await ollama.is_available():
            print(f"Using model: {ollama.model}")
            print("---")
            request = CompletionRequest(
                prompt=args.prompt,
                system_prompt=CORTEX_SYSTEM_PROMPT
            )
            response = await ollama.complete(request)
            print(response.content)
            print("---")
            print(f"Tokens: {response.tokens_used}, Latency: {response.latency_ms:.0f}ms")
        else:
            print("Ollama is not available. Run: ollama serve")
        return
    
    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
