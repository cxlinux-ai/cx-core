# check-repo-status.md

**allowed-tools:** Bash(gh pr list:*), Bash(gh issue list:*), Bash(gh run list:*), Bash(gh api:*), Bash(curl:*)
**description:** Get a complete status overview of the Cortex Linux repository

## Your Task

Provide a comprehensive status report of the repository.

## Data to Gather

### 1. Open Pull Requests
```bash
gh pr list --repo cortexlinux/cortex --state open --json number,title,author,createdAt,mergeable,reviewDecision --limit 30
```

### 2. Recent CI Runs
```bash
gh run list --repo cortexlinux/cortex --limit 10
```

### 3. Open Issues by Priority
```bash
gh issue list --repo cortexlinux/cortex --state open --label "critical" --json number,title,assignees
gh issue list --repo cortexlinux/cortex --state open --label "high" --json number,title,assignees
```

### 4. Unassigned Issues with Bounties
```bash
gh issue list --repo cortexlinux/cortex --state open --assignee "" --json number,title,labels
```

### 5. Recently Merged PRs (for bounty tracking)
```bash
gh pr list --repo cortexlinux/cortex --state merged --limit 10 --json number,title,author,mergedAt
```

### 6. Repository Stats
```bash
gh api repos/cortexlinux/cortex --jq '{stars: .stargazers_count, forks: .forks_count, issues: .open_issues_count}'
```

## Output Format

```markdown
# Cortex Linux - Repository Status
*Generated: [timestamp]*

## 📊 Quick Stats
| Metric | Count |
|--------|-------|
| Open PRs | XX |
| Open Issues | XX |
| Stars | XX |
| Forks | XX |

## 🔴 Critical/Blocking
[List any PRs or issues blocking MVP]

## ✅ Ready to Merge
| PR | Title | Author | CI Status |
|----|-------|--------|-----------|
| #XX | Title | @user | ✅ Pass |

## 🔄 Needs Review
| PR | Title | Author | Waiting Since |
|----|-------|--------|---------------|
| #XX | Title | @user | X days |

## ⚠️ Has Conflicts
| PR | Title | Author | Issue |
|----|-------|--------|-------|
| #XX | Title | @user | Merge conflict |

## 💰 Bounties Available
| Issue | Title | Bounty | Priority |
|-------|-------|--------|----------|
| #XX | Title | $XX | high |

## 👥 Top Contributors (Open PRs)
| Contributor | Open PRs |
|-------------|----------|
| @user | X |

## 🏃 Recent CI Runs
| Workflow | Status | Branch | Time |
|----------|--------|--------|------|
| CI | ✅/❌ | main | Xm ago |

## 📋 Recommended Actions
1. [Most important action]
2. [Second priority]
3. [Third priority]
```

## Categories

### Ready to Merge
PRs where:
- `mergeable: true`
- `reviewDecision: APPROVED` or no review required
- CI passing

### Needs Review
PRs where:
- `mergeable: true`
- `reviewDecision: REVIEW_REQUIRED` or empty
- Waiting > 24 hours

### Has Conflicts
PRs where:
- `mergeable: false`
- Need contributor to rebase

### Stale PRs
PRs where:
- No activity > 7 days
- May need follow-up or closing

## Priority Actions

Recommend actions based on:
1. **Blockers first** - Anything blocking other work
2. **Quick wins** - PRs that can merge immediately
3. **Bounty payments** - Recently merged PRs needing payment
4. **Contributor follow-up** - PRs needing nudges
5. **Issue triage** - New issues needing labels/bounties

## End with

```
## Next Steps
1. [Specific action with command]
2. [Specific action with command]
3. [Specific action with command]

Ready to proceed with any of these?
```
