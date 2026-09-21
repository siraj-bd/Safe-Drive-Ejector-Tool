#!/bin/bash
# SafeEject macOS Installer
# Builds native Menu Bar App and installs LaunchAgent for auto-start

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$DIR"

echo "=========================================="
echo "  SafeEject macOS Installer"
echo "=========================================="

echo "[1/3] Building native Menu Bar app..."
mkdir -p bin .build/cache
swiftc -module-cache-path .build/cache -O ui/SafeEjectMenuBar.swift -o bin/SafeEjectMenuBar
chmod +x bin/SafeEjectMenuBar main.py

echo "[2/3] Configuring LaunchAgent..."
PLIST_SRC="install/macos/com.user.safeeject.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.user.safeeject.plist"

mkdir -p "$HOME/Library/LaunchAgents"

# Update path in plist to actual absolute path of binary
sed "s|/Volumes/backup-software/workplace/safely-disk-ejector-tool/bin/SafeEjectMenuBar|$DIR/bin/SafeEjectMenuBar|g" "$PLIST_SRC" > "$PLIST_DEST"

echo "[3/3] Loading LaunchAgent into launchd..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "SafeEject installed and launched successfully!"
echo "Look for the ⏏ icon in your macOS Menu Bar."
echo ""
echo "To uninstall:"
echo "    launchctl unload $PLIST_DEST"
echo "    rm -f $PLIST_DEST"
echo "=========================================="
