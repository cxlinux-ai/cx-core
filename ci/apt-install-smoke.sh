#!/usr/bin/env bash
# Official APT install smoke test (README instructions).
# Usage: apt-install-smoke.sh [ubuntu|debian]
set -euo pipefail

DISTRO="${1:-ubuntu}"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq curl gnupg ca-certificates

install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://repo.cxlinux.com/key.gpg | gpg --dearmor -o /etc/apt/keyrings/cxlinux.gpg
echo "deb [signed-by=/etc/apt/keyrings/cxlinux.gpg] https://repo.cxlinux.com/apt stable main" \
  | tee /etc/apt/sources.list.d/cxlinux.list

apt-get update
apt-get install -y cx-terminal

echo "=== dpkg -l cx-terminal ==="
dpkg -l cx-terminal

echo "=== cx-terminal --version ==="
cx-terminal --version

echo "=== cx-terminal --help (first 25 lines) ==="
cx-terminal --help 2>&1 | head -25

if command -v cx >/dev/null 2>&1; then
  echo "=== cx --version ==="
  cx --version
else
  echo "NOTE: /usr/bin/cx not present (expected until postinst adds update-alternatives)"
fi

echo "=== APT smoke test passed on ${DISTRO} ==="
