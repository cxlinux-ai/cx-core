#!/usr/bin/env python3
"""
Test Suite for LLM Router
Tests routing logic, fallback behavior, cost tracking, and error handling.

Author: Cortex Linux Team
License: Modified MIT License
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.llm_router import (
    LLMProvider,
    LLMResponse,
    LLMRouter,
    TaskType,
    check_hardware_configs_parallel,
    complete_task,
    diagnose_errors_parallel,
    query_multiple_packages,
)


class TestRoutingLogic(unittest.TestCase):
    """Test routing decisions for different task types."""

    def setUp(self):
        """Set up test router with mock API keys."""
        self.router = LLMRouter(claude_api_key="test-claude-key", kimi_api_key="test-kimi-key")

    def test_user_chat_routes_to_claude(self):
        """User chat tasks should route to Claude."""
        decision = self.router.route_task(TaskType.USER_CHAT)
        self.assertEqual(decision.provider, LLMProvider.CLAUDE)
        self.assertEqual(decision.task_type, TaskType.USER_CHAT)
        self.assertGreater(decision.confidence, 0.9)

    def test_system_operation_routes_to_kimi(self):
        """System operations should route to Kimi K2."""
        decision = self.router.route_task(TaskType.SYSTEM_OPERATION)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)
        self.assertEqual(decision.task_type, TaskType.SYSTEM_OPERATION)

    def test_error_debugging_routes_to_kimi(self):
        """Error debugging should route to Kimi K2."""
        decision = self.router.route_task(TaskType.ERROR_DEBUGGING)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    def test_requirement_parsing_routes_to_claude(self):
        """Requirement parsing should route to Claude."""
        decision = self.router.route_task(TaskType.REQUIREMENT_PARSING)
        self.assertEqual(decision.provider, LLMProvider.CLAUDE)

    def test_code_generation_routes_to_kimi(self):
        """Code generation should route to Kimi K2."""
        decision = self.router.route_task(TaskType.CODE_GENERATION)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    def test_dependency_resolution_routes_to_kimi(self):
        """Dependency resolution should route to Kimi K2."""
        decision = self.router.route_task(TaskType.DEPENDENCY_RESOLUTION)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    def test_configuration_routes_to_kimi(self):
        """Configuration tasks should route to Kimi K2."""
        decision = self.router.route_task(TaskType.CONFIGURATION)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    def test_tool_execution_routes_to_kimi(self):
        """Tool execution should route to Kimi K2."""
        decision = self.router.route_task(TaskType.TOOL_EXECUTION)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    def test_force_provider_override(self):
        """Forcing a provider should override routing logic."""
        decision = self.router.route_task(TaskType.USER_CHAT, force_provider=LLMProvider.KIMI_K2)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)
        self.assertIn("Forced", decision.reasoning)


class TestFallbackBehavior(unittest.TestCase):
    """Test fallback when primary LLM is unavailable."""

    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_kimi_when_claude_unavailable(self):
        """Should fallback to Kimi K2 if Claude unavailable."""
        router = LLMRouter(
            claude_api_key=None,
            kimi_api_key="test-kimi-key",
            enable_fallback=True,  # No Claude
        )

        # User chat normally goes to Claude, should fallback to Kimi
        decision = router.route_task(TaskType.USER_CHAT)
        self.assertEqual(decision.provider, LLMProvider.KIMI_K2)

    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_claude_when_kimi_unavailable(self):
        """Should fallback to Claude if Kimi K2 unavailable."""
        router = LLMRouter(
            claude_api_key="test-claude-key",
            kimi_api_key=None,
            enable_fallback=True,  # No Kimi
        )

        # System ops normally go to Kimi, should fallback to Claude
        decision = router.route_task(TaskType.SYSTEM_OPERATION)
        self.assertEqual(decision.provider, LLMProvider.CLAUDE)

    @patch("cortex.llm_router.OpenAI")
    @patch("cortex.llm_router.AsyncOpenAI")
    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_ollama(self, mock_async_openai, mock_openai):
        """Should fallback to Ollama if primary providers unavailable."""
        router = LLMRouter(
            claude_api_key=None,
            kimi_api_key=None,
            ollama_base_url="http://localhost:11434",
            enable_fallback=True,
        )

        # User chat normally Claude -> fallback to Ollama
        decision = router.route_task(TaskType.USER_CHAT)
        self.assertEqual(decision.provider, LLMProvider.OLLAMA)

        # System ops normally Kimi -> fallback to Ollama
        decision = router.route_task(TaskType.SYSTEM_OPERATION)
        self.assertEqual(decision.provider, LLMProvider.OLLAMA)

    @patch("cortex.llm_router.OpenAI", side_effect=ImportError)
    @patch.dict(os.environ, {}, clear=True)
    def test_error_when_no_providers_available(self, mock_openai):
        """Should raise error if no providers configured."""
        router = LLMRouter(claude_api_key=None, kimi_api_key=None, enable_fallback=True)

        with self.assertRaises(RuntimeError):
            router.route_task(TaskType.USER_CHAT)

    @patch.dict(os.environ, {}, clear=True)
    def test_error_when_fallback_disabled(self):
        """Should raise error if primary unavailable and fallback disabled."""
        router = LLMRouter(claude_api_key=None, kimi_api_key="test-kimi-key", enable_fallback=False)

        with self.assertRaises(RuntimeError):
            router.route_task(TaskType.USER_CHAT)


class TestCostTracking(unittest.TestCase):
    """Test cost calculation and statistics tracking."""

    def setUp(self):
        """Set up router with tracking enabled."""
        self.router = LLMRouter(
            claude_api_key="test-claude-key", kimi_api_key="test-kimi-key", track_costs=True
        )

    def test_cost_calculation_claude(self):
        """Test Claude cost calculation."""
        cost = self.router._calculate_cost(LLMProvider.CLAUDE, input_tokens=1000, output_tokens=500)
        # $3 per 1M input, $15 per 1M output
        expected = (1000 / 1_000_000 * 3.0) + (500 / 1_000_000 * 15.0)
        self.assertAlmostEqual(cost, expected, places=6)

    def test_cost_calculation_kimi(self):
        """Test Kimi K2 cost calculation."""
        cost = self.router._calculate_cost(
            LLMProvider.KIMI_K2, input_tokens=1000, output_tokens=500
        )
        # $1 per 1M input, $5 per 1M output
        expected = (1000 / 1_000_000 * 1.0) + (500 / 1_000_000 * 5.0)
        self.assertAlmostEqual(cost, expected, places=6)

    def test_stats_update(self):
        """Test statistics update after response."""
        response = LLMResponse(
            content="test",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=1500,
            cost_usd=0.01,
            latency_seconds=1.0,
        )

        self.router._update_stats(response)

        stats = self.router.get_stats()
        self.assertEqual(stats["total_requests"], 1)
        self.assertEqual(stats["total_cost_usd"], 0.01)
        self.assertEqual(stats["providers"]["claude"]["requests"], 1)
        self.assertEqual(stats["providers"]["claude"]["tokens"], 1500)

    def test_multiple_provider_stats(self):
        """Test stats tracking across multiple providers."""
        # Add Claude request
        claude_response = LLMResponse(
            content="test1",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=1000,
            cost_usd=0.01,
            latency_seconds=1.0,
        )
        self.router._update_stats(claude_response)

        # Add Kimi request
        kimi_response = LLMResponse(
            content="test2",
            provider=LLMProvider.KIMI_K2,
            model="kimi-k2-instruct",
            tokens_used=2000,
            cost_usd=0.005,
            latency_seconds=0.8,
        )
        self.router._update_stats(kimi_response)

        stats = self.router.get_stats()
        self.assertEqual(stats["total_requests"], 2)
        self.assertAlmostEqual(stats["total_cost_usd"], 0.015, places=4)
        self.assertEqual(stats["providers"]["claude"]["requests"], 1)
        self.assertEqual(stats["providers"]["kimi_k2"]["requests"], 1)

    def test_reset_stats(self):
        """Test resetting statistics."""
        # Add some requests
        response = LLMResponse(
            content="test",
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet-4",
            tokens_used=1000,
            cost_usd=0.01,
            latency_seconds=1.0,
        )
        self.router._update_stats(response)

        # Reset
        self.router.reset_stats()

        stats = self.router.get_stats()
        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["total_cost_usd"], 0.0)


class TestClaudeIntegration(unittest.TestCase):
    """Test Claude API integration."""

    @patch("cortex.llm_router.Anthropic")
    def test_claude_completion(self, mock_anthropic):
        """Test Claude completion with mocked API."""
        # Mock response
        mock_content = Mock()
        mock_content.text = "Hello from Claude"

        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_response.model_dump = lambda: {"mock": "response"}

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        # Create router
        router = LLMRouter(claude_api_key="test-key")
        router.claude_client = mock_client

        # Test completion
        result = router._complete_claude(
            messages=[{"role": "user", "content": "Hello"}], temperature=0.7, max_tokens=1024
        )

        self.assertEqual(result.content, "Hello from Claude")
        self.assertEqual(result.provider, LLMProvider.CLAUDE)
        self.assertEqual(result.tokens_used, 150)
        self.assertGreater(result.cost_usd, 0)

    @patch("cortex.llm_router.Anthropic")
    def test_claude_with_system_message(self, mock_anthropic):
        """Test Claude handles system messages correctly."""
        mock_content = Mock()
        mock_content.text = "Response"

        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        router = LLMRouter(claude_api_key="test-key")
        router.claude_client = mock_client

        # Call with system message
        result = router._complete_claude(
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"},
            ],
            temperature=0.7,
            max_tokens=1024,
        )

        # Verify system message was extracted
        call_args = mock_client.messages.create.call_args
        self.assertIn("system", call_args.kwargs)
        self.assertEqual(call_args.kwargs["system"], "You are helpful")


class TestKimiIntegration(unittest.TestCase):
    """Test Kimi K2 API integration."""

    @patch("cortex.llm_router.OpenAI")
    def test_kimi_completion(self, mock_openai):
        """Test Kimi K2 completion with mocked API."""
        # Mock response
        mock_message = Mock()
        mock_message.content = "Hello from Kimi K2"

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        mock_response.model_dump = lambda: {"mock": "response"}

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # Create router
        router = LLMRouter(kimi_api_key="test-key")
        router.kimi_client = mock_client

        # Test completion
        result = router._complete_kimi(
            messages=[{"role": "user", "content": "Hello"}], temperature=0.7, max_tokens=1024
        )

        self.assertEqual(result.content, "Hello from Kimi K2")
        self.assertEqual(result.provider, LLMProvider.KIMI_K2)
        self.assertEqual(result.tokens_used, 150)
        self.assertGreater(result.cost_usd, 0)

    @patch("cortex.llm_router.OpenAI")
    def test_kimi_temperature_mapping(self, mock_openai):
        """Test Kimi K2 temperature is scaled by 0.6."""
        mock_message = Mock()
        mock_message.content = "Response"

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        router = LLMRouter(kimi_api_key="test-key")
        router.kimi_client = mock_client

        # Call with temperature=1.0
        router._complete_kimi(
            messages=[{"role": "user", "content": "Hello"}], temperature=1.0, max_tokens=1024
        )

        # Verify temperature was scaled to 0.6
        call_args = mock_client.chat.completions.create.call_args
        self.assertAlmostEqual(call_args.kwargs["temperature"], 0.6, places=2)

    @patch("cortex.llm_router.OpenAI")
    def test_kimi_with_tools(self, mock_openai):
        """Test Kimi K2 handles tool calling."""
        mock_message = Mock()
        mock_message.content = "Using tools"

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        router = LLMRouter(kimi_api_key="test-key")
        router.kimi_client = mock_client

        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        router._complete_kimi(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=1024,
            tools=tools,
        )

        # Verify tools were passed
        call_args = mock_client.chat.completions.create.call_args
        self.assertIn("tools", call_args.kwargs)
        self.assertEqual(call_args.kwargs["tool_choice"], "auto")


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    def test_complete_with_routing(self, mock_openai, mock_anthropic):
        """Test complete() method with full routing."""
        # Mock Kimi K2 (should be used for system operations)
        mock_message = Mock()
        mock_message.content = "Installing CUDA..."

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_kimi_client = Mock()
        mock_kimi_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_kimi_client

        # Create router
        router = LLMRouter(claude_api_key="test-claude", kimi_api_key="test-kimi")

        # Test system operation (should route to Kimi)
        response = router.complete(
            messages=[{"role": "user", "content": "Install CUDA"}],
            task_type=TaskType.SYSTEM_OPERATION,
        )

        self.assertEqual(response.provider, LLMProvider.KIMI_K2)
        self.assertIn("Installing", response.content)

    @patch("cortex.llm_router.Anthropic")
    @patch("cortex.llm_router.OpenAI")
    def test_fallback_on_error(self, mock_openai, mock_anthropic):
        """Test fallback when primary provider fails."""
        # Mock Kimi K2 to fail
        mock_kimi_client = Mock()
        mock_kimi_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_kimi_client

        # Mock Claude to succeed
        mock_content = Mock()
        mock_content.text = "Fallback response"

        mock_claude_response = Mock()
        mock_claude_response.content = [mock_content]
        mock_claude_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_claude_response.model_dump = lambda: {}

        mock_claude_client = Mock()
        mock_claude_client.messages.create.return_value = mock_claude_response
        mock_anthropic.return_value = mock_claude_client

        # Create router with fallback enabled
        router = LLMRouter(
            claude_api_key="test-claude", kimi_api_key="test-kimi", enable_fallback=True
        )

        # System operation should try Kimi, then fallback to Claude
        response = router.complete(
            messages=[{"role": "user", "content": "Install CUDA"}],
            task_type=TaskType.SYSTEM_OPERATION,
        )

        self.assertEqual(response.provider, LLMProvider.CLAUDE)
        self.assertEqual(response.content, "Fallback response")


class TestConvenienceFunction(unittest.TestCase):
    """Test the complete_task convenience function."""

    @patch("cortex.llm_router.LLMRouter")
    def test_complete_task_simple(self, mock_router_class):
        """Test simple completion with complete_task()."""
        # Mock router
        mock_response = Mock()
        mock_response.content = "Test response"

        mock_router = Mock()
        mock_router.complete.return_value = mock_response
        mock_router_class.return_value = mock_router

        # Call convenience function
        result = complete_task("Hello", task_type=TaskType.USER_CHAT)

        self.assertEqual(result, "Test response")
        mock_router.complete.assert_called_once()

    @patch("cortex.llm_router.LLMRouter")
    def test_complete_task_with_system_prompt(self, mock_router_class):
        """Test complete_task() includes system prompt."""
        mock_response = Mock()
        mock_response.content = "Response"

        mock_router = Mock()
        mock_router.complete.return_value = mock_response
        mock_router_class.return_value = mock_router

        result = complete_task(
            "Hello", system_prompt="You are helpful", task_type=TaskType.USER_CHAT
        )

        # Verify system message was included
        call_args = mock_router.complete.call_args
        messages = call_args[0][0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are helpful")


class TestParallelProcessing(unittest.TestCase):
    """Test parallel LLM call functionality."""

    def setUp(self):
        """Set up test router with mock API keys."""
        self.router = LLMRouter(claude_api_key="test-claude-key", kimi_api_key="test-kimi-key")

    @patch("cortex.llm_router.AsyncAnthropic")
    @patch("cortex.llm_router.AsyncOpenAI")
    def test_acomplete_claude(self, mock_async_openai, mock_async_anthropic):
        """Test async completion with Claude."""
        # Mock async Claude client
        mock_message = Mock()
        mock_message.text = "Async Claude response"

        mock_content = Mock()
        mock_content.text = "Async Claude response"

        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_async_anthropic.return_value = mock_client

        # Create router and test
        router = LLMRouter(claude_api_key="test-claude")
        router.claude_client_async = mock_client

        async def run_test():
            response = await router.acomplete(
                messages=[{"role": "user", "content": "Hello"}],
                task_type=TaskType.USER_CHAT,
            )
            self.assertEqual(response.provider, LLMProvider.CLAUDE)
            self.assertEqual(response.content, "Async Claude response")

        asyncio.run(run_test())

    @patch("cortex.llm_router.AsyncOpenAI")
    def test_acomplete_kimi(self, mock_async_openai):
        """Test async completion with Kimi K2."""
        # Mock async Kimi client
        mock_message = Mock()
        mock_message.content = "Async Kimi response"

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        mock_response.model_dump = lambda: {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client

        # Create router and test
        router = LLMRouter(kimi_api_key="test-kimi")
        router.kimi_client_async = mock_client

        async def run_test():
            response = await router.acomplete(
                messages=[{"role": "user", "content": "Install nginx"}],
                task_type=TaskType.SYSTEM_OPERATION,
            )
            self.assertEqual(response.provider, LLMProvider.KIMI_K2)
            self.assertEqual(response.content, "Async Kimi response")

        asyncio.run(run_test())

    @patch("cortex.llm_router.AsyncAnthropic")
    @patch("cortex.llm_router.AsyncOpenAI")
    def test_complete_batch(self, mock_async_openai, mock_async_anthropic):
        """Test batch completion with multiple requests."""
        # Mock responses
        mock_claude_response = Mock()
        mock_claude_content = Mock()
        mock_claude_content.text = "Response 1"
        mock_claude_response.content = [mock_claude_content]
        mock_claude_response.usage = Mock(input_tokens=50, output_tokens=25)
        mock_claude_response.model_dump = lambda: {}

        mock_kimi_response = Mock()
        mock_kimi_message = Mock()
        mock_kimi_message.content = "Response 2"
        mock_kimi_choice = Mock()
        mock_kimi_choice.message = mock_kimi_message
        mock_kimi_response.choices = [mock_kimi_choice]
        mock_kimi_response.usage = Mock(prompt_tokens=50, completion_tokens=25)
        mock_kimi_response.model_dump = lambda: {}

        # Setup async clients
        mock_claude_client = AsyncMock()
        mock_claude_client.messages.create = AsyncMock(return_value=mock_claude_response)
        mock_async_anthropic.return_value = mock_claude_client

        mock_kimi_client = AsyncMock()
        mock_kimi_client.chat.completions.create = AsyncMock(return_value=mock_kimi_response)
        mock_async_openai.return_value = mock_kimi_client

        router = LLMRouter(claude_api_key="test-claude", kimi_api_key="test-kimi")
        router.claude_client_async = mock_claude_client
        router.kimi_client_async = mock_kimi_client

        async def run_test():
            requests = [
                {
                    "messages": [{"role": "user", "content": "Query 1"}],
                    "task_type": TaskType.USER_CHAT,
                },
                {
                    "messages": [{"role": "user", "content": "Query 2"}],
                    "task_type": TaskType.SYSTEM_OPERATION,
                },
            ]

            responses = await router.complete_batch(requests, max_concurrent=2)
            self.assertEqual(len(responses), 2)
            self.assertEqual(responses[0].provider, LLMProvider.CLAUDE)
            self.assertEqual(responses[1].provider, LLMProvider.KIMI_K2)

        asyncio.run(run_test())

    @patch("cortex.llm_router.AsyncAnthropic")
    @patch("cortex.llm_router.AsyncOpenAI")
    def test_query_multiple_packages(self, mock_async_openai, mock_async_anthropic):
        """Test parallel package queries."""
        # Mock responses
        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "Package info for {pkg}"
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=50, output_tokens=25)
        mock_response.model_dump = lambda: {}

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_async_anthropic.return_value = mock_client

        router = LLMRouter(claude_api_key="test-claude")
        router.claude_client_async = mock_client

        async def run_test():
            packages = ["nginx", "postgresql", "redis"]
            responses = await query_multiple_packages(router, packages, max_concurrent=3)
            self.assertEqual(len(responses), 3)
            self.assertIn("nginx", responses)
            self.assertIn("postgresql", responses)
            self.assertIn("redis", responses)

        asyncio.run(run_test())

    @patch("cortex.llm_router.AsyncOpenAI")
    def test_diagnose_errors_parallel(self, mock_async_openai):
        """Test parallel error diagnosis."""
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Diagnosis for error"
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=50, completion_tokens=25)
        mock_response.model_dump = lambda: {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client

        router = LLMRouter(kimi_api_key="test-kimi")
        router.kimi_client_async = mock_client

        async def run_test():
            errors = ["Error 1", "Error 2"]
            diagnoses = await diagnose_errors_parallel(router, errors, max_concurrent=2)
            self.assertEqual(len(diagnoses), 2)

        asyncio.run(run_test())

    @patch("cortex.llm_router.AsyncOpenAI")
    def test_check_hardware_configs_parallel(self, mock_async_openai):
        """Test parallel hardware config checks."""
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Config for hardware"
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(prompt_tokens=50, completion_tokens=25)
        mock_response.model_dump = lambda: {}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client

        router = LLMRouter(kimi_api_key="test-kimi")
        router.kimi_client_async = mock_client

        async def run_test():
            components = ["nvidia_gpu", "intel_cpu"]
            configs = await check_hardware_configs_parallel(router, components, max_concurrent=2)
            self.assertEqual(len(configs), 2)
            self.assertIn("nvidia_gpu", configs)
            self.assertIn("intel_cpu", configs)

        asyncio.run(run_test())

    def test_rate_limit_semaphore(self):
        """Test rate limiting semaphore setup."""
        router = LLMRouter()
        router.set_rate_limit(max_concurrent=5)
        self.assertIsNotNone(router._rate_limit_semaphore)
        self.assertEqual(router._rate_limit_semaphore._value, 5)


def run_tests():
    """Run all tests with detailed output."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRoutingLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestFallbackBehavior))
    suite.addTests(loader.loadTestsFromTestCase(TestCostTracking))
    suite.addTests(loader.loadTestsFromTestCase(TestClaudeIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestKimiIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEnd))
    suite.addTests(loader.loadTestsFromTestCase(TestConvenienceFunction))
    suite.addTests(loader.loadTestsFromTestCase(TestParallelProcessing))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
