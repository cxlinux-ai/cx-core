#!/bin/bash
# Deploy new modules to ~/Desktop/polymarket-bot
# Run this from your Mac terminal

set -e
cd ~/Desktop/polymarket-bot

echo "=== Deploying Polymarket Bot Addon Modules ==="

# Create directories
mkdir -p src/arb src/whale src/events data

# Create __init__.py files
touch src/arb/__init__.py
touch src/whale/__init__.py
touch src/events/__init__.py

echo "  Created directories and __init__.py files"

# Install new dependency
pip install anthropic aiohttp 2>/dev/null || pip3 install anthropic aiohttp 2>/dev/null
echo "  Installed anthropic SDK"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "New modules installed:"
echo "  src/arb/scanner.py     - Arbitrage scanner (YES+NO < 0.98)"
echo "  src/whale/wallets.py   - Whale wallet registry"
echo "  src/whale/tracker.py   - Whale trade tracker"
echo "  src/events/analyzer.py - Claude AI market analyzer"
echo "  src/events/trader.py   - AI event trader"
echo "  src/addons.py          - Addon runner (wires everything together)"
echo ""
echo "To test standalone (without main bot):"
echo "  cd ~/Desktop/polymarket-bot && python -m src.addons"
echo ""
echo "To integrate with main bot:"
echo "  python patch_main.py"
echo ""
echo "Don't forget to set ANTHROPIC_API_KEY in .env for the event trader!"
