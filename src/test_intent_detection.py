from intent.detector import IntentDetector


def test_detector_basic():
    d = IntentDetector()
    intents = d.detect("Install CUDA and PyTorch for GPU")

    targets = {i.target for i in intents}
    assert "cuda" in targets
    assert "pytorch" in targets
    assert "gpu" in targets


def test_detector_empty():
    d = IntentDetector()
    intents = d.detect("Hello world, nothing here")
    assert intents == []
