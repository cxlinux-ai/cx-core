import pytest

pytest.importorskip("langchain_core")

import langchain
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate


def test_langchain_imports():
    assert langchain is not None
