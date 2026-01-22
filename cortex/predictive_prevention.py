#!/usr/bin/env python3
"""
Predictive Error Prevention System for Cortex Linux

Analyzes installation requests before execution to predict and prevent failures.
Uses hardware detection, historical failure analysis, and LLM-backed risk assessment.

Issue: #54
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Optional

from cortex.hardware_detection import HardwareDetector, SystemInfo
from cortex.installation_history import InstallationHistory, InstallationStatus
from cortex.llm_router import LLMProvider, LLMRouter, TaskType

logger = logging.getLogger(__name__)


class RiskLevel(IntEnum):
    """Risk levels for installation operations."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class FailurePrediction:
    """Detailed prediction of potential installation failures."""

    risk_level: RiskLevel = RiskLevel.NONE
    reasons: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    predicted_errors: list[str] = field(default_factory=list)
    context_data: dict[str, Any] = field(default_factory=dict)


class PredictiveErrorManager:
    """
    Manages predictive error analysis for software installations.

    Combines:
    1. Hardware compatibility checks
    2. Historical failure analysis
    3. LLM-based risk prediction
    """

    def __init__(self, api_key: str | None = None, provider: str | None = None):
        self.detector = HardwareDetector()
        self.history = InstallationHistory()
        self.api_key = api_key
        # Normalize provider casing to avoid missed API-key wiring
        normalized_provider = provider.lower() if provider else None
        self.provider = normalized_provider

        # Handle 'fake' provider used in testing
        llm_provider = LLMProvider.OLLAMA
        if normalized_provider:
            try:
                llm_provider = LLMProvider(normalized_provider)
            except ValueError:
                # Fallback to OLLAMA if 'fake' or other unknown provider is passed
                logger.warning(
                    f"Provider '{provider}' not in LLMProvider enum, using OLLAMA fallback"
                )
                llm_provider = LLMProvider.OLLAMA

        self.router = LLMRouter(
            claude_api_key=api_key if normalized_provider == "claude" else None,
            kimi_api_key=api_key if normalized_provider == "kimi_k2" else None,
            default_provider=llm_provider,
        )

    def analyze_installation(
        self, software: str, commands: list[str], redact: bool = True
    ) -> FailurePrediction:
        """
        Analyze a planned installation for potential risks.

        Args:
            software: The software request string
            commands: List of commands planned for execution
            redact: Whether to redact sensitive data before LLM call

        Returns:
            FailurePrediction object with risk details
        """
        logger.info(f"Analyzing installation risk for: {software}")

        prediction = FailurePrediction()

        # 1. Get system context
        system_info = self.detector.detect()
        prediction.context_data["system"] = system_info.to_dict()

        # 2. Check basic system compatibility (Static rules)
        self._check_static_compatibility(software, system_info, prediction)

        # 3. Analyze history for similar failures
        self._analyze_history_patterns(software, commands, prediction)

        # 4. LLM-backed advanced prediction (if AI available and not in fake mode)
        if (self.api_key or self.provider == "ollama") and self.provider != "fake":
            # Redact sensitive data from commands before sending to LLM if requested
            redacted_commands = self.redact_commands(commands) if redact else commands
            self._get_llm_prediction(software, redacted_commands, system_info, prediction)

        # 5. Final risk level adjustment based on findings
        self._finalize_risk_level(prediction)

        return prediction

    def redact_commands(self, commands: list[str]) -> list[str]:
        """Mask potential tokens, passwords, and API keys in commands."""
        # Common patterns for sensitive data in CLI commands:
        # 1. --password PASSWORD or --api-key=TOKEN
        # 2. env vars like AUTH_TOKEN=xxx
        redacted = []
        redact_count = 0
        for cmd in commands:
            # Mask common credential flags (handles both spaces and equals)
            new_cmd, count1 = re.subn(
                r"(?i)(--?(?:token|api[-_]?key|password|secret|pwd|auth|key)(?:\s+|=))(\S+)",
                r"\1<REDACTED>",
                cmd,
            )
            # Mask env var assignments
            new_cmd, count2 = re.subn(
                r"(?i)\b([A-Z0-9_-]*(?:TOKEN|PASSWORD|SECRET|KEY|AUTH)=)(\S+)",
                r"\1<REDACTED>",
                new_cmd,
            )
            redacted.append(new_cmd)
            redact_count += count1 + count2

        if redact_count > 0:
            logger.info(f"Redacted {redact_count} sensitive fields in commands before LLM call")

        return redacted

    def _check_static_compatibility(
        self, software: str, system: SystemInfo, prediction: FailurePrediction
    ) -> None:
        """Run fast, rule-based compatibility checks."""
        normalized_software = software.lower()

        # Kernel compatibility examples
        if "cuda" in normalized_software or "nvidia" in normalized_software:
            # Check for very old kernels (explicitly handle None/Empty case)
            if system.kernel_version:
                version_match = re.search(r"^(\d+)\.(\d+)", system.kernel_version)
                if version_match:
                    major = int(version_match.group(1))
                    minor = int(version_match.group(2))
                    if major < 5 or (major == 5 and minor < 4):
                        prediction.reasons.append(
                            f"Kernel version {system.kernel_version} may be too old for modern CUDA drivers (requires 5.4+)"
                        )
                        prediction.recommendations.append("Update kernel to 5.15+ first")
                        prediction.risk_level = max(prediction.risk_level, RiskLevel.HIGH)
                    else:  # Modern kernel (5.4+) found, check for driver synchronization risk
                        # Add a risk-focused warning for newer kernels regarding driver/header complexity
                        prediction.reasons.append(
                            f"Risk of driver-kernel mismatch on {system.kernel_version}. Modern CUDA requires perfectly synchronized kernel headers and drivers to avoid installation failure."
                        )
                        prediction.recommendations.append(
                            "Verify that official NVIDIA drivers and matching kernel headers are installed before proceeding"
                        )
                        prediction.risk_level = max(prediction.risk_level, RiskLevel.LOW)

        # RAM checks
        ram_gb = system.memory.total_gb
        if "docker" in normalized_software and ram_gb < 2:
            prediction.reasons.append(
                f"Low RAM detected ({ram_gb}GB). Docker may perform poorly or fail to start containers."
            )
            prediction.recommendations.append("Ensure at least 4GB RAM for Docker environments")
            prediction.risk_level = max(prediction.risk_level, RiskLevel.MEDIUM)

        # Disk space checks
        for storage in system.storage:
            if storage.mount_point == "/" and storage.available_gb < 2:
                prediction.reasons.append(
                    f"Critically low disk space on root ({storage.available_gb:.1f} GB free)"
                )
                prediction.recommendations.append(
                    "Free up at least 5GB of disk space before proceeding"
                )
                prediction.risk_level = max(prediction.risk_level, RiskLevel.CRITICAL)

    def _analyze_history_patterns(
        self, software: str, commands: list[str], prediction: FailurePrediction
    ) -> None:
        """Learn from past failures in the installation records."""
        history = self.history.get_history(limit=50, status_filter=InstallationStatus.FAILED)

        if not history:
            return

        request_packages = set(software.lower().split())
        # Also extract from commands
        extracted = self.history._extract_packages_from_commands(commands)
        request_packages.update(p.lower() for p in extracted)

        failure_count = 0
        common_errors = []

        for record in history:
            record_packages = [p.lower() for p in record.packages]
            match_found = False
            for req_pkg in request_packages:
                if len(req_pkg) < 2:
                    continue  # Ignore single letters like 'a'
                for hist_pkg in record_packages:
                    # Partial match for package names (e.g., 'docker' matches 'docker.io')
                    if req_pkg in hist_pkg or hist_pkg in req_pkg:
                        match_found = True
                        break
                if match_found:
                    break

            if match_found:
                failure_count += 1
                if record.error_message and record.error_message not in common_errors:
                    common_errors.append(record.error_message)

        if failure_count > 0:
            prediction.reasons.append(
                f"This software (or related components) failed {failure_count} times in previous attempts."
            )
            prediction.predicted_errors.extend(common_errors[:3])

            if failure_count >= 3:
                prediction.risk_level = max(prediction.risk_level, RiskLevel.HIGH)
            else:
                prediction.risk_level = max(prediction.risk_level, RiskLevel.MEDIUM)

    def _get_llm_prediction(
        self, software: str, commands: list[str], system: SystemInfo, prediction: FailurePrediction
    ) -> None:
        """Use LLM to predict complex failure scenarios."""
        try:
            # Prepare context for LLM
            context = {
                "software": software,
                "commands": commands,
                "system_context": {
                    "kernel": system.kernel_version,
                    "distro": f"{system.distro or 'Unknown'} {system.distro_version or ''}".strip(),
                    "cpu": system.cpu.model,
                    "gpu": [g.model for g in system.gpu],
                    "ram_gb": system.memory.total_gb,
                    "virtualization": system.virtualization,
                },
                "history_reasons": prediction.reasons,
                "static_reasons": prediction.reasons,
            }

            prompt = f"""
            Analyze the following installation request for potential failure risks on this specific Linux system.

            USER REQUEST: {software}
            COMMANDS PLANNED: {json.dumps(commands)}
            SYSTEM CONTEXT: {json.dumps(context["system_context"])}

            Identify specific reasons why this might fail (dependency conflicts, hardware mismatches, kernel requirements, etc.).
            Provide your response in JSON format with the following keys:
            - risk_level: "none", "low", "medium", "high", "critical"
            - reasons: list of strings (specific risks)
            - recommendations: list of strings (how to prevent failure)
            - predicted_errors: list of strings (likely error messages)
            """

            messages = [
                {
                    "role": "system",
                    "content": "You are a Linux system expert specializing in installation failure prediction and prevention.",
                },
                {"role": "user", "content": prompt},
            ]

            response = self.router.complete(
                messages=messages, task_type=TaskType.ERROR_DEBUGGING, temperature=0.3
            )

            # Try to parse JSON from response
            try:
                # Find JSON block if it's wrapped in markdown
                json_str = response.content
                # Robust parsing: handle markdown code blocks or raw JSON
                # Removed \s* inside regex to prevent potential backtracking issues (ReDoS)
                code_block_match = re.search(r"```(?:json)?(.*?)```", json_str, re.DOTALL)
                if code_block_match:
                    json_str = code_block_match.group(1).strip()

                # Cleanup potential non-json characters
                json_data = json.loads(json_str)

                # Update prediction
                llm_risk_str = json_data.get("risk_level", "none").lower()
                mapping = {
                    "none": RiskLevel.NONE,
                    "low": RiskLevel.LOW,
                    "medium": RiskLevel.MEDIUM,
                    "high": RiskLevel.HIGH,
                    "critical": RiskLevel.CRITICAL,
                }
                llm_risk = mapping.get(llm_risk_str, RiskLevel.NONE)

                if llm_risk > prediction.risk_level:
                    prediction.risk_level = llm_risk

                prediction.reasons.extend(json_data.get("reasons", []))
                prediction.recommendations.extend(json_data.get("recommendations", []))
                prediction.predicted_errors.extend(json_data.get("predicted_errors", []))

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                # Fallback: just use the content if it's not JSON
                if "Risk:" in response.content:
                    prediction.reasons.append(
                        "LLM detected risks: " + response.content[:200] + "..."
                    )

        except Exception as e:
            logger.error(f"LLM prediction failed: {e}")
            prediction.reasons.append(f"Advanced AI analysis unavailable: {str(e)}")

    def _finalize_risk_level(self, prediction: FailurePrediction) -> None:
        """Clean up and finalize the risk assessment."""
        # Deduplicate reasons and recommendations
        prediction.reasons = list(dict.fromkeys(prediction.reasons))
        prediction.recommendations = list(dict.fromkeys(prediction.recommendations))
        prediction.predicted_errors = list(dict.fromkeys(prediction.predicted_errors))

        # Ensure risk level matches the number of reasons if not already high
        if prediction.reasons and prediction.risk_level == RiskLevel.NONE:
            prediction.risk_level = RiskLevel.LOW

        # Escalate based on critical keywords in reasons
        reasons_lower = [r.lower() for r in prediction.reasons]
        if any("critical" in r for r in reasons_lower):
            prediction.risk_level = max(prediction.risk_level, RiskLevel.CRITICAL)
        elif any("unsupported" in r for r in reasons_lower):
            prediction.risk_level = max(prediction.risk_level, RiskLevel.HIGH)


if __name__ == "__main__":
    # Test block
    manager = PredictiveErrorManager(provider="ollama")
    pred = manager.analyze_installation("cuda-12.0", ["sudo apt-get install cuda-12.0"])
    print(f"Risk Level: {pred.risk_level}")
    print(f"Reasons: {pred.reasons}")
    print(f"Recommendations: {pred.recommendations}")
