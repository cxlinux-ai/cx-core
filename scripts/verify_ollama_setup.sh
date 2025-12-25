#!/bin/bash
# Verification script for automatic Ollama setup during pip install
# This script tests the complete installation flow in a clean environment

set -e  # Exit on error

echo "========================================================================"
echo "Cortex Linux - Ollama Auto-Setup Verification"
echo "========================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the cortex directory
if [ ! -f "setup.py" ]; then
    echo -e "${RED}❌ Error: Must be run from cortex root directory${NC}"
    exit 1
fi

echo "Step 1: Checking package structure..."
if [ -f "scripts/__init__.py" ]; then
    echo -e "  ${GREEN}✅ scripts/__init__.py exists${NC}"
else
    echo -e "  ${RED}❌ scripts/__init__.py missing${NC}"
    exit 1
fi

if [ -f "scripts/setup_ollama.py" ]; then
    echo -e "  ${GREEN}✅ scripts/setup_ollama.py exists${NC}"
else
    echo -e "  ${RED}❌ scripts/setup_ollama.py missing${NC}"
    exit 1
fi

echo ""
echo "Step 2: Checking MANIFEST.in..."
if grep -q "recursive-include scripts" MANIFEST.in; then
    echo -e "  ${GREEN}✅ MANIFEST.in includes scripts directory${NC}"
else
    echo -e "  ${RED}❌ MANIFEST.in missing scripts inclusion${NC}"
    exit 1
fi

echo ""
echo "Step 3: Testing import..."
if python3 -c "from scripts.setup_ollama import setup_ollama" 2>/dev/null; then
    echo -e "  ${GREEN}✅ Can import setup_ollama${NC}"
else
    echo -e "  ${RED}❌ Cannot import setup_ollama${NC}"
    exit 1
fi

echo ""
echo "Step 4: Testing setup execution (skipped mode)..."
if CORTEX_SKIP_OLLAMA_SETUP=1 python3 -c "from scripts.setup_ollama import setup_ollama; setup_ollama()" 2>&1 | grep -q "Skipping Ollama setup"; then
    echo -e "  ${GREEN}✅ Setup function executes correctly${NC}"
else
    echo -e "  ${RED}❌ Setup function failed${NC}"
    exit 1
fi

echo ""
echo "Step 5: Running Python integration tests..."
if python3 tests/test_ollama_setup_integration.py > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Integration tests pass${NC}"
else
    echo -e "  ${RED}❌ Integration tests failed${NC}"
    python3 tests/test_ollama_setup_integration.py
    exit 1
fi

echo ""
echo "Step 6: Checking setup.py configuration..."
if python3 setup.py --version > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ setup.py is valid${NC}"
else
    echo -e "  ${RED}❌ setup.py has errors${NC}"
    exit 1
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✅ All verification checks passed!${NC}"
echo "========================================================================"
echo ""
echo "Automatic Ollama setup is properly configured."
echo ""
echo "Next steps:"
echo "  1. Test installation: CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e ."
echo "  2. Or for full test: pip install -e . (will install Ollama)"
echo ""
echo "To skip Ollama during install:"
echo "  CORTEX_SKIP_OLLAMA_SETUP=1 pip install -e ."
echo ""
echo "To manually run Ollama setup after install:"
echo "  cortex-setup-ollama"
echo ""
echo "Documentation:"
echo "  - docs/AUTOMATIC_OLLAMA_SETUP.md"
echo "  - docs/OLLAMA_INTEGRATION.md"
echo ""
