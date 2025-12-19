import pytest

pytest.importorskip("langchain_core")

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda


def test_chain_execution():
    prompt = ChatPromptTemplate.from_messages(
        [
            ("human", "Hello {name}"),
        ]
    )

    fake_llm = RunnableLambda(lambda _: "Hello User")

    chain = prompt | fake_llm

    result = chain.invoke({"name": "User"})

    assert result == "Hello User"
