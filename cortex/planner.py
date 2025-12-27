from typing import Any, dict, list

from cortex.llm.interpreter import CommandInterpreter


def generate_plan(intent: str, slots: dict[str, Any]) -> list[str]:
    """
    Generate a human-readable installation plan using LLM (Ollama).
    """

    prompt = f"""
You are a DevOps assistant.

User intent:
{intent}

Extracted details:
{slots}

Generate a step-by-step installation plan.
Rules:
- High-level steps only
- No shell commands
- One sentence per step
- Return as a JSON list of strings

Example:
["Install Python", "Install ML libraries", "Set up Jupyter"]
"""

    interpreter = CommandInterpreter(
        api_key="ollama",  # dummy value, Ollama ignores it
        provider="ollama",
    )

    # Reuse interpreter to get structured output
    steps = interpreter.parse(prompt, validate=False)

    return steps
