import datetime
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

# Use absolute path for history file
HISTORY_FILE = pathlib.Path.home() / ".cortex" / "security_history.json"

# Command constants (full paths for security - avoids PATH manipulation attacks)
SYSTEMCTL_CMD = "/usr/bin/systemctl"
UFW_CMD = "/usr/sbin/ufw"
SUDO_CMD = "/usr/bin/sudo"
SSH_SERVICE = "ssh"


def load_history():
    """Load past execution history"""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def save_history(score, status, details):
    """Save execution result to history"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    history = load_history()
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "score": score,
        "status": status,
        "details": details
    }
    history.append(record)
    history = history[-10:]

    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)

    return history


def show_trend(history):
    """Show historical trend (Trend Tracking)"""
    print("\n=== 📊 Historical Trend Analysis ===")
    if not history:
        print("    No historical data available yet.")
        return

    scores = [h["score"] for h in history]
    avg_score = sum(scores) / len(scores)
    last_score = scores[-1]

    print(f"    History Count: {len(history)} runs")
    print(f"    Average Score: {avg_score:.1f}")
    print(f"    Last Run Score: {last_score}")

    if len(scores) > 1:
        prev_score = scores[-2]
        diff = last_score - prev_score
        if diff > 0:
            print(f"    Trend: 📈 Improved by {diff} points since previous run")
        elif diff < 0:
            print(f"    Trend: 📉 Dropped by {abs(diff)} points since previous run")
        else:
            print("    Trend: ➡️ Stable")


def fix_firewall():
    """Enable UFW firewall (Automated Fix).

    Uses sudo -n (non-interactive) to avoid password prompts hanging the script.
    """
    print("\n    [Fixing] Enabling UFW Firewall...")

    if not shutil.which("ufw") and not os.path.exists(UFW_CMD):
        print("    -> ⚠️ UFW is not installed. Cannot enable.")
        return False

    try:
        subprocess.run(
            [SUDO_CMD, "-n", UFW_CMD, "--force", "enable"],
            check=True,
            timeout=30,
            capture_output=True,
            text=True
        )
        print("    -> ✅ Success: Firewall enabled.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"    -> ❌ Failed to enable firewall: {e.stderr or e}")
        return False
    except subprocess.TimeoutExpired:
        print("    -> ❌ Command timed out.")
        return False


def fix_ssh_config(config_path):
    """Disable SSH root login (Automated Fix).

    Uses atomic write pattern to prevent partial file corruption.
    Creates a backup before making changes.
    """
    print(f"\n    [Fixing] Disabling Root Login in {config_path}...")

    if not os.path.exists(config_path):
        print(f"    -> ⚠️ Config file not found: {config_path}")
        return False

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = f"{config_path}.bak.{timestamp}"

    try:
        shutil.copy2(config_path, backup_path)
        print(f"    -> Backup created at: {backup_path}")
    except PermissionError:
        print("    -> ❌ Failed to create backup (Permission denied). Need sudo?")
        return False
    except OSError as e:
        print(f"    -> ❌ Failed to create backup: {e}")
        return False

    try:
        new_lines = []
        with open(config_path) as f:
            lines = f.readlines()

        fixed = False
        for line in lines:
            if line.strip().startswith("PermitRootLogin") and "yes" in line:
                new_lines.append(f"# {line.strip()} (Disabled by Auto-Fix)\n")
                new_lines.append("PermitRootLogin no\n")
                fixed = True
            else:
                new_lines.append(line)

        if fixed:
            # Atomic write using temporary file
            dir_path = os.path.dirname(config_path)
            with tempfile.NamedTemporaryFile(
                mode='w', dir=dir_path, delete=False, suffix='.tmp'
            ) as tmp_file:
                tmp_file.writelines(new_lines)
                tmp_path = tmp_file.name

            # Atomic replace
            os.replace(tmp_path, config_path)
            print("    -> ✅ Success: sshd_config updated.")

            print("    -> Restarting sshd service...")
            res = subprocess.run(
                [SUDO_CMD, "-n", SYSTEMCTL_CMD, "restart", SSH_SERVICE],
                capture_output=True,
                text=True,
                timeout=30
            )
            if res.returncode != 0:
                print(f"    -> ⚠️ SSH restart failed: {res.stderr}")
                print("    -> Please restart SSH service manually.")
            return True
        else:
            print("    -> No changes needed.")
            return True

    except PermissionError:
        print("    -> ❌ Permission denied. Try running with sudo.")
        return False
    except OSError as e:
        print(f"    -> ❌ Error during fix: {e}")
        return False


def _check_firewall_status():
    """Helper to check firewall status."""
    print("\n[1] Checking Firewall (UFW)...")
    try:
        print(f"    Running: {SYSTEMCTL_CMD} is-active ufw")
        res = subprocess.run(
            [SYSTEMCTL_CMD, "is-active", "ufw"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = res.stdout.strip()
        print(f"    Output: '{output}'")

        if res.returncode == 0 and output == "active":
            print("    -> JUDGEMENT: Firewall is ACTIVE (Score: 100)")
            return True
        else:
            print("    -> JUDGEMENT: Firewall is INACTIVE (Score: 0)")
            return False

    except FileNotFoundError:
        print("    -> ERROR: 'systemctl' command not found.")
    except subprocess.TimeoutExpired:
        print("    -> ERROR: Command timed out.")
    except OSError as e:
        print(f"    -> ERROR: {e}")
    return False


def _check_ssh_status(ssh_config):
    """Helper to check SSH status."""
    print("\n[2] Checking SSH Configuration...")
    score_penalty = 0
    needs_fix = False

    if os.path.exists(ssh_config):
        print(f"    File found: {ssh_config}")
        try:
            with open(ssh_config) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "PermitRootLogin" and parts[1] == "yes":
                        print(f"    -> FOUND RISKY LINE: {line.strip()}")
                        score_penalty = 50
                        needs_fix = True
                        break

                if not needs_fix:
                    print("    -> No 'PermitRootLogin yes' found (Safe)")

        except PermissionError:
            print("    -> ERROR: Permission denied. Try running with 'sudo'.")
    else:
        print(f"    -> WARNING: {ssh_config} does not exist.")

    return score_penalty, needs_fix


def verify_security_logic():
    print("=== Ubuntu Security Logic Verification ===")

    ufw_active = _check_firewall_status()
    ssh_config = "/etc/ssh/sshd_config"
    ssh_penalty, ssh_needs_fix = _check_ssh_status(ssh_config)

    # Final Report
    print("\n=== Summary ===")
    final_score = 100
    if not ufw_active:
        final_score = 0
    final_score -= ssh_penalty
    final_score = max(0, final_score)

    status = "OK"
    if final_score < 50:
        status = "CRITICAL"
    elif final_score < 100:
        status = "WARNING"

    print(f"Current Score: {final_score}")
    print(f"Status: {status}")

    # History
    print("\n... Saving history ...")
    details = []
    ufw_needs_fix = not ufw_active
    if ufw_needs_fix:
        details.append("Firewall Inactive")
    if ssh_needs_fix:
        details.append("Root SSH Allowed")

    history = save_history(final_score, status, ", ".join(details))
    show_trend(history)

    # Automated Fixes
    if ufw_needs_fix or ssh_needs_fix:
        print("\n=== 🛠️ Automated Fixes Available ===")
        print("Issues detected that can be automatically fixed.")
        user_input = input("Do you want to apply fixes now? (y/n): ").strip().lower()

        if user_input == 'y':
            if ufw_needs_fix:
                fix_firewall()
            if ssh_needs_fix:
                fix_ssh_config(ssh_config)
            print("\n✅ Fixes attempt complete. Please re-run script to verify.")
        else:
            print("Skipping fixes.")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("NOTE: This script works best with 'sudo' for fixing issues.")
    verify_security_logic()