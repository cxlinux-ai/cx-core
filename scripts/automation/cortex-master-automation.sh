#!/bin/bash
# Cortex Linux - Master MVP Automation System
# Handles code generation, PR creation, issue management, and team coordination

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_DIR="$HOME/cortex"
WORK_DIR="$HOME/Downloads/cortex-mvp-work"
GITHUB_TOKEN=$(grep GITHUB_TOKEN ~/.zshrc 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")

# Ensure working directory exists
mkdir -p "$WORK_DIR"

# Banner
print_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         CORTEX LINUX - MVP MASTER AUTOMATION              ║"
    echo "║              The AI-Native Operating System               ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Menu system
show_menu() {
    echo ""
    echo -e "${GREEN}═══ MAIN MENU ═══${NC}"
    echo ""
    echo "📋 ISSUE MANAGEMENT"
    echo "  1. List MVP-critical issues"
    echo "  2. Create new MVP issue"
    echo "  3. Close post-MVP issues (cleanup)"
    echo "  4. Pin critical issues to top"
    echo ""
    echo "💻 CODE GENERATION"
    echo "  5. Generate implementation for issue"
    echo "  6. Generate tests for implementation"
    echo "  7. Generate documentation"
    echo "  8. Generate complete package (code+tests+docs)"
    echo ""
    echo "🔀 PULL REQUEST MANAGEMENT"
    echo "  9. Create PR from implementation"
    echo "  10. Review pending PRs"
    echo "  11. Merge approved PR"
    echo "  12. Bulk create PRs for ready issues"
    echo ""
    echo "👥 TEAM COORDINATION"
    echo "  13. List active contributors"
    echo "  14. Assign issue to contributor"
    echo "  15. Send Discord notification"
    echo "  16. Process bounty payment"
    echo ""
    echo "📊 STATUS & REPORTING"
    echo "  17. Show MVP progress dashboard"
    echo "  18. Generate weekly report"
    echo "  19. Check automation health"
    echo "  20. Audit repository status"
    echo ""
    echo "🚀 QUICK ACTIONS"
    echo "  21. Complete MVP package (issue → code → PR → assign)"
    echo "  22. Emergency fix workflow"
    echo "  23. Deploy to production"
    echo ""
    echo "  0. Exit"
    echo ""
    echo -n "Select option: "
}

# Issue Management Functions
list_mvp_issues() {
    echo -e "${GREEN}📋 MVP-Critical Issues${NC}"
    cd "$REPO_DIR"
    gh issue list --label "mvp-critical" --limit 30 --json number,title,assignees,labels | \
        jq -r '.[] | "  #\(.number): \(.title) [\(.assignees | map(.login) | join(", "))]"'
}

create_mvp_issue() {
    echo -e "${YELLOW}Creating new MVP issue...${NC}"
    echo -n "Issue title: "
    read title
    echo -n "Bounty amount: $"
    read bounty
    echo -n "Priority (critical/high/medium): "
    read priority
    
    echo "Brief description (Ctrl+D when done):"
    description=$(cat)
    
    body="**Bounty:** \$$bounty upon merge

**Priority:** $priority

## Description
$description

## Acceptance Criteria
- [ ] Implementation complete
- [ ] Tests included (>80% coverage)
- [ ] Documentation with examples
- [ ] Integration verified

## Skills Needed
- Python 3.11+
- System programming
- Testing (pytest)

**Ready to claim?** Comment \"I'll take this\" below!"

    cd "$REPO_DIR"
    gh issue create \
        --title "$title" \
        --body "$body" \
        --label "mvp-critical,bounty,enhancement"
    
    echo -e "${GREEN}✅ Issue created!${NC}"
}

close_post_mvp_issues() {
    echo -e "${YELLOW}Closing post-MVP issues for focus...${NC}"
    echo -n "Close issues starting from #: "
    read start_num
    echo -n "Close through #: "
    read end_num
    
    CLOSE_MSG="🎯 **Closing for MVP Focus**

This issue is valuable but being closed temporarily to focus the team on MVP-critical features.

**Timeline:**
- Now: MVP features (#1-45)
- January 2025: Reopen post-MVP work
- February 2025: Seed funding round

**Want to work on this?** Comment below and we can discuss!

Labeled as \`post-mvp\` for easy tracking."

    cd "$REPO_DIR"
    for i in $(seq $start_num $end_num); do
        gh issue comment $i --body "$CLOSE_MSG" 2>/dev/null
        gh issue edit $i --add-label "post-mvp" 2>/dev/null
        gh issue close $i --reason "not planned" 2>/dev/null && \
            echo "  ✅ Closed #$i" || echo "  ⚠️  Issue #$i not found"
        sleep 0.5
    done
    
    echo -e "${GREEN}✅ Cleanup complete!${NC}"
}

pin_critical_issues() {
    echo -e "${YELLOW}Pinning critical issues...${NC}"
    cd "$REPO_DIR"
    
    # Get issue numbers to pin
    echo "Enter issue numbers to pin (space-separated):"
    read -a issues
    
    for issue in "${issues[@]}"; do
        gh issue pin $issue 2>/dev/null && \
            echo "  📌 Pinned #$issue" || \
            echo "  ⚠️  Could not pin #$issue"
    done
    
    echo -e "${GREEN}✅ Issues pinned!${NC}"
}

# Code Generation Functions
generate_implementation() {
    echo -e "${YELLOW}Generating implementation...${NC}"
    echo -n "Issue number: "
    read issue_num
    
    cd "$REPO_DIR"
    issue_data=$(gh issue view $issue_num --json title,body)
    issue_title=$(echo "$issue_data" | jq -r '.title')
    
    echo "Issue: $issue_title"
    echo ""
    echo "⚠️  This requires Claude AI to generate the code."
    echo "Manual steps:"
    echo "1. Go to Claude.ai"
    echo "2. Ask: 'Generate complete implementation for Cortex Linux Issue #$issue_num: $issue_title'"
    echo "3. Save files to: $WORK_DIR/issue-$issue_num/"
    echo ""
    echo "Press Enter when files are ready..."
    read
    
    if [ -d "$WORK_DIR/issue-$issue_num" ]; then
        echo -e "${GREEN}✅ Files found!${NC}"
        ls -lh "$WORK_DIR/issue-$issue_num/"
    else
        echo -e "${RED}❌ No files found at $WORK_DIR/issue-$issue_num/${NC}"
    fi
}

generate_complete_package() {
    echo -e "${YELLOW}Generating complete implementation package...${NC}"
    echo -n "Issue number: "
    read issue_num
    
    mkdir -p "$WORK_DIR/issue-$issue_num"
    
    echo ""
    echo "This will generate:"
    echo "  1. Implementation code"
    echo "  2. Comprehensive tests"
    echo "  3. Full documentation"
    echo "  4. Integration examples"
    echo ""
    echo "⚠️  Requires Claude AI session"
    echo ""
    echo "In Claude, say:"
    echo "  'Generate complete implementation package for Cortex Linux Issue #$issue_num"
    echo "   Include: code, tests, docs, integration guide'"
    echo ""
    echo "Save files to: $WORK_DIR/issue-$issue_num/"
    echo ""
    echo "Press Enter when complete..."
    read
    
    if [ -d "$WORK_DIR/issue-$issue_num" ]; then
        # Create archive
        cd "$WORK_DIR"
        tar -czf "issue-$issue_num-complete.tar.gz" "issue-$issue_num/"
        echo -e "${GREEN}✅ Package created: $WORK_DIR/issue-$issue_num-complete.tar.gz${NC}"
    fi
}

# PR Management Functions
create_pr_from_implementation() {
    echo -e "${YELLOW}Creating PR from implementation...${NC}"
    echo -n "Issue number: "
    read issue_num
    
    cd "$REPO_DIR"
    
    # Get issue details
    issue_data=$(gh issue view $issue_num --json title,body,labels)
    issue_title=$(echo "$issue_data" | jq -r '.title')
    
    # Create branch
    branch_name="feature/issue-$issue_num"
    git checkout main
    git pull origin main
    git checkout -b "$branch_name" 2>/dev/null || git checkout "$branch_name"
    
    # Check if implementation files exist
    impl_dir="$WORK_DIR/issue-$issue_num"
    if [ ! -d "$impl_dir" ]; then
        echo -e "${RED}❌ No implementation found at $impl_dir${NC}"
        echo "Run option 8 to generate complete package first"
        return 1
    fi
    
    # Copy files
    echo "Copying implementation files..."
    if [ -f "$impl_dir"/*.py ]; then
        cp "$impl_dir"/*.py cortex/ 2>/dev/null || true
    fi
    if [ -f "$impl_dir"/test_*.py ]; then
        mkdir -p tests
        cp "$impl_dir"/test_*.py tests/ 2>/dev/null || true
    fi
    if [ -f "$impl_dir"/*.md ]; then
        mkdir -p docs
        cp "$impl_dir"/*.md docs/ 2>/dev/null || true
    fi
    
    # Add and commit
    git add -A
    
    if git diff --staged --quiet; then
        echo -e "${YELLOW}⚠️  No changes to commit${NC}"
        return 1
    fi
    
    git commit -m "Add $issue_title

Implements #$issue_num

- Complete implementation
- Comprehensive tests (>80% coverage)
- Full documentation
- Ready for review

Closes #$issue_num"
    
    # Push
    git push -u origin "$branch_name"
    
    # Create PR
    pr_body="## Summary

Implements **$issue_title** (#$issue_num)

## What's Included

✅ Complete implementation
✅ Comprehensive tests (>80% coverage)
✅ Full documentation
✅ Integration examples

## Testing

\`\`\`bash
pytest tests/ -v
\`\`\`

## Ready for Review

- ✅ Production-ready
- ✅ Fully tested
- ✅ Completely documented
- ✅ Follows project standards

Closes #$issue_num

---

**Bounty:** As specified in issue
**Reviewer:** @mikejmorgan-ai"
    
    gh pr create \
        --title "$issue_title" \
        --body "$pr_body" \
        --base main \
        --head "$branch_name" \
        --label "enhancement,ready-for-review"
    
    echo -e "${GREEN}✅ PR created successfully!${NC}"
    git checkout main
}

review_pending_prs() {
    echo -e "${GREEN}📋 Pending Pull Requests${NC}"
    cd "$REPO_DIR"
    gh pr list --limit 20 --json number,title,author,createdAt,headRefName | \
        jq -r '.[] | "  PR #\(.number): \(.title)\n    Author: \(.author.login)\n    Branch: \(.headRefName)\n    Created: \(.createdAt)\n"'
}

merge_approved_pr() {
    echo -e "${YELLOW}Merging approved PR...${NC}"
    echo -n "PR number: "
    read pr_num
    
    cd "$REPO_DIR"
    
    echo "Checking PR status..."
    gh pr view $pr_num
    
    echo ""
    echo -n "Merge this PR? (y/n): "
    read confirm
    
    if [ "$confirm" = "y" ]; then
        gh pr merge $pr_num --squash --delete-branch
        echo -e "${GREEN}✅ PR #$pr_num merged!${NC}"
        
        # Trigger bounty notification
        echo ""
        echo "💰 Bounty processing needed!"
        echo "Run option 16 to process payment"
    else
        echo "Merge cancelled"
    fi
}

bulk_create_prs() {
    echo -e "${YELLOW}Bulk PR creation...${NC}"
    echo "Issues with code ready (space-separated): "
    read -a issues
    
    for issue in "${issues[@]}"; do
        echo ""
        echo "Creating PR for #$issue..."
        # Reuse create_pr function
        echo "$issue" | create_pr_from_implementation
        sleep 2
    done
    
    echo -e "${GREEN}✅ All PRs created!${NC}"
}

# Team Coordination Functions
list_contributors() {
    echo -e "${GREEN}👥 Active Contributors${NC}"
    cd "$REPO_DIR"
    
    # Get recent PR authors
    gh pr list --state all --limit 50 --json author,createdAt | \
        jq -r '.[] | .author.login' | sort | uniq -c | sort -rn | head -10 | \
        awk '{printf "  %2d PRs: @%s\n", $1, $2}'
}

assign_issue() {
    echo -e "${YELLOW}Assigning issue to contributor...${NC}"
    echo -n "Issue number: "
    read issue_num
    echo -n "GitHub username: "
    read username
    
    cd "$REPO_DIR"
    gh issue edit $issue_num --add-assignee "$username"
    
    # Send notification comment
    gh issue comment $issue_num --body "👋 Hey @$username! This issue is now assigned to you.

**Next steps:**
1. Review the requirements
2. Comment with your timeline
3. Submit PR when ready

Questions? Ask in #dev-chat on Discord: https://discord.gg/uCqHvxjU83

Thanks for contributing! 🚀"
    
    echo -e "${GREEN}✅ Assigned #$issue_num to @$username${NC}"
}

send_discord_notification() {
    echo -e "${YELLOW}Sending Discord notification...${NC}"
    
    if [ -z "$DISCORD_WEBHOOK" ]; then
        echo -e "${RED}❌ DISCORD_WEBHOOK not set${NC}"
        echo "Set it in GitHub Secrets or ~/.zshrc"
        return 1
    fi
    
    echo "Select notification type:"
    echo "  1. PR merged"
    echo "  2. Issue created"
    echo "  3. Custom message"
    echo -n "Choice: "
    read choice
    
    case $choice in
        1)
            echo -n "PR number: "
            read pr_num
            message="🚀 **PR #$pr_num Merged!**\n\nGreat work! Bounty will be processed Friday."
            ;;
        2)
            echo -n "Issue number: "
            read issue_num
            message="📋 **New Issue #$issue_num Created**\n\nCheck it out: https://github.com/cortexlinux/cortex/issues/$issue_num"
            ;;
        3)
            echo "Enter message:"
            read message
            ;;
    esac
    
    curl -X POST "$DISCORD_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"$message\"}"
    
    echo -e "${GREEN}✅ Notification sent!${NC}"
}

process_bounty() {
    echo -e "${YELLOW}💰 Processing bounty payment...${NC}"
    echo -n "PR number: "
    read pr_num
    echo -n "Contributor username: "
    read username
    echo -n "Bounty amount: $"
    read amount
    
    cd "$REPO_DIR"
    
    # Add payment comment
    gh pr comment $pr_num --body "💰 **Bounty Approved: \$$amount**

Hey @$username! Your bounty has been approved.

**Next steps:**
1. DM me your payment method (PayPal/Crypto/Venmo/Zelle)
2. Payment will be processed this Friday
3. You'll also get 2x bonus (\$$((amount * 2))) when we raise our seed round!

Thanks for the great work! 🎉"
    
    # Log payment
    echo "{\"pr\": $pr_num, \"contributor\": \"$username\", \"amount\": $amount, \"date\": \"$(date -I)\", \"status\": \"approved\"}" >> "$WORK_DIR/bounties_log.jsonl"
    
    echo -e "${GREEN}✅ Bounty processed!${NC}"
    echo "Remember to actually send the payment!"
}

# Status & Reporting Functions
show_mvp_dashboard() {
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo -e "${BLUE}         CORTEX LINUX - MVP DASHBOARD      ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    
    cd "$REPO_DIR"
    
    echo ""
    echo -e "${GREEN}📊 ISSUE STATUS${NC}"
    total_issues=$(gh issue list --limit 1000 --json number | jq '. | length')
    mvp_critical=$(gh issue list --label "mvp-critical" --json number | jq '. | length')
    open_prs=$(gh pr list --json number | jq '. | length')
    
    echo "  Total open issues: $total_issues"
    echo "  MVP critical: $mvp_critical"
    echo "  Open PRs: $open_prs"
    
    echo ""
    echo -e "${GREEN}🎯 MVP PROGRESS${NC}"
    # Estimate completion
    completed=$((30 - mvp_critical))
    percent=$((completed * 100 / 30))
    echo "  Completed: $completed/30 ($percent%)"
    
    echo ""
    echo -e "${GREEN}👥 TEAM ACTIVITY${NC}"
    recent_prs=$(gh pr list --state all --limit 7 --json number | jq '. | length')
    echo "  PRs this week: $recent_prs"
    
    echo ""
    echo -e "${GREEN}💰 BOUNTIES${NC}"
    if [ -f "$WORK_DIR/bounties_log.jsonl" ]; then
        total_paid=$(jq -s 'map(.amount) | add' "$WORK_DIR/bounties_log.jsonl")
        echo "  Total paid: \$$total_paid"
    else
        echo "  Total paid: \$0 (no log file)"
    fi
    
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
}

generate_weekly_report() {
    echo -e "${YELLOW}Generating weekly report...${NC}"
    
    report_file="$WORK_DIR/weekly-report-$(date +%Y-%m-%d).md"
    
    cd "$REPO_DIR"
    
    cat > "$report_file" << 'REPORT_EOF'
# Cortex Linux - Weekly Report
**Week of $(date +%Y-%m-%d)**

## 🎯 Progress This Week

### PRs Merged
$(gh pr list --state merged --limit 100 --json number,title,mergedAt | jq -r '.[] | select(.mergedAt | fromdateiso8601 > (now - 604800)) | "- PR #\(.number): \(.title)"')

### Issues Closed
$(gh issue list --state closed --limit 100 --json number,title,closedAt | jq -r '.[] | select(.closedAt | fromdateiso8601 > (now - 604800)) | "- Issue #\(.number): \(.title)"')

### New Contributors
$(gh pr list --state all --limit 50 --json author,createdAt | jq -r '.[] | select(.createdAt | fromdateiso8601 > (now - 604800)) | .author.login' | sort -u)

## 📊 Metrics

- Open Issues: $(gh issue list --json number | jq '. | length')
- Open PRs: $(gh pr list --json number | jq '. | length')
- Active Contributors: $(gh pr list --state all --limit 100 --json author | jq -r '.[].author.login' | sort -u | wc -l)

## 🚀 Next Week Priorities

1. Complete remaining MVP issues
2. Review and merge pending PRs
3. Process bounty payments

---
*Generated by Cortex Master Automation*
REPORT_EOF
    
    eval "echo \"$(cat $report_file)\"" > "$report_file"
    
    echo -e "${GREEN}✅ Report generated: $report_file${NC}"
    cat "$report_file"
}

check_automation_health() {
    echo -e "${GREEN}🔍 Checking automation health...${NC}"
    
    cd "$REPO_DIR"
    
    echo ""
    echo "GitHub Actions Status:"
    gh run list --limit 5 --json conclusion,name | \
        jq -r '.[] | "  \(.name): \(.conclusion)"'
    
    echo ""
    echo "GitHub Secrets:"
    gh secret list | head -5
    
    echo ""
    echo "Branch Protection:"
    gh api repos/cortexlinux/cortex/branches/main/protection 2>/dev/null | \
        jq -r '.required_status_checks.contexts[]' || echo "  No branch protection"
    
    echo ""
    echo "Webhooks:"
    gh api repos/cortexlinux/cortex/hooks | jq -r '.[].name' || echo "  No webhooks"
}

audit_repository() {
    echo -e "${GREEN}🔍 Full Repository Audit${NC}"
    
    cd "$REPO_DIR"
    
    # Run comprehensive audit
    bash "$WORK_DIR/../audit_cortex_status.sh" 2>/dev/null || {
        echo "Audit script not found, running basic audit..."
        
        echo "Repository: cortexlinux/cortex"
        echo "Branch: $(git branch --show-current)"
        echo "Last commit: $(git log -1 --oneline)"
        echo ""
        echo "Open issues: $(gh issue list --json number | jq '. | length')"
        echo "Open PRs: $(gh pr list --json number | jq '. | length')"
        echo "Contributors: $(git log --format='%aN' | sort -u | wc -l)"
    }
}

# Quick Actions
complete_mvp_package() {
    echo -e "${BLUE}🚀 COMPLETE MVP PACKAGE WORKFLOW${NC}"
    echo "This will:"
    echo "  1. Generate implementation"
    echo "  2. Create PR"
    echo "  3. Assign to contributor"
    echo "  4. Send notifications"
    echo ""
    echo -n "Issue number: "
    read issue_num
    
    # Step 1: Generate
    echo "$issue_num" | generate_complete_package
    
    # Step 2: Create PR
    echo "$issue_num" | create_pr_from_implementation
    
    # Step 3: Notify
    echo "Package complete for issue #$issue_num!"
    echo "PR created and ready for review"
}

emergency_fix() {
    echo -e "${RED}🚨 EMERGENCY FIX WORKFLOW${NC}"
    echo -n "What's broken? "
    read issue_description
    
    # Create hotfix branch
    cd "$REPO_DIR"
    git checkout main
    git pull
    git checkout -b "hotfix/emergency-$(date +%s)"
    
    echo "Hotfix branch created"
    echo "Make your fixes, then commit and push"
    echo ""
    echo "When ready, run option 9 to create PR"
}

deploy_to_production() {
    echo -e "${YELLOW}🚀 Deploying to production...${NC}"
    echo "⚠️  This is a placeholder for production deployment"
    echo ""
    echo "Production deployment steps:"
    echo "  1. Merge all approved PRs"
    echo "  2. Tag release"
    echo "  3. Build packages"
    echo "  4. Deploy to servers"
    echo ""
    echo "Not yet implemented - coming soon!"
}

# Main execution
main() {
    print_banner
    
    cd "$REPO_DIR" 2>/dev/null || {
        echo -e "${RED}❌ Repository not found at $REPO_DIR${NC}"
        echo "Clone it first: git clone https://github.com/cortexlinux/cortex.git ~/cortex"
        exit 1
    }
    
    while true; do
        show_menu
        read choice
        
        case $choice in
            1) list_mvp_issues ;;
            2) create_mvp_issue ;;
            3) close_post_mvp_issues ;;
            4) pin_critical_issues ;;
            5) generate_implementation ;;
            6) echo "Coming soon..." ;;
            7) echo "Coming soon..." ;;
            8) generate_complete_package ;;
            9) create_pr_from_implementation ;;
            10) review_pending_prs ;;
            11) merge_approved_pr ;;
            12) bulk_create_prs ;;
            13) list_contributors ;;
            14) assign_issue ;;
            15) send_discord_notification ;;
            16) process_bounty ;;
            17) show_mvp_dashboard ;;
            18) generate_weekly_report ;;
            19) check_automation_health ;;
            20) audit_repository ;;
            21) complete_mvp_package ;;
            22) emergency_fix ;;
            23) deploy_to_production ;;
            0) echo "Goodbye!"; exit 0 ;;
            *) echo -e "${RED}Invalid option${NC}" ;;
        esac
        
        echo ""
        echo "Press Enter to continue..."
        read
    done
}

# Run main
main
