from typing import Optional

from intent.detector import Intent

# clarifier.py


class Clarifier:
    """
    Checks if the detected intents have missing information.
    Returns a clarifying question if needed.
    """

    def needs_clarification(self, intents: list[Intent], text: str) -> str | None:
        text = text.lower()

        # 1. If user mentions "gpu" but has not specified which GPU → ask
        if "gpu" in text and not any(
            i.target in ["cuda", "pytorch", "tensorflow"] for i in intents
        ):
            return "Do you have an NVIDIA GPU? (Needed for CUDA/PyTorch/TensorFlow installation)"

        # 2. If user says "machine learning tools" but nothing specific
        generic_terms = ["ml", "machine learning", "deep learning", "ai tools"]
        if any(term in text for term in generic_terms) and len(intents) == 0:
            return "Which ML frameworks do you need? (PyTorch, TensorFlow, JupyterLab...)"

        # 3. If user asks to install CUDA but no GPU exists in context
        if any(i.target == "cuda" for i in intents) and "gpu" not in text:
            return "Installing CUDA requires an NVIDIA GPU. Do you have one?"

        # 4. If package versions are missing (later we can add real version logic)
        if "torch" in text and "version" not in text:
            return "Do you need the GPU version or CPU version of PyTorch?"

        # 5. Otherwise no clarification needed
        return None
