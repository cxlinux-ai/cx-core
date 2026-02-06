#!/bin/bash
# CX-Core Branch Cleanup Script
# Run this from a machine with push access to cxlinux-ai/cx-core
#
# Generated: 2026-02-06 (revised after code audit)
# Total branches to delete: 24 (down from 26 after audit)
# Kept: main, 8 open-PR branches, 4 active claude/* branches,
#       2 archive branches, 2 branches with salvageable code
#
# AUDITED: Every branch was checked for unique commits not in main.
# Two branches were removed from the delete list after finding useful code.

set -e

REPO="cxlinux-ai/cx-core"

echo "=== CX-Core Branch Cleanup ==="
echo ""

# -------------------------------------------------------
# STAGE 0: Archive valuable code BEFORE deleting anything
# -------------------------------------------------------
echo "--- Stage 0: Tagging branches with code worth preserving ---"
echo ""

# copilot/sub-pr-688 has 3,614 lines of Rust security module code
# (scanner, patcher, scheduler, database) not in main
echo "  Tagging copilot/sub-pr-688 -> archive/security-vuln-module"
git tag archive/security-vuln-module origin/copilot/sub-pr-688 2>/dev/null \
  || echo "  Tag already exists"
git push origin archive/security-vuln-module 2>/dev/null \
  || echo "  Tag already pushed"

# feat/debian-packaging is the most complete snapshot of the old Python CLI
echo "  Tagging feat/debian-packaging -> archive/old-python-cortex-cli"
git tag archive/old-python-cortex-cli origin/feat/debian-packaging 2>/dev/null \
  || echo "  Tag already exists"
git push origin archive/old-python-cortex-cli 2>/dev/null \
  || echo "  Tag already pushed"

echo ""
echo "  Tags created. Code is preserved permanently even after branch deletion."
echo ""

# -------------------------------------------------------
# STAGE 1: Merged PR branches (PR was merged, branch left behind)
# -------------------------------------------------------
echo "--- Stage 1: Merged PR branches (2) ---"
MERGED_BRANCHES=(
  "issue-427-core-daemon"       # Merged PR #612, old Python codebase
  "mikejmorgan-ai-patch-1"      # Merged PR #676, only 1 unique commit (SECURITY.md)
)

for branch in "${MERGED_BRANCHES[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

# -------------------------------------------------------
# STAGE 2: Closed (unmerged) PR branches
# Now safe to delete copilot/sub-pr-688 and feat/debian-packaging
# because we tagged them in Stage 0
# -------------------------------------------------------
echo ""
echo "--- Stage 2: Closed PR branches (10) ---"
CLOSED_BRANCHES=(
  "alert-autofix-19"                    # Closed PR #647, 1 trivial bot commit
  "copilot/sub-pr-688"                  # Closed PR #689, TAGGED as archive/security-vuln-module
  "feat/debian-packaging"               # Closed PR #660, TAGGED as archive/old-python-cortex-cli
  "feature/issue-275-jit-benchmarking"  # Closed PR #605, old Python JIT benchmarks
  "feature/rich-ui-module"              # Closed PR #581, old Python Rich UI
  "feature/smart-retry-logic"           # Related to merged PR #658, trivial pattern
  "fix/codeql-url-sanitization"         # Closed PR #673, scanner fix on dead code
  "fix/sonarcloud-blockers"             # Closed PR #675, scanner fix on dead code
  "fix/sonarcloud-bugs"                 # Closed PR #672, scanner fix on dead code
  "security-422"                        # Closed PR #423, contained in feat/debian-packaging
)

for branch in "${CLOSED_BRANCHES[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

# -------------------------------------------------------
# STAGE 3: Stale branches with no PR, 81+ behind main
# -------------------------------------------------------
echo ""
echo "--- Stage 3: Stale no-PR branches (10) ---"
STALE_BRANCHES=(
  "coderabbitai/docstrings/1a146dd"     # Bot-generated docstrings on old Python code
  "coderabbitai/docstrings/f6bfa49"     # Bot-generated docstrings on old Python code
  "docs/common-errors-guide"            # Old Python-era troubleshooting doc
  "feat/deps"                           # Old Python pyproject.toml cleanup
  "feature/auto-detect-api-keys"        # Single commit, trivial, old Python
  "feature/issue-36"                    # Early prototype, 15 files, old Python
  "feature/ollama-integration"          # Will be re-implemented in Rust per CLAUDE.md
  "feature/pr-checks-workflow"          # Old CI workflow on dead codebase
  "fix/shell-injection-vulnerabilities" # Scanner fixes on old Python code
  "setup-pr-automation"                 # Old CI automation, superseded
)

for branch in "${STALE_BRANCHES[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

# -------------------------------------------------------
# STAGE 4: Branches with 0 commits ahead (already in main)
# -------------------------------------------------------
echo ""
echo "--- Stage 4: 0-ahead branches (2) ---"
ZERO_AHEAD=(
  "feat/cx-terminal-ui"                     # 0 ahead, identical to main
  "feat/enterprise-alert-manager-security"  # 0 ahead, identical to main
)

for branch in "${ZERO_AHEAD[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

echo ""
echo "=== Cleanup complete: 24 branches deleted ==="
echo ""
echo "ARCHIVE TAGS CREATED (permanent, survives branch deletion):"
echo "  archive/security-vuln-module     - 3,614 LOC Rust security scanner/patcher"
echo "  archive/old-python-cortex-cli    - Full old Python Cortex CLI history"
echo ""
echo "KEPT (18 branches remaining):"
echo "  main                                          - default, protected"
echo "  docs/spdx-license-identifier                  - open PR #732"
echo "  feature/color-scheme-update                   - open PR #700"
echo "  feature/hrm-ai-integration                    - open PR #693"
echo "  dependabot/.../upload-pages-artifact-4        - open PR #692"
echo "  copilot/improve-copilot-functionality         - open PR #690"
echo "  feature/security-vulnerability-management     - open PR #688"
echo "  copilot/add-system-monitoring-alert-management - open PR #685"
echo "  rebrand/phase-2-user-facing                   - open PR #683"
echo "  claude/agent-swarm-setup-ca3Fy                - active (today)"
echo "  claude/cx-identity-reset-atfkY                - active (yesterday)"
echo "  claude/review-pr-691-atfkY                    - recent review"
echo "  claude/polymarket-clob-bot-EDifI              - active (today)"
echo "  backup/pre-rewrite                            - ARCHIVE: pre-rewrite snapshot"
echo "  cx-terminal-cleanup                           - ARCHIVE: cleanup work"
echo "  improve/onboarding-docs-branding-polish       - 3 commits, docs only"
echo "  test/cla-verification                         - CLA test infrastructure"
echo ""
echo "To recover archived code later:"
echo "  git checkout -b recover-security-module archive/security-vuln-module"
echo "  git checkout -b recover-old-python archive/old-python-cortex-cli"
