#!/bin/bash
# CX-Core Branch Cleanup Script
# Run this from a machine with push access to cxlinux-ai/cx-core
#
# Generated: 2026-02-06
# Total branches to delete: 26
# Kept: main, 8 open-PR branches, 3 active claude/* branches, 2 archive branches
#
# SAFE: Every branch below is either merged, closed, 81+ behind main,
# or has 0 commits ahead of main. Nothing with an open PR is touched.

set -e

REPO="cxlinux-ai/cx-core"

echo "=== CX-Core Branch Cleanup ==="
echo "Deleting 26 stale branches from $REPO"
echo ""

# -------------------------------------------------------
# STAGE 1: Merged PR branches (PR was merged, branch left behind)
# -------------------------------------------------------
echo "--- Stage 1: Merged PR branches (2) ---"
MERGED_BRANCHES=(
  "issue-427-core-daemon"       # Merged PR #612
  "mikejmorgan-ai-patch-1"      # Merged PR #676
)

for branch in "${MERGED_BRANCHES[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

# -------------------------------------------------------
# STAGE 2: Closed (unmerged) PR branches
# -------------------------------------------------------
echo ""
echo "--- Stage 2: Closed PR branches (10) ---"
CLOSED_BRANCHES=(
  "alert-autofix-19"                    # Closed PR #647
  "copilot/sub-pr-688"                  # Closed PR #689
  "feat/debian-packaging"               # Closed PR #660
  "feature/issue-275-jit-benchmarking"  # Closed PR #605
  "feature/rich-ui-module"              # Closed PR #581
  "feature/smart-retry-logic"           # Related to merged PR #658
  "fix/codeql-url-sanitization"         # Closed PR #673
  "fix/sonarcloud-blockers"             # Closed PR #675
  "fix/sonarcloud-bugs"                 # Closed PR #672
  "security-422"                        # Closed PR #423
)

for branch in "${CLOSED_BRANCHES[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

# -------------------------------------------------------
# STAGE 3: Stale branches with no PR, 81+ behind main
# -------------------------------------------------------
echo ""
echo "--- Stage 3: Stale no-PR branches (12) ---"
STALE_BRANCHES=(
  "coderabbitai/docstrings/1a146dd"     # Auto-generated bot branch
  "coderabbitai/docstrings/f6bfa49"     # Auto-generated bot branch
  "docs/common-errors-guide"            # 81 behind, no PR
  "feat/deps"                           # 81 behind, no PR
  "feature/auto-detect-api-keys"        # 81 behind, no PR
  "feature/issue-36"                    # 81 behind, no PR
  "feature/ollama-integration"          # 81 behind, no PR
  "feature/pr-checks-workflow"          # 81 behind, no PR
  "fix/shell-injection-vulnerabilities" # 81 behind, no PR
  "improve/onboarding-docs-branding-polish" # 81 behind, 3 ahead
  "setup-pr-automation"                 # 81 behind, no PR
  "test/cla-verification"               # 81 behind, no PR
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
  "feat/cx-terminal-ui"                 # 0 ahead, content in main
  "feat/enterprise-alert-manager-security" # 0 ahead, content in main
)

for branch in "${ZERO_AHEAD[@]}"; do
  echo "  Deleting: $branch"
  git push origin --delete "$branch" || echo "  SKIP: $branch (already deleted?)"
done

echo ""
echo "=== Cleanup complete ==="
echo ""
echo "KEPT (do not delete):"
echo "  main                              - default branch"
echo "  docs/spdx-license-identifier      - open PR #732"
echo "  feature/color-scheme-update       - open PR #700"
echo "  feature/hrm-ai-integration        - open PR #693"
echo "  dependabot/.../upload-pages-artifact-4 - open PR #692"
echo "  copilot/improve-copilot-functionality  - open PR #690"
echo "  feature/security-vulnerability-management - open PR #688"
echo "  copilot/add-system-monitoring-alert-management - open PR #685"
echo "  rebrand/phase-2-user-facing       - open PR #683"
echo "  claude/agent-swarm-setup-ca3Fy    - active (today)"
echo "  claude/cx-identity-reset-atfkY    - active (yesterday)"
echo "  claude/review-pr-691-atfkY        - recent review"
echo "  claude/polymarket-clob-bot-EDifI  - active (today)"
echo "  backup/pre-rewrite                - ARCHIVE: pre-rewrite snapshot"
echo "  cx-terminal-cleanup               - ARCHIVE: cleanup work"
