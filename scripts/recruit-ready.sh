#!/bin/bash
#
# recruit-ready.sh - Repository status and Discord recruitment message generator
# For Cortex Linux repository management
#

set -e

REPO="cortexlinux/cortex"
DISCORD_BLUE="\033[34m"
DISCORD_GREEN="\033[32m"
DISCORD_YELLOW="\033[33m"
DISCORD_RED="\033[31m"
DISCORD_CYAN="\033[36m"
BOLD="\033[1m"
RESET="\033[0m"

echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${DISCORD_CYAN}       CORTEX LINUX - REPOSITORY STATUS REPORT${RESET}"
echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
echo ""

# 1. CI Status
echo -e "${BOLD}${DISCORD_BLUE}📊 CI STATUS${RESET}"
echo "─────────────────────────────────────────"
CI_STATUS=$(gh run list --repo $REPO --workflow=ci.yml --limit 1 --json status,conclusion,displayTitle --jq '.[0]')
CI_CONCLUSION=$(echo $CI_STATUS | jq -r '.conclusion')
CI_TITLE=$(echo $CI_STATUS | jq -r '.displayTitle')

if [ "$CI_CONCLUSION" = "success" ]; then
    echo -e "${DISCORD_GREEN}✅ CI PASSING${RESET} - $CI_TITLE"
elif [ "$CI_CONCLUSION" = "failure" ]; then
    echo -e "${DISCORD_RED}❌ CI FAILING${RESET} - $CI_TITLE"
else
    echo -e "${DISCORD_YELLOW}⏳ CI IN PROGRESS${RESET} - $CI_TITLE"
fi
echo ""

# 2. Repository Stats
echo -e "${BOLD}${DISCORD_BLUE}📈 REPOSITORY STATS${RESET}"
echo "─────────────────────────────────────────"
REPO_STATS=$(gh api repos/$REPO --jq '{stars: .stargazers_count, forks: .forks_count, issues: .open_issues_count, watchers: .subscribers_count}')
STARS=$(echo $REPO_STATS | jq -r '.stars')
FORKS=$(echo $REPO_STATS | jq -r '.forks')
ISSUES=$(echo $REPO_STATS | jq -r '.issues')
WATCHERS=$(echo $REPO_STATS | jq -r '.watchers')

echo "⭐ Stars: $STARS | 🍴 Forks: $FORKS | 📋 Open Issues: $ISSUES | 👀 Watchers: $WATCHERS"
echo ""

# 3. Mergeable PRs
echo -e "${BOLD}${DISCORD_BLUE}✅ MERGEABLE PRs (Ready to Merge)${RESET}"
echo "─────────────────────────────────────────"
MERGEABLE_PRS=$(gh pr list --repo $REPO --state open --json number,title,author,mergeable,reviewDecision --jq '.[] | select(.mergeable == "MERGEABLE") | "PR #\(.number): \(.title) by @\(.author.login)"')

if [ -z "$MERGEABLE_PRS" ]; then
    echo "No PRs currently ready to merge"
else
    echo "$MERGEABLE_PRS"
fi
echo ""

# 4. PRs Needing Review
echo -e "${BOLD}${DISCORD_BLUE}👀 PRs NEEDING REVIEW${RESET}"
echo "─────────────────────────────────────────"
REVIEW_PRS=$(gh pr list --repo $REPO --state open --json number,title,author,reviewDecision --jq '.[] | select(.reviewDecision == "REVIEW_REQUIRED" or .reviewDecision == "") | "PR #\(.number): \(.title) by @\(.author.login)"' | head -10)

if [ -z "$REVIEW_PRS" ]; then
    echo "No PRs awaiting review"
else
    echo "$REVIEW_PRS"
fi
echo ""

# 5. Recently Merged PRs (potential bounty payments)
echo -e "${BOLD}${DISCORD_YELLOW}💰 RECENTLY MERGED (Check Bounty Payments)${RESET}"
echo "─────────────────────────────────────────"
MERGED_PRS=$(gh pr list --repo $REPO --state merged --limit 10 --json number,title,author,mergedAt,labels --jq '.[] | "PR #\(.number): \(.title) by @\(.author.login) - Merged: \(.mergedAt[:10])"')

if [ -z "$MERGED_PRS" ]; then
    echo "No recently merged PRs"
else
    echo "$MERGED_PRS"
fi
echo ""

# 6. Open Issues with Bounties
echo -e "${BOLD}${DISCORD_BLUE}🎯 OPEN ISSUES WITH BOUNTIES${RESET}"
echo "─────────────────────────────────────────"
BOUNTY_ISSUES=$(gh issue list --repo $REPO --state open --label "bounty" --json number,title,labels --jq '.[] | "#\(.number): \(.title)"' 2>/dev/null || echo "")

if [ -z "$BOUNTY_ISSUES" ]; then
    # Try to find issues that might have bounty in title or other bounty-related labels
    BOUNTY_ISSUES=$(gh issue list --repo $REPO --state open --json number,title,labels --jq '.[] | select(.title | test("bounty|\\$"; "i")) | "#\(.number): \(.title)"' 2>/dev/null || echo "No bounty issues found")
fi

if [ -z "$BOUNTY_ISSUES" ] || [ "$BOUNTY_ISSUES" = "No bounty issues found" ]; then
    echo "No issues with bounty labels found"
    echo "Tip: Add 'bounty' label to issues to track them here"
else
    echo "$BOUNTY_ISSUES"
fi
echo ""

# 7. Top Contributors (from recent PRs)
echo -e "${BOLD}${DISCORD_BLUE}👥 ACTIVE CONTRIBUTORS (Recent PRs)${RESET}"
echo "─────────────────────────────────────────"
CONTRIBUTORS=$(gh pr list --repo $REPO --state all --limit 50 --json author --jq '.[].author.login' | sort | uniq -c | sort -rn | head -5)
echo "$CONTRIBUTORS"
echo ""

# 8. Discord Recruitment Message
echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${DISCORD_CYAN}       DISCORD RECRUITMENT MESSAGE (Copy Below)${RESET}"
echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
echo ""

# Count open PRs and issues for the message
OPEN_PRS=$(gh pr list --repo $REPO --state open --json number --jq 'length')
OPEN_ISSUES_COUNT=$(gh issue list --repo $REPO --state open --json number --jq 'length')

cat << 'DISCORD_MSG'
```
🚀 CORTEX LINUX - OPEN SOURCE CONTRIBUTORS WANTED! 🚀
```

**What is Cortex Linux?**
An AI-powered package manager for Debian/Ubuntu that understands natural language. Instead of memorizing apt commands, just tell Cortex what you want:

```bash
cortex install "set up a Python ML environment with TensorFlow"
```

**Why Contribute?**
DISCORD_MSG

echo "- 💰 **Bounty Program** - Get paid for merged PRs"
echo "- 🌟 **$STARS stars** and growing"
echo "- 🔥 **$OPEN_PRS open PRs** to review/merge"
echo "- 📋 **$OPEN_ISSUES_COUNT open issues** to work on"
echo "- 🤝 Friendly community, fast PR reviews"

cat << 'DISCORD_MSG'

**Good First Issues:**
- Documentation improvements
- Test coverage
- Bug fixes with clear reproduction steps

**Tech Stack:**
- Python 3.10+
- OpenAI/Anthropic APIs
- Rich TUI library

**Links:**
DISCORD_MSG

echo "- GitHub: https://github.com/$REPO"
echo "- Discussions: https://github.com/$REPO/discussions"

cat << 'DISCORD_MSG'

**How to Start:**
1. Fork the repo
2. Pick an issue labeled `good-first-issue` or `help-wanted`
3. Submit a PR
4. Get reviewed & merged!

Drop a 👋 if you're interested or have questions!
DISCORD_MSG

echo ""
echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}Generated: $(date)${RESET}"
echo -e "${BOLD}${DISCORD_CYAN}════════════════════════════════════════════════════════════${RESET}"
