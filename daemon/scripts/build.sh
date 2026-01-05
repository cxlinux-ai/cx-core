#!/bin/bash
# Build script for cortexd daemon
# Usage: ./daemon/scripts/build.sh [Release|Debug]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_TYPE="${1:-Release}"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "=== Building cortexd ==="
echo "Build Type: $BUILD_TYPE"
echo "Build Directory: $BUILD_DIR"

# Check dependencies
echo "Checking dependencies..."
which cmake > /dev/null || {
    echo "Error: cmake not found. Install with: sudo apt install cmake"
    exit 1
}

# Check for required libraries
pkg-config --exists systemd || {
    echo "Error: systemd-dev not found. Install with: sudo apt install libsystemd-dev"
    exit 1
}

pkg-config --exists openssl || {
    echo "Error: OpenSSL not found. Install with: sudo apt install libssl-dev"
    exit 1
}

pkg-config --exists sqlite3 || {
    echo "Error: SQLite3 not found. Install with: sudo apt install libsqlite3-dev"
    exit 1
}

pkg-config --exists uuid || {
    echo "Error: uuid not found. Install with: sudo apt install uuid-dev"
    exit 1
}

# Create build directory
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Run CMake
echo "Running CMake..."
cmake -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
       -DCMAKE_CXX_FLAGS="-std=c++17 -Wall -Wextra -Wpedantic" \
       "$SCRIPT_DIR"

# Build
echo "Building..."
make -j"$(nproc)"

echo ""
echo "✓ Build successful!"
echo "Binary: $BUILD_DIR/cortexd"
echo ""
echo "To install: sudo ./daemon/scripts/install.sh"