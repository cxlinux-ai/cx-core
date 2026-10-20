#!/usr/bin/env bash
# Install a locally built .deb inside debian:12 and smoke-test the CLI.
set -euo pipefail

DEB="${1:?Usage: test-deb-bookworm.sh /path/to/cx-terminal-*.deb}"

if [[ ! -f "$DEB" ]]; then
  echo "Deb not found: $DEB" >&2
  exit 1
fi

DEB="$(realpath "$DEB")"

echo "=== Testing $DEB in debian:12 ==="

docker run --rm \
  -v "$DEB:/tmp/cx-terminal.deb:ro" \
  debian:12 \
  bash -euxo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates
    apt-get install -y /tmp/cx-terminal.deb

    echo "=== cx --version ==="
    cx --version

    echo "=== cx activate --help ==="
    cx activate --help

    echo "=== cx license activate --help ==="
    cx license activate --help

    echo "=== cx license (no key) ==="
    cx license 2>&1 || true

    echo "=== cx activate invalid key (license server) ==="
    set +e
    cx activate CX-PRO-TEST-TEST-TEST-TEST 2>&1
    ACTIVATE_RC=$?
    set -e
    echo "activate exit code: $ACTIVATE_RC"
    if [[ "$ACTIVATE_RC" -eq 0 ]]; then
      echo "Expected non-zero exit for invalid key" >&2
      exit 1
    fi
  '

echo "=== Bookworm deb install smoke test passed ==="
