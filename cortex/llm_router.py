#!/usr/bin/env python3
"""
LLM Router for Cortex Linux
Routes requests to the most appropriate LLM based on task type.

Supports:
- Claude API (Anthropic) - Best for natural language, chat, requirement parsing
- Kimi K2 API (Moonshot) - Best for system operations, debugging, tool use

Author: Cortex Linux Team
License: Modified MIT License
"""

import os
import time
import json
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
from dataclasses import dataclass, asdict
from anthropic import Anthropic
from openai import OpenAI
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks that determine LLM routing."""
    USER_CHAT = "user_chat"                    # General conversation
    REQUIREMENT_PARSING = "requirement_parsing"  # Understanding user needs
    SYSTEM_OPERATION = "system_operation"      # Package install, config
    ERROR_DEBUGGING = "error_debugging"        # Diagnosing failures
    CODE_GENERATION = "code_generation"        # Writing scripts
    DEPENDENCY_RESOLUTION = "dependency_resolution"  # Figuring out deps
    CONFIGURATION = "configuration"            # System config files
    TOOL_EXECUTION = "tool_execution"          # Running system tools


class LLMProvider(Enum):
    """Supported LLM providers."""
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
    raw_response: Optional[Dict] = None


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
        LLMProvider.CLAUDE: {
            "input": 3.0,   # $3 per 1M input tokens
            "output": 15.0  # $15 per 1M output tokens
        },
        LLMProvider.KIMI_K2: {
            "input": 1.0,   # Estimated lower cost
            "output": 5.0   # Estimated lower cost
        }
    }
    
    # Routing rules: TaskType → Preferred LLM
    ROUTING_RULES = {
        TaskType.USER_CHAT: LLMProvider.CLAUDE,
        TaskType.REQUIREMENT_PARSING: LLMProvider.CLAUDE,
        TaskType.SYSTEM_OPERATION: LLMProvider.KIMI_K2,
        TaskType.ERROR_DEBUGGING: LLMProvider.KIMI_K2,
        TaskType.CODE_GENERATION: LLMProvider.KIMI_K2,
        TaskType.DEPENDENCY_RESOLUTION: LLMProvider.KIMI_K2,
        TaskType.CONFIGURATION: LLMProvider.KIMI_K2,
        TaskType.TOOL_EXECUTION: LLMProvider.KIMI_K2,
    }
    
    def __init__(
        self,
        claude_api_key: Optional[str] = None,
        kimi_api_key: Optional[str] = None,
        default_provider: LLMProvider = LLMProvider.CLAUDE,
        enable_fallback: bool = True,
        track_costs: bool = True
    ):
        """
        Initialize LLM Router.
        
        Args:
            claude_api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env)
            kimi_api_key: Moonshot API key (defaults to MOONSHOT_API_KEY env)
            default_provider: Fallback provider if routing fails
            enable_fallback: Try alternate LLM if primary fails
            track_costs: Track token usage and costs
        """
        self.claude_api_key = claude_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.kimi_api_key = kimi_api_key or os.getenv("MOONSHOT_API_KEY")
        self.default_provider = default_provider
        self.enable_fallback = enable_fallback
        self.track_costs = track_costs
        
        # Initialize clients
        self.claude_client = None
        self.kimi_client = None
        
        if self.claude_api_key:
            self.claude_client = Anthropic(api_key=self.claude_api_key)
            logger.info("✅ Claude API client initialized")
        else:
            logger.warning("⚠️  No Claude API key provided")
            
        if self.kimi_api_key:
            self.kimi_client = OpenAI(
                api_key=self.kimi_api_key,
                base_url="https://api.moonshot.ai/v1"
            )
            logger.info("✅ Kimi K2 API client initialized")
        else:
            logger.warning("⚠️  No Kimi K2 API key provided")
        
        # Cost tracking
        self.total_cost_usd = 0.0
        self.request_count = 0
        self.provider_stats = {
            LLMProvider.CLAUDE: {"requests": 0, "tokens": 0, "cost": 0.0},
            LLMProvider.KIMI_K2: {"requests": 0, "tokens": 0, "cost": 0.0}
        }
    
    def route_task(
        self,
        task_type: TaskType,
        force_provider: Optional[LLMProvider] = None
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
                confidence=1.0
            )
        
        # Use routing rules
        provider = self.ROUTING_RULES.get(task_type, self.default_provider)
        
        # Check if preferred provider is available
        if provider == LLMProvider.CLAUDE and not self.claude_client:
            if self.kimi_client and self.enable_fallback:
                logger.warning(f"Claude unavailable, falling back to Kimi K2")
                provider = LLMProvider.KIMI_K2
            else:
                raise RuntimeError("Claude API not configured and no fallback available")
        
        if provider == LLMProvider.KIMI_K2 and not self.kimi_client:
            if self.claude_client and self.enable_fallback:
                logger.warning(f"Kimi K2 unavailable, falling back to Claude")
                provider = LLMProvider.CLAUDE
            else:
                raise RuntimeError("Kimi K2 API not configured and no fallback available")
        
        reasoning = f"{task_type.value} → {provider.value} (optimal for this task)"
        
        return RoutingDecision(
            provider=provider,
            task_type=task_type,
            reasoning=reasoning,
            confidence=0.95
        )
    
    def complete(
        self,
        messages: List[Dict[str, str]],
        task_type: TaskType = TaskType.USER_CHAT,
        force_provider: Optional[LLMProvider] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None
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
            
        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()
        
        # Route to appropriate LLM
        routing = self.route_task(task_type, force_provider)
        logger.info(f"🧭 Routing: {routing.reasoning}")
        
        try:
            if routing.provider == LLMProvider.CLAUDE:
                response = self._complete_claude(
                    messages, temperature, max_tokens, tools
                )
            else:  # KIMI_K2
                response = self._complete_kimi(
                    messages, temperature, max_tokens, tools
                )
            
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
                    LLMProvider.KIMI_K2 if routing.provider == LLMProvider.CLAUDE
                    else LLMProvider.CLAUDE
                )
                logger.info(f"🔄 Attempting fallback to {fallback_provider.value}")
                
                return self.complete(
                    messages=messages,
                    task_type=task_type,
                    force_provider=fallback_provider,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools
                )
            else:
                raise
    
    def _complete_claude(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict]] = None
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
            "messages": user_messages
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
            if hasattr(block, 'text'):
                content += block.text
        
        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(
            LLMProvider.CLAUDE, input_tokens, output_tokens
        )
        
        return LLMResponse(
            content=content,
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4-20250514",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None
        )
    
    def _complete_kimi(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict]] = None
    ) -> LLMResponse:
        """Generate completion using Kimi K2 API."""
        # Kimi K2 recommends temperature=0.6
        # Map user's temperature to Kimi's scale
        kimi_temp = temperature * 0.6
        
        kwargs = {
            "model": "kimi-k2-instruct",
            "messages": messages,
            "temperature": kimi_temp,
            "max_tokens": max_tokens
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
        cost = self._calculate_cost(
            LLMProvider.KIMI_K2, input_tokens, output_tokens
        )
        
        return LLMResponse(
            content=content,
            provider=LLMProvider.KIMI_K2,
            model="kimi-k2-instruct",
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            latency_seconds=0.0,  # Set by caller
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None
        )
    
    def _calculate_cost(
        self,
        provider: LLMProvider,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate cost in USD for this request."""
        costs = self.COSTS[provider]
        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (output_tokens / 1_000_000) * costs["output"]
        return input_cost + output_cost
    
    def _update_stats(self, response: LLMResponse):
        """Update usage statistics."""
        self.total_cost_usd += response.cost_usd
        self.request_count += 1
        
        stats = self.provider_stats[response.provider]
        stats["requests"] += 1
        stats["tokens"] += response.tokens_used
        stats["cost"] += response.cost_usd
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Returns:
            Dictionary with request counts, tokens, costs per provider
        """
        return {
            "total_requests": self.request_count,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "providers": {
                "claude": {
                    "requests": self.provider_stats[LLMProvider.CLAUDE]["requests"],
                    "tokens": self.provider_stats[LLMProvider.CLAUDE]["tokens"],
                    "cost_usd": round(self.provider_stats[LLMProvider.CLAUDE]["cost"], 4)
                },
                "kimi_k2": {
                    "requests": self.provider_stats[LLMProvider.KIMI_K2]["requests"],
                    "tokens": self.provider_stats[LLMProvider.KIMI_K2]["tokens"],
                    "cost_usd": round(self.provider_stats[LLMProvider.KIMI_K2]["cost"], 4)
                }
            }
        }
    
    def reset_stats(self):
        """Reset all usage statistics."""
        self.total_cost_usd = 0.0
        self.request_count = 0
        for provider in self.provider_stats:
            self.provider_stats[provider] = {"requests": 0, "tokens": 0, "cost": 0.0}


# Convenience function for simple use cases
def complete_task(
    prompt: str,
    task_type: TaskType = TaskType.USER_CHAT,
    system_prompt: Optional[str] = None,
    **kwargs
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


if __name__ == "__main__":
    # Example usage
    print("=== LLM Router Demo ===\n")
    
    router = LLMRouter()
    
    # Example 1: User chat (routed to Claude)
    print("1. User Chat Example:")
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! What can you help me with?"}
        ],
        task_type=TaskType.USER_CHAT
    )
    print(f"Provider: {response.provider.value}")
    print(f"Response: {response.content[:100]}...")
    print(f"Cost: ${response.cost_usd:.6f}\n")
    
    # Example 2: System operation (routed to Kimi K2)
    print("2. System Operation Example:")
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are a Linux system administrator."},
            {"role": "user", "content": "Install CUDA drivers for NVIDIA RTX 4090"}
        ],
        task_type=TaskType.SYSTEM_OPERATION
    )
    print(f"Provider: {response.provider.value}")
    print(f"Response: {response.content[:100]}...")
    print(f"Cost: ${response.cost_usd:.6f}\n")
    
    # Show stats
    print("=== Usage Statistics ===")
    stats = router.get_stats()
    print(json.dumps(stats, indent=2))
