# create-pr.md

**allowed-tools:** Bash(git status:*), Bash(git log:*), Bash(git branch:*), Bash(gh pr create:*)
**description:** Create a GitHub pull request for Cortex Linux

## Context

* Current git status: `git status`
* Current branch: `git branch --show-current`
* Commits on this branch: `git log --oneline main..HEAD`
* Recent commits for context: `git log --oneline -5`

## Additional Context

$ARGUMENTS

## Your Task

Create a GitHub pull request using `gh pr create` with the following requirements:

## PR Requirements

1. **Title Format:**
   - Keep short and concise
   - Use conventional commit style: `feat:`, `fix:`, `docs:`, etc.
   - If closing an issue, reference it: `feat: add offline mode (Issue #XX)`

2. **Body Format:**
   ```markdown
   ## Summary
   Brief description of what this PR does.

   ## Changes
   - Bullet point of change 1
   - Bullet point of change 2
   - Bullet point of change 3

   ## Testing
   - How to test these changes
   - Expected results

   ## Checklist
   - [ ] Tests pass (`pytest tests/`)
   - [ ] Code follows project style
   - [ ] Documentation updated if needed

   Closes #XX
   ```

3. **Command Structure:**
   ```bash
   gh pr create --title "Title here" --body "Body here" --base main
   ```

## Rules

1. Pass all options to avoid interactive mode
2. Always use `--title` and `--body` flags
3. Always target `main` as base branch
4. Include `Closes #XX` if this addresses an issue
5. Add labels if relevant: `--label "enhancement"` or `--label "bug"`

## Example

```bash
gh pr create \
  --title "feat: add semantic caching for offline mode" \
  --body "## Summary
Implements GPTCache integration for offline package queries.

## Changes
- Add GPTCache wrapper in cortex/cache/
- Implement semantic similarity matching
- Add fallback to local SQLite when offline

## Testing
\`\`\`bash
pytest tests/test_cache.py -v
\`\`\`

## Checklist
- [x] Tests pass
- [x] Documentation updated

Closes #42" \
  --base main \
  --label "enhancement"
```
