#!/usr/bin/env bash
set -euo pipefail

# -------- Colors for user feedback --------
RED="\033[0;31m"
GREEN="\033[0;32m"
NC="\033[0m"

# -------- Error helper --------
error() {
  echo -e "${RED}ERROR: $*${NC}" >&2
  exit 1
}

echo "🧠 Cortex Linux Installer"

# -------- OS detection (Debian / Ubuntu only) --------
if [[ -r /etc/os-release ]]; then
  source /etc/os-release
  OS_ID=$(printf '%s' "${ID:-}" | tr '[:upper:]' '[:lower:]')
  OS_LIKE=$(printf '%s' "${ID_LIKE:-}" | tr '[:upper:]' '[:lower:]')
else
  error "Cannot detect operating system"
fi

if [[ "$OS_ID" != "ubuntu" && "$OS_ID" != "debian" && ! "$OS_LIKE" =~ debian ]]; then
  error "Unsupported OS: $OS_ID"
fi

# -------- Python version validation (3.10+) --------
command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.10+"

read -r PY_MAJOR PY_MINOR <<< "$(python3 - <<EOF
import sys
print(sys.version_info.major, sys.version_info.minor)
EOF
)"

if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]]; then
  error "Python 3.10+ is required"
fi

# Ensure venv module is available
python3 -c "import venv" 2>/dev/null || \
  error "python3-venv not installed. Run: sudo apt install python3-venv"

echo "Detected: ${PRETTY_NAME%% LTS}, Python ${PY_MAJOR}.${PY_MINOR}"
echo "Installing to ~/.cortex..."

# -------- Virtual environment setup --------
CORTEX_HOME="$HOME/.cortex"
VENV_PATH="$CORTEX_HOME/venv"
mkdir -p "$CORTEX_HOME"

if [[ ! -d "$VENV_PATH" || ! -f "$VENV_PATH/bin/activate" ]]; then
  rm -rf "$VENV_PATH"
  python3 -m venv "$VENV_PATH"
fi

# -------- Install Cortex (PyPI with fallback) --------
"$VENV_PATH/bin/pip" install --upgrade pip

CORTEX_PKG_SPEC="${CORTEX_PKG_SPEC:-cortex-linux==0.1.0}"
CORTEX_PIP_HASH_FILE="${CORTEX_PIP_HASH_FILE:-}"

if [[ -n "$CORTEX_PIP_HASH_FILE" ]]; then
  INSTALL_CMD=("$VENV_PATH/bin/pip" install --require-hashes -r "$CORTEX_PIP_HASH_FILE")
else
  INSTALL_CMD=("$VENV_PATH/bin/pip" install "$CORTEX_PKG_SPEC")
fi

if ! "${INSTALL_CMD[@]}"; then
  command -v git >/dev/null 2>&1 || error "git not available for fallback install"
  CORTEX_REPO_URL="${CORTEX_REPO_URL:-https://github.com/cortexlinux/cortex.git}"
  CORTEX_REPO_BRANCH="${CORTEX_REPO_BRANCH:-main}"
  TMP_DIR=$(mktemp -d)

  git clone --depth 1 --single-branch --branch "$CORTEX_REPO_BRANCH" \
    "$CORTEX_REPO_URL" "$TMP_DIR" || error "git clone failed"

  "$VENV_PATH/bin/pip" install "$TMP_DIR"
  rm -rf "$TMP_DIR"
fi

# -------- Validate cortex binary --------
[[ -x "$VENV_PATH/bin/cortex" ]] || error "cortex binary not found after installation"

# -------- Expose cortex CLI to user PATH --------
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$VENV_PATH/bin/cortex" "$BIN_DIR/cortex" || \
  error "Failed to create cortex symlink"

# Persist PATH update across shells
for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.zshrc"; do
  [[ -f "$rc" ]] || continue
  grep -qE '^\s*export\s+PATH=.*\.local/bin' "$rc" && continue
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
done

# -------- Store supported LLM API keys (multi-provider) --------
ENV_FILE="$CORTEX_HOME/.env"

for key in OPENAI_API_KEY ANTHROPIC_API_KEY KIMI_API_KEY; do
  if [[ -n "${!key:-}" ]]; then
    touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    grep -v "^$key=" "$ENV_FILE" > "${ENV_FILE}.tmp" || true
    mv "${ENV_FILE}.tmp" "$ENV_FILE"
    echo "$key=${!key}" >> "$ENV_FILE"
  fi
done

# -------- Final verification --------
CORTEX_CMD="$BIN_DIR/cortex"
[[ -x "$CORTEX_CMD" ]] || CORTEX_CMD="$VENV_PATH/bin/cortex"

"$CORTEX_CMD" --help >/dev/null 2>&1 || \
  error "cortex installed but failed to run"

echo -e "${GREEN}✅ Installed! Run: cortex --help to get started.${NC}"
