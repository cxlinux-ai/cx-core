import pytest

pytest.importorskip("langchain_core")

from langchain_core.runnables import RunnableLambda


def test_streaming():
    def streamer(_):
        yield "Hello"
        yield " "
        yield "World"

    runnable = RunnableLambda(streamer)

    output = "".join(runnable.stream("input"))

    assert output == "Hello World"
