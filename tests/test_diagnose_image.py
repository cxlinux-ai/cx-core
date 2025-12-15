import pytest

PIL = pytest.importorskip("PIL", reason="Pillow not installed")
from PIL import Image

from cortex.llm_router import LLMRouter


def test_diagnose_image_fallback_without_claude():
    """
    If Claude is unavailable, diagnose_image should return
    a safe fallback message instead of crashing.
    """
    router = LLMRouter(claude_api_key=None)

    # Create a dummy image in memory
    image = Image.new("RGB", (100, 100), color="red")

    result = router.diagnose_image(image)

    assert isinstance(result, str)
    assert "Claude Vision unavailable" in result


def test_llmrouter_has_diagnose_image_method():
    """
    Ensure diagnose_image exists on LLMRouter
    """
    router = LLMRouter()
    assert hasattr(router, "diagnose_image")
