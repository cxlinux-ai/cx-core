#!/usr/bin/env python3
"""
LLM Router for Cortex Linux
Routes requests to the most appropriate LLM based on task type.

Supports:
- Ollama (Local) - Privacy-first, offline-capable, no API keys needed
- Claude API (Anthropic) - Best for natural language, chat, requirement parsing
- Kimi K2 API (Moonshot) - Best for system operations, debugging, tool use

Author: Cortex Linux Team
License: Apache 2.0
"""

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from anthropic import Anthropic, AsyncAnthropic
from openai import AsyncOpenAI, OpenAI

from cortex.providers.ollama_provider import OllamaProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks that determine LLM routing."""

    USER_CHAT = "user_chat"  # General conversation
    REQUIREMENT_PARSING = "requirement_parsing"  # Understanding user needs
    SYSTEM_OPERATION = "system_operation"  # Package install, config
    ERROR_DEBUGGING = "error_debugging"  # Diagnosing failures
    CODE_GENERATION = "code_generation"  # Writing scripts
    DEPENDENCY_RESOLUTION = "dependency_resolution"  # Figuring out deps
    CONFIGURATION = "configuration"  # System config files
    TOOL_EXECUTION = "tool_execution"  # Running system tools


class LLMProvider(Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"  # Local LLM via Ollama
    CLAUDE = "claude"
    KIMI_K2 = "kimi_k2"


@dataclass
class LLMResponse:
    """Standardized response from any LLM."""

    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    raw_response: dict | None = None


@dataclass
class RoutingDecision:
    """Details about why a specific LLM was chosen."""

    provider: LLMProvider
    task_type: TaskType
    reasoning: str
    confidence: float  # 0.0 to 1.0


class LLMRouter:
    """
    Intelligent router that selects the best LLM for each task.

    Routing Logic:
    - User-facing tasks → Claude (better at natural language)
    - System operations → Kimi K2 (65.8% SWE-bench, beats Claude)
    - Error debugging → Kimi K2 (better at technical problem-solving)
    - Complex installs → Kimi K2 (superior agentic capabilities)

    Includes fallback logic if primary LLM fails.
    """

    # Cost per 1M tokens (estimated, update with actual pricing)
    COSTS = {
        LLMProvider.OLLAMA: {
            "input": 0.0,  # Free - runs locally
            "output": 0.0,  # Free - runs locally
        },
        LLMProvider.CLAUDE: {
            "input": 3.0,  # $3 per 1M input tokens
            "output": 15.0,  # $15 per 1M output tokens
        },
        LLMProvider.KIMI_K2: {
            "input": 1.0,  # Estimated lower cost
            "output": 5.0,  # Estimated lower cost
        },
    }

    # Routing rules: TaskType → Preferred LLM
    # Default to Ollama for privacy and offline capability
    # Falls back to cloud providers if Ollama unavailable
    ROUTING_RULES = {
        TaskType.USER_CHAT: LLMProvider.OLLAMA,
        TaskType.REQUIREMENT_PARSING: LLMProvider.OLLAMA,
        TaskType.SYSTEM_OPERATION: LLMProvider.OLLAMA,
        TaskType.ERROR_DEBUGGING: LLMProvider.OLLAMA,
        TaskType.CODE_GENERATION: LLMProvider.OLLAMA,
        TaskType.DEPENDENCY_RESOLUTION: LLMProvider.OLLAMA,
        TaskType.CONFIGURATION: LLMProvider.OLLAMA,
        TaskType.TOOL_EXECUTION: LLMProvider.OLLAMA,
    }

    def __init__(
        self,
        claude_api_key: str | None = None,
        kimi_api_key: str | None = None,
        default_provider: LLMProvider = LLMProvider.OLLAMA,
        enable_fallback: bool = True,
        track_costs: bool = True,
        prefer_local: bool = True,
    ):
        """
        Initialize LLM Router.

        Args:
            claude_api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env)
            kimi_api_key: Moonshot API key (defaults to MOONSHOT_API_KEY env)
            default_provider: Fallback provider if routing fails
            enable_fallback: Try alternate LLM if primary fails
            track_costs: Track token usage and costs
            prefer_local: Prefer Ollama over cloud providers when available
        """
        self.claude_api_key = claude_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.kimi_api_key = kimi_api_key or os.getenv("MOONSHOT_API_KEY")
        self.default_provider = default_provider
        self.enable_fallback = enable_fallback
        self.track_costs = track_costs
        self.prefer_local = prefer_local

        # Initialize Ollama provider
        self.ollama_client = None
        self.ollama_has_models = False
        try:
            # Initialize without auto-pull during setup to avoid long delays
            ollama_temp = OllamaProvider(auto_pull=False)
            if ollama_temp.is_installed():
                logger.info("✅ Ollama provider initialized (local, privacy-first)")
                # Try to ensure service is running and model is available
                if ollama_temp.is_running() or ollama_temp.start_service():
                    model = ollama_temp.select_best_model()
                    if model:
                        logger.info(f"✅ Using local model: {model}")
                        self.ollama_client = ollama_temp
                        self.ollama_has_models = True
                    else:
                        logger.warning("⚠️  Ollama running but no models available")
                        logger.info(
                            "💡 Run 'cortex-setup-ollama' or 'ollama pull <model>' to download a model"
                        )
                else:
                    logger.warning("⚠️  Ollama installed but service not running")
            else:
                logger.info("ℹ️  Ollama not installed - will use cloud providers")
        except Exception as e:
            logger.warning(f"⚠️  Ollama initialization failed: {e}")

        # Initialize clients (sync)
        self.claude_client = None
        self.kimi_client = None

        # Initialize async clients
        self.claude_client_async = None
        self.kimi_client_async = None

        if self.claude_api_key:
            self.claude_client = Anthropic(api_key=self.claude_api_key)
            self.claude_client_async = AsyncAnthropic(api_key=self.claude_api_key)
            logger.info("✅ Claude API client initialized")
        else:
            logger.warning("⚠️  No Claude API key provided")

        if self.kimi_api_key:
            self.kimi_client = OpenAI(
                api_key=self.kimi_api_key, base_url="https://api.moonshot.ai/v1"
            )
            self.kimi_client_async = AsyncOpenAI(
                api_key=self.kimi_api_key, base_url="https://api.moonshot.ai/v1"
            )
            logger.info("✅ Kimi K2 API client initialized")
        else:
            logger.warning("⚠️  No Kimi K2 API key provided")

        # Rate limiting for parallel calls
        self._rate_limit_semaphore: asyncio.Semaphore | None = None

        # Cost tracking (protected by lock for thread-safety)
        self._stats_lock = threading.Lock()
        self.total_cost_usd = 0.0
        self.request_count = 0
        self.provider_stats = {
            LLMProvider.OLLAMA: {"requests": 0, "tokens": 0, "cost": 0.0},
            LLMProvider.CLAUDE: {"requests": 0, "tokens": 0, "cost": 0.0},
            LLMProvider.KIMI_K2: {"requests": 0, "tokens": 0, "cost": 0.0},
        }

        # Check if we have ANY usable LLM
        if not self.ollama_has_models and not self.claude_client and not self.kimi_client:
            error_msg = (
                "\n❌ No LLM providers available!\n\n"
                "Cortex needs at least one of the following:\n"
                "  1. Local Ollama with a model installed:\n"
                "     → Run: cortex-setup-ollama\n"
                "     → Or: ollama pull codellama:7b\n\n"
                "  2. Cloud API key configured:\n"
                "     → Set ANTHROPIC_API_KEY in .env file\n"
                "     → Or: export ANTHROPIC_API_KEY=your-key\n\n"
                "For more help: https://github.com/cortexlinux/cortex\n"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def route_task(
        self, task_type: TaskType, force_provider: LLMProvider | None = None
    ) -> RoutingDecision:
        """
        Determine which LLM should handle this task.

        Args:
            task_type: Type of task to route
            force_provider: Override routing logic (for testing)

        Returns:
            RoutingDecision with provider and reasoning
        """
        if force_provider:
            return RoutingDecision(
                provider=force_provider,
                task_type=task_type,
                reasoning="Forced by caller",
                confidence=1.0,
            )

        # Use routing rules
        provider = self.ROUTING_RULES.get(task_type, self.default_provider)

        # Check if preferred provider is available (with smart fallback)
        if provider == LLMProvider.OLLAMA and not self.ollama_has_models:
            # Ollama unavailable or no models, fall back to cloud providers
            if self.claude_client and self.enable_fallback:
                logger.warning("Ollama unavailable, falling back to Claude")
                provider = LLMProvider.CLAUDE
            elif self.kimi_client and self.enable_fallback:
                logger.warning("Ollama unavailable, falling back to Kimi K2")
                provider = LLMProvider.KIMI_K2
            else:
                raise RuntimeError("No LLM providers available")

        if provider == LLMProvider.CLAUDE and not self.claude_client:
            if self.ollama_has_models and self.enable_fallback:
                logger.warning("Claude unavailable, falling back to Ollama")
                provider = LLMProvider.OLLAMA
            elif self.kimi_client and self.enable_fallback:
                logger.warning("Claude unavailable, falling back to Kimi K2")
                provider = LLMProvider.KIMI_K2
            else:
                raise RuntimeError("Claude API not configured and no fallback available")

        if provider == LLMProvider.KIMI_K2 and not self.kimi_client:
            if self.ollama_has_models and self.enable_fallback:
                logger.warning("Kimi K2 unavailable, falling back to Ollama")
                provider = LLMProvider.OLLAMA
            elif self.claude_client and self.enable_fallback:
                logger.warning("Kimi K2 unavailable, falling back to Claude")
                provider = LLMProvider.CLAUDE
            else:
                raise RuntimeError("Kimi K2 API not configured and no fallback available")

        reasoning = f"{task_type.value} → {provider.value} (optimal for this task)"

        return RoutingDecision(
            provider=provider, task_type=task_type, reasoning=reasoning, confidence=0.95
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        task_type: TaskType = TaskType.USER_CHAT,
        force_provider: LLMProvider | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        _attempted_providers: set[LLMProvider] | None = None,
    ) -> LLMResponse:
        """
        Generate completion using the most appropriate LLM.

        Args:
            messages: Chat messages in OpenAI format
            task_type: Type of task (determines routing)
            force_provider: Override routing decision
            temperature: Sampling temperature
            max_tokens: Maximum response length
            tools: Tool definitions for function calling
            _attempted_providers: Internal - tracks providers tried (prevents infinite loop)

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        # Track attempted providers to prevent infinite recursion
        if _attempted_providers is None:
            _attempted_providers = set()

        # Route to appropriate LLM
        routing = self.route_task(task_type, force_provider)
        logger.info(f"🧭 Routing: {routing.reasoning}")

        # Check if we've already tried this provider (prevent infinite loop)
        if routing.provider in _attempted_providers:
            available_providers = []
            if self.ollama_has_models:
                available_providers.append("Ollama (local)")
            if self.claude_client:
                available_providers.append("Claude")
            if self.kimi_client:
                available_providers.append("Kimi K2")

            raise RuntimeError(
                f"All available LLM providers have been attempted and failed.\n"
                f"Available providers: {', '.join(available_providers) if available_providers else 'None'}\n"
                f"Please check your configuration and try again."
            )

        _attempted_providers.add(routing.provider)

        try:
            if routing.provider == LLMProvider.OLLAMA:
                response = self._complete_ollama(messages, temperature, max_tokens)
            elif routing.provider == LLMProvider.CLAUDE:
                response = self._complete_claude(messages, temperature, max_tokens, tools)
            else:  # KIMI_K2
                response = self._complete_kimi(messages, temperature, max_tokens, tools)

            response.latency_seconds = time.time() - start_time

            # Track stats
            if self.track_costs:
                self._update_stats(response)

            return response

        except Exception as e:
            logger.error(f"❌ Error with {routing.provider.value}: {e}")

            # Try fallback if enabled
            if self.enable_fallback:
                # Smart fallback priority: Local → Cloud
                if routing.provider == LLMProvider.OLLAMA:
                    fallback_provider = (
                        LLMProvider.CLAUDE
                        if self.claude_client
                        else LLMProvider.KIMI_K2 if self.kimi_client else None
                    )
                elif routing.provider == LLMProvider.CLAUDE:
                    fallback_provider = (
                        LLMProvider.OLLAMA
                        if self.ollama_has_models
                        else LLMProvider.KIMI_K2 if self.kimi_client else None
                    )
                else:  # KIMI_K2
                    fallback_provider = (
                        LLMProvider.OLLAMA
                        if self.ollama_has_models
                        else LLMProvider.CLAUDE if self.claude_client else None
                    )

                if fallback_provider:
                    logger.info(f"🔄 Attempting fallback to {fallback_provider.value}")

                    return self.complete(
                        messages=messages,
                        task_type=task_type,
                        force_provider=fallback_provider,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=tools,
                        _attempted_providers=_attempted_providers,
                    )
                else:
                    raise RuntimeError("No fallback provider available")
            else:
                raise

    def _complete_ollama(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """
        Complete using Ollama local LLM.

        Args:
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Max response tokens

        Returns:
            LLMResponse with standardized format
        """
        if not self.ollama_client:
            raise RuntimeError("Ollama client not initialized")

        start_time = time.time()

        response_data = self.ollama_client.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        content = response_data.get("response", "")
        model = response_data.get("model", "unknown")

        # Ollama doesn't provide token counts in the same way
        # Estimate based on response length
        tokens_used = len(content.split()) * 1.3  # Rough estimate

        return LLMResponse(
            content=content,
            provider=LLMProvider.OLLAMA,
            model=model,
            tokens_used=int(tokens_used),
            cost_usd=0.0,  # Local models are free
            latency_seconds=time.time() - start_time,
            raw_response=response_data,
        )

    def _complete_claude(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate completion using Claude API."""
        # Extract system message if present
        system_message = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        # Call Claude API
        kwargs = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }

        if system_message:
            kwargs["system"] = system_message

        if tools:
            # Convert OpenAI tool format to Claude format if needed
            kwargs["tools"] = tools

        response = self.claude_client.messages.create(**kwargs)

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(LLMProvider.CLAUDE, input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-20250514",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    def _complete_kimi(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Generate completion using Kimi K2 API."""
        # Kimi K2 recommends temperature=0.6
        # Map user's temperature to Kimi's scale
        kimi_temp = temperature * 0.6

        kwargs = {
            "model": "kimi-k2-instruct",
            "messages": messages,
            "temperature": kimi_temp,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.kimi_client.chat.completions.create(**kwargs)

        # Extract content
        content = response.choices[0].message.content or ""

        # Calculate cost
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = self._calculate_cost(LLMProvider.KIMI_K2, input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            provider=LLMProvider.KIMI_K2,
            model="kimi-k2-instruct",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    def _calculate_cost(
        self, provider: LLMProvider, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost in USD for this request."""
        costs = self.COSTS[provider]
        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (output_tokens / 1_000_000) * costs["output"]
        return input_cost + output_cost

    def _update_stats(self, response: LLMResponse):
        """Update usage statistics (thread-safe)."""
        with self._stats_lock:
            self.total_cost_usd += response.cost_usd
            self.request_count += 1

            stats = self.provider_stats[response.provider]
            stats["requests"] += 1
            stats["tokens"] += response.tokens_used
            stats["cost"] += response.cost_usd

    def get_stats(self) -> dict[str, Any]:
        """
        Get usage statistics (thread-safe).

        Returns:
            Dictionary with request counts, tokens, costs per provider
        """
        with self._stats_lock:
            return {
                "total_requests": self.request_count,
                "total_cost_usd": round(self.total_cost_usd, 4),
                "providers": {
                    "claude": {
                        "requests": self.provider_stats[LLMProvider.CLAUDE]["requests"],
                        "tokens": self.provider_stats[LLMProvider.CLAUDE]["tokens"],
                        "cost_usd": round(self.provider_stats[LLMProvider.CLAUDE]["cost"], 4),
                    },
                    "kimi_k2": {
                        "requests": self.provider_stats[LLMProvider.KIMI_K2]["requests"],
                        "tokens": self.provider_stats[LLMProvider.KIMI_K2]["tokens"],
                        "cost_usd": round(self.provider_stats[LLMProvider.KIMI_K2]["cost"], 4),
                    },
                },
            }

    def reset_stats(self):
        """Reset all usage statistics."""
        self.total_cost_usd = 0.0
        self.request_count = 0
        for provider in self.provider_stats:
            self.provider_stats[provider] = {"requests": 0, "tokens": 0, "cost": 0.0}

    def set_rate_limit(self, max_concurrent: int = 10):
        """
        Set rate limit for parallel API calls.

        Args:
            max_concurrent: Maximum number of concurrent API calls
        """
        self._rate_limit_semaphore = asyncio.Semaphore(max_concurrent)

    async def acomplete(
        self,
        messages: list[dict[str, str]],
        task_type: TaskType = TaskType.USER_CHAT,
        force_provider: LLMProvider | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """
        Async version of complete() - Generate completion using the most appropriate LLM.

        Args:
            messages: Chat messages in OpenAI format
            task_type: Type of task (determines routing)
            force_provider: Override routing decision
            temperature: Sampling temperature
            max_tokens: Maximum response length
            tools: Tool definitions for function calling

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        # Route to appropriate LLM
        routing = self.route_task(task_type, force_provider)
        logger.info(f"🧭 Routing: {routing.reasoning}")

        try:
            if routing.provider == LLMProvider.CLAUDE:
                response = await self._acomplete_claude(messages, temperature, max_tokens, tools)
            else:  # KIMI_K2
                response = await self._acomplete_kimi(messages, temperature, max_tokens, tools)

            response.latency_seconds = time.time() - start_time

            # Track stats
            if self.track_costs:
                self._update_stats(response)

            return response

        except Exception as e:
            logger.error(f"❌ Error with {routing.provider.value}: {e}")

            # Try fallback if enabled
            if self.enable_fallback:
                fallback_provider = (
                    LLMProvider.KIMI_K2
                    if routing.provider == LLMProvider.CLAUDE
                    else LLMProvider.CLAUDE
                )
                logger.info(f"🔄 Attempting fallback to {fallback_provider.value}")

                return await self.acomplete(
                    messages=messages,
                    task_type=task_type,
                    force_provider=fallback_provider,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )
            else:
                raise

    async def _acomplete_claude(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Async: Generate completion using Claude API."""
        if not self.claude_client_async:
            raise RuntimeError("Claude async client not initialized")

        # Extract system message if present
        system_message = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        # Call Claude API
        kwargs = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }

        if system_message:
            kwargs["system"] = system_message

        if tools:
            kwargs["tools"] = tools

        response = await self.claude_client_async.messages.create(**kwargs)

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(LLMProvider.CLAUDE, input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-20250514",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def _acomplete_kimi(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Async: Generate completion using Kimi K2 API."""
        if not self.kimi_client_async:
            raise RuntimeError("Kimi K2 async client not initialized")

        # Kimi K2 recommends temperature=0.6
        kimi_temp = temperature * 0.6

        kwargs = {
            "model": "kimi-k2-instruct",
            "messages": messages,
            "temperature": kimi_temp,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.kimi_client_async.chat.completions.create(**kwargs)

        # Extract content
        content = response.choices[0].message.content or ""

        # Calculate cost
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = self._calculate_cost(LLMProvider.KIMI_K2, input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            provider=LLMProvider.KIMI_K2,
            model="kimi-k2-instruct",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def complete_batch(
        self,
        requests: list[dict[str, Any]],
        max_concurrent: int | None = None,
    ) -> list[LLMResponse]:
        """
        Process multiple LLM requests in parallel with rate limiting.

        Args:
            requests: List of request dicts, each containing:
                - messages: list[dict[str, str]] (required)
                - task_type: TaskType (optional, defaults to USER_CHAT)
                - force_provider: LLMProvider (optional)
                - temperature: float (optional, defaults to 0.7)
                - max_tokens: int (optional, defaults to 4096)
                - tools: list[dict] (optional)
            max_concurrent: Maximum concurrent requests (defaults to rate limit semaphore or 10)

        Returns:
            List of LLMResponse objects in the same order as requests

        Example:
            requests = [
                {
                    "messages": [{"role": "user", "content": "What is Python?"}],
                    "task_type": TaskType.USER_CHAT,
                },
                {
                    "messages": [{"role": "user", "content": "Install nginx"}],
                    "task_type": TaskType.SYSTEM_OPERATION,
                },
            ]
            responses = await router.complete_batch(requests)
        """
        if not requests:
            return []

        # Use provided max_concurrent or semaphore limit or default
        if max_concurrent is None:
            if self._rate_limit_semaphore:
                max_concurrent = self._rate_limit_semaphore._value
            else:
                max_concurrent = 10
                self.set_rate_limit(max_concurrent)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _complete_with_rate_limit(request: dict[str, Any]) -> LLMResponse:
            """Complete a single request with rate limiting."""
            async with semaphore:
                return await self.acomplete(
                    messages=request["messages"],
                    task_type=request.get("task_type", TaskType.USER_CHAT),
                    force_provider=request.get("force_provider"),
                    temperature=request.get("temperature", 0.7),
                    max_tokens=request.get("max_tokens", 4096),
                    tools=request.get("tools"),
                )

        # Execute all requests in parallel
        tasks = [_complete_with_rate_limit(req) for req in requests]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions - convert to error responses or re-raise
        result: list[LLMResponse] = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                logger.error(f"Request {i} failed: {response}")
                # Create error response
                error_response = LLMResponse(
                    content=f"Error: {str(response)}",
                    provider=LLMProvider.CLAUDE,  # Default
                    model="error",
                    tokens_used=0,
                    cost_usd=0.0,
                    latency_seconds=0.0,
                )
                result.append(error_response)
            else:
                result.append(response)

        return result


# Convenience function for simple use cases
def complete_task(
    prompt: str,
    task_type: TaskType = TaskType.USER_CHAT,
    system_prompt: str | None = None,
    **kwargs,
) -> str:
    """
    Simple interface for one-off completions.

    Args:
        prompt: User prompt
        task_type: Type of task (determines LLM routing)
        system_prompt: Optional system message
        **kwargs: Additional arguments passed to LLMRouter.complete()

    Returns:
        String response from LLM
    """
    router = LLMRouter()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = router.complete(messages, task_type=task_type, **kwargs)
    return response.content


# Parallel processing helper functions
async def query_multiple_packages(
    router: LLMRouter,
    package_names: list[str],
    system_prompt: str | None = None,
    max_concurrent: int = 10,
) -> dict[str, LLMResponse]:
    """
    Query multiple packages in parallel for installation requirements.

    Args:
        router: LLMRouter instance
        package_names: List of package names to query
        system_prompt: Optional system prompt (defaults to package query prompt)
        max_concurrent: Maximum concurrent queries

    Returns:
        Dictionary mapping package names to LLMResponse objects

    Example:
        router = LLMRouter()
        responses = await query_multiple_packages(
            router, ["nginx", "postgresql", "redis"]
        )
        for pkg, response in responses.items():
            print(f"{pkg}: {response.content[:100]}")
    """
    default_system = (
        system_prompt
        or "You are a Linux package expert. Provide installation requirements and dependencies for packages."
    )

    requests = []
    for pkg in package_names:
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": default_system},
                    {
                        "role": "user",
                        "content": f"What are the installation requirements for {pkg}?",
                    },
                ],
                "task_type": TaskType.DEPENDENCY_RESOLUTION,
            }
        )

    responses = await router.complete_batch(requests, max_concurrent=max_concurrent)
    return dict(zip(package_names, responses))


async def diagnose_errors_parallel(
    router: LLMRouter,
    error_messages: list[str],
    context: str | None = None,
    max_concurrent: int = 10,
) -> list[LLMResponse]:
    """
    Diagnose multiple error messages in parallel.

    Args:
        router: LLMRouter instance
        error_messages: List of error messages to diagnose
        context: Optional context about the system/environment
        max_concurrent: Maximum concurrent diagnoses

    Returns:
        List of LLMResponse objects with diagnoses

    Example:
        router = LLMRouter()
        errors = [
            "Package 'nginx' has unmet dependencies",
            "Permission denied: /etc/nginx/nginx.conf",
        ]
        diagnoses = await diagnose_errors_parallel(router, errors)
        for error, diagnosis in zip(errors, diagnoses):
            print(f"{error}: {diagnosis.content}")
    """
    system_prompt = (
        "You are a Linux system debugging expert. Analyze error messages and provide solutions."
    )
    if context:
        system_prompt += f"\n\nSystem context: {context}"

    requests = []
    for error in error_messages:
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Diagnose and fix this error: {error}"},
                ],
                "task_type": TaskType.ERROR_DEBUGGING,
            }
        )

    return await router.complete_batch(requests, max_concurrent=max_concurrent)


async def check_hardware_configs_parallel(
    router: LLMRouter,
    hardware_components: list[str],
    hardware_info: dict[str, Any] | None = None,
    max_concurrent: int = 10,
) -> dict[str, LLMResponse]:
    """
    Check hardware configuration requirements for multiple components in parallel.

    Args:
        router: LLMRouter instance
        hardware_components: List of hardware components to check (e.g., ["nvidia_gpu", "intel_cpu"])
        hardware_info: Optional hardware information dict
        max_concurrent: Maximum concurrent checks

    Returns:
        Dictionary mapping component names to LLMResponse objects

    Example:
        router = LLMRouter()
        components = ["nvidia_gpu", "intel_cpu", "amd_gpu"]
        hw_info = {"nvidia_gpu": {"model": "RTX 4090", "driver": "535.0"}}
        configs = await check_hardware_configs_parallel(router, components, hw_info)
    """
    system_prompt = (
        "You are a hardware configuration expert. "
        "Analyze hardware components and provide optimal configuration recommendations."
    )

    if hardware_info:
        system_prompt += f"\n\nHardware information: {json.dumps(hardware_info, indent=2)}"

    requests = []
    for component in hardware_components:
        requests.append(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Check configuration requirements for {component}",
                    },
                ],
                "task_type": TaskType.CONFIGURATION,
            }
        )

    responses = await router.complete_batch(requests, max_concurrent=max_concurrent)
    return dict(zip(hardware_components, responses))


if __name__ == "__main__":
    # Example usage
    print("=== LLM Router Demo ===\n")

    router = LLMRouter()

    # Example 1: User chat (routed to Claude)
    print("1. User Chat Example:")
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! What can you help me with?"},
        ],
        task_type=TaskType.USER_CHAT,
    )
    print(f"Provider: {response.provider.value}")
    print(f"Response: {response.content[:100]}...")
    print(f"Cost: ${response.cost_usd:.6f}\n")

    # Example 2: System operation (routed to Kimi K2)
    print("2. System Operation Example:")
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are a Linux system administrator."},
            {"role": "user", "content": "Install CUDA drivers for NVIDIA RTX 4090"},
        ],
        task_type=TaskType.SYSTEM_OPERATION,
    )
    print(f"Provider: {response.provider.value}")
    print(f"Response: {response.content[:100]}...")
    print(f"Cost: ${response.cost_usd:.6f}\n")

    # Show stats
    print("=== Usage Statistics ===")
    stats = router.get_stats()
    print(json.dumps(stats, indent=2))
