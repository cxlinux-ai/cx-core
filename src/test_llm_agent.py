from intent.llm_agent import LLMIntentAgent


class MockMessages:
    def create(self, **kwargs):
        class Response:
            class Content:
                text = "install: tensorflow\ninstall: jupyter"

            content = [Content()]

        return Response()


class MockLLM:
    def __init__(self):
        self.messages = MockMessages()


def test_llm_agent_mocked():
    agent = LLMIntentAgent(api_key="fake-key")

    # Replace real LLM with mock
    agent.llm = MockLLM()

    # Disable clarification during testing
    agent.clarifier.needs_clarification = lambda *a, **k: None

    result = agent.process("Install ML tools on GPU")

    assert "plan" in result
    assert len(result["plan"]) > 0
    assert "suggestions" in result
