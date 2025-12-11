#!/bin/bash
# CORTEX - CONTRIBUTOR PR REVIEW & MERGE SYSTEM
# Reviews PRs from contributors, tracks bounties, posts thank-yous

set -e

echo "🔍 CORTEX - CONTRIBUTOR PR REVIEW SYSTEM"
echo "========================================"
echo ""

REPO="cortexlinux/cortex"
GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.zshrc | cut -d'=' -f2 | tr -d '"' | tr -d "'")

export GH_TOKEN="$GITHUB_TOKEN"

# Track bounties owed
BOUNTIES_FILE="$HOME/cortex/bounties_owed.csv"

# Create bounties file if doesn't exist
if [ ! -f "$BOUNTIES_FILE" ]; then
    echo "PR,Developer,Feature,Bounty_Amount,Date_Merged,Status" > "$BOUNTIES_FILE"
fi

echo "📊 CONTRIBUTOR PR REVIEW QUEUE"
echo "────────────────────────────────"
echo ""

# Contributor PRs to review (in priority order)
declare -A PR_DETAILS
PR_DETAILS[17]="chandrapratamar|Package Manager Wrapper (Issue #7)|100|CRITICAL_MVP_BLOCKER"
PR_DETAILS[37]="AlexanderLuzDH|Progress Notifications (Issue #27)|125|HIGH_PRIORITY"
PR_DETAILS[38]="AlexanderLuzDH|Requirements Pre-flight Check (Issue #28)|100|HIGH_PRIORITY"
PR_DETAILS[21]="aliraza556|Config File Templates (Issue #16)|150|HIGH_PRIORITY"
PR_DETAILS[18]="Sahilbhatane|CLI Interface (Issue #11)|100|DRAFT_WAIT"

# Function to review a PR
review_pr() {
    local pr_num=$1
    local pr_data="${PR_DETAILS[$pr_num]}"
    
    IFS='|' read -r developer feature bounty priority <<< "$pr_data"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 PR #$pr_num - $feature"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "👤 Developer: @$developer"
    echo "🎯 Feature: $feature"
    echo "💰 Bounty: \$$bounty"
    echo "🔥 Priority: $priority"
    echo ""
    
    # Check if draft
    pr_state=$(gh pr view $pr_num --repo $REPO --json isDraft 2>/dev/null | jq -r '.isDraft')
    
    if [ "$pr_state" = "true" ]; then
        echo "📝 Status: DRAFT - Not ready for review yet"
        echo "   Action: Skip for now, will review when marked ready"
        echo ""
        return
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "REVIEW CHECKLIST"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Before approving, verify:"
    echo "  [ ] Code implements the feature described in the issue"
    echo "  [ ] Unit tests included with >80% coverage"
    echo "  [ ] Documentation/README included"
    echo "  [ ] Integrates with existing Cortex architecture"
    echo "  [ ] No obvious bugs or security issues"
    echo "  [ ] Follows Python best practices"
    echo ""
    
    echo "Actions:"
    echo "  [v] View PR in browser (to review code)"
    echo "  [a] Approve & Merge (if review passed)"
    echo "  [c] Request Changes (if issues found)"
    echo "  [m] Add Comment (questions/feedback)"
    echo "  [s] Skip to next PR"
    echo "  [q] Quit review mode"
    echo ""
    echo -n "Choose action: "
    read -n 1 action
    echo ""
    echo ""
    
    case $action in
        v|V)
            echo "🌐 Opening PR #$pr_num in browser..."
            gh pr view $pr_num --repo $REPO --web
            echo ""
            echo "After reviewing, come back to approve/change/comment."
            echo ""
            echo "Take action now? (y/n)"
            read -n 1 take_action
            echo ""
            
            if [[ ! $take_action =~ ^[Yy]$ ]]; then
                echo "⏭️  Skipping for now..."
                return
            fi
            
            # Ask again which action
            echo ""
            echo "What action? [a]pprove [c]hange [m]comment [s]kip"
            read -n 1 action
            echo ""
            ;;&  # Continue to next pattern
            
        a|A)
            echo "✅ APPROVING & MERGING PR #$pr_num"
            echo ""
            
            # Post approval review
            approval_msg="✅ **APPROVED - Excellent Work!**

Thank you @$developer for this outstanding contribution! 🎉

**Review Summary:**
- ✅ Code quality: Professional implementation
- ✅ Testing: Comprehensive unit tests included
- ✅ Documentation: Clear and complete
- ✅ Integration: Works seamlessly with Cortex architecture

**What's Next:**
1. Merging this PR immediately
2. Your bounty of **\$$bounty USD** will be processed within 48 hours
3. Payment via crypto (Bitcoin/USDC) or PayPal - we'll coordinate via issue comment

**You're making history** - this is a foundational piece of the AI-native operating system! 🧠⚡

**Bonus Reminder:** At funding (Feb 2025), you'll receive **2x this bounty** as a thank-you bonus.

Welcome to the Cortex Linux core contributor team! 🚀

---
*Automated review from Cortex PR Management System*"
            
            echo "$approval_msg" | gh pr review $pr_num --repo $REPO --approve --body-file - 2>/dev/null || \
                echo "⚠️  Could not post review (may need manual approval)"
            
            echo ""
            echo "Merging PR #$pr_num now..."
            
            gh pr merge $pr_num --repo $REPO --squash --delete-branch 2>/dev/null && {
                echo "✅ PR #$pr_num merged successfully!"
                
                # Record bounty owed
                merge_date=$(date +%Y-%m-%d)
                echo "$pr_num,$developer,$feature,$bounty,$merge_date,PENDING" >> "$BOUNTIES_FILE"
                
                echo ""
                echo "💰 Bounty recorded: \$$bounty owed to @$developer"
                echo "    Recorded in: $BOUNTIES_FILE"
            } || {
                echo "❌ Merge failed - may need manual intervention"
            }
            
            echo ""
            ;;
            
        c|C)
            echo "🔄 REQUESTING CHANGES on PR #$pr_num"
            echo ""
            echo "Enter your feedback (what needs to change):"
            echo "Press Ctrl+D when done"
            echo "---"
            feedback=$(cat)
            
            change_msg="🔄 **Changes Requested**

Thank you for your contribution @$developer! The code is solid, but a few items need attention before merge:

$feedback

**Please update and let me know when ready** for re-review. I'll prioritize getting this merged quickly once addressed.

**Questions?** Comment here or ping me in Discord (#dev-questions).

We appreciate your patience! 🙏

---
*Automated review from Cortex PR Management System*"
            
            echo "$change_msg" | gh pr review $pr_num --repo $REPO --request-changes --body-file - 2>/dev/null || \
                echo "⚠️  Could not post review"
            
            echo ""
            echo "✅ Change request posted"
            echo ""
            ;;
            
        m|M)
            echo "💬 ADDING COMMENT to PR #$pr_num"
            echo ""
            echo "Enter your comment:"
            echo "Press Ctrl+D when done"
            echo "---"
            comment=$(cat)
            
            gh pr comment $pr_num --repo $REPO --body "$comment" 2>/dev/null && \
                echo "✅ Comment posted" || \
                echo "⚠️  Could not post comment"
            
            echo ""
            ;;
            
        s|S)
            echo "⏭️  Skipping PR #$pr_num"
            echo ""
            ;;
            
        q|Q)
            echo "👋 Exiting review mode..."
            echo ""
            return 1
            ;;
            
        *)
            echo "⏭️  Invalid action, skipping..."
            echo ""
            ;;
    esac
}

# Main review loop
echo "Starting PR review process..."
echo ""

PR_ORDER=(17 37 38 21 18)  # Priority order

for pr in "${PR_ORDER[@]}"; do
    review_pr $pr || break
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 REVIEW SESSION COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show bounties owed
if [ -f "$BOUNTIES_FILE" ]; then
    echo "💰 BOUNTIES OWED (from this session and previous)"
    echo "──────────────────────────────────────────────────"
    echo ""
    
    total_owed=0
    
    tail -n +2 "$BOUNTIES_FILE" | while IFS=',' read -r pr dev feature amount date status; do
        if [ "$status" = "PENDING" ]; then
            echo "  PR #$pr - @$dev: \$$amount ($feature)"
            total_owed=$((total_owed + amount))
        fi
    done
    
    echo ""
    echo "  Total pending: \$$total_owed USD"
    echo ""
    echo "  Payment file: $BOUNTIES_FILE"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 NEXT STEPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Process bounty payments (see $BOUNTIES_FILE)"
echo "2. Post Discord announcement about merged PRs"
echo "3. Check if Issue #7 unblocked (if PR #17 merged)"
echo "4. Welcome new developers to comment on issues"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Generate Discord announcement
discord_msg="🎉 **PR MERGE UPDATE - $(date +%Y-%m-%d)**

**PRs Merged Today:**
(Check the bounties file for details)

**Critical Path Progress:**
- Issue #7 (Package Manager): $([ -f "$BOUNTIES_FILE" ] && grep -q "^17," "$BOUNTIES_FILE" && echo "✅ MERGED - MVP BLOCKER CLEARED!" || echo "⏳ In review")

**Bounties Being Processed:**
- See individual PR comments for payment coordination
- 2x bonus reminder: When we close funding (Feb 2025), all bounties paid so far get 2x bonus

**What This Means:**
- MVP velocity accelerating
- February funding timeline on track
- Professional team execution demonstrated

**For Contributors:**
- Check your merged PRs for bounty coordination comments
- Payment within 48 hours of merge
- Crypto (Bitcoin/USDC) or PayPal options

**Open Issues Still Available:**
Browse: https://github.com/cortexlinux/cortex/issues
Join: Discord #dev-questions

Let's keep the momentum! 🧠⚡"

echo "📱 DISCORD ANNOUNCEMENT (copy and post to #announcements)"
echo "────────────────────────────────────────────────────────"
echo ""
echo "$discord_msg"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ PR Review System Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
