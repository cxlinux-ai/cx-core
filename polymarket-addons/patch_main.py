#!/usr/bin/env python3
"""
Patch script: Adds addon module integration to an existing main.py.

Usage:
    cd ~/Desktop/polymarket-bot
    python patch_main.py

This adds ~15 lines to your existing main.py to wire in the Arb Scanner,
Whale Tracker, and AI Event Trader alongside your existing 15-min crypto strategy.
"""

import re
import shutil
import sys
from pathlib import Path

MAIN_PY = Path("src/main.py")

# Lines to add for imports (after the last existing import block)
IMPORT_BLOCK = """
# CX Terminal: Addon modules — arb scanner, whale tracker, event trader
from src.addons import AddonRunner
"""

# Lines to add in __init__ (after telegram init)
INIT_BLOCK = """
        # CX Terminal: Initialize addon modules
        self._addons = AddonRunner(
            data_dir=self._settings.data.data_dir if hasattr(self._settings, 'data') else "data",
            paper_trading=self._settings.paper_trading,
        )
"""

# Lines to add in run() / start area (creates task alongside existing ones)
RUN_BLOCK = """
        # CX Terminal: Start addon modules
        addon_tasks = await self._addons.start()
        tasks.extend(addon_tasks) if hasattr(tasks, 'extend') else None
"""

# Lines to add in shutdown()
SHUTDOWN_BLOCK = """
        # CX Terminal: Stop addon modules
        await self._addons.stop()
"""

# Lines to add in heartbeat
HEARTBEAT_BLOCK = """
                # CX Terminal: Addon stats
                addon_summary = self._addons.summary()
                logger.info("Addon stats:\\n%s", addon_summary)
"""


def main():
    if not MAIN_PY.exists():
        print(f"ERROR: {MAIN_PY} not found. Run from your bot project root.")
        sys.exit(1)

    # Backup
    backup = MAIN_PY.with_suffix(".py.bak")
    shutil.copy2(MAIN_PY, backup)
    print(f"Backed up to {backup}")

    content = MAIN_PY.read_text()

    # Check if already patched
    if "AddonRunner" in content:
        print("main.py already contains AddonRunner. Skipping patch.")
        sys.exit(0)

    changes = 0

    # 1. Add import after the last 'from src.' import line
    lines = content.split("\n")
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from src.") or line.startswith("from config."):
            last_import_idx = i
    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, IMPORT_BLOCK.strip())
        changes += 1
        print(f"  Added addon import after line {last_import_idx + 1}")
    else:
        print("  WARNING: Could not find import block. Add manually:")
        print(IMPORT_BLOCK)

    content = "\n".join(lines)

    # 2. Add init block after self._telegram line
    telegram_pattern = r"(self\._telegram\s*=\s*TelegramBot\([^)]*\))"
    match = re.search(telegram_pattern, content, re.DOTALL)
    if match:
        insert_pos = match.end()
        # Find end of that line
        next_newline = content.index("\n", insert_pos)
        content = content[:next_newline] + "\n" + INIT_BLOCK.rstrip() + content[next_newline:]
        changes += 1
        print("  Added addon init after TelegramBot initialization")
    else:
        print("  WARNING: Could not find TelegramBot init. Add manually:")
        print(INIT_BLOCK)

    # 3. Add addon start in the run/start method
    # Look for the pattern where tasks are created
    if "create_task" in content and "redeemer" in content.lower():
        # Find a good insertion point after the last create_task in run()
        task_pattern = r"(asyncio\.create_task\(self\._telegram\.start\(\)[^)]*\))"
        match = re.search(task_pattern, content)
        if match:
            insert_pos = match.end()
            # Find end of that statement (next line ending with ])
            # Actually just find the next line that has ]
            after = content[insert_pos:]
            bracket_idx = after.find("]")
            if bracket_idx >= 0:
                abs_pos = insert_pos + bracket_idx
                content = content[:abs_pos] + "\n" + RUN_BLOCK.rstrip() + "\n        " + content[abs_pos:]
                changes += 1
                print("  Added addon start in run() method")
            else:
                print("  WARNING: Could not find task list end. Add addon_tasks manually.")
        else:
            print("  WARNING: Could not find telegram create_task. Add addon start manually.")
    else:
        print("  WARNING: Could not find run method. Add manually:")
        print(RUN_BLOCK)

    # 4. Add shutdown in shutdown method
    shutdown_pattern = r"(async def shutdown\(self\)[^:]*:.*?logger\.info.*?[Ss]hut)"
    match = re.search(shutdown_pattern, content, re.DOTALL)
    if match:
        # Insert at the beginning of shutdown, after the first logger line
        shutdown_start = match.start()
        # Find first logger.info in shutdown
        after_shutdown = content[shutdown_start:]
        first_logger = after_shutdown.find("logger.info")
        if first_logger >= 0:
            # Find end of that logger line
            line_end = after_shutdown.index("\n", first_logger)
            abs_pos = shutdown_start + line_end
            content = content[:abs_pos] + "\n" + SHUTDOWN_BLOCK.rstrip() + content[abs_pos:]
            changes += 1
            print("  Added addon stop in shutdown()")
    else:
        print("  WARNING: Could not find shutdown method. Add manually:")
        print(SHUTDOWN_BLOCK)

    # Write back
    MAIN_PY.write_text(content)
    print(f"\nPatched {MAIN_PY} with {changes} changes.")
    print(f"Backup saved to {backup}")
    print("\nTo wire up Telegram notifications, add this line after addon init:")
    print("        self._addons._send_telegram = self._telegram.send_message")
    print("\nDone! Test with: python -m src.main")


if __name__ == "__main__":
    main()
