#!/bin/bash
# Build .deb package for cortex-linux
# Usage: ./scripts/build-deb.sh [--no-sign] [--install-deps] [--clean]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Build dependencies (single source of truth)
DEB_BUILD_DEPS="dpkg-dev debhelper dh-virtualenv python3-dev python3-venv python3-pip python3-setuptools"

# Use sudo only if not root (for CI containers)
if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
else
    SUDO="sudo"
fi

install_deps() {
    echo "Installing build dependencies..."
    $SUDO apt-get update
    $SUDO apt-get install -y $DEB_BUILD_DEPS
    echo "Debian build dependencies installed"
    return 0
}

clean_build() {
    echo "Cleaning debian build artifacts..."
    rm -rf debian/cortex-linux
    rm -rf debian/.debhelper
    rm -f debian/debhelper-build-stamp
    rm -f debian/files
    rm -f debian/*.substvars
    rm -f dist/*.deb dist/*.buildinfo dist/*.changes
    echo "Cleaned"
    return 0
}

check_deps() {
    local missing=0
    for cmd in dpkg-buildpackage dh_virtualenv; do
        if ! command -v "$cmd" &> /dev/null; then
            echo "Error: $cmd is not installed" >&2
            missing=1
        fi
    done
    if [[ $missing -eq 1 ]]; then
        echo "" >&2
        echo "Install dependencies with: $0 --install-deps" >&2
        exit 1
    fi
    return 0
}

# Parse arguments
NO_SIGN=""
ACTION="build"
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-sign)
            NO_SIGN="-us -uc"
            shift
            ;;
        --install-deps)
            ACTION="install-deps"
            shift
            ;;
        --clean)
            ACTION="clean"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--no-sign] [--install-deps] [--clean]"
            exit 1
            ;;
    esac
done

# Handle actions
case $ACTION in
    install-deps)
        install_deps
        exit 0
        ;;
    clean)
        clean_build
        exit 0
        ;;
    build)
        # Continue to build logic below
        ;;
    *)
        echo "Unknown action: $ACTION" >&2
        exit 1
        ;;
esac

echo "Checking build dependencies..."
check_deps

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf debian/cortex-linux
rm -rf debian/.debhelper
rm -f debian/debhelper-build-stamp
rm -f debian/files
rm -f debian/*.substvars

# Get version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/' || true)
if [[ -z "${VERSION:-}" ]]; then
    echo "Error: Could not extract version from pyproject.toml" >&2
    exit 1
fi
echo "Building cortex-linux version $VERSION"

# Update changelog version if needed
CHANGELOG_VERSION=$(head -1 debian/changelog | sed 's/cortex-linux (\(.*\)).*/\1/')
if [[ "$VERSION" != "$CHANGELOG_VERSION" ]]; then
    echo "Updating debian/changelog to version $VERSION"
    sed -i "s/cortex-linux ($CHANGELOG_VERSION)/cortex-linux ($VERSION)/" debian/changelog
fi

# Build the package
echo "Building .deb package..."
dpkg-buildpackage -b $NO_SIGN

# Move built packages to dist/
echo "Moving packages to dist/..."
mkdir -p dist
mv ../*.deb dist/ 2>/dev/null || true
mv ../*.buildinfo dist/ 2>/dev/null || true
mv ../*.changes dist/ 2>/dev/null || true

echo ""
echo "Build complete! Packages:"
ls -la dist/*.deb 2>/dev/null || echo "No .deb files found"

echo ""
echo "To install: sudo dpkg -i dist/cortex-linux_${VERSION}_*.deb"
echo "To fix deps: sudo apt install -f"
