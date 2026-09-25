#!/bin/bash
# ==============================================================================
# Safe Drive Ejector Tool - macOS Standalone Build & DMG Packaging Script
# Generates a standalone, dependency-free Safe Drive Ejector.app and .dmg
# ==============================================================================

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

BUILD_DIR="$DIR/.build"
DIST_DIR="$DIR/dist"
APP_NAME="Safe Drive Ejector"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
ARCH="$(uname -m)"
DMG_NAME="${DMG_NAME:-SafeDriveEjector-1.0.0-macOS-${ARCH}.dmg}"
DMG_OUTPUT="$DIST_DIR/$DMG_NAME"

echo "======================================================="
echo "   Building $APP_NAME for macOS ($ARCH Standalone)"
echo "======================================================="

# 1. Clean previous build & dist artifacts
echo "[1/6] Cleaning build directories..."
rm -rf "$BUILD_DIR/work" "$BUILD_DIR/dist" "$APP_BUNDLE" "$DMG_OUTPUT"
mkdir -p "$BUILD_DIR/cache" "$BUILD_DIR/pyinstaller_config" "$DIST_DIR"

# 2. Build standalone Python engine (safeeject_core)
echo "[2/6] Freezing Python core engine with PyInstaller..."
if command -v pyinstaller >/dev/null 2>&1; then
    PYINSTALLER_BIN="pyinstaller"
elif [ -f ".venv/bin/pyinstaller" ]; then
    PYINSTALLER_BIN=".venv/bin/pyinstaller"
else
    echo "ERROR: PyInstaller not found in PATH or .venv/bin/pyinstaller"
    exit 1
fi

PYINSTALLER_CONFIG_DIR="$BUILD_DIR/pyinstaller_config" \
"$PYINSTALLER_BIN" \
    --clean \
    --noconfirm \
    --onefile \
    --name safeeject_core \
    --workpath "$BUILD_DIR/work" \
    --distpath "$BUILD_DIR/dist" \
    --paths . \
    --collect-submodules core \
    --collect-submodules platform_adapters \
    --collect-submodules ui \
    main.py

chmod +x "$BUILD_DIR/dist/safeeject_core"

# 3. Compile native Swift Menu Bar binary
echo "[3/6] Compiling native Swift Menu Bar application..."
swiftc -module-cache-path "$BUILD_DIR/cache" -O ui/SafeEjectMenuBar.swift -o "$BUILD_DIR/SafeEjectMenuBar"
chmod +x "$BUILD_DIR/SafeEjectMenuBar"

# 4. Construct Safe Drive Ejector.app bundle structure
echo "[4/6] Constructing .app bundle structure..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy binaries
cp "$BUILD_DIR/SafeEjectMenuBar" "$APP_BUNDLE/Contents/MacOS/"
cp "$BUILD_DIR/dist/safeeject_core" "$APP_BUNDLE/Contents/MacOS/"

# Copy WebKit HTML UI resource
cp "ui/components/SafeDriveEjectorCard.html" "$APP_BUNDLE/Contents/Resources/"

# Generate Info.plist
cat << 'EOF' > "$APP_BUNDLE/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>SafeEjectMenuBar</string>
    <key>CFBundleIdentifier</key>
    <string>com.user.safedriveejector</string>
    <key>CFBundleName</key>
    <string>Safe Drive Ejector</string>
    <key>CFBundleDisplayName</key>
    <string>Safe Drive Ejector</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>
</plist>
EOF

# Ensure execute permissions on bundle executables
chmod +x "$APP_BUNDLE/Contents/MacOS/SafeEjectMenuBar"
chmod +x "$APP_BUNDLE/Contents/MacOS/safeeject_core"

# 5. Verify App Bundle Integrity
echo "[5/6] Verifying app bundle contents..."
test -f "$APP_BUNDLE/Contents/Info.plist"
test -x "$APP_BUNDLE/Contents/MacOS/SafeEjectMenuBar"
test -x "$APP_BUNDLE/Contents/MacOS/safeeject_core"
test -f "$APP_BUNDLE/Contents/Resources/SafeDriveEjectorCard.html"

# 6. Package Drag-and-Drop DMG
echo "[6/6] Packaging into $DMG_NAME..."
DMG_STAGE="$BUILD_DIR/dmg_stage"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"

cp -R "$APP_BUNDLE" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDZO \
    "$DMG_OUTPUT"

rm -rf "$DMG_STAGE"

echo ""
echo "======================================================="
echo "BUILD & PACKAGING SUCCESSFUL!"
echo "App Bundle: $APP_BUNDLE"
echo "DMG Image:  $DMG_OUTPUT"
echo "======================================================="
