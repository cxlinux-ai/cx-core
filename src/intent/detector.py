from dataclasses import dataclass
from typing import ClassVar

# detector.py


@dataclass
class Intent:
    action: str
    target: str
    details: dict | None = None


class IntentDetector:
    """
    Extracts high-level installation intents from natural language requests.
    """

    COMMON_PACKAGES: ClassVar[dict[str, list[str]]] = {
        "cuda": ["cuda", "nvidia toolkit"],
        "pytorch": ["pytorch", "torch"],
        "tensorflow": ["tensorflow", "tf"],
        "jupyter": ["jupyter", "jupyterlab", "notebook"],
        "cudnn": ["cudnn"],
        "gpu": ["gpu", "graphics card", "rtx", "nvidia"],
    }

    def detect(self, text: str) -> list[Intent]:
        text = text.lower()
        intents = []

        # 1. Rule-based keyword detection (skip GPU to avoid duplicate install intent)
        for pkg, keywords in self.COMMON_PACKAGES.items():
            if pkg == "gpu":
                continue  # GPU handled separately below
            if any(k in text for k in keywords):
                intents.append(Intent(action="install", target=pkg))

        # 2. Look for verify steps
        if "verify" in text or "check" in text:
            intents.append(Intent(action="verify", target="installation"))

        # 3. GPU configure intent (use all GPU synonyms)
        gpu_keywords = self.COMMON_PACKAGES.get("gpu", ["gpu"])
        if any(k in text for k in gpu_keywords) and not any(
            i.action == "configure" and i.target == "gpu" for i in intents
        ):
            intents.append(Intent(action="configure", target="gpu"))

        return intents
