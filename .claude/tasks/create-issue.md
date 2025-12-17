# create-issue.md

**allowed-tools:** Bash(gh issue create:*), Bash(gh issue list:*)
**description:** Create a bounty issue for Cortex Linux

## Context

* Feature or bug description: $ARGUMENTS
* Existing issues: `gh issue list --repo cortexlinux/cortex --limit 20`

## Your Task

Create a well-structured GitHub issue with bounty information.

## Issue Template

```markdown
## Problem
[What's broken or missing - 2-3 sentences]

## Solution
[How to fix it - include code examples if relevant]

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3

## Acceptance Criteria
- [ ] Feature works as described
- [ ] Unit tests included (>80% coverage)
- [ ] Documentation with examples
- [ ] Integrates with existing `cortex/` architecture

## Technical Notes
- Files to create/modify: `cortex/feature_name.py`, `test/test_feature_name.py`
- Integration points: [Which existing modules this connects to]
- Dependencies: [Any new packages needed]

## Example Usage
```python
# How the feature should be used
from cortex.feature_name import FeatureClass

feature = FeatureClass()
result = feature.do_something()
```

## Bounty: $XX (+ $XX bonus after funding)
Paid on merge to main via crypto (BTC/USDC) or PayPal.

## Labels
- `enhancement` or `bug`
- `good first issue` (if beginner-friendly)
- Priority: `critical`, `high`, `medium`, or `low`
```

## Bounty Guidelines

| Complexity | Amount | Examples |
|------------|--------|----------|
| Quick fix | $25-50 | Typo, small bug, docs update |
| Small feature | $50-75 | Single-file feature, test coverage |
| Medium feature | $75-100 | Multi-file feature, integration |
| Large feature | $150-200 | Core system component |

## Command Format

```bash
gh issue create \
  --repo cortexlinux/cortex \
  --title "feat: [Feature Name]" \
  --body "[Full issue body from template above]" \
  --label "enhancement" \
  --label "medium"
```

## Rules

1. Always include bounty amount with post-funding bonus
2. Always include acceptance criteria
3. Always specify which files to create/modify
4. Always include example usage
5. Check for duplicate issues before creating
6. Use conventional commit prefix in title: `feat:`, `fix:`, `docs:`

## Labels Reference

| Label | When to Use |
|-------|-------------|
| `enhancement` | New features |
| `bug` | Something broken |
| `documentation` | Docs only |
| `good first issue` | Simple, beginner-friendly |
| `critical` | Blocks MVP |
| `high` | Important for MVP |
| `medium` | Nice to have |
| `low` | Future consideration |

## After Creating

1. Note the issue number
2. Add to project board if applicable
3. Post in Discord #bounties channel
4. Track in bounty CSV if claimed
