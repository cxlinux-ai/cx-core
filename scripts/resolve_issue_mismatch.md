# GitHub Issues Resolution Plan

## Issues Analysis

After analyzing the open issues in cxlinux-ai/cx, there's a clear mismatch between the current CX Terminal codebase (Rust-based terminal emulator) and the issues which reference a "Cortex" CLI system administration tool (Python-based).

## Issues to Close with Explanation

### Security Issues (Not Applicable)
- **#671**: References `cx/do_runner/diagnosis.py` - file doesn't exist in terminal emulator
- **#674**: References `cli.py` and `docker_sandbox.py` - files don't exist in terminal emulator

### CLI/System Admin Issues (Not Applicable)
- **#547**: API key reconfiguration wizard for "cx wizard" - not part of terminal emulator
- **#371**: Offline mode export for "CX_PROVIDER" - not part of terminal emulator
- **#267**: Tiered approval modes for "cx config" - not part of terminal emulator
- **#51**: Real-time system health monitor for "cx monitor" - not part of terminal emulator
- **#445**: Network config validator for "cx" tool - not part of terminal emulator

### Documentation Issue (Needs Adaptation)
- **#619**: BSL license documentation - relevant but needs adaptation for CX Terminal context

## Recommended Actions

1. **Close irrelevant issues** with explanation and link to PROJECT_SCOPE.md
2. **Update #619** to focus on CX Terminal BSL documentation rather than "Cortex"
3. **Create new issues** for actual terminal emulator features needed
4. **Update README** to clarify project scope

## Terminal-Relevant Features to Consider

If system administration features are desired in the terminal:
- Health monitoring could be integrated into terminal status bar
- Network configuration could be terminal commands with validation
- API key management could be terminal configuration
- These would need to be implemented in Rust as terminal emulator features

## Resolution Messages Template

```
This issue references the "Cortex" CLI system administration tool, but this repository contains CX Terminal - a Rust-based terminal emulator built on WezTerm.

The files/commands referenced in this issue (cx wizard, cli.py, etc.) do not exist in the current codebase.

See docs/PROJECT_SCOPE.md for clarification of what CX Terminal includes.

If this feature should be implemented in the terminal emulator, please create a new issue with terminal-specific requirements.

Closing as not applicable to current codebase.
```