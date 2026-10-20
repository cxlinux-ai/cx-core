#!/usr/bin/env bash
# Build cx-terminal .deb on Debian Bookworm (glibc/libssl match target users).
set -euo pipefail

cd "$(dirname "$0")/.."

export CI=yes
export CARGO_TERM_COLOR=always
export TAG_NAME="${TAG_NAME:-bookworm-$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)}"

echo "=== Bookworm deb build (TAG_NAME=$TAG_NAME) ==="

if command -v git >/dev/null 2>&1; then
  git submodule update --init --depth 1 \
    deps/freetype/zlib deps/freetype/libpng deps/freetype/freetype2 2>/dev/null || true
fi

if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "Build environment: ${ID:-unknown} ${VERSION_CODENAME:-}"
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo not found; install Rust toolchain first" >&2
  exit 1
fi

if [[ "${SKIP_VENDOR:-}" != "1" ]]; then
  echo "Vendoring dependencies (--locked)..."
  rm -rf vendor
  mkdir -p .cargo
  # Progress on stderr; TOML source config on stdout (see cargo vendor docs).
  cargo vendor --locked --versioned-dirs > .cargo/config.toml
fi

if [[ "${SKIP_GET_DEPS:-}" != "1" ]]; then
  env CI=yes ./get-deps
fi

git config --global --add safe.directory "$(pwd)" 2>/dev/null || true

if [[ "${MINIMAL_DEB:-}" == "1" ]]; then
  echo "=== Minimal Bookworm deb (cx-terminal CLI only) ==="
  cargo build -p cx-terminal --release --locked
  bash ci/package-deb-bookworm-minimal.sh
  ls -la cx-terminal-*.debian12-minimal.deb
  exit 0
fi

cargo build -p cx-terminal --release --locked
cargo build -p cx-terminal-gui --release --locked
cargo build -p wezterm-mux-server --release --locked
cargo build -p strip-ansi-escapes --release --locked

bash ci/deploy.sh

echo "=== Built packages ==="
ls -la cx-terminal-*.deb cx-terminal-*.tar.xz 2>/dev/null || ls -la cx-terminal-*.deb
