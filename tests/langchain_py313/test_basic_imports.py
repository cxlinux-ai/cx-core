import pytest

pytest.importorskip("langchain_core")

import langchain


def test_langchain_imports():
    assert langchain is not None
