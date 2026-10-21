#!/usr/bin/env bash
# Reproducible ~30s safety demo for CX Linux (Ubuntu 24.04).
# Uses CX_ASK_MOCK_RESPONSE (offline, labeled) — no paid API key.
# Uses an isolated temporary HOME so real ~/.cx audit/history is never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_HOME="$(mktemp -d -t cx-safety-demo-home.XXXXXX)"
export HOME="$DEMO_HOME"
MARKER="${HOME}/.cx/demo-risk-marker"

MOCK_JSON=$(cat <<EOF
{
  "status": "success",
  "source": "mock-offline",
  "message": "[mock-offline] Simulated AI suggestion for demo only.",
  "command": "touch \"${HOME}/.cx/demo-risk-marker\"",
  "undo": "rm -f \"${HOME}/.cx/demo-risk-marker\""
}
EOF
)

export CX_ASK_MOCK_RESPONSE="$MOCK_JSON"

cleanup() {
  rm -rf "$DEMO_HOME"
}
trap cleanup EXIT

echo "=== CX safety demo (offline mock, isolated HOME: $DEMO_HOME) ==="

resolve_cx() {
  if [[ -n "${CX_BIN:-}" ]] && [[ -x "${CX_BIN}" ]]; then
    echo "$CX_BIN"
    return
  fi
  if [[ -x "$ROOT/target/release/cx-terminal" ]]; then
    echo "$ROOT/target/release/cx-terminal"
    return
  fi
  if command -v cx-terminal >/dev/null 2>&1; then
    command -v cx-terminal
    return
  fi
  if command -v cx >/dev/null 2>&1; then
    command -v cx
    return
  fi
  echo "Building cx-terminal from source (first run may take several minutes)..."
  cd "$ROOT"
  export CXX="${CXX:-g++-12}"
  export CC="${CC:-gcc-12}"
  export RUSTFLAGS="${RUSTFLAGS:--C linker=g++-12}"
  rustup run stable cargo build -p cx-terminal --release --locked
  echo "$ROOT/target/release/cx-terminal"
}

CX="$(resolve_cx)"

echo ""
echo "--- 1) Natural language request (default: dry-run only) ---"
"$CX" ask "create a demo risk marker file" </dev/null || true
test ! -f "$MARKER" || { echo "FAIL: marker created without --execute"; exit 1; }

echo ""
echo "--- 2) Execute with --execute -y ---"
"$CX" ask --execute -y "create a demo risk marker file"
test -f "$MARKER" || { echo "FAIL: marker missing after execute"; exit 1; }

echo ""
echo "--- 3) Audit log (last entries) ---"
"$CX" audit --tail 3

echo ""
echo "--- 4) Undo ---"
"$CX" undo --execute -y
test ! -f "$MARKER" || { echo "FAIL: marker still present after undo"; exit 1; }

echo ""
echo "=== Demo complete ==="
