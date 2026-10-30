#!/usr/bin/env bash
# Package a minimal Bookworm .deb containing cx-terminal (+ cx symlink via postinst).
# Use after: cargo build -p cx-terminal --release --locked (on debian:12).
set -euo pipefail

cd "$(dirname "$0")/.."

TAG_NAME="${TAG_NAME:-bookworm-minimal}"
# Debian version must start with a digit.
DEB_VERSION="0.0.0+${TAG_NAME}"
BIN="${1:-target/release/cx-terminal}"

if [[ ! -f "$BIN" ]]; then
  echo "Missing binary: $BIN" >&2
  exit 1
fi

rm -rf pkg/debian-min
mkdir -p pkg/debian-min/DEBIAN pkg/debian-min/usr/bin

install -Dm755 "$BIN" pkg/debian-min/usr/bin/cx-terminal

cat > pkg/debian-min/DEBIAN/control <<EOF
Package: cx-terminal
Version: ${DEB_VERSION}
Architecture: amd64
Maintainer: CX Linux <packages@cxlinux.com>
Section: utils
Priority: optional
Homepage: https://cxlinux.com
Description: CX Terminal CLI (minimal Bookworm build for smoke tests)
EOF

# Bookworm-linked runtime libraries (from ldd on debian:12).
cat >> pkg/debian-min/DEBIAN/control <<'EOF'
Depends: libc6 (>= 2.36), libgcc-s1 (>= 4.2), libgomp1 (>= 10), libssl3 (>= 3.0.0), libstdc++6 (>= 12), zlib1g (>= 1:1.2.0)
EOF

cat > pkg/debian-min/DEBIAN/postinst <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  update-alternatives --install /usr/bin/cx cx /usr/bin/cx-terminal 100
fi
EOF
chmod 0755 pkg/debian-min/DEBIAN/postinst

OUT="cx-terminal-${TAG_NAME}.debian12-minimal.deb"
fakeroot dpkg-deb --build pkg/debian-min "$OUT"
echo "Wrote $OUT"
