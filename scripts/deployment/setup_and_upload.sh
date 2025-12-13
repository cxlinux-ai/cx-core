#!/bin/bash

echo "=========================================="
echo "  GitHub Token Setup"
echo "=========================================="
echo ""
echo "Get your token from: https://github.com/settings/tokens"
echo "Click 'Generate new token (classic)'"
echo "Check 'repo' scope, then generate"
echo ""
echo "Paste your GitHub token here:"
read -s TOKEN
echo ""

if [ -z "$TOKEN" ]; then
    echo "❌ No token provided"
    exit 1
fi

# Remove any old GITHUB_TOKEN lines
grep -v "GITHUB_TOKEN" ~/.zshrc > ~/.zshrc.tmp 2>/dev/null || touch ~/.zshrc.tmp
mv ~/.zshrc.tmp ~/.zshrc

# Add new token
echo "export GITHUB_TOKEN=\"$TOKEN\"" >> ~/.zshrc

# Reload
export GITHUB_TOKEN="$TOKEN"

echo "✅ Token saved to ~/.zshrc"
echo ""

# Test it
echo "Testing token..."
python3 << 'PYEOF'
from github import Github
import os

token = os.getenv("GITHUB_TOKEN")
try:
    g = Github(token)
    user = g.get_user()
    print(f"✅ Token works! Logged in as: {user.login}")
except Exception as e:
    print(f"❌ Token invalid: {e}")
PYEOF

echo ""
echo "=========================================="
echo "Now running file upload..."
echo "=========================================="
echo ""

# Run the upload
python3 /Users/allbots/Downloads/commit_files.py
