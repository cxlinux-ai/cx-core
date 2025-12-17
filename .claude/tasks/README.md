# Cortex Linux - Claude Code Task Files

Task files for Claude Code to automate common workflows.

## Installation

Copy these files to your Cortex repo:

```bash
mkdir -p ~/cortex/.claude/tasks
cp *.md ~/cortex/.claude/tasks/
```

Or keep them in a central location and reference with full path.

## Available Tasks

| Task | File | Description |
|------|------|-------------|
| **Commit** | `commit.md` | Create properly formatted git commits |
| **Create PR** | `create-pr.md` | Create pull requests with proper format |
| **Review PR** | `review-pr.md` | Review contributor PRs with checklist |
| **Merge PR** | `merge-pr.md` | Safely merge PRs and track bounties |
| **Create Issue** | `create-issue.md` | Create bounty issues with proper template |
| **Pay Bounty** | `pay-bounty.md` | Record and track bounty payments |
| **Repo Status** | `check-repo-status.md` | Get overview of PRs, issues, CI |

## Usage in Claude Code

### Method 1: Direct Task Reference
```bash
claude --task commit.md
claude --task review-pr.md 213
claude --task check-repo-status.md
```

### Method 2: In Conversation
```
/task review-pr.md 299
```

### Method 3: Describe the Task
```
Review PR #213 using the review checklist
```

## Task Arguments

Some tasks accept arguments via `$ARGUMENTS`:

| Task | Arguments | Example |
|------|-----------|---------|
| `review-pr.md` | PR number | `213` |
| `merge-pr.md` | PR number | `299` |
| `create-issue.md` | Feature description | `"add fuzzy search to CLI"` |
| `pay-bounty.md` | Payment details | `"PR 213 @user $100 btc tx123"` |

## Workflow Examples

### Daily Standup
```bash
claude --task check-repo-status.md
```

### Review and Merge a PR
```bash
claude --task review-pr.md 299
# If approved:
claude --task merge-pr.md 299
claude --task pay-bounty.md "PR 299 @Sahilbhatane $75 paypal PP-123"
```

### Create New Feature Issue
```bash
claude --task create-issue.md "Add semantic caching with GPTCache for offline mode"
```

### Commit and Push Changes
```bash
claude --task commit.md
claude --task create-pr.md
```

## File Locations

Default paths used by these tasks:

| File | Path |
|------|------|
| Bounty tracker | `~/cortex/data/bounty-payments.csv` |
| Task files | `~/cortex/.claude/tasks/` |
| Repo root | `~/cortex/` |

## Requirements

- GitHub CLI (`gh`) installed and authenticated
- Git configured with push access
- Repo cloned to `~/cortex/`

## Customization

Edit any `.md` file to adjust:
- Bounty amounts
- Review criteria
- PR/Issue templates
- Payment methods

## Contributing

These task files are part of the Cortex Linux project.
Improvements welcome via PR.
