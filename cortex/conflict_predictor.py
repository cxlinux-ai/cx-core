"""
AI-Powered Dependency Conflict Predictor

This module predicts and resolves package dependency conflicts BEFORE installation
using LLM analysis instead of hardcoded rules.
"""

import json
import logging
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from cortex.installation_history import InstallationHistory
from cortex.llm_router import LLMRouter, TaskType

# Use DEPENDENCY_RESOLUTION since DEPENDENCY_ANALYSIS doesn't exist
CONFLICT_TASK_TYPE = TaskType.DEPENDENCY_RESOLUTION

logger = logging.getLogger(__name__)

# Security: Validate version constraint format
CONSTRAINT_PATTERN = re.compile(r"^(<|>|<=|>=|==|!=|~=|~|===)?[\w.!*+\-]+$")


def validate_version_constraint(constraint: str) -> bool:
    """Validate pip version constraint format to prevent injection."""
    if not constraint:
        return True
    return bool(CONSTRAINT_PATTERN.match(constraint.strip()))


def escape_command_arg(arg: str) -> str:
    """Safely escape argument for shell commands."""
    return shlex.quote(arg)


class ConflictType(Enum):
    """Types of dependency conflicts"""

    VERSION = "version"
    PORT = "port"
    LIBRARY = "library"
    FILE = "file"
    MUTUAL_EXCLUSION = "mutual_exclusion"
    CIRCULAR = "circular"


class StrategyType(Enum):
    """Resolution strategy types"""

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    ALTERNATIVE = "alternative"
    VENV = "venv"
    REMOVE_CONFLICT = "remove_conflict"
    PORT_CHANGE = "port_change"
    DO_NOTHING = "do_nothing"


@dataclass
class ConflictPrediction:
    """Represents a predicted dependency conflict"""

    package1: str
    package2: str
    conflict_type: ConflictType
    confidence: float
    explanation: str
    affected_packages: list[str] = field(default_factory=list)
    severity: str = "MEDIUM"
    installed_by: str | None = None
    current_version: str | None = None
    required_constraint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "conflict_type": self.conflict_type.value}


@dataclass
class ResolutionStrategy:
    """Suggested resolution for a conflict"""

    strategy_type: StrategyType
    description: str
    safety_score: float
    commands: list[str]
    risks: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    estimated_time_minutes: float = 2.0
    affects_packages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "strategy_type": self.strategy_type.value}


class ConflictPredictor:
    """
    AI-powered dependency conflict prediction using LLM analysis.

    Instead of hardcoded rules, this sends the system state to an LLM
    which analyzes potential conflicts based on its knowledge of package
    ecosystems.
    """

    def __init__(
        self,
        llm_router: LLMRouter | None = None,
        history: InstallationHistory | None = None,
    ):
        self.llm_router = llm_router
        self.history = history or InstallationHistory()

    def predict_conflicts(
        self, package_name: str, version: str | None = None
    ) -> list[ConflictPrediction]:
        """
        Predict conflicts for a package installation using LLM analysis.
        (Legacy method - use predict_conflicts_with_resolutions for better performance)
        """
        conflicts, _ = self.predict_conflicts_with_resolutions(package_name, version)
        return conflicts

    def predict_conflicts_with_resolutions(
        self, package_name: str, version: str | None = None
    ) -> tuple[list[ConflictPrediction], list[ResolutionStrategy]]:
        """
        Predict conflicts AND generate resolutions in a single LLM call.
        Returns (conflicts, strategies) tuple.
        """
        logger.info(f"Predicting conflicts for {package_name} {version or 'latest'}")

        if not self.llm_router:
            logger.warning("No LLM router available, skipping conflict prediction")
            return [], []

        # Gather system state
        pip_packages = get_pip_packages()
        apt_packages = get_apt_packages_summary()

        # Build the combined prompt
        prompt = self._build_combined_prompt(package_name, version, pip_packages, apt_packages)

        try:
            # Single LLM call for both conflicts AND resolutions
            messages = [
                {"role": "system", "content": COMBINED_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = self.llm_router.complete(
                messages=messages,
                task_type=CONFLICT_TASK_TYPE,
                temperature=0.2,
                max_tokens=3000,
            )

            if not response or not response.content:
                logger.warning("Empty response from LLM")
                return [], []

            # Parse the combined JSON response
            conflicts, strategies = self._parse_combined_response(response.content, package_name)
            logger.info(f"Found {len(conflicts)} conflicts, {len(strategies)} strategies")
            return conflicts, strategies

        except Exception as e:
            logger.warning(f"AI conflict detection failed: {e}")
            return [], []

    def _build_combined_prompt(
        self,
        package_name: str,
        version: str | None,
        pip_packages: dict[str, str],
        apt_packages: list[str],
    ) -> str:
        """Build combined prompt for conflicts AND resolutions."""
        pip_list = "\n".join(
            [f"  - {name}=={ver}" for name, ver in list(pip_packages.items())[:50]]
        )
        apt_list = "\n".join([f"  - {pkg}" for pkg in apt_packages[:30]])
        version_str = f"=={version}" if version else " (latest)"

        return f"""Analyze potential dependency conflicts for installing: {package_name}{version_str}

CURRENTLY INSTALLED PIP PACKAGES:
{pip_list or "  (none)"}

RELEVANT APT PACKAGES:
{apt_list or "  (none)"}

Analyze for conflicts AND provide resolution strategies if conflicts exist.
Respond with JSON only."""

    def _parse_combined_response(
        self, response: str, package_name: str
    ) -> tuple[list[ConflictPrediction], list[ResolutionStrategy]]:
        """Parse combined LLM response into conflicts and strategies."""
        conflicts = []
        strategies = []

        try:
            data = extract_json_from_response(response)
            if not data:
                logger.warning("No valid JSON found in LLM response")
                return [], []

            # Parse conflicts
            conflict_list = data.get("conflicts", [])
            for c in conflict_list:
                try:
                    conflict_type_str = c.get("type", "VERSION").upper()
                    if conflict_type_str not in [ct.name for ct in ConflictType]:
                        conflict_type_str = "VERSION"

                    conflicts.append(
                        ConflictPrediction(
                            package1=package_name,
                            package2=c.get("conflicting_package", c.get("package2", "unknown")),
                            conflict_type=ConflictType[conflict_type_str],
                            confidence=float(c.get("confidence", 0.8)),
                            explanation=c.get(
                                "explanation", c.get("reason", "Potential conflict detected")
                            ),
                            affected_packages=c.get("affected_packages", []),
                            severity=c.get("severity", "HIGH"),
                            installed_by=c.get("installed_by"),
                            current_version=c.get("current_version"),
                            required_constraint=c.get("required_constraint"),
                        )
                    )
                except (KeyError, ValueError) as e:
                    logger.debug(f"Failed to parse conflict entry: {e}")
                    continue

            # Parse strategies (only if conflicts exist)
            if conflicts:
                strategy_list = data.get("strategies", data.get("resolutions", []))
                for s in strategy_list:
                    try:
                        strategy_type_str = s.get("type", "VENV").upper()
                        if strategy_type_str not in [st.name for st in StrategyType]:
                            strategy_type_str = "VENV"

                        strategies.append(
                            ResolutionStrategy(
                                strategy_type=StrategyType[strategy_type_str],
                                description=s.get("description", ""),
                                safety_score=float(s.get("safety_score", 0.5)),
                                commands=s.get("commands", []),
                                benefits=s.get("benefits", []),
                                risks=s.get("risks", []),
                                affects_packages=s.get("affects_packages", []),
                            )
                        )
                    except (KeyError, ValueError):
                        continue

                strategies.sort(key=lambda s: s.safety_score, reverse=True)

                # If LLM didn't provide strategies, use basic fallback
                if not strategies:
                    strategies = self._generate_basic_strategies(conflicts)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")

        return conflicts, strategies

    def generate_resolutions(self, conflicts: list[ConflictPrediction]) -> list[ResolutionStrategy]:
        """Generate resolution strategies using LLM."""
        if not conflicts:
            return []

        if not self.llm_router:
            # Fallback to basic strategies
            return self._generate_basic_strategies(conflicts)

        # Build prompt for resolution suggestions
        conflict_summary = "\n".join([f"- {c.explanation}" for c in conflicts])

        prompt = f"""Given these dependency conflicts:
{conflict_summary}

Suggest resolution strategies. For each strategy provide:
1. Description of what to do
2. Safety score (0.0-1.0, higher = safer)
3. Commands to execute
4. Benefits and risks

Respond with JSON only."""

        try:
            messages = [
                {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = self.llm_router.complete(
                messages=messages,
                task_type=CONFLICT_TASK_TYPE,
                temperature=0.3,
                max_tokens=2048,
            )

            if response and response.content:
                strategies = self._parse_resolution_response(response.content, conflicts)
                if strategies:
                    return strategies

        except Exception as e:
            logger.warning(f"LLM resolution generation failed: {e}")

        # Fallback to basic strategies
        return self._generate_basic_strategies(conflicts)

    def _parse_resolution_response(
        self, response: str, conflicts: list[ConflictPrediction]
    ) -> list[ResolutionStrategy]:
        """Parse LLM response into ResolutionStrategy objects."""
        strategies = []

        try:
            data = extract_json_from_response(response)
            if not data:
                return []

            strategy_list = data.get("strategies", data.get("resolutions", []))

            for s in strategy_list:
                try:
                    strategy_type_str = s.get("type", "VENV").upper()
                    if strategy_type_str not in [st.name for st in StrategyType]:
                        strategy_type_str = "VENV"

                    strategies.append(
                        ResolutionStrategy(
                            strategy_type=StrategyType[strategy_type_str],
                            description=s.get("description", ""),
                            safety_score=float(s.get("safety_score", 0.5)),
                            commands=s.get("commands", []),
                            benefits=s.get("benefits", []),
                            risks=s.get("risks", []),
                            affects_packages=s.get("affects_packages", []),
                        )
                    )
                except (KeyError, ValueError):
                    continue

        except json.JSONDecodeError as exc:
            logging.warning("Failed to decode JSON from LLM response: %s", exc)
            return []

        # Sort by safety score
        strategies.sort(key=lambda s: s.safety_score, reverse=True)
        return strategies

    def _generate_basic_strategies(
        self, conflicts: list[ConflictPrediction]
    ) -> list[ResolutionStrategy]:
        """Generate basic resolution strategies without LLM."""
        strategies = []

        for conflict in conflicts:
            pkg = conflict.package1
            conflicting = conflict.package2

            # Strategy 1: Virtual environment (safest)
            strategies.append(
                ResolutionStrategy(
                    strategy_type=StrategyType.VENV,
                    description=f"Install {pkg} in virtual environment (isolate)",
                    safety_score=0.85,
                    commands=[
                        f"python3 -m venv {escape_command_arg(pkg)}_env",
                        f"source {escape_command_arg(pkg)}_env/bin/activate",
                        f"pip install {escape_command_arg(pkg)}",
                    ],
                    benefits=["Complete isolation", "No system impact", "Reversible"],
                    risks=["Must activate venv to use package"],
                    affects_packages=[pkg],
                )
            )

            # Strategy 2: Try newer version
            strategies.append(
                ResolutionStrategy(
                    strategy_type=StrategyType.UPGRADE,
                    description=f"Install newer version of {pkg} (may be compatible)",
                    safety_score=0.75,
                    commands=[f"pip install --upgrade {escape_command_arg(pkg)}"],
                    benefits=["May resolve compatibility", "Gets latest features"],
                    risks=["May have different features than requested version"],
                    affects_packages=[pkg],
                )
            )

            # Strategy 3: Downgrade conflicting package
            if conflict.required_constraint and validate_version_constraint(
                conflict.required_constraint
            ):
                strategies.append(
                    ResolutionStrategy(
                        strategy_type=StrategyType.DOWNGRADE,
                        description=f"Downgrade {conflicting} to compatible version",
                        safety_score=0.50,
                        commands=[
                            f"pip install {escape_command_arg(conflicting)}{conflict.required_constraint}"
                        ],
                        benefits=[f"Satisfies {pkg} requirements"],
                        risks=[f"May affect packages depending on {conflicting}"],
                        affects_packages=[conflicting],
                    )
                )

            # Strategy 4: Remove conflicting (risky)
            strategies.append(
                ResolutionStrategy(
                    strategy_type=StrategyType.REMOVE_CONFLICT,
                    description=f"Remove {conflicting} (not recommended)",
                    safety_score=0.10,
                    commands=[
                        f"pip uninstall -y {escape_command_arg(conflicting)}",
                        f"pip install {escape_command_arg(pkg)}",
                    ],
                    benefits=["Resolves conflict directly"],
                    risks=["May break dependent packages", "Data loss possible"],
                    affects_packages=[conflicting, pkg],
                )
            )

        # Sort by safety and deduplicate
        strategies.sort(key=lambda s: s.safety_score, reverse=True)
        seen = set()
        unique = []
        for s in strategies:
            key = (s.strategy_type, s.description)
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique[:4]  # Return top 4 strategies

    def record_resolution(
        self,
        conflict: ConflictPrediction,
        chosen_strategy: ResolutionStrategy,
        success: bool,
        user_feedback: str | None = None,
    ) -> None:
        """Record conflict resolution for learning."""
        logger.info(
            f"Recording resolution: {chosen_strategy.strategy_type.value} - "
            f"{'success' if success else 'failed'}"
        )


# ============================================================================
# System Prompts for LLM
# ============================================================================

COMBINED_ANALYSIS_SYSTEM_PROMPT = """You are an expert Linux/Python dependency analyzer.
Your job is to predict package conflicts BEFORE installation AND suggest resolutions.

Analyze the user's installed packages and the package they want to install.
Based on your knowledge of package ecosystems (PyPI, apt), identify potential conflicts.

Respond with JSON in this exact format:
{
  "has_conflicts": true/false,
  "conflicts": [
    {
      "conflicting_package": "numpy",
      "current_version": "2.1.0",
      "required_constraint": "< 2.0",
      "type": "VERSION",
      "confidence": 0.95,
      "severity": "HIGH",
      "explanation": "tensorflow 2.15 requires numpy < 2.0, but numpy 2.1.0 is installed",
      "installed_by": "pandas",
      "affected_packages": ["pandas", "scipy"]
    }
  ],
  "strategies": [
    {
      "type": "VENV",
      "description": "Create virtual environment with compatible versions (safest)",
      "safety_score": 0.95,
      "commands": ["python3 -m venv myenv", "source myenv/bin/activate", "pip install package"],
      "benefits": ["Complete isolation", "No system impact"],
      "risks": ["Must activate venv to use"],
      "affects_packages": ["package"]
    },
    {
      "type": "DOWNGRADE",
      "description": "Downgrade conflicting package to compatible version",
      "safety_score": 0.70,
      "commands": ["pip install 'numpy<2.0'"],
      "benefits": ["Simple fix"],
      "risks": ["May affect other packages"],
      "affects_packages": ["numpy"]
    }
  ]
}

If no conflicts, respond with:
{"has_conflicts": false, "conflicts": [], "strategies": []}

Strategy types: VENV, UPGRADE, DOWNGRADE, REMOVE_CONFLICT, ALTERNATIVE
Safety scores: 0.0-1.0 (higher = safer)

IMPORTANT:
- Only report REAL conflicts you're confident about
- Always include VENV as the safest option
- Rank strategies by safety_score (highest first)
- Provide 3-4 strategies if conflicts exist"""

CONFLICT_ANALYSIS_SYSTEM_PROMPT = """You are an expert Linux/Python dependency analyzer.
Your job is to predict package conflicts BEFORE installation.

Analyze the user's installed packages and the package they want to install.
Based on your knowledge of package ecosystems (PyPI, apt), identify potential conflicts.

Common conflict patterns to check:
- numpy version requirements (tensorflow, pandas, scipy often conflict)
- CUDA/GPU library versions
- Flask/Django with specific Werkzeug versions
- Packages that install conflicting system libraries

Respond with JSON in this exact format:
{
  "has_conflicts": true/false,
  "conflicts": [
    {
      "conflicting_package": "numpy",
      "current_version": "2.1.0",
      "required_constraint": "< 2.0",
      "type": "VERSION",
      "confidence": 0.95,
      "severity": "HIGH",
      "explanation": "tensorflow 2.15 requires numpy < 2.0, but numpy 2.1.0 is installed",
      "installed_by": "pandas",
      "affected_packages": ["pandas", "scipy"]
    }
  ]
}

If no conflicts, respond with:
{"has_conflicts": false, "conflicts": []}

IMPORTANT: Only report REAL conflicts you're confident about. Don't make up issues."""

RESOLUTION_SYSTEM_PROMPT = """You are an expert at resolving Python/Linux dependency conflicts.
Given a list of conflicts, suggest practical resolution strategies.

Respond with JSON in this format:
{
  "strategies": [
    {
      "type": "VENV",
      "description": "Install in virtual environment (safest)",
      "safety_score": 0.95,
      "commands": ["python3 -m venv myenv", "source myenv/bin/activate", "pip install package"],
      "benefits": ["Complete isolation", "No system impact"],
      "risks": ["Must activate venv to use"],
      "affects_packages": ["package"]
    }
  ]
}

Strategy types: UPGRADE, DOWNGRADE, VENV, REMOVE_CONFLICT, ALTERNATIVE
Safety scores: 0.0-1.0 (higher = safer)

Rank strategies by safety. Always include VENV as a safe option."""


# ============================================================================
# JSON Parsing Utilities
# ============================================================================


def extract_json_from_response(response: str) -> dict | None:
    """Safely extract first valid JSON object from LLM response.

    Uses JSONDecoder to properly handle nested structures instead of greedy regex.
    This prevents issues with multiple JSON blocks or text after the JSON.
    """
    if not response:
        return None

    decoder = json.JSONDecoder()
    idx = 0

    while idx < len(response):
        idx = response.find("{", idx)
        if idx == -1:
            return None

        try:
            obj, end_idx = decoder.raw_decode(response, idx)
            return obj
        except json.JSONDecodeError:
            idx += 1

    return None


# ============================================================================
# Display Functions
# ============================================================================


def format_conflict_summary(
    conflicts: list[ConflictPrediction], strategies: list[ResolutionStrategy]
) -> str:
    """Format conflicts and strategies for CLI display."""
    if not conflicts:
        return ""

    output = "\n"

    # Show conflicts
    for conflict in conflicts:
        output += f"⚠️  Conflict predicted: {conflict.explanation}\n"

        if conflict.current_version:
            installed_by = (
                f" (installed by {conflict.installed_by})" if conflict.installed_by else ""
            )
            output += f"    Your system has {conflict.package2} {conflict.current_version}{installed_by}\n"

        output += (
            f"    Confidence: {int(conflict.confidence * 100)}% | Severity: {conflict.severity}\n"
        )

        if conflict.affected_packages:
            other = [
                p
                for p in conflict.affected_packages
                if p not in (conflict.package1, conflict.package2)
            ]
            if other:
                output += f"    Also affects: {', '.join(other[:5])}\n"

        output += "\n"

    # Show strategies
    if strategies:
        output += "\n    Suggestions (ranked by safety):\n"

        for i, strategy in enumerate(strategies[:4], 1):
            recommended = " [RECOMMENDED]" if i == 1 else ""
            output += f"    {i}. {strategy.description}{recommended}\n"

            # Safety bar
            pct = int(strategy.safety_score * 100)
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            output += f"       Safety: [{bar}] {pct}%\n"

            if strategy.benefits:
                output += f"       ✓ {strategy.benefits[0]}\n"
            if strategy.risks:
                output += f"       ⚠ {strategy.risks[0]}\n"

            output += "\n"

    return output


def prompt_resolution_choice(
    strategies: list[ResolutionStrategy], auto_select: bool = False
) -> tuple[ResolutionStrategy | None, int]:
    """Prompt user to choose a resolution strategy."""
    if not strategies:
        return None, -1

    if auto_select:
        return strategies[0], 0

    max_choices = min(4, len(strategies))

    try:
        prompt = f"\n    Proceed with option 1? [Y/n/2-{max_choices}]: "
        choice = input(prompt).strip().lower()

        if choice in ("", "y", "yes"):
            return strategies[0], 0

        if choice in ("n", "no", "q"):
            return None, -1

        try:
            idx = int(choice) - 1
            if 0 <= idx < max_choices:
                return strategies[idx], idx
        except ValueError:
            pass

        print("    Invalid choice. Using option 1.")
        return strategies[0], 0

    except (EOFError, KeyboardInterrupt):
        print("\n    Cancelled.")
        return None, -1


# ============================================================================
# Helper Functions
# ============================================================================


def get_pip_packages() -> dict[str, str]:
    """Get installed pip packages with timeout protection."""
    try:
        result = subprocess.run(
            ["pip3", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=5,  # Reduced from 15 to prevent UI blocking
        )
        if result.returncode == 0:
            packages = json.loads(result.stdout)
            return {pkg["name"]: pkg["version"] for pkg in packages}
    except subprocess.TimeoutExpired:
        logger.debug("pip3 list timed out after 5 seconds")
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse pip output as JSON: {e}")
    except FileNotFoundError:
        logger.debug("pip3 command not found")
    except Exception as e:
        logger.debug(f"Failed to get pip packages: {e}")
    return {}


def get_apt_packages_summary() -> list[str]:
    """Get summary of relevant apt packages with timeout protection."""
    relevant_prefixes = [
        "python",
        "lib",
        "cuda",
        "nvidia",
        "tensorflow",
        "torch",
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
    ]

    try:
        result = subprocess.run(
            ["dpkg", "--get-selections"],
            capture_output=True,
            text=True,
            timeout=5,  # Reduced from 10 to prevent UI blocking
        )
        if result.returncode == 0:
            packages = []
            for line in result.stdout.split("\n"):
                if "\tinstall" in line:
                    try:
                        pkg = line.split()[0]
                        if any(pkg.startswith(p) for p in relevant_prefixes):
                            packages.append(pkg)
                    except (IndexError, ValueError):
                        continue  # Skip malformed lines
            return packages[:30]
    except subprocess.TimeoutExpired:
        logger.debug("dpkg --get-selections timed out after 5 seconds")
    except FileNotFoundError:
        logger.debug("dpkg command not found")
    except Exception as e:
        logger.debug(f"Failed to get apt packages: {e}")
    return []


# ============================================================================
# CLI Interface
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Predict dependency conflicts")
    parser.add_argument("package", help="Package name to analyze")
    parser.add_argument("--version", help="Specific version")
    parser.add_argument("--resolve", action="store_true", help="Show resolutions")

    args = parser.parse_args()

    predictor = ConflictPredictor()

    print(f"\n🔍 Analyzing {args.package}...")
    conflicts = predictor.predict_conflicts(args.package, args.version)

    if not conflicts:
        print("✅ No conflicts predicted!")
    else:
        strategies = predictor.generate_resolutions(conflicts) if args.resolve else []
        print(format_conflict_summary(conflicts, strategies))
