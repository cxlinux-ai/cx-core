from intent.context import SessionContext
from intent.detector import Intent


def test_context_storage():
    ctx = SessionContext()
    ctx.set_gpu("NVIDIA RTX 4090")

    ctx.add_intents([Intent("install", "cuda")])
    ctx.add_installed("cuda")

    assert ctx.get_gpu() == "NVIDIA RTX 4090"
    assert ctx.is_installed("cuda") is True
    assert len(ctx.get_previous_intents()) == 1
