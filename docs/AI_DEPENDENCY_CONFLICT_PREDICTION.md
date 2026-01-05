# AI-Powered Dependency Conflict Prediction

**Issue**: #428 - Dependency Conflict Prediction
**Status**: Implemented

## Overview

Cortex Linux includes AI-powered dependency conflict prediction that detects and resolves package conflicts BEFORE installation, unlike traditional tools (apt, dpkg) that only report errors after failure.

## Features

- **Predict conflicts BEFORE installation** - Analyzes dependencies and system state before attempting install
- **Version constraint analysis** - Parses and validates version constraints like `< 2.0`, `>= 1.5`
- **Transitive dependency tracking** - Identifies which package originally installed a conflicting dependency
- **Multiple resolution strategies** - Offers UPGRADE, DOWNGRADE, VENV, and REMOVE options
- **Safety-ranked suggestions** - Strategies sorted by safety score with `[RECOMMENDED]` label
- **Learning from history** - Records resolution outcomes to improve future suggestions
- **Works with both apt AND pip packages** - Major pain point addressed

## Example Usage

```bash
$ cortex install tensorflow

🔍 Checking for dependency conflicts...

⚠️  Conflict predicted: tensorflow 2.15 requires numpy < 2.0, but you have 2.1.0 (installed by pandas)
    Your system has numpy 2.1.0 (installed by pandas)
    Confidence: 95% | Severity: HIGH
    Also affects: scipy, matplotlib

    Suggestions (ranked by safety):
    1. Install tensorflow 2.16 (compatible with numpy 2.1.0) [RECOMMENDED]
       Safety: [████████░░] 80%
       ✓ Uses newer version 2.16
       ⚠ May have different features than requested version

    2. Downgrade numpy to 1.26.4
       Safety: [██████░░░░] 60%
       ✓ Satisfies tensorflow requirement (< 2.0)
       ⚠ May affect: pandas, scipy, matplotlib

    3. Install tensorflow in virtual environment (isolate)
       Safety: [█████████░] 95%
       ✓ Complete isolation
       ⚠ Must activate venv to use package

    4. Remove numpy (not recommended)
       Safety: [██░░░░░░░░] 20%
       ✓ Resolves conflict directly
       ⚠ May break dependent packages

    Proceed with option 1? [Y/n/2-4]:
```

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     CLI Layer (cli.py)                      │
│            Entry point: `cortex install <package>`          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              ConflictPredictor (conflict_predictor.py)      │
│               • Analyze dependency graph                    │
│               • Predict conflicts (rule-based + AI)         │
│               • Generate resolution strategies              │
│               • Rank solutions by safety                    │
│               • Record outcomes for learning                │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┬─────────────┐
        │              │              │             │
        ▼              ▼              ▼             ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│ Dependency   │ │   LLM    │ │ System   │ │   History    │
│  Resolver    │ │  Router  │ │ State    │ │   Database   │
│  (existing)  │ │(existing)│ │ Parser   │ │  (existing)  │
└──────────────┘ └──────────┘ └──────────┘ └──────────────┘
```

## Core Components

### Module: `cortex/conflict_predictor.py`

#### LLM-Based Conflict Analysis

Unlike traditional package managers that use hardcoded rules, Cortex uses LLM analysis
for conflict prediction. This approach leverages the LLM's knowledge of package ecosystems
to identify complex conflicts that rule-based systems miss.

```python
# System state gathering (implemented)
get_pip_packages()          # -> {"numpy": "2.1.0", "pandas": "2.0.0", ...}
get_apt_packages_summary()  # -> ["python3", "libssl-dev", ...]

# Version constraint validation (implemented)
validate_version_constraint("< 2.0")   # -> True (safe format)
validate_version_constraint("; rm -rf") # -> False (injection attempt)

# Command argument escaping (implemented)
escape_command_arg("package; rm -rf /")  # -> "'package; rm -rf /'" (safe)
```

**Note**: Version parsing, comparison, and PyPI/apt version lookup are handled by
the LLM rather than explicit functions. The LLM analyzes the system state and uses
its knowledge of package ecosystems to predict conflicts.

#### Data Classes

```python
@dataclass
class ConflictPrediction:
    package1: str                    # Package being installed
    package2: str                    # Conflicting package
    conflict_type: ConflictType      # VERSION, PORT, LIBRARY, FILE, MUTUAL_EXCLUSION
    confidence: float                # 0.0 to 1.0
    explanation: str                 # Human-readable description
    affected_packages: list[str]     # Transitive impact
    severity: str                    # LOW, MEDIUM, HIGH, CRITICAL
    installed_by: str | None         # Package that installed the conflicting dependency
    current_version: str | None      # Currently installed version of package2
    required_constraint: str | None  # Version constraint required by package1

@dataclass
class ResolutionStrategy:
    strategy_type: StrategyType      # UPGRADE, DOWNGRADE, VENV, REMOVE_CONFLICT, etc.
    description: str                 # Human-readable description
    safety_score: float              # 0.0 to 1.0 (higher = safer)
    commands: list[str]              # Commands to execute
    benefits: list[str]              # Advantages of this strategy
    risks: list[str]                 # Potential downsides
    estimated_time_minutes: float    # Estimated execution time
    affects_packages: list[str]      # Packages that will be modified
```

#### ConflictPredictor Class

```python
class ConflictPredictor:
    def __init__(
        self,
        llm_router: LLMRouter | None = None,
        history: InstallationHistory | None = None
    ):
        """Initialize with optional LLM and history for learning."""

    def predict_conflicts(
        self,
        package_name: str,
        version: str | None = None
    ) -> list[ConflictPrediction]:
        """
        Predict conflicts for installing a package.

        Uses multiple detection methods:
        1. Rule-based detection (mutual exclusions, port conflicts)
        2. System state analysis (dpkg, pip)
        3. AI-powered detection (for complex scenarios)
        """

    def generate_resolutions(
        self,
        conflicts: list[ConflictPrediction]
    ) -> list[ResolutionStrategy]:
        """
        Generate and rank resolution strategies for conflicts.

        Returns strategies sorted by safety score (safest first).
        """

    def record_resolution(
        self,
        conflict: ConflictPrediction,
        chosen_strategy: ResolutionStrategy,
        success: bool,
        user_feedback: str | None = None
    ) -> float | None:
        """Record resolution outcome and return updated success rate for learning."""
```

#### Display Functions

```python
# Format conflicts for CLI display
format_conflicts_for_display(conflicts: list[ConflictPrediction]) -> str

# Format resolution strategies with [RECOMMENDED] label and safety bars
format_resolutions_for_display(strategies: list[ResolutionStrategy], limit: int = 5) -> str

# Combined summary matching the example UX
format_conflict_summary(conflicts, strategies) -> str

# Interactive prompt for resolution choice
prompt_resolution_choice(strategies, auto_select_recommended=False) -> tuple[ResolutionStrategy | None, int]
```

### Conflict Types

| Type | Description | Example |
|------|-------------|---------|
| `VERSION` | Version constraint violation | tensorflow requires numpy<2.0 |
| `MUTUAL_EXCLUSION` | Packages cannot coexist | mysql-server vs mariadb-server |
| `PORT` | Port binding conflict | apache2 vs nginx (port 80) |
| `LIBRARY` | System library conflict | Different OpenSSL versions |
| `FILE` | File path conflict | Multiple packages providing same file |
| `CIRCULAR` | Circular dependency | A depends on B depends on A |

### Resolution Strategy Types

| Type | Safety | Description |
|------|--------|-------------|
| `VENV` | 95% | Install in virtual environment (complete isolation) |
| `UPGRADE` | 80% | Install newer version compatible with dependencies |
| `ALTERNATIVE` | 75% | Use alternative package |
| `DOWNGRADE` | 60% | Downgrade conflicting package to compatible version |
| `REMOVE_CONFLICT` | 20% | Remove conflicting package (risky) |

### Safety Score Calculation

The safety score (0.0 to 1.0) is calculated based on:

1. **Base score by strategy type**:
   - VENV: 0.95 (highest - complete isolation)
   - UPGRADE: 0.80
   - ALTERNATIVE: 0.75
   - DOWNGRADE: 0.60
   - REMOVE_CONFLICT: 0.30 (lowest - risky)

2. **Adjustments**:
   - `-0.05` per risk listed
   - `-0.02` per affected package (beyond first 2)
   - `+0.10` if strategy has historical success rate > 80%
   - `+0.05` per benefit listed

## CLI Integration

The conflict prediction is integrated into the `cortex install` command:

```python
# In cli.py install() method

# Initialize predictor
predictor = ConflictPredictor(llm_router=llm_router, history=history)

# Predict conflicts
conflicts = predictor.predict_conflicts(package_name)

if conflicts:
    # Generate resolutions
    strategies = predictor.generate_resolutions(conflicts)

    # Display summary
    print(format_conflict_summary(conflicts, strategies))

    # Get user choice
    chosen_strategy, idx = prompt_resolution_choice(strategies)

    if chosen_strategy:
        # Prepend resolution commands
        commands = chosen_strategy.commands + commands
    else:
        return 1  # User cancelled

# After installation completes:
if predictor and chosen_strategy and conflicts:
    predictor.record_resolution(
        conflict=conflicts[0],
        chosen_strategy=chosen_strategy,
        success=result.success,
        user_feedback=result.error_message if not result.success else None
    )
```

## Database Schema

Resolution outcomes are stored in `installation_history.db` for learning:

```sql
CREATE TABLE IF NOT EXISTS conflict_resolutions (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    package_name TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    conflicting_package TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    strategy_description TEXT NOT NULL,
    success INTEGER NOT NULL,  -- 0 or 1
    user_feedback TEXT,
    system_state TEXT  -- JSON snapshot
);

CREATE INDEX idx_conflict_pkg ON conflict_resolutions(package_name);
CREATE INDEX idx_conflict_success ON conflict_resolutions(success);
CREATE INDEX idx_conflict_strategy ON conflict_resolutions(strategy_type);
```

## Testing

Run the test suite:

```bash
python -m pytest tests/test_conflict_predictor.py -v
```

### Test Coverage

- **TestConflictPrediction**: Data class creation and serialization
- **TestResolutionStrategy**: Strategy data class tests
- **TestConflictPredictor**: Predictor initialization, conflict detection
- **TestResolutionGeneration**: Strategy generation for different conflict types
- **TestSafetyScore**: Safety score calculation algorithm
- **TestSystemParsing**: dpkg status and pip package parsing
- **TestRecordResolution**: Recording outcomes for learning
- **TestSecurityValidation**: Security validation (constraint checking, command escaping)
- **TestCommandInjectionProtection**: Command injection protection tests
- **TestJsonExtractionRobustness**: JSON extraction edge cases
- **TestDisplayFormatting**: UI formatting with [RECOMMENDED] label
- **TestConflictPredictionExtendedFields**: New fields (installed_by, current_version)

## Known Conflict Patterns

### Built-in Patterns

```python
# Mutual exclusions
mutual_exclusions = {
    "mysql-server": ["mariadb-server", "percona-server"],
    "apache2": ["nginx"],  # When configured for same port
    "python2": ["python-is-python3"],
}

# Port conflicts
port_conflicts = {
    80: ["apache2", "nginx", "caddy", "lighttpd"],
    443: ["apache2", "nginx", "caddy"],
    3306: ["mysql-server", "mariadb-server"],
    5432: ["postgresql"],
}

# Version conflicts (pip packages)
version_conflicts = {
    "tensorflow": {
        "2.15": {"numpy": "< 2.0", "protobuf": ">= 3.20"},
        "2.16": {"numpy": ">= 1.23.5"},
    },
    "torch": {
        "*": {"numpy": ">= 1.17"},
    },
}
```

## Acceptance Criteria Status

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Dependency graph analysis before install | ✅ | `predict_conflicts()` method |
| Conflict prediction with confidence scores | ✅ | `ConflictPrediction.confidence` field |
| Resolution suggestions ranked by safety | ✅ | `generate_resolutions()` with sorting |
| Integration with apt/dpkg dependency data | ✅ | `get_apt_packages_summary()` (LLM-based analysis) |
| Works with pip packages too | ✅ | `get_pip_packages()` (LLM-based analysis) |
| CLI output shows prediction and suggestions | ✅ | `format_conflict_summary()` with [RECOMMENDED] |
| Learning from outcomes | ✅ | `record_resolution()` method |

## Future Enhancements

1. **Libraries.io API Integration** - Query ecosystem-wide dependency data
2. **PyPI API Integration** - Get package metadata directly from PyPI
3. **Parallel Conflict Detection** - Detect conflicts across multiple packages concurrently
4. **Conflict History Dashboard** - View past conflicts and resolution success rates
5. **Custom Conflict Rules** - Allow users to define custom conflict patterns

---

## AI/IDE Agents Used

Used Cursor Copilot with Claude Opus 4.5 model for generating test cases and documentation. Core implementation was done manually.

---

**Document Version**: 2.0
**Last Updated**: 2026-01-02
**Status**: Implemented
