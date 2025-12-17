#!/bin/bash
# CORTEX - Quick Merge Mike's PRs
# Merges all PRs authored by @mikejmorgan-ai to clear backlog

set -e

echo "🚀 CORTEX - MERGE MIKE'S IMPLEMENTATION PRs"
echo "==========================================="
echo ""

REPO="cortexlinux/cortex"
GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.zshrc | cut -d'=' -f2 | tr -d '"' | tr -d "'")

export GH_TOKEN="$GITHUB_TOKEN"

echo "Merging PRs authored by @mikejmorgan-ai..."
echo ""

# PRs to merge (excluding #17, #18, #21, #37, #38 which are from contributors)
MIKE_PRS=(41 36 34 23 22 20)

for pr in "${MIKE_PRS[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "PR #$pr"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Get PR info
    pr_info=$(gh pr view $pr --repo $REPO --json title,state,mergeable 2>/dev/null || echo "")
    
    if [ -z "$pr_info" ]; then
        echo "❌ PR #$pr not found or not accessible"
        echo ""
        continue
    fi
    
    pr_title=$(echo "$pr_info" | jq -r '.title')
    pr_state=$(echo "$pr_info" | jq -r '.state')
    pr_mergeable=$(echo "$pr_info" | jq -r '.mergeable')
    
    echo "Title: $pr_title"
    echo "State: $pr_state"
    echo "Mergeable: $pr_mergeable"
    echo ""
    
    if [ "$pr_state" != "OPEN" ]; then
        echo "⏭️  PR already merged or closed"
        echo ""
        continue
    fi
    
    if [ "$pr_mergeable" = "CONFLICTING" ]; then
        echo "⚠️  PR has merge conflicts - needs manual resolution"
        echo ""
        continue
    fi
    
    echo "Merge this PR? (y/n)"
    read -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔄 Merging PR #$pr..."
        
        gh pr merge $pr --repo $REPO --squash --delete-branch 2>/dev/null && \
            echo "✅ PR #$pr merged successfully!" || \
            echo "❌ Failed to merge PR #$pr (may need manual merge)"
    else
        echo "⏭️  Skipped PR #$pr"
    fi
    
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ MERGE PROCESS COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "1. Review contributor PRs: #17, #21, #37, #38"
echo "2. Process bounty payments"
echo "3. Post update to Discord"
