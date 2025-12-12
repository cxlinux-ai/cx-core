#!/bin/bash

# Upload Issue #34 files to GitHub

echo "🔐 Enter your GitHub Personal Access Token:"
read -s GITHUB_TOKEN

REPO="cortexlinux/cortex"
BRANCH="feature/issue-34"

echo ""
echo "📤 Uploading llm_router.py..."
curl -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Add LLM Router implementation\",\"content\":\"$(base64 -i llm_router.py)\",\"branch\":\"$BRANCH\"}" \
  "https://api.github.com/repos/$REPO/contents/src/llm_router.py"

echo ""
echo "📤 Uploading test_llm_router.py..."
curl -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Add LLM Router tests\",\"content\":\"$(base64 -i test_llm_router.py)\",\"branch\":\"$BRANCH\"}" \
  "https://api.github.com/repos/$REPO/contents/src/test_llm_router.py"

echo ""
echo "📤 Uploading README_LLM_ROUTER.md..."
curl -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Add LLM Router documentation\",\"content\":\"$(base64 -i README_LLM_ROUTER.md)\",\"branch\":\"$BRANCH\"}" \
  "https://api.github.com/repos/$REPO/contents/docs/README_LLM_ROUTER.md"

echo ""
echo "✅ Upload complete! Check: https://github.com/$REPO/tree/$BRANCH"
