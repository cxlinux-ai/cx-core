"""Onboarding web app for Polymarket Bot setup."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file

app = Flask(__name__)

BOT_ROOT = Path(__file__).resolve().parent.parent

# Files to include in the downloadable zip
INCLUDE_DIRS = ["config", "src", "scripts", "data"]
INCLUDE_FILES = [
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "Procfile",
    "railway.json",
    "requirements.txt",
    "README.md",
    "CLAUDE.md",
]


def _collect_bot_files() -> list[tuple[str, Path]]:
    """Return (archive_path, disk_path) pairs for all bot source files."""
    files: list[tuple[str, Path]] = []

    for fname in INCLUDE_FILES:
        p = BOT_ROOT / fname
        if p.exists():
            files.append((fname, p))

    for dname in INCLUDE_DIRS:
        d = BOT_ROOT / dname
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and "__pycache__" not in str(p):
                    rel = p.relative_to(BOT_ROOT)
                    files.append((str(rel), p))

    return files


def _generate_env(form: dict) -> str:
    """Generate .env content from form submission."""
    lines = [
        "# Polymarket",
        f"POLYMARKET_PRIVATE_KEY={form.get('private_key', '')}",
        f"POLYMARKET_FUNDER_ADDRESS={form.get('funder_address', '')}",
        f"POLYMARKET_SIGNATURE_TYPE={form.get('signature_type', '0')}",
        "POLYMARKET_API_HOST=https://clob.polymarket.com",
        "POLYMARKET_CHAIN_ID=137",
        "",
        "# Telegram",
        f"TELEGRAM_BOT_TOKEN={form.get('telegram_token', '')}",
        f"TELEGRAM_CHAT_ID={form.get('telegram_chat_id', '')}",
        "",
        "# Strategy",
        f"ENTRY_WINDOW_SECONDS={form.get('entry_window', '240')}",
        f"MIN_EDGE_PCT={form.get('min_edge', '0.02')}",
        f"MAX_POSITION_USDC={form.get('max_position', '50.0')}",
        f"MIN_LEADER_CONFIDENCE={form.get('min_confidence', '0.60')}",
        f"REQUIRED_CONFIRMATIONS={form.get('confirmations', '2')}",
        f"KELLY_FRACTION={form.get('kelly_fraction', '0.25')}",
        "",
        "# Risk",
        f"MAX_DAILY_LOSS_USDC={form.get('max_daily_loss', '200.0')}",
        f"MAX_CONSECUTIVE_LOSSES={form.get('max_consec_losses', '5')}",
        f"MAX_DRAWDOWN_PCT={form.get('max_drawdown', '0.15')}",
        f"MAX_CONCURRENT_POSITIONS={form.get('max_positions', '4')}",
        "",
        "# Mode",
        f"PAPER_TRADING={form.get('paper_trading', 'true')}",
        "",
        "# Data",
        "LOG_TRADES_CSV=true",
        "DATA_DIR=./data",
    ]
    return "\n".join(lines) + "\n"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    """Generate a zip with bot code + personalized .env and send it."""
    env_content = _generate_env(request.form)
    bot_files = _collect_bot_files()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add the personalized .env
        zf.writestr("polymarket-bot/.env", env_content)

        # Add all bot source files
        for archive_path, disk_path in bot_files:
            zf.write(disk_path, f"polymarket-bot/{archive_path}")

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="polymarket-bot.zip",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
