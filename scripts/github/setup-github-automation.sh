#!/bin/bash
# Cortex Linux - GitHub Automation Setup
# Run this once to set up everything

set -e

echo "🚀 CORTEX LINUX AUTOMATION SETUP"
echo "=================================="
echo ""

# Check if we're in a git repo
if [ ! -d .git ]; then
    echo "❌ Error: Not in a git repository"
    echo "   Run this from your cortex repo root: cd ~/path/to/cortex"
    exit 1
fi

# Check GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI not found"
    echo "   Install: brew install gh"
    echo "   Then: gh auth login"
    exit 1
fi

echo "✅ Prerequisites check passed"
echo ""

# Create .github/workflows directory
echo "📁 Creating .github/workflows directory..."
mkdir -p .github/workflows

# Copy workflow file
echo "📄 Installing automation workflow..."
if [ -f ~/Downloads/cortex-automation-github.yml ]; then
    cp ~/Downloads/cortex-automation-github.yml .github/workflows/automation.yml
    echo "✅ Workflow file installed"
else
    echo "❌ Error: cortex-automation-github.yml not found in Downloads"
    echo "   Download it first from Claude"
    exit 1
fi

# Create tracking files
echo "📊 Creating tracking files..."
echo "[]" > bounties_pending.json
echo "[]" > payments_history.json
echo "{}" > contributors.json
echo "✅ Tracking files created"

# Add to .gitignore if needed
if [ ! -f .gitignore ]; then
    touch .gitignore
fi

if ! grep -q "bounties_pending.json" .gitignore; then
    echo "" >> .gitignore
    echo "# Cortex Automation tracking files" >> .gitignore
    echo "bounties_pending.json" >> .gitignore
    echo "payments_history.json" >> .gitignore
    echo "contributors.json" >> .gitignore
    echo "bounty_report.txt" >> .gitignore
    echo "discord_message.txt" >> .gitignore
    echo "✅ Added to .gitignore"
fi

# Commit and push
echo ""
echo "💾 Committing automation setup..."
git add .github/workflows/automation.yml
git add bounties_pending.json payments_history.json contributors.json
git add .gitignore
git commit -m "Add GitHub Actions automation for bounty tracking" || echo "Nothing to commit"

echo ""
echo "📤 Pushing to GitHub..."
git push

echo ""
echo "✅ SETUP COMPLETE!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔐 NEXT: Add Discord Webhook to GitHub Secrets"
echo ""
echo "1. Get Discord webhook URL:"
echo "   • Go to your Discord server"
echo "   • Server Settings → Integrations → Webhooks"
echo "   • Click 'New Webhook'"
echo "   • Name: 'Cortex Bot'"
echo "   • Channel: #announcements"
echo "   • Copy Webhook URL"
echo ""
echo "2. Add to GitHub Secrets:"
echo "   • Go to: https://github.com/cortexlinux/cortex/settings/secrets/actions"
echo "   • Click 'New repository secret'"
echo "   • Name: DISCORD_WEBHOOK"
echo "   • Value: [paste webhook URL]"
echo "   • Click 'Add secret'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎉 AUTOMATION IS NOW LIVE!"
echo ""
echo "What happens automatically:"
echo "  ✅ Every Friday 6pm UTC - Bounty report posted to Discord"
echo "  ✅ Every Monday noon UTC - Leaderboard updated"
echo "  ✅ Every PR merge - Discord notification + welcome message"
echo ""
echo "You just approve payments in Discord. That's it!"
echo ""
echo "Test it now:"
echo "  gh workflow run automation.yml"
echo ""
