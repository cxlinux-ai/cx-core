# review-pr.md

**allowed-tools:** Bash(gh pr view:*), Bash(gh pr diff:*), Bash(curl:*), Bash(gh api:*)
**description:** Review a contributor pull request for Cortex Linux

## Context

* PR number to review: $ARGUMENTS

## Your Task

Perform a thorough code review of the specified PR and provide a verdict.

## Review Process

### Step 1: Fetch PR Information
```bash
gh pr view $PR_NUMBER --repo cortexlinux/cortex --json title,author,body,files,additions,deletions,mergeable,mergeStateStatus
```

### Step 2: Fetch Full Diff
```bash
gh pr diff $PR_NUMBER --repo cortexlinux/cortex
```

### Step 3: Check CI Status
```bash
gh pr checks $PR_NUMBER --repo cortexlinux/cortex
```

## Review Checklist

### Code Quality
- [ ] Code is in correct directory (`cortex/` not `src/`)
- [ ] No TODO or placeholder comments
- [ ] Error handling is present
- [ ] No hardcoded secrets or API keys
- [ ] Follows Python style (snake_case, type hints)

### Testing
- [ ] Tests are included (`test/test_*.py`)
- [ ] Tests cover main functionality
- [ ] Tests use mocking for external services
- [ ] All CI checks pass

### Integration
- [ ] Imports use `cortex.` prefix correctly
- [ ] Integrates with existing architecture
- [ ] No breaking changes to existing APIs
- [ ] Documentation updated if needed

### Security
- [ ] No command injection vulnerabilities
- [ ] Subprocess calls are sandboxed
- [ ] Sensitive data is not logged

## Verdict Format

Provide one of:

### ✅ APPROVE
```
**Verdict: APPROVE**

Code quality is good. All checks pass. Ready to merge.

Strengths:
- [What's good about this PR]

Merge command:
\`gh pr merge $PR_NUMBER --repo cortexlinux/cortex --squash\`
```

### 🔄 REQUEST CHANGES
```
**Verdict: REQUEST CHANGES**

Issues found that must be fixed before merge:

1. **[Issue Category]** - [Description]
2. **[Issue Category]** - [Description]

Comment to post:
\`\`\`
@contributor Thanks for this work! [Specific issues to fix]
\`\`\`
```

### 💬 NEEDS DISCUSSION
```
**Verdict: NEEDS DISCUSSION**

Questions or architectural concerns that need input:

1. [Question or concern]
2. [Question or concern]

Suggested action: [What to do next]
```

## Common Issues to Watch For

| Issue | How to Detect |
|-------|---------------|
| Wrong directory | Files in `src/` instead of `cortex/` |
| Broken imports | `from X import` without `cortex.` prefix |
| Missing tests | No `test_*.py` files in diff |
| Merge conflicts | `mergeable: false` in PR data |
| CI failures | Red X in checks output |
| Sensitive data | API keys, passwords in code |

## Output Format

1. **PR Summary** - Title, author, what it does
2. **Files Changed** - List with line counts
3. **CI Status** - Pass/fail for each check
4. **Code Review** - Issues found (if any)
5. **Verdict** - APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
6. **Next Action** - Exact command or comment to post
