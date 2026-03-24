"""
Dependency conflict prediction for CX Linux pre-install flows.

MVP scope:
- Analyze apt/dpkg metadata before install.
- Predict conflicts with confidence scores.
- Rank resolution suggestions by safety.
- Include a pip conflict check path.
- Provide CLI output for operators.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple


@dataclass
class ConflictFinding:
    ecosystem: str  # apt | pip
    package: str
    issue: str
    confidence: float
    evidence: str


@dataclass
class ResolutionSuggestion:
    action: str
    safety_score: float
    rationale: str


@dataclass
class PredictionResult:
    findings: List[ConflictFinding]
    suggestions: List[ResolutionSuggestion]

    @property
    def overall_confidence(self) -> float:
        if not self.findings:
            return 0.0
        return round(sum(item.confidence for item in self.findings) / len(self.findings), 3)


def _run_cmd(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_name_from_alt_dep(token: str) -> str:
    # apt-cache outputs alternatives with "pkg | other" and architecture suffixes.
    token = token.strip().split("|")[0].strip()
    token = token.split(":")[0]
    token = token.split(" ")[0]
    return token


def _parse_apt_field(line: str, field: str) -> List[str]:
    if not line.startswith(field + ":"):
        return []
    value = line.split(":", 1)[1].strip()
    if not value:
        return []
    items: List[str] = []
    for part in value.split(","):
        part = part.strip()
        name = _parse_name_from_alt_dep(part)
        if name:
            items.append(name)
    return items


def _iter_apt_fields(show_output: str, field: str) -> List[str]:
    items: List[str] = []
    current_value = ""

    for raw_line in show_output.splitlines():
        if raw_line.startswith(field + ":"):
            if current_value:
                items.extend(_parse_apt_field(f"{field}: {current_value}", field))
            current_value = raw_line.split(":", 1)[1].strip()
            continue

        if current_value and raw_line.startswith(" "):
            current_value = f"{current_value} {raw_line.strip()}".strip()
            continue

        if current_value:
            items.extend(_parse_apt_field(f"{field}: {current_value}", field))
            current_value = ""

    if current_value:
        items.extend(_parse_apt_field(f"{field}: {current_value}", field))

    return items


def get_installed_dpkg_packages(run_cmd: Callable[[Sequence[str]], str] = _run_cmd) -> Dict[str, str]:
    output = run_cmd(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"])
    installed: Dict[str, str] = {}
    for row in output.splitlines():
        cols = row.strip().split("\t")
        if len(cols) == 2:
            installed[cols[0]] = cols[1]
    return installed


def inspect_apt_package(
    package: str,
    installed: Dict[str, str],
    run_cmd: Callable[[Sequence[str]], str] = _run_cmd,
) -> List[ConflictFinding]:
    findings: List[ConflictFinding] = []

    show_output = run_cmd(["apt-cache", "show", package])
    if not show_output:
        findings.append(
            ConflictFinding(
                ecosystem="apt",
                package=package,
                issue="package-not-found",
                confidence=0.8,
                evidence=f"apt-cache show {package} returned no metadata",
            )
        )
        return findings

    conflicts: List[str] = []
    breaks: List[str] = []
    depends: List[str] = []

    conflicts.extend(_iter_apt_fields(show_output, "Conflicts"))
    breaks.extend(_iter_apt_fields(show_output, "Breaks"))
    depends.extend(_iter_apt_fields(show_output, "Depends"))

    for target in conflicts:
        if target in installed:
            findings.append(
                ConflictFinding(
                    ecosystem="apt",
                    package=package,
                    issue="conflicts-installed-package",
                    confidence=0.95,
                    evidence=f"{package} Conflicts with installed package {target}",
                )
            )

    for target in breaks:
        if target in installed:
            findings.append(
                ConflictFinding(
                    ecosystem="apt",
                    package=package,
                    issue="breaks-installed-package",
                    confidence=0.9,
                    evidence=f"{package} Breaks installed package {target}",
                )
            )

    # Soft risk: many unmet deps in an unstable system may indicate install friction.
    missing = [dep for dep in depends if dep and dep not in installed]
    if len(missing) >= 5:
        findings.append(
            ConflictFinding(
                ecosystem="apt",
                package=package,
                issue="many-missing-dependencies",
                confidence=0.55,
                evidence=f"{package} has {len(missing)} dependencies not currently installed",
            )
        )

    return findings


def _parse_req_name_and_constraints(spec: str) -> Tuple[str, str]:
    # MVP parser for common pip specs: name, name==x, name>=x,<y
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(.*)$", spec.strip())
    if not match:
        return spec.strip().lower(), ""
    return match.group(1).lower(), match.group(2).strip()


def _split_version(version: str) -> Tuple[int, ...]:
    parts = re.findall(r"\d+", version)
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)


def _version_satisfies_constraint(version: str, constraint: str) -> bool:
    # Minimal comparator support for MVP: ==,!=,>=,<=,>,< with comma-separated clauses.
    if not constraint:
        return True

    parsed_version = _split_version(version)
    comparators = {
        "==": lambda other: parsed_version == other,
        "!=": lambda other: parsed_version != other,
        ">=": lambda other: parsed_version >= other,
        "<=": lambda other: parsed_version <= other,
        ">": lambda other: parsed_version > other,
        "<": lambda other: parsed_version < other,
    }

    for clause in [item.strip() for item in constraint.split(",") if item.strip()]:
        op_match = re.match(r"^(==|!=|>=|<=|>|<)\s*([A-Za-z0-9_.-]+)$", clause)
        if not op_match:
            continue
        operator, rhs_raw = op_match.groups()
        if not comparators[operator](_split_version(rhs_raw)):
            return False
    return True


def _find_unsupported_constraint_clauses(constraint: str) -> List[str]:
    unsupported: List[str] = []
    for clause in [c.strip() for c in constraint.split(",") if c.strip()]:
        if re.match(r"^(==|!=|>=|<=|>|<)\s*([A-Za-z0-9_.-]+)$", clause):
            continue
        unsupported.append(clause)
    return unsupported


def _build_requested_constraint_map(requested: Sequence[Tuple[str, str]]) -> Dict[str, str]:
    return {name: constraint for name, constraint in requested}


def _inspect_requested_pip_constraints(
    requested: Sequence[Tuple[str, str]],
    installed: Dict[str, str],
) -> List[ConflictFinding]:
    findings: List[ConflictFinding] = []

    for name, constraint in requested:
        for clause in _find_unsupported_constraint_clauses(constraint):
            findings.append(
                ConflictFinding(
                    ecosystem="pip",
                    package=name,
                    issue="unsupported-constraint",
                    confidence=0.7,
                    evidence=f"Unsupported version clause '{clause}' in requested constraint '{constraint}'",
                )
            )

        installed_version = installed.get(name)
        if installed_version and constraint and not _version_satisfies_constraint(installed_version, constraint):
            findings.append(
                ConflictFinding(
                    ecosystem="pip",
                    package=name,
                    issue="installed-version-violates-requested-constraint",
                    confidence=0.85,
                    evidence=f"Installed {name}=={installed_version} does not satisfy {constraint}",
                )
            )

    return findings


def _inspect_reverse_dependency_risks(
    distributions: Sequence[importlib.metadata.Distribution],
    requested_constraints: Dict[str, str],
) -> List[ConflictFinding]:
    findings: List[ConflictFinding] = []

    for dist in distributions:
        parent = (dist.metadata.get("Name") or "").lower()
        if not parent:
            continue
        requires = dist.requires or []
        for requirement in requires:
            dep_name, dep_constraint = _parse_req_name_and_constraints(requirement)
            requested_constraint = requested_constraints.get(dep_name)
            if requested_constraint and dep_constraint and dep_constraint != requested_constraint:
                findings.append(
                    ConflictFinding(
                        ecosystem="pip",
                        package=dep_name,
                        issue="reverse-dependency-constraint-risk",
                        confidence=0.65,
                        evidence=f"{parent} requires '{requirement}', requested '{dep_name}{requested_constraint}'",
                    )
                )
                break

    return findings


def inspect_pip_requirements(requested_specs: List[str]) -> List[ConflictFinding]:
    findings: List[ConflictFinding] = []
    if not requested_specs:
        return findings

    distributions = list(importlib.metadata.distributions())
    installed: Dict[str, str] = {}
    for dist in distributions:
        name = (dist.metadata.get("Name") or "").lower()
        if name:
            installed[name] = dist.version

    requested = [_parse_req_name_and_constraints(spec) for spec in requested_specs]
    findings.extend(_inspect_requested_pip_constraints(requested, installed))
    findings.extend(_inspect_reverse_dependency_risks(distributions, _build_requested_constraint_map(requested)))
    return findings


def rank_suggestions(findings: List[ConflictFinding]) -> List[ResolutionSuggestion]:
    if not findings:
        return [
            ResolutionSuggestion(
                action="Proceed with install",
                safety_score=0.97,
                rationale="No obvious package conflicts detected in current metadata scan.",
            )
        ]

    suggestions = [
        ResolutionSuggestion(
            action="Dry-run apt transaction (apt-get -s install ...) before applying",
            safety_score=0.96,
            rationale="Simulation validates solver decisions without changing system state.",
        ),
        ResolutionSuggestion(
            action="Prefer non-destructive version pinning over package removal",
            safety_score=0.9,
            rationale="Pinning lowers breakage risk while preserving currently working packages.",
        ),
        ResolutionSuggestion(
            action="Isolate risky pip installs in virtualenv",
            safety_score=0.88,
            rationale="Environment isolation prevents global dependency contamination.",
        ),
        ResolutionSuggestion(
            action="Remove conflicting packages only after explicit review",
            safety_score=0.52,
            rationale="Package removal can cascade into service disruption.",
        ),
    ]
    return sorted(suggestions, key=lambda x: x.safety_score, reverse=True)


def predict_conflicts(
    apt_packages: List[str],
    pip_requirements: Optional[List[str]] = None,
    run_cmd: Callable[[Sequence[str]], str] = _run_cmd,
) -> PredictionResult:
    installed = get_installed_dpkg_packages(run_cmd=run_cmd)
    findings: List[ConflictFinding] = []

    for package in apt_packages:
        findings.extend(inspect_apt_package(package, installed=installed, run_cmd=run_cmd))

    findings.extend(inspect_pip_requirements(pip_requirements or []))

    suggestions = rank_suggestions(findings)
    return PredictionResult(findings=findings, suggestions=suggestions)


def render_cli(result: PredictionResult) -> None:
    print(f"Conflict prediction confidence: {result.overall_confidence:.3f}")
    print("\nPredicted Conflicts")
    print("-" * 80)

    if not result.findings:
        print("none | No high-risk conflicts found")
    else:
        for finding in result.findings:
            print(
                f"{finding.ecosystem} | {finding.package} | {finding.issue} | "
                f"{finding.confidence:.3f} | {finding.evidence}"
            )

    print("\nResolution Suggestions (ranked by safety)")
    print("-" * 80)
    for suggestion in result.suggestions:
        print(f"{suggestion.safety_score:.2f} | {suggestion.action} | {suggestion.rationale}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CX pre-install dependency conflict predictor")
    parser.add_argument("--apt", nargs="*", default=[], help="apt packages planned for install")
    parser.add_argument("--pip", nargs="*", default=[], help="pip requirement specs planned for install")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    args = parser.parse_args()

    result = predict_conflicts(apt_packages=args.apt, pip_requirements=args.pip)

    if args.json:
        payload = {
            "overall_confidence": result.overall_confidence,
            "findings": [asdict(f) for f in result.findings],
            "suggestions": [asdict(s) for s in result.suggestions],
        }
        print(json.dumps(payload, indent=2))
    else:
        render_cli(result)

    # Non-zero code only for confidence-worthy risks.
    if any(f.confidence >= 0.85 for f in result.findings):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
