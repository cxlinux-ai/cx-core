import pytest

pytest.importorskip("langchain_core")

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage


def test_in_memory_chat_history():
    history = InMemoryChatMessageHistory()

    history.add_message(HumanMessage(content="Hello"))
    history.add_message(AIMessage(content="Hi there"))

    messages = history.messages

    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there"
