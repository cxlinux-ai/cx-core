from typing import Optional

from intent.detector import Intent

# context.py


class SessionContext:
    """
    Stores context from previous user interactions.
    This is needed for Issue #53:
    'Uses context from previous commands'
    """

    def __init__(self):
        self.detected_gpu: str | None = None
        self.previous_intents: list[Intent] = []
        self.installed_packages: list[str] = []
        self.clarifications: list[str] = []

    # -------------------
    # GPU CONTEXT
    # -------------------

    def set_gpu(self, gpu_name: str):
        self.detected_gpu = gpu_name

    def get_gpu(self) -> str | None:
        return self.detected_gpu

    # -------------------
    # INTENT CONTEXT
    # -------------------

    def add_intents(self, intents: list[Intent]):
        self.previous_intents.extend(intents)

    def get_previous_intents(self) -> list[Intent]:
        return self.previous_intents

    # -------------------
    # INSTALLED PACKAGES
    # -------------------

    def add_installed(self, pkg: str):
        if pkg not in self.installed_packages:
            self.installed_packages.append(pkg)

    def is_installed(self, pkg: str) -> bool:
        return pkg in self.installed_packages

    # -------------------
    # CLARIFICATIONS
    # -------------------

    def add_clarification(self, question: str):
        self.clarifications.append(question)

    def get_clarifications(self) -> list[str]:
        return self.clarifications

    # -------------------
    # RESET CONTEXT
    # -------------------

    def reset(self):
        """Reset context (new session)"""
        self.detected_gpu = None
        self.previous_intents = []
        self.installed_packages = []
        self.clarifications = []
