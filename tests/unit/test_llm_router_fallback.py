import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock imports if they are missing
sys.modules["anthropic"] = MagicMock()
sys.modules["openai"] = MagicMock()

# Now we can import cortex.llm_router
# accessing it from the current directory
sys.path.insert(0, os.getcwd())

from cortex.llm_router import LLMProvider, LLMResponse, LLMRouter, TaskType


class TestLLMRouterFallback(unittest.TestCase):
    def test_fallback_chain(self):
        # Setup: Claude (Env) -> OpenAI (Env) -> Ollama (Local)
        # We simulate:
        # 1. Claude configured but fails
        # 2. OpenAI configured and succeeds
        # 3. Kimi not configured

        router = LLMRouter(
            claude_api_key="sk-ant-test",
            openai_api_key="sk-proj-test",
            kimi_api_key=None,
            ollama_base_url="http://localhost:11434",
        )

        # Verify initial state
        self.assertIsNotNone(router.claude_client)
        self.assertIsNotNone(router.openai_client)

        # Mock Claude to raise Exception
        router.claude_client.messages = MagicMock()
        router.claude_client.messages.create.side_effect = Exception("401 Authentication Error")

        # Mock OpenAI to succeed
        router.openai_client.chat = MagicMock()
        router.openai_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="OpenAI success"))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=10),
        )
        # Mock usage.prompt_tokens separately if needed by the code structure,
        # but the structure above should work for response.objects

        # Execute
        try:
            # We use USER_CHAT which prefers Claude
            response = router.complete(
                messages=[{"role": "user", "content": "hello"}], task_type=TaskType.USER_CHAT
            )

            # Assertions
            self.assertEqual(response.content, "OpenAI success")
            self.assertEqual(response.provider, LLMProvider.OPENAI)
            print("\n✅ Verification Passed: Successfully fell back to OpenAI after Claude failed")

        except Exception as e:
            self.fail(f"Router crashed or failed to fallback: {e}")


if __name__ == "__main__":
    unittest.main()
