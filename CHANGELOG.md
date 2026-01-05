# Changelog

All notable changes to Cortex Linux will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive code assessment (ASSESSMENT.md)
- Detailed improvement roadmap (ROADMAP.md)
- Enhanced contribution guidelines (CONTRIBUTING.md)
- Professional README with full documentation
- This CHANGELOG file
- Daemon LLM health status documentation (docs/DAEMON_LLM_HEALTH_STATUS.md)

### Changed
- Updated README with proper installation instructions
- Standardized Python version requirement to 3.10+
- Improved documentation structure

### Removed
- **BREAKING**: Removed `--offline` flag (redundant with semantic cache and `CORTEX_PROVIDER=ollama`)
  - The semantic cache automatically provides offline capability for cached requests
  - For true offline operation, use `export CORTEX_PROVIDER=ollama` instead

### Fixed
- **Daemon**: LLM loaded status now correctly reports "Yes" in `cortex daemon health` when model loads successfully
  - Added `set_llm_loaded()` method to SystemMonitor interface
  - Main daemon calls this method after successful model load
  - Implementation is generic and works with any GGUF model
- (Pending) Shell injection vulnerability in coordinator.py
- (Pending) CI/CD pipeline test directory path

### Security
- (Pending) Added additional dangerous command patterns to sandbox

---

## [0.1.0] - 2025-11-01

### Added
- **Core CLI Interface** (`cortex/cli.py`)
  - Natural language command parsing
  - Install, rollback, and history commands
  - Dry-run mode for previewing changes
  - Support for `--execute` flag for actual installation

- **LLM Integration** (`LLM/interpreter.py`)
  - OpenAI GPT-4 support
  - Anthropic Claude support
  - Natural language to command translation
  - Context-aware command generation

- **Multi-Provider LLM Router** (`llm_router.py`)
  - Intelligent routing between Claude and Kimi K2
  - Task-type based provider selection
  - Fallback logic for provider failures
  - Cost tracking and statistics

- **Package Manager Wrapper** (`cortex/packages.py`)
  - Support for apt, yum, and dnf
  - 32+ software category mappings
  - Intelligent package name resolution
  - Natural language to package translation

- **Installation Coordinator** (`cortex/coordinator.py`)
  - Multi-step installation orchestration
  - Step-by-step progress tracking
  - Error handling and reporting
  - Timeout management

- **Sandbox Executor** (`src/sandbox_executor.py`)
  - Firejail-based command isolation
  - AppArmor security profiles
  - Dangerous command pattern detection
  - Path traversal prevention

- **Installation History** (`installation_history.py`)
  - SQLite-based installation tracking
  - Full audit trail of installations
  - Rollback capability
  - Installation step recording

- **Hardware Profiler** (`src/hwprofiler.py`)
  - GPU detection (NVIDIA, AMD, Intel)
  - CPU information extraction
  - Memory and storage analysis
  - Hardware-aware installation recommendations

- **Error Parser** (`error_parser.py`)
  - Pattern-based error categorization
  - Automatic fix suggestions
  - Confidence scoring for matches
  - JSON export for analysis

- **Dependency Resolver** (`dependency_resolver.py`)
  - Package dependency analysis
  - Conflict detection
  - Installation order calculation
  - Transitive dependency resolution

- **Progress Tracker** (`src/progress_tracker.py`)
  - Real-time progress visualization
  - Terminal UI for installation status
  - Step completion tracking

- **Context Memory** (`context_memory.py`)
  - Installation pattern learning
  - User preference tracking
  - Command history analysis

- **Logging System** (`logging_system.py`)
  - Structured logging
  - Multiple output destinations
  - Log rotation support

### Infrastructure
- GitHub Actions CI/CD pipeline
- Unit test suite with pytest
- Apache 2.0 License
- Discord community integration
- Bounty program for contributions

### Documentation
- README with project overview
- Developer Guide
- FAQ document
- Bounties documentation
- Contributing guidelines (basic)

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 0.1.0 | Nov 2025 | Initial alpha release |
| Unreleased | - | Security fixes, documentation improvements |

---

## Upgrade Guide

### From 0.1.0 to 0.2.0 (Upcoming)

No breaking changes expected. Update with:

```bash
pip install --upgrade cortex-linux
```

---

## Deprecation Notices

None at this time.

---

## Security Advisories

### CVE-XXXX-XXXX (Pending)

**Severity:** Critical
**Component:** `cortex/coordinator.py`
**Description:** Shell injection vulnerability through unsanitized LLM output
**Status:** Fix pending in next release
**Mitigation:** Use `--dry-run` mode until patched

---

## Contributors

Thanks to all contributors who have helped build Cortex Linux!

- Michael J. Morgan ([@cortexlinux](https://github.com/cortexlinux)) - Creator & Lead

---

[Unreleased]: https://github.com/cortexlinux/cortex/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cortexlinux/cortex/releases/tag/v0.1.0
