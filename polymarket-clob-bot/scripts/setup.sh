#!/bin/bash
# One-command setup for polymarket-clob-bot
set -e

echo "Setting up polymarket-clob-bot..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

# Create data directory
mkdir -p data

echo ""
echo "Setup complete."
echo "  1. Edit .env with your credentials"
echo "  2. Run: source venv/bin/activate"
echo "  3. Run: python -m src.main"
