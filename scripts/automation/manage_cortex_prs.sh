#!/bin/bash
# Cortex Linux - Master PR Control & Team Coordination
# Complete automation: reviews, assignments, Discord, payments, everything

set -e

echo "🧠 CORTEX LINUX - MASTER PR CONTROL SYSTEM"
echo "=========================================="
echo ""

# Configuration
REPO="cortexlinux/cortex"
REPO_DIR="$HOME/cortex"
DISCORD_INVITE="https://discord.gg/uCqHvxjU83"
GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.zshrc | cut -d'=' -f2 | tr -d '"' | tr -d "'")
BOUNTY_CSV="$REPO_DIR/bounties_paid.csv"

# Ensure we're in the repo
cd "$REPO_DIR" || { echo "❌ Repo not found at $REPO_DIR"; exit 1; }

# Create bounty tracking CSV if it doesn't exist
if [ ! -f "$BOUNTY_CSV" ]; then
    echo "PR_Number,Author,Amount,Status,Payment_Status,Date" > "$BOUNTY_CSV"
fi

echo "📊 STEP 1: FETCHING ALL OPEN PRS"
echo "================================="
echo ""

# Get all open PRs
prs=$(gh pr list --repo "$REPO" --state open --json number,title,author,createdAt,reviews,isDraft,mergeable --limit 50)
total_prs=$(echo "$prs" | jq length)

echo "Found $total_prs open PR(s)"
echo ""

if [ "$total_prs" -eq 0 ]; then
    echo "✅ No PRs to process!"
    exit 0
fi

# Display all PRs
echo "$prs" | jq -r '.[] | "PR #\(.number): \(.title) by @\(.author.login) - Draft: \(.isDraft)"'
echo ""

echo "🎯 STEP 2: CATEGORIZING PRS"
echo "==========================="
echo ""

# Arrays for different PR categories
critical_prs=()
ready_to_merge=()
needs_review=()
draft_prs=()
stale_prs=()

# Categorize each PR
while IFS= read -r pr_num; do
    pr_data=$(echo "$prs" | jq -r ".[] | select(.number == $pr_num)")
    author=$(echo "$pr_data" | jq -r '.author.login')
    title=$(echo "$pr_data" | jq -r '.title')
    is_draft=$(echo "$pr_data" | jq -r '.isDraft')
    created=$(echo "$pr_data" | jq -r '.createdAt')
    mergeable=$(echo "$pr_data" | jq -r '.mergeable')
    review_count=$(echo "$pr_data" | jq -r '.reviews | length')
    
    # Calculate age
    created_ts=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$created" +%s 2>/dev/null || echo 0)
    now_ts=$(date +%s)
    age_days=$(( (now_ts - created_ts) / 86400 ))
    
    # Skip drafts
    if [ "$is_draft" = "true" ]; then
        draft_prs+=($pr_num)
        continue
    fi
    
    # Check if it's the critical package manager PR
    if [[ "$title" == *"package"* ]] || [[ "$title" == *"Package"* ]] || [ "$pr_num" -eq 195 ]; then
        critical_prs+=($pr_num)
        echo "🔥 CRITICAL: PR #$pr_num - $title (Age: $age_days days)"
    elif [ "$mergeable" = "MERGEABLE" ] && [ "$review_count" -gt 0 ]; then
        ready_to_merge+=($pr_num)
        echo "✅ READY TO MERGE: PR #$pr_num - $title"
    elif [ "$review_count" -eq 0 ]; then
        needs_review+=($pr_num)
        echo "📋 NEEDS REVIEW: PR #$pr_num - $title (Age: $age_days days)"
    fi
    
    # Check if stale (>5 days)
    if [ "$age_days" -gt 5 ]; then
        stale_prs+=($pr_num)
    fi
done < <(echo "$prs" | jq -r '.[].number')

echo ""
echo "Summary:"
echo "  🔥 Critical PRs: ${#critical_prs[@]}"
echo "  ✅ Ready to merge: ${#ready_to_merge[@]}"
echo "  📋 Need review: ${#needs_review[@]}"
echo "  📝 Drafts: ${#draft_prs[@]}"
echo "  ⏰ Stale (>5 days): ${#stale_prs[@]}"
echo ""

read -p "Continue with automated processing? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "🎯 STEP 3: PROCESSING CRITICAL PRS"
echo "=================================="
echo ""

for pr_num in "${critical_prs[@]}"; do
    pr_data=$(echo "$prs" | jq -r ".[] | select(.number == $pr_num)")
    author=$(echo "$pr_data" | jq -r '.author.login')
    title=$(echo "$pr_data" | jq -r '.title')
    
    echo "Processing CRITICAL PR #$pr_num: $title"
    echo "Author: @$author"
    echo ""
    
    # Assign reviewers if not already assigned
    echo "  Assigning reviewers: dhvil, mikejmorgan-ai"
    gh pr edit $pr_num --add-reviewer dhvil,mikejmorgan-ai 2>/dev/null || echo "  (Reviewers already assigned)"
    
    # Post urgent review comment
    comment="🔥 **CRITICAL PATH REVIEW**

Hi @$author! This PR is blocking our MVP completion.

**Urgent Review In Progress:**
- ✅ Technical review by @dhvil
- ✅ Final approval by @mikejmorgan-ai
- ⏱️ Target decision: Within 24 hours

**Payment Ready:**
💰 Bounty will be paid via Discord crypto (BTC/USDC) within 24 hours of merge

**Join Discord for payment coordination:**
👉 $DISCORD_INVITE

We're prioritizing this merge! Thanks for the critical work. 🚀"

    gh pr comment $pr_num --body "$comment" 2>/dev/null || echo "  (Comment already exists)"
    
    echo "  ✅ Critical PR tagged and reviewers notified"
    echo ""
    sleep 1
done

echo ""
echo "✅ STEP 4: AUTO-MERGING READY PRS"
echo "================================="
echo ""

merged_count=0
for pr_num in "${ready_to_merge[@]}"; do
    pr_data=$(echo "$prs" | jq -r ".[] | select(.number == $pr_num)")
    author=$(echo "$pr_data" | jq -r '.author.login')
    title=$(echo "$pr_data" | jq -r '.title')
    
    echo "PR #$pr_num: $title by @$author"
    echo "  Status: Mergeable with approvals"
    
    # Determine bounty amount based on issue
    bounty_amount="TBD"
    if [[ "$title" == *"context"* ]] || [[ "$title" == *"Context"* ]]; then
        bounty_amount="150"
    elif [[ "$title" == *"logging"* ]] || [[ "$title" == *"Logging"* ]]; then
        bounty_amount="100"
    fi
    
    read -p "  Merge PR #$pr_num? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Merge the PR
        gh pr merge $pr_num --squash --delete-branch
        echo "  ✅ Merged!"
        
        # Post payment comment
        payment_comment="🎉 **PR MERGED!**

Thanks @$author! Your contribution has been merged into main.

**💰 Payment Details:**
- Bounty: \$$bounty_amount (as specified in issue)
- Method: Crypto (Bitcoin or USDC)
- Timeline: Within 24 hours

**Next Steps:**
1. Join Discord: $DISCORD_INVITE
2. DM @mikejmorgan with your wallet address
3. Receive payment confirmation

Great work! Looking forward to your next contribution. 🚀"

        gh pr comment $pr_num --body "$payment_comment"
        
        # Track in CSV
        echo "$pr_num,$author,$bounty_amount,Merged,Pending Payment,$(date +%Y-%m-%d)" >> "$BOUNTY_CSV"
        
        ((merged_count++))
        echo ""
    else
        echo "  ⏭️  Skipped"
        echo ""
    fi
    sleep 1
done

echo "Merged $merged_count PR(s)"
echo ""

echo "📋 STEP 5: ASSIGNING REVIEWERS TO PENDING PRS"
echo "=============================================="
echo ""

for pr_num in "${needs_review[@]}"; do
    pr_data=$(echo "$prs" | jq -r ".[] | select(.number == $pr_num)")
    author=$(echo "$pr_data" | jq -r '.author.login')
    title=$(echo "$pr_data" | jq -r '.title')
    
    echo "PR #$pr_num: $title by @$author"
    
    # Assign reviewers
    if [ "$author" != "dhvil" ] && [ "$author" != "mikejmorgan-ai" ]; then
        gh pr edit $pr_num --add-reviewer dhvil,mikejmorgan-ai 2>/dev/null || true
        echo "  ✅ Assigned reviewers: dhvil, mikejmorgan-ai"
    else
        gh pr edit $pr_num --add-reviewer mikejmorgan-ai 2>/dev/null || true
        echo "  ✅ Assigned reviewer: mikejmorgan-ai"
    fi
    
    # Post welcome comment
    welcome_comment="Thanks @$author for this contribution! 🎉

**Review Process:**
1. ✅ Reviewers assigned - expect feedback within 24-48 hours
2. 💬 **Join Discord**: $DISCORD_INVITE
3. 💰 **Bounty Payment**: Crypto (BTC/USDC) via Discord after merge

**Important:**
- All bounties tracked and paid through Discord
- Please join to coordinate payment details
- Typical merge → payment time: 24-48 hours

Looking forward to reviewing this! 🚀"

    # Check if we already commented
    existing=$(gh pr view $pr_num --json comments --jq '[.comments[] | select(.author.login == "mikejmorgan-ai")] | length')
    if [ "$existing" -eq 0 ]; then
        gh pr comment $pr_num --body "$welcome_comment"
        echo "  ✅ Posted welcome comment"
    else
        echo "  (Welcome comment already exists)"
    fi
    
    echo ""
    sleep 1
done

echo ""
echo "⏰ STEP 6: SENDING STALE PR REMINDERS"
echo "====================================="
echo ""

for pr_num in "${stale_prs[@]}"; do
    # Skip if it's in draft or critical (already handled)
    if [[ " ${draft_prs[@]} " =~ " ${pr_num} " ]] || [[ " ${critical_prs[@]} " =~ " ${pr_num} " ]]; then
        continue
    fi
    
    pr_data=$(echo "$prs" | jq -r ".[] | select(.number == $pr_num)")
    author=$(echo "$pr_data" | jq -r '.author.login')
    title=$(echo "$pr_data" | jq -r '.title')
    created=$(echo "$pr_data" | jq -r '.createdAt')
    
    created_ts=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$created" +%s 2>/dev/null || echo 0)
    now_ts=$(date +%s)
    age_days=$(( (now_ts - created_ts) / 86400 ))
    
    echo "PR #$pr_num: $title by @$author ($age_days days old)"
    
    stale_comment="Hi @$author! 👋

This PR has been open for $age_days days. Quick status check:

📋 **Checklist:**
- [ ] Joined Discord? ($DISCORD_INVITE)
- [ ] All tests passing?
- [ ] Addressed review feedback?

💰 **Payment Reminder:**
- Bounties paid via crypto (Bitcoin/USDC)
- Processed through Discord DMs
- Sent within 24 hours of merge

Need help? Let us know in Discord! We want to get this merged and pay you ASAP. 🚀"

    gh pr comment $pr_num --body "$stale_comment"
    echo "  ✅ Sent reminder"
    echo ""
    sleep 1
done

echo ""
echo "💬 STEP 7: GENERATING DISCORD ANNOUNCEMENT"
echo "=========================================="
echo ""

cat << DISCORD_EOF > /tmp/discord_announcement.txt
🚀 **PR STATUS UPDATE - $(date +"%B %d, %Y")**

Just completed automated PR processing! Here's where we stand:

**📊 Statistics:**
- Total Open PRs: $total_prs
- 🔥 Critical (Package Manager): ${#critical_prs[@]}
- ✅ Merged Today: $merged_count
- 📋 Under Review: ${#needs_review[@]}
- ⏰ Stale Reminders Sent: ${#stale_prs[@]}

**🎯 Focus Areas:**
DISCORD_EOF

if [ ${#critical_prs[@]} -gt 0 ]; then
    echo "• 🔥 PR #${critical_prs[0]} (Package Manager) - CRITICAL PATH - Under urgent review" >> /tmp/discord_announcement.txt
fi

cat << DISCORD_EOF2 >> /tmp/discord_announcement.txt

**💰 Payment Process:**
1. PR gets merged ✅
2. I DM you for wallet address 💬
3. Crypto sent within 24 hours 💸
4. You confirm receipt ✅

**All contributors:** Join Discord for bounty coordination!
👉 $DISCORD_INVITE

Let's keep the momentum going! 🔥

- Mike
DISCORD_EOF2

echo "Discord announcement generated:"
echo "==============================="
cat /tmp/discord_announcement.txt
echo "==============================="
echo ""
echo "📋 Copy the above to Discord #announcements"
echo ""

echo ""
echo "📊 STEP 8: PAYMENT TRACKING SUMMARY"
echo "==================================="
echo ""

if [ -f "$BOUNTY_CSV" ]; then
    echo "Payments Pending:"
    tail -n +2 "$BOUNTY_CSV" | grep "Pending" 2>/dev/null | while IFS=, read -r pr author amount status payment date; do
        echo "  PR #$pr - @$author - \$$amount - $date"
    done || echo "  No pending payments"
    echo ""
    echo "Full tracking: $BOUNTY_CSV"
fi

echo ""
echo "📧 STEP 9: CONTRIBUTOR DM TEMPLATES"
echo "==================================="
echo ""

# Generate DM templates for unique contributors
contributors=$(echo "$prs" | jq -r '.[].author.login' | sort -u)

echo "Send these DMs on Discord:"
echo ""

for contributor in $contributors; do
    pr_count=$(echo "$prs" | jq -r --arg author "$contributor" '[.[] | select(.author.login == $author)] | length')
    
    if [ "$pr_count" -gt 0 ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "To: @$contributor ($pr_count open PR)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        cat << DM_EOF

Hey! Just processed your Cortex PR(s) - great work! 🎉

**Quick Check:**
1. Have you joined Discord? ($DISCORD_INVITE)
2. What's your crypto wallet address? (BTC or USDC)
3. Any blockers I can help with?

**Payment Timeline:**
- PR review: 24-48 hours
- Merge decision: Clear feedback either way
- Payment: Within 24 hours of merge

Looking forward to merging your work!

- Mike

DM_EOF
    fi
done

echo ""
echo "=============================================="
echo "✅ MASTER PR CONTROL COMPLETE"
echo "=============================================="
echo ""

echo "📊 Summary of Actions:"
echo "  • Reviewed $total_prs PRs"
echo "  • Assigned reviewers to ${#needs_review[@]} PRs"
echo "  • Merged $merged_count PRs"
echo "  • Flagged ${#critical_prs[@]} critical PR(s)"
echo "  • Sent ${#stale_prs[@]} stale reminders"
echo ""

echo "📋 Next Manual Steps:"
echo "  1. Copy Discord announcement to #announcements"
echo "  2. Send DMs to contributors (templates above)"
echo "  3. Review critical PR #${critical_prs[0]:-N/A} urgently"
echo "  4. Process $merged_count payment(s) via crypto"
echo ""

echo "🔄 Run this script daily to maintain PR velocity!"
echo ""
echo "✅ All done!"
