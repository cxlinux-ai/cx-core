#!/bin/bash
# Cortex Linux - Repo Cleanup Script
# Run this once to organize the repo for public launch
# Usage: cd ~/cortex && bash cortex-cleanup.sh

set -e

echo "🧹 CORTEX LINUX REPO CLEANUP"
echo "============================"
echo ""

cd ~/cortex || { echo "❌ ~/cortex not found"; exit 1; }

# Confirm we're in the right place
if [ ! -f "README.md" ] || [ ! -d ".git" ]; then
    echo "❌ Not in cortex repo root. Run from ~/cortex"
    exit 1
fi

echo "📁 Current root files: $(ls *.py *.sh *.json *.csv *.md 2>/dev/null | wc -l | tr -d ' ')"
echo ""

# Step 1: Create directories if they don't exist
echo "1️⃣  Creating directory structure..."
mkdir -p cortex/modules
mkdir -p tests
mkdir -p scripts
mkdir -p docs
mkdir -p internal

# Step 2: Move Python modules into cortex/
echo "2️⃣  Moving Python modules to cortex/..."
for file in context_memory.py dependency_resolver.py error_parser.py \
            installation_history.py installation_verifier.py llm_router.py \
            logging_system.py; do
    if [ -f "$file" ]; then
        mv "$file" cortex/ 2>/dev/null && echo "   ✓ $file → cortex/"
    fi
done

# Step 3: Move test files into tests/
echo "3️⃣  Moving test files to tests/..."
for file in test_*.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/ 2>/dev/null && echo "   ✓ $file → tests/"
    fi
done

# Step 4: Move shell scripts into scripts/
echo "4️⃣  Moving shell scripts to scripts/..."
for file in *.sh; do
    # Keep this cleanup script in root temporarily
    if [ "$file" != "cortex-cleanup.sh" ] && [ -f "$file" ]; then
        mv "$file" scripts/ 2>/dev/null && echo "   ✓ $file → scripts/"
    fi
done

# Step 5: Move markdown docs to docs/ (except key root files)
echo "5️⃣  Moving documentation to docs/..."
for file in *.md; do
    case "$file" in
        README.md|CHANGELOG.md|LICENSE|Contributing.md)
            echo "   ⊘ $file (keeping in root)"
            ;;
        *)
            if [ -f "$file" ]; then
                mv "$file" docs/ 2>/dev/null && echo "   ✓ $file → docs/"
            fi
            ;;
    esac
done

# Step 6: Move internal/admin files and gitignore them
echo "6️⃣  Moving internal files to internal/..."
for file in bounties_owed.csv bounties_pending.json contributors.json \
            issue_status.json payments_history.json pr_status.json; do
    if [ -f "$file" ]; then
        mv "$file" internal/ 2>/dev/null && echo "   ✓ $file → internal/"
    fi
done

# Step 7: Delete duplicate/junk files
echo "7️⃣  Removing duplicate files..."
rm -f "README_DEPENDENCIES (1).md" 2>/dev/null && echo "   ✓ Removed README_DEPENDENCIES (1).md"
rm -f "deploy_jesse_system (1).sh" 2>/dev/null && echo "   ✓ Removed deploy_jesse_system (1).sh"

# Step 8: Update .gitignore
echo "8️⃣  Updating .gitignore..."
if ! grep -q "internal/" .gitignore 2>/dev/null; then
    echo "" >> .gitignore
    echo "# Internal admin files (bounties, payments, etc.)" >> .gitignore
    echo "internal/" >> .gitignore
    echo "   ✓ Added internal/ to .gitignore"
else
    echo "   ⊘ internal/ already in .gitignore"
fi

# Step 9: Create __init__.py files if missing
echo "9️⃣  Ensuring Python packages are importable..."
touch cortex/__init__.py 2>/dev/null
touch tests/__init__.py 2>/dev/null
echo "   ✓ __init__.py files created"

# Step 10: Show results
echo ""
echo "📊 CLEANUP COMPLETE"
echo "==================="
echo "Root files now: $(ls *.py *.sh *.json *.csv 2>/dev/null | wc -l | tr -d ' ') (should be ~0)"
echo ""
echo "Directory structure:"
echo "  cortex/     - $(ls cortex/*.py 2>/dev/null | wc -l | tr -d ' ') Python modules"
echo "  tests/      - $(ls tests/*.py 2>/dev/null | wc -l | tr -d ' ') test files"
echo "  scripts/    - $(ls scripts/*.sh 2>/dev/null | wc -l | tr -d ' ') shell scripts"
echo "  docs/       - $(ls docs/*.md 2>/dev/null | wc -l | tr -d ' ') markdown files"
echo "  internal/   - $(ls internal/ 2>/dev/null | wc -l | tr -d ' ') admin files (gitignored)"
echo ""

# Step 11: Git commit
echo "🔟 Committing changes..."
git add -A
git status --short
echo ""
read -p "Commit and push these changes? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git commit -m "Reorganize repo structure for public launch

- Move Python modules to cortex/
- Move tests to tests/
- Move scripts to scripts/
- Move docs to docs/
- Move internal admin files to internal/ (gitignored)
- Remove duplicate files
- Clean root directory for professional appearance"
    
    git push origin main
    echo ""
    echo "✅ DONE! Repo is now clean and pushed."
else
    echo ""
    echo "⚠️  Changes staged but NOT committed. Run 'git commit' when ready."
fi

echo ""
echo "🧪 NEXT STEP: Test the CLI"
echo "   cd ~/cortex && source venv/bin/activate && cortex install nginx --dry-run"
echo ""
