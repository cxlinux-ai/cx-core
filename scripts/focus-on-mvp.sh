#!/bin/bash
# Close non-MVP issues to focus contributors on critical work

set -e

echo "🎯 FOCUSING REPOSITORY ON MVP ISSUES"
echo "======================================"
echo ""

cd ~/cortex || { echo "❌ cortex repo not found"; exit 1; }

# Strategy: Close issues 46-200+ with explanation comment
# Keep issues 1-45 open (MVP critical work)

echo "Strategy:"
echo "  Keep open: Issues #1-45 (MVP critical)"
echo "  Close: Issues #46+ (post-MVP features)"
echo ""

read -p "Close issues #46-200 as 'post-MVP'? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Comment to add when closing
CLOSE_MESSAGE="🎯 **Closing for MVP Focus**

This issue is being closed to help the team focus on MVP-critical features (#1-45).

**This is NOT abandoned** - it's an important feature we'll revisit after MVP completion.

**Timeline:**
- **Now (Nov-Dec 2024):** Focus on MVP (Issues #1-45)
- **January 2025:** Reopen post-MVP features
- **February 2025:** Seed funding round

**Want to work on this anyway?**
Comment below and we can discuss! We're always open to great contributions.

**Tracking:** Labeled as \`post-mvp\` for easy filtering when we reopen.

Thanks for understanding! 🚀

— Mike (@mikejmorgan-ai)"

echo "📝 Closing issues #46-200..."
echo ""

# Function to close issue
close_issue() {
    local issue_num=$1
    
    echo "  Closing #$issue_num..."
    
    # Add comment
    gh issue comment $issue_num --body "$CLOSE_MESSAGE" 2>/dev/null || {
        echo "    ⚠️  Could not comment on #$issue_num (may not exist)"
        return 1
    }
    
    # Add post-mvp label
    gh issue edit $issue_num --add-label "post-mvp" 2>/dev/null
    
    # Close issue
    gh issue close $issue_num --reason "not planned" 2>/dev/null || {
        echo "    ⚠️  Could not close #$issue_num"
        return 1
    }
    
    echo "    ✅ Closed #$issue_num"
    return 0
}

# Close issues 46-200
CLOSED_COUNT=0
FAILED_COUNT=0

for issue_num in {46..200}; do
    if close_issue $issue_num; then
        ((CLOSED_COUNT++))
    else
        ((FAILED_COUNT++))
    fi
    
    # Rate limiting - pause every 10 issues
    if (( issue_num % 10 == 0 )); then
        echo "  ⏸️  Pausing for rate limit..."
        sleep 2
    fi
done

echo ""
echo "=============================================="
echo "✅ CLEANUP COMPLETE"
echo "=============================================="
echo "Issues closed: $CLOSED_COUNT"
echo "Failed/not found: $FAILED_COUNT"
echo ""
echo "Repository now shows MVP-focused issues only!"
echo ""
echo "View open issues: https://github.com/cortexlinux/cortex/issues"
echo "View post-MVP: https://github.com/cortexlinux/cortex/issues?q=is%3Aclosed+label%3Apost-mvp"
echo ""
