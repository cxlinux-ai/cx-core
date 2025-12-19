from intent.clarifier import Clarifier
from intent.detector import IntentDetector


def test_clarifier_gpu_missing():
    d = IntentDetector()
    c = Clarifier()

    text = "I want to run ML models"
    intents = d.detect(text)

    question = c.needs_clarification(intents, text)
    assert question is not None
