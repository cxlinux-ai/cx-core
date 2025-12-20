from intent.clarifier import Clarifier
from intent.context import SessionContext
from intent.detector import Intent, IntentDetector
from intent.planner import InstallationPlanner

# src/intent/llm_agent.py

# -------------------------------
# Safe import of anthropic SDK
# -------------------------------
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


class LLMIntentAgent:
    """
    High-level orchestrator combining:
    - rule-based intent detection
    - optional LLM-enhanced interpretation
    - planning & optimization
    - clarification handling
    - session context
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet-20240620"):

        # LLM is enabled ONLY if SDK + API key is available
        if Anthropic is None or api_key is None:
            self.llm = None
        else:
            self.llm = Anthropic(api_key=api_key)

        self.model = model

        self.detector = IntentDetector()
        self.planner = InstallationPlanner()
        self.clarifier = Clarifier()
        self.context = SessionContext()

    # ----------------------------------------------
    # Main request handler
    # ----------------------------------------------
    def process(self, text: str):
        # 1. Rule-based intent detection
        intents = self.detector.detect(text)

        # 2. Ask clarification if needed
        clarifying_q = self.clarifier.needs_clarification(intents, text)
        if clarifying_q:
            self.context.add_clarification(clarifying_q)
            return {"clarification_needed": clarifying_q}

        # 3. If LLM is unavailable → fallback mode
        if self.llm is None:
            self.context.add_intents(intents)
            return {
                "intents": intents,
                "plan": self.planner.build_plan(intents),
                "suggestions": [],
                "gpu": self.context.get_gpu(),
            }

        # 4. Improve intents using LLM (safe)
        try:
            improved_intents = self.enhance_intents_with_llm(text, intents)
        except Exception:
            improved_intents = intents

        # Save them to context
        self.context.add_intents(improved_intents)

        # 5. Build installation plan
        plan = self.planner.build_plan(improved_intents)

        # 6. Optional suggestions from LLM (safe)
        try:
            suggestions = self.suggest_optimizations(text)
        except Exception:
            suggestions = []

        return {
            "intents": improved_intents,
            "plan": plan,
            "suggestions": suggestions,
            "gpu": self.context.get_gpu(),
        }

    # ----------------------------------------------
    # LLM enhancement of intents
    # ----------------------------------------------
    def enhance_intents_with_llm(self, text: str, intents: list[Intent]) -> list[Intent]:

        prompt = f"""
You are an installation-intent expert. Convert the user request into structured intents.

User request: "{text}"

Initial intents detected:
{[str(i) for i in intents]}

Return improvements or extra intents.
Format: "install: package" or "configure: component"
"""

        # add explicit timeout to avoid long hangs
        response = self.llm.with_options(timeout=30.0).messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        # ---- Safety check ----
        if not getattr(response, "content", None) or not hasattr(response.content[0], "text"):
            return intents

        llm_output = response.content[0].text.lower().split("\n")

        new_intents = intents[:]

        for line in llm_output:
            if "install:" in line:
                pkg = line.replace("install:", "").strip()
                if pkg:
                    new_intents.append(Intent("install", pkg))
            elif "configure:" in line:
                target = line.replace("configure:", "").strip()
                if target:
                    new_intents.append(Intent("configure", target))
            elif "verify:" in line:
                target = line.replace("verify:", "").strip()
                if target:
                    new_intents.append(Intent("verify", target))

        return new_intents

    # ----------------------------------------------
    # LLM optimization suggestions
    # ----------------------------------------------
    def suggest_optimizations(self, text: str) -> list[str]:

        prompt = f"""
User request: "{text}"

Suggest optional tools to improve ML installation.
Examples: Conda, VSCode extensions, CUDA toolkit managers, Docker, Anaconda.
Return bullet list only.
"""

        response = self.llm.with_options(timeout=30.0).messages.create(
            model=self.model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )

        # ---- Safety check ----
        if not getattr(response, "content", None) or not hasattr(response.content[0], "text"):
            return []

        return [
            line.strip() for line in response.content[0].text.strip().split("\n") if line.strip()
        ]
