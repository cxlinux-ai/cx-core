# merge-pr.md

**allowed-tools:** Bash(gh pr view:*), Bash(gh pr checks:*), Bash(gh pr merge:*), Bash(gh pr comment:*)
**description:** Merge an approved pull request for Cortex Linux

## Context

* PR number to merge: $ARGUMENTS

## Your Task

Verify the PR is ready and merge it safely.

## Pre-Merge Checklist

### Step 1: Verify PR Status
```bash
gh pr view $PR_NUMBER --repo cortexlinux/cortex --json title,author,mergeable,mergeStateStatus,reviews
```

### Step 2: Verify CI Passes
```bash
gh pr checks $PR_NUMBER --repo cortexlinux/cortex
```

### Step 3: Check for Conflicts
- `mergeable: true` required
- `mergeStateStatus: clean` or `unstable` (if only optional checks fail)

## Merge Criteria

| Check | Required |
|-------|----------|
| CI tests pass | ✅ Yes |
| No merge conflicts | ✅ Yes |
| At least 1 approval | ✅ Yes (Mike or designated reviewer) |
| CodeQL pass | ⚠️ No (non-blocking) |
| SonarQube pass | ⚠️ No (non-blocking) |

## Merge Command

```bash
gh pr merge $PR_NUMBER --repo cortexlinux/cortex --squash --delete-branch
```

Options:
- `--squash` - Combine all commits into one (preferred)
- `--merge` - Keep all commits (for large features)
- `--rebase` - Rebase onto main
- `--delete-branch` - Clean up feature branch after merge

## Post-Merge Actions

### Step 1: Add Bounty Comment
```bash
gh pr comment $PR_NUMBER --repo cortexlinux/cortex --body "🎉 Merged! Thanks @$AUTHOR for this contribution.

**Bounty:** $XX ready for payment
**Payment method:** DM me on Discord with your preferred method (crypto/PayPal)

Tracking in bounty ledger."
```

### Step 2: Update Bounty Tracker
Add to `bounty-payments.csv`:
```
$DATE,$PR_NUMBER,$AUTHOR,$AMOUNT,pending,$ISSUE_NUMBER
```

### Step 3: Discord Notification
```
✅ **PR #$PR_NUMBER Merged**
Feature: [Title]
Contributor: @$AUTHOR
Bounty: $XX - DM for payment
```

## Error Handling

### If Merge Fails: Conflicts
```
❌ Cannot merge - conflicts exist

Tell contributor:
"@$AUTHOR This PR has merge conflicts. Please rebase on latest main:
\`\`\`
git fetch origin
git rebase origin/main
git push --force-with-lease
\`\`\`"
```

### If Merge Fails: CI Red
```
❌ Cannot merge - CI failing

Check which tests fail:
\`gh pr checks $PR_NUMBER --repo cortexlinux/cortex\`

Tell contributor which specific tests need fixing.
```

### If Merge Fails: No Approval
```
❌ Cannot merge - needs approval

Either:
1. Review and approve: \`gh pr review $PR_NUMBER --approve\`
2. Or bypass (owner only): \`gh pr merge $PR_NUMBER --admin\`
```

## Output Format

```
## Merge Report: PR #$PR_NUMBER

**Title:** [PR Title]
**Author:** @[username]
**Status:** ✅ Merged / ❌ Blocked

**CI Checks:**
- Tests: ✅ Pass
- Lint: ✅ Pass
- CodeQL: ⚠️ Skipped (non-blocking)

**Merge Commit:** [commit hash]

**Post-Merge:**
- [ ] Bounty comment posted
- [ ] Bounty tracker updated
- [ ] Discord notified

**Bounty:** $XX owed to @[username]
```
