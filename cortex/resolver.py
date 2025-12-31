"""
Semantic Version Conflict Resolver Module.
Handles dependency version conflicts using AI-driven intelligent analysis.
"""

import json
import logging

import semantic_version as sv

from cortex.llm.interpreter import CommandInterpreter

logger = logging.getLogger(__name__)


class DependencyResolver:
    """
    AI-powered semantic version conflict resolver.
    Analyzes dependency version conflicts and suggests intelligent
    upgrade/downgrade paths using both deterministic analysis and LLM reasoning.
    """

    def __init__(self):
        """Initialize the resolver with the CommandInterpreter using Ollama."""
        self.interpreter = CommandInterpreter(
            api_key="ollama",
            provider="ollama",
        )

    async def resolve(self, conflict_data: dict) -> list[dict]:
        """
        Resolve semantic version conflicts using deterministic analysis first,
        followed by AI-powered reasoning as a fallback.
        """
        # Validate Input
        required_keys = ["package_a", "package_b", "dependency"]
        for key in required_keys:
            if key not in conflict_data:
                raise KeyError(f"Missing required key: {key}")

        # 1. Attempt deterministic resolution first (Reliable & Fast)
        strategies = self._deterministic_resolution(conflict_data)
        if strategies and strategies[0]["type"] == "Recommended" and strategies[0]["risk"] == "Low":
            return strategies

        # 2. If conflict is complex, use AI for intelligent reasoning
        prompt = self._build_prompt(conflict_data)

        try:
            # Query the AI via CommandInterpreter
            response_list = self.interpreter.parse(prompt)
            response_text = " ".join(response_list)
            return self._parse_ai_response(response_text, conflict_data)
        except Exception as e:
            logger.error(f"AI Resolution failed: {e}")
            # Fallback to deterministic strategies if AI fails
            return strategies or [
                {
                    "id": 0,
                    "type": "Error",
                    "action": f"AI analysis unavailable. Manual resolution required: {e}",
                    "risk": "High",
                }
            ]

    def _deterministic_resolution(self, data: dict) -> list[dict]:
        """Perform semantic-version constraint analysis without relying on AI."""
        try:
            dependency = data["dependency"]
            a_req = sv.NpmSpec(data["package_a"]["requires"])
            b_req = sv.NpmSpec(data["package_b"]["requires"])

            # Check if there is a version that satisfies both
            intersection = a_req & b_req
            if intersection:
                return [
                    {
                        "id": 1,
                        "type": "Recommended",
                        "action": f"Use {dependency} {intersection}",
                        "risk": "Low",
                        "explanation": "Version constraints are compatible",
                    }
                ]

            # If no intersection, suggest standard upgrade/downgrade paths
            a_major = a_req.specs[0].version.major
            b_major = b_req.specs[0].version.major

            return [
                {
                    "id": 1,
                    "type": "Recommended",
                    "action": f"Upgrade {data['package_b']['name']} to support {dependency} ^{a_major}.0.0",
                    "risk": "Medium",
                    "explanation": "Major version upgrade required",
                },
                {
                    "id": 2,
                    "type": "Alternative",
                    "action": f"Downgrade {data['package_a']['name']} to support {dependency} ~{b_major}.x",
                    "risk": "High",
                    "explanation": "Downgrade may remove features or fixes",
                },
            ]
        except Exception as e:
            logger.debug(f"Deterministic resolution skipped: {e}")
            return []

    def _build_prompt(self, data: dict) -> str:
        """Constructs a detailed prompt with escaped JSON braces for the LLM."""
        return f"""
Act as an expert DevOps Engineer. Analyze this dependency conflict:
Dependency: {data['dependency']}

Conflict Context:
1. {data['package_a']['name']} requires {data['package_a']['requires']}
2. {data['package_b']['name']} requires {data['package_b']['requires']}

Task:
- Detect potential breaking changes beyond just major version numbers.
- Provide a "Recommended" smart upgrade strategy (id: 1).
- Provide an "Alternative" safe downgrade strategy (id: 2).
- Include a specific risk assessment for each.

Return ONLY valid JSON in this exact structure:
{{
  "commands": [
    "[{{\\"id\\": 1, \\\"type\\": \\\"Recommended\\\", \\\"action\\": \\\"Update...\\\", \\\"risk\\": \\\"Low...\\\"}}, {{\\"id\\": 2, \\\"type\\": \\\"Alternative\\\", \\\"action\\": \\\"Keep...\\\", \\\"risk\\": \\\"Medium...\\\"}}]"
  ]
}}
"""

    def _parse_ai_response(self, response: str, data: dict) -> list[dict]:
        """Parses the LLM output into a list of strategy dictionaries."""
        try:
            # Look for the JSON array within the potentially messy AI response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1 and end != 0:
                json_str = response[start:end].replace("'", '"')
                return json.loads(json_str)
            raise ValueError("No JSON array found in AI response")
        except Exception:
            # Final safety fallback to deterministic logic
            return self._deterministic_resolution(data)
