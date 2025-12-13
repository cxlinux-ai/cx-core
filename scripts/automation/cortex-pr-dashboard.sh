#!/bin/bash
# CORTEX - MASTER PR DASHBOARD & MANAGEMENT
# Complete PR overview, batch operations, and bounty tracking

set -e

echo "🎛️  CORTEX - MASTER PR DASHBOARD"
echo "================================"
echo ""

REPO="cortexlinux/cortex"
GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.zshrc | cut -d'=' -f2 | tr -d '"' | tr -d "'")
export GH_TOKEN="$GITHUB_TOKEN"

# Colors for terminal output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 PR STATUS OVERVIEW"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get all open PRs
prs=$(gh pr list --repo $REPO --state open --json number,title,author,createdAt,isDraft,reviewDecision --limit 50 2>/dev/null)

total_prs=$(echo "$prs" | jq 'length')
contributor_prs=$(echo "$prs" | jq '[.[] | select(.author.login != "mikejmorgan-ai")] | length')
mike_prs=$(echo "$prs" | jq '[.[] | select(.author.login == "mikejmorgan-ai")] | length')

echo "Total Open PRs: $total_prs"
echo "  ├─ From Contributors: $contributor_prs (🔥 Need review)"
echo "  └─ From Mike: $mike_prs (Can merge anytime)"
echo ""

# Calculate bounties at stake
echo "💰 ESTIMATED BOUNTIES AT STAKE"
echo "────────────────────────────────"
echo ""

declare -A BOUNTY_MAP
BOUNTY_MAP[17]=100  # Package Manager
BOUNTY_MAP[37]=125  # Progress Notifications
BOUNTY_MAP[38]=100  # Requirements Check
BOUNTY_MAP[21]=150  # Config Templates
BOUNTY_MAP[18]=100  # CLI Interface

total_contributor_bounties=0

for pr in 17 37 38 21 18; do
    bounty=${BOUNTY_MAP[$pr]}
    total_contributor_bounties=$((total_contributor_bounties + bounty))
done

echo "Contributor PRs: \$$total_contributor_bounties"
echo "At 2x bonus (funding): \$$((total_contributor_bounties * 2))"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔴 CRITICAL PRIORITY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pr17_info=$(gh pr view 17 --repo $REPO --json number,title,author,createdAt,state 2>/dev/null)
pr17_title=$(echo "$pr17_info" | jq -r '.title')
pr17_author=$(echo "$pr17_info" | jq -r '.author.login')
pr17_created=$(echo "$pr17_info" | jq -r '.createdAt' | cut -d'T' -f1)
pr17_days_old=$(( ( $(date +%s) - $(date -j -f "%Y-%m-%d" "$pr17_created" +%s 2>/dev/null || date +%s) ) / 86400 ))

echo "PR #17: $pr17_title"
echo "Author: @$pr17_author"
echo "Age: $pr17_days_old days old"
echo "Bounty: \$100"
echo "Impact: ⚠️  MVP BLOCKER - Everything waits on this"
echo ""
echo -e "${RED}▶ ACTION REQUIRED: Review this PR FIRST${NC}"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🟡 HIGH PRIORITY (Contributors Waiting)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

for pr in 37 38 21; do
    pr_info=$(gh pr view $pr --repo $REPO --json number,title,author,createdAt 2>/dev/null)
    pr_title=$(echo "$pr_info" | jq -r '.title')
    pr_author=$(echo "$pr_info" | jq -r '.author.login')
    pr_bounty=${BOUNTY_MAP[$pr]}
    
    echo "PR #$pr: $pr_title"
    echo "  Author: @$pr_author | Bounty: \$$pr_bounty"
done

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🟢 MIKE'S PRs (Ready to Merge)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

mike_pr_list=$(echo "$prs" | jq -r '.[] | select(.author.login == "mikejmorgan-ai") | .number')

for pr in $mike_pr_list; do
    pr_info=$(gh pr view $pr --repo $REPO --json number,title 2>/dev/null)
    pr_title=$(echo "$pr_info" | jq -r '.title')
    echo "PR #$pr: $pr_title"
done

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 QUICK ACTIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "What would you like to do?"
echo ""
echo "  [1] Review PR #17 (THE CRITICAL BLOCKER) 🔴"
echo "  [2] Review ALL contributor PRs (guided workflow) 🟡"
echo "  [3] Merge ALL of Mike's PRs (batch operation) 🟢"
echo "  [4] View detailed PR list in browser"
echo "  [5] Generate bounty payment report"
echo "  [6] Post Discord update"
echo "  [q] Quit"
echo ""
echo -n "Choose action: "
read -n 1 choice
echo ""
echo ""

case $choice in
    1)
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🔴 REVIEWING PR #17 - PACKAGE MANAGER WRAPPER"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "This is THE MVP blocker. Everything depends on this."
        echo ""
        echo "Opening in browser for review..."
        echo ""
        
        gh pr view 17 --repo $REPO --web
        
        echo ""
        echo "After reviewing the code, what's your decision?"
        echo ""
        echo "  [a] Approve & Merge (\$100 bounty to @chandrapratamar)"
        echo "  [c] Request Changes (specify what needs fixing)"
        echo "  [s] Skip for now (review later)"
        echo ""
        echo -n "Decision: "
        read -n 1 decision
        echo ""
        echo ""
        
        case $decision in
            a|A)
                echo "✅ Approving PR #17..."
                
                approval="✅ **APPROVED - OUTSTANDING WORK!**

@chandrapratamar - You just unblocked the entire MVP! 🎉🎉🎉

**This is THE critical feature** that everything else depends on. Your implementation:
- ✅ Translates natural language to apt commands perfectly
- ✅ Integrates seamlessly with our LLM layer
- ✅ Includes comprehensive tests
- ✅ Documentation is clear and complete

**Payment Details:**
- **Bounty: \$100 USD**
- **Processing: Within 48 hours**
- **Method: Crypto (Bitcoin/USDC) or PayPal**
- **Bonus: 2x at funding (Feb 2025) = \$200 total**

**You're now a core Cortex contributor!** 🧠⚡

We'll coordinate payment via your preferred method in the next comment.

**Thank you for making history with us!**

---
*Automated approval from Cortex PR Management System*"
                
                echo "$approval" | gh pr review 17 --repo $REPO --approve --body-file -
                
                echo ""
                echo "Merging PR #17..."
                
                gh pr merge 17 --repo $REPO --squash --delete-branch && {
                    echo ""
                    echo "🎉🎉🎉 PR #17 MERGED! 🎉🎉🎉"
                    echo ""
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo "🚀 MVP BLOCKER CLEARED!"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    echo ""
                    echo "This unblocks:"
                    echo "  ✅ Issue #12 (Dependency Resolution)"
                    echo "  ✅ Issue #10 (Installation Verification)"
                    echo "  ✅ Issue #14 (Rollback System)"
                    echo "  ✅ MVP demonstration"
                    echo "  ✅ February funding timeline"
                    echo ""
                    echo "💰 Bounty owed: \$100 to @chandrapratamar"
                    echo ""
                    echo "IMMEDIATELY post to Discord #announcements!"
                    echo ""
                } || {
                    echo "❌ Merge failed - needs manual intervention"
                }
                ;;
            c|C)
                echo "Requesting changes on PR #17..."
                echo ""
                echo "Enter what needs to change:"
                echo "(Press Ctrl+D when done)"
                echo "---"
                feedback=$(cat)
                
                change_request="🔄 **Changes Requested**

Thank you @chandrapratamar for tackling this critical feature!

Before we can merge, please address:

$feedback

**This is THE MVP blocker**, so I'll prioritize re-review once you update.

Questions? Ping me here or in Discord (#dev-questions).

We're close! 💪"
                
                echo "$change_request" | gh pr review 17 --repo $REPO --request-changes --body-file -
                echo ""
                echo "✅ Change request posted"
                ;;
            *)
                echo "⏭️  Skipped PR #17"
                ;;
        esac
        ;;
        
    2)
        echo "🟡 LAUNCHING CONTRIBUTOR PR REVIEW WORKFLOW..."
        echo ""
        
        # Check if review script exists
        if [ -f "$HOME/cortex/review-contributor-prs.sh" ]; then
            bash "$HOME/cortex/review-contributor-prs.sh"
        else
            echo "Review script not found. Download it first:"
            echo "  review-contributor-prs.sh"
        fi
        ;;
        
    3)
        echo "🟢 BATCH MERGING MIKE'S PRs..."
        echo ""
        
        # Check if merge script exists
        if [ -f "$HOME/cortex/merge-mike-prs.sh" ]; then
            bash "$HOME/cortex/merge-mike-prs.sh"
        else
            echo "Merge script not found. Download it first:"
            echo "  merge-mike-prs.sh"
        fi
        ;;
        
    4)
        echo "🌐 Opening PR list in browser..."
        gh pr list --repo $REPO --web
        ;;
        
    5)
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "💰 BOUNTY PAYMENT REPORT"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        
        echo "PENDING BOUNTIES (if merged):"
        echo "──────────────────────────────"
        echo ""
        echo "PR #17 - @chandrapratamar: \$100 (Package Manager)"
        echo "PR #37 - @AlexanderLuzDH: \$125 (Progress Notifications)"
        echo "PR #38 - @AlexanderLuzDH: \$100 (Requirements Check)"
        echo "PR #21 - @aliraza556: \$150 (Config Templates)"
        echo "PR #18 - @Sahilbhatane: \$100 (CLI Interface - DRAFT)"
        echo ""
        echo "──────────────────────────────"
        echo "TOTAL PENDING: \$575"
        echo "AT 2X BONUS (FUNDING): \$1,150"
        echo ""
        
        if [ -f "$HOME/cortex/bounties_owed.csv" ]; then
            echo "ALREADY MERGED (need payment):"
            echo "──────────────────────────────"
            tail -n +2 "$HOME/cortex/bounties_owed.csv" | while IFS=',' read -r pr dev feature amount date status; do
                if [ "$status" = "PENDING" ]; then
                    echo "$pr - @$dev: \$$amount"
                fi
            done
            echo ""
        fi
        ;;
        
    6)
        echo "📱 GENERATING DISCORD ANNOUNCEMENT..."
        echo ""
        
        announcement="🎉 **CORTEX PROJECT UPDATE - $(date +%B\ %d,\ %Y)**

**PR Review Session Complete!**

**Current Status:**
- 📊 **$total_prs PRs open** ($contributor_prs from contributors, $mike_prs from Mike)
- 💰 **\$$total_contributor_bounties in bounties** pending review
- 🔴 **PR #17 (Package Manager)** = THE MVP BLOCKER

**Action Items:**
- Contributor PRs being reviewed this week
- Bounties will be processed within 48 hours of merge
- 2x bonus reminder: All bounties double at funding (Feb 2025)

**For Contributors:**
- Check your PR status on GitHub
- Questions? #dev-questions channel
- New issues available for claiming

**The Momentum is Real:**
- Professional team execution
- MVP timeline on track (Feb 2025)
- Building the future of Linux! 🧠⚡

Browse open issues: https://github.com/$REPO/issues
Join discussion: https://discord.gg/uCqHvxjU83"
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "$announcement"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "Copy the above and post to Discord #announcements"
        ;;
        
    q|Q)
        echo "👋 Exiting dashboard..."
        exit 0
        ;;
        
    *)
        echo "Invalid choice"
        ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Dashboard session complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
