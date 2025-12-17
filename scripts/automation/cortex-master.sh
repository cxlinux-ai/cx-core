#!/bin/bash
# Cortex Linux - Master MVP Automation System
# One script to rule them all

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_DIR="$HOME/cortex"
WORK_DIR="$HOME/Downloads/cortex-work"
mkdir -p "$WORK_DIR"

print_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════╗"
    echo "║    CORTEX LINUX - MVP MASTER AUTOMATION       ║"
    echo "╚════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

show_menu() {
    echo ""
    echo -e "${GREEN}═══ MAIN MENU ═══${NC}"
    echo ""
    echo "1. Show MVP dashboard"
    echo "2. List MVP-critical issues"
    echo "3. Create PR for issue #10"
    echo "4. Review pending PRs"
    echo "5. Merge PR"
    echo "6. List contributors"
    echo "7. Assign issue to contributor"
    echo "8. Process bounty payment"
    echo "9. Generate weekly report"
    echo "10. Full repository audit"
    echo ""
    echo "0. Exit"
    echo ""
    echo -n "Select: "
}

show_dashboard() {
    cd "$REPO_DIR"
    echo -e "${BLUE}═══ CORTEX MVP DASHBOARD ═══${NC}"
    echo ""
    echo "📊 Issues:"
    echo "  Total: $(gh issue list --limit 1000 --json number | jq '. | length')"
    echo "  MVP Critical: $(gh issue list --label 'mvp-critical' --json number | jq '. | length')"
    echo ""
    echo "🔀 Pull Requests:"
    echo "  Open: $(gh pr list --json number | jq '. | length')"
    echo ""
    echo "👥 Recent activity:"
    gh pr list --state all --limit 5 --json number,title,author | \
        jq -r '.[] | "  PR #\(.number): \(.title) (@\(.author.login))"'
}

list_mvp() {
    cd "$REPO_DIR"
    echo -e "${GREEN}📋 MVP-Critical Issues:${NC}"
    gh issue list --label "mvp-critical" --limit 20 --json number,title,assignees | \
        jq -r '.[] | "  #\(.number): \(.title)"'
}

create_pr_issue10() {
    cd "$REPO_DIR"
    git checkout feature/issue-10 2>/dev/null || {
        echo "Branch feature/issue-10 not found"
        return 1
    }
    
    gh pr create \
        --title "Add Installation Verification System - Fixes #10" \
        --body "Complete implementation: 918 lines (code+tests+docs). Ready for review." \
        --label "enhancement,ready-for-review,priority: critical"
    
    git checkout main
    echo "✅ PR created!"
}

review_prs() {
    cd "$REPO_DIR"
    echo -e "${GREEN}📋 Open Pull Requests:${NC}"
    gh pr list --json number,title,author,createdAt | \
        jq -r '.[] | "  PR #\(.number): \(.title)\n    Author: @\(.author.login)\n    Created: \(.createdAt)\n"'
}

merge_pr() {
    echo -n "PR number to merge: "
    read pr_num
    cd "$REPO_DIR"
    gh pr merge $pr_num --squash --delete-branch
    echo "✅ Merged!"
}

list_contributors() {
    cd "$REPO_DIR"
    echo -e "${GREEN}👥 Active Contributors:${NC}"
    gh pr list --state all --limit 50 --json author | \
        jq -r '.[].author.login' | sort | uniq -c | sort -rn | head -10
}

assign_issue() {
    echo -n "Issue #: "
    read issue
    echo -n "Assign to (username): "
    read user
    cd "$REPO_DIR"
    gh issue edit $issue --add-assignee "$user"
    gh issue comment $issue --body "👋 @$user - This is assigned to you! Questions? Ask in Discord."
    echo "✅ Assigned!"
}

process_bounty() {
    echo -n "PR #: "
    read pr
    echo -n "Username: "
    read user
    echo -n "Amount $: "
    read amount
    
    cd "$REPO_DIR"
    gh pr comment $pr --body "💰 **Bounty Approved: \$$amount**

@$user - DM me your payment method. Payment Friday. Plus 2x bonus at funding!

Thanks! 🎉"
    
    echo "✅ Bounty processed!"
}

weekly_report() {
    cd "$REPO_DIR"
    echo "# Cortex Linux - Weekly Report"
    echo "Week of $(date +%Y-%m-%d)"
    echo ""
    echo "## PRs This Week"
    gh pr list --state merged --limit 10 --json number,title | \
        jq -r '.[] | "- PR #\(.number): \(.title)"'
    echo ""
    echo "## Metrics"
    echo "- Open Issues: $(gh issue list --json number | jq '. | length')"
    echo "- Open PRs: $(gh pr list --json number | jq '. | length')"
}

audit_repo() {
    cd "$REPO_DIR"
    echo "Repository: cortexlinux/cortex"
    echo "Branch: $(git branch --show-current)"
    echo "Last commit: $(git log -1 --oneline)"
    echo ""
    echo "Issues: $(gh issue list --json number | jq '. | length') open"
    echo "PRs: $(gh pr list --json number | jq '. | length') open"
    echo ""
    echo "Recent activity:"
    gh run list --limit 3
}

main() {
    print_banner
    
    cd "$REPO_DIR" 2>/dev/null || {
        echo "❌ Repo not found at $REPO_DIR"
        exit 1
    }
    
    while true; do
        show_menu
        read choice
        
        case $choice in
            1) show_dashboard ;;
            2) list_mvp ;;
            3) create_pr_issue10 ;;
            4) review_prs ;;
            5) merge_pr ;;
            6) list_contributors ;;
            7) assign_issue ;;
            8) process_bounty ;;
            9) weekly_report ;;
            10) audit_repo ;;
            0) echo "Goodbye!"; exit 0 ;;
            *) echo "Invalid option" ;;
        esac
        
        echo ""
        read -p "Press Enter..." 
    done
}

main
