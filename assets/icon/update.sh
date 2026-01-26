#!/bin/bash
# CX Terminal: This script updates the icon files from the SVG source.
# It assumes that the svg file is square.
set -x
cd $(git rev-parse --show-toplevel)/assets/icon

# CX Terminal: Use our custom icon
src=cx-terminal-icon.svg

conv_opts="-colors 256 -background none -density 300"

# the linux icon
convert $conv_opts -resize "!128x128" "$src" ../icon/terminal.png

# Generate iconset for macOS
ICONSET="cx-terminal.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

for dim in 16 32 128 256 512 ; do
  # convert is the imagemagick convert utility
  convert $conv_opts -resize "!${dim}x${dim}" "$src" "$ICONSET/icon_${dim}x${dim}.png"
  # @2x versions (double resolution)
  convert $conv_opts -resize "!$((dim*2))x$((dim*2))" "$src" "$ICONSET/icon_${dim}x${dim}@2x.png"
done

# Create .icns file using macOS iconutil (preferred) or png2icns as fallback
if command -v iconutil &> /dev/null; then
  # macOS native method
  iconutil -c icns -o cx-terminal.icns "$ICONSET"
elif command -v png2icns &> /dev/null; then
  # Linux fallback (libicns-utils)
  for dim in 16 32 128 256 512 1024 ; do
    convert $conv_opts -resize "!${dim}x${dim}" "$src" "icon_${dim}px.png"
  done
  png2icns cx-terminal.icns icon_*px.png
  rm -f icon_*px.png
else
  echo "Warning: Neither iconutil nor png2icns found. Cannot create .icns file."
fi

# Copy to app bundle
cp cx-terminal.icns "../macos/CX Terminal.app/Contents/Resources/"

# The Windows icon
convert $conv_opts -define icon:auto-resize=256,128,96,64,48,32,16 $src ../windows/terminal.ico 2>/dev/null || true

echo "Icon generation complete!"

