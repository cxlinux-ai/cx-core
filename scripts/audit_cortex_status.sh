#!/bin/bash
# Cortex Linux - Complete System Audit
# Run this once to give Claude full visibility

echo "🔍 CORTEX LINUX - SYSTEM AUDIT"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

cd ~/cortex 2>/dev/null || { echo "❌ ~/cortex not found. Run: cd ~ && git clone https://github.com/cortexlinux/cortex.git"; exit 1; }

echo "📁 REPOSITORY STRUCTURE"
echo "========================================"
echo "Files in repo:"
find . -type f -not -path '*/\.*' | head -30
echo ""

echo "🤖 GITHUB ACTIONS WORKFLOWS"
echo "========================================"
if [ -d ".github/workflows" ]; then
    echo "✅ Workflows directory exists"
    ls -lh .github/workflows/
    echo ""
    echo "📄 Workflow file contents:"
    for file in .github/workflows/*.yml; do
        echo "--- $file ---"
        head -50 "$file"
        echo ""
    done
else
    echo "❌ No .github/workflows directory"
fi
echo ""

echo "📊 AUTOMATION DATA FILES"
echo "========================================"
for file in bounties_pending.json payments_history.json contributors.json; do
    if [ -f "$file" ]; then
        echo "✅ $file exists"
        cat "$file"
    else
        echo "❌ $file missing"
    fi
    echo ""
done

echo "🔐 GITHUB SECRETS STATUS"
echo "========================================"
echo "Checking if secrets are configured..."
gh secret list 2>/dev/null || echo "⚠️  gh CLI not authenticated or not installed"
echo ""

echo "🌐 GITHUB ACTIONS RUNS"
echo "========================================"
echo "Recent workflow runs:"
gh run list --limit 5 2>/dev/null || echo "⚠️  gh CLI not authenticated"
echo ""

echo "📋 RECENT COMMITS"
echo "========================================"
git log --oneline -10
echo ""

echo "🔀 BRANCHES"
echo "========================================"
git branch -a
echo ""

echo "📍 CURRENT STATUS"
echo "========================================"
echo "Current branch: $(git branch --show-current)"
echo "Remote URL: $(git remote get-url origin)"
echo "Git status:"
git status --short
echo ""

echo "💬 DISCORD WEBHOOK CHECK"
echo "========================================"
if gh secret list 2>/dev/null | grep -q "DISCORD_WEBHOOK"; then
    echo "✅ DISCORD_WEBHOOK secret is configured"
else
    echo "❌ DISCORD_WEBHOOK secret not found"
    echo "   Add it at: https://github.com/cortexlinux/cortex/settings/secrets/actions"
fi
echo ""

echo "🎯 ISSUES & PRS"
echo "========================================"
echo "Open issues with bounties:"
gh issue list --label "bounty" --limit 10 2>/dev/null || echo "⚠️  gh CLI issue"
echo ""
echo "Recent PRs:"
gh pr list --limit 5 2>/dev/null || echo "⚠️  gh CLI issue"
echo ""

echo "✅ AUDIT COMPLETE"
echo "========================================"
echo "Save this output and share with Claude for full visibility"
echo ""
echo "Next steps:"
echo "1. Share this output with Claude"
echo "2. Claude can now see everything without asking"
echo "3. No more copy/paste needed"
