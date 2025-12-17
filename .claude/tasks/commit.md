# commit.md

**allowed-tools:** Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git diff:*)
**description:** Create a git commit for Cortex Linux

## Context

* Current git status: `git status`
* Current git diff (staged and unstaged): `git diff HEAD`
* Current branch: `git branch --show-current`
* Recent commits: `git log --oneline -10`

## Your Task

Based on the above changes, create a single git commit.

## Commit Message Guidelines

* First line: Short, concise summary (50 chars or less)
* Use conventional commit prefixes: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
* Leave a blank line after the first line
* Add detailed bullet points explaining the work (8-10 lines max)
* Keep bullets focused on technical changes
* Do NOT include attribution, co-authorship, or mentions of Claude/AI

## Format

```
<type>: <short description>

- Bullet point explaining change 1
- Bullet point explaining change 2
- Bullet point explaining change 3
```

## Example

```
feat: add offline mode for package queries

- Implement local cache fallback when network unavailable
- Add SQLite storage for previously fetched package metadata
- Create timeout detection with 3-second threshold
- Add --offline flag to force local-only operation
- Update CLI help text with offline usage examples
```

## Rules

1. Stage all relevant files before committing
2. Do not commit unrelated changes
3. Never amend commits without explicit permission
4. Verify staged changes match intended scope before committing
5. If changes span multiple features, suggest splitting into separate commits
