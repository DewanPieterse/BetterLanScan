#!/bin/bash
# Build BetterLanScan.app.
#
# The Python runtime lives in ~/Library/Application Support/BetterLanScan/venv
# (created by setup.sh) — NOT inside the bundle. Reasons:
#   * ~/Documents is TCC-protected, so a GUI-launched app can't read a venv
#     stored next to the project; ~/Library/Application Support is not.
#   * Copying + re-signing the Qt frameworks into the bundle breaks their
#     code signatures, which makes macOS reject the cocoa platform plugin.
# Only the (small, plain-text) source is placed inside the bundle, which an
# app can always read regardless of location.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/dist/BetterLanScan.app"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Runtime venv missing. Run ./setup.sh first." >&2
  exit 1
fi

echo "Cleaning previous build…"
rm -rf "$APP"
RES="$APP/Contents/Resources"
mkdir -p "$APP/Contents/MacOS" "$RES"

echo "Copying source into bundle…"
cp -R "$ROOT/betterlanscan" "$RES/betterlanscan"
cp "$ROOT/app.py" "$RES/app.py"
find "$RES/betterlanscan" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>BetterLanScan</string>
    <key>CFBundleDisplayName</key><string>BetterLanScan</string>
    <key>CFBundleIdentifier</key><string>com.betterlanscan.app</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>BetterLanScan</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>NSLocationUsageDescription</key>
    <string>Location access lets BetterLanScan read nearby Wi-Fi network names (SSIDs) and signal details.</string>
    <key>NSLocationWhenInUseUsageDescription</key>
    <string>Location access lets BetterLanScan read nearby Wi-Fi network names (SSIDs) and signal details.</string>
</dict>
</plist>
PLIST

# Launcher references the external runtime; resolves $HOME at runtime.
cat > "$APP/Contents/MacOS/BetterLanScan" <<'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"
export PYTHONNOUSERSITE=1
if [ ! -x "$VENV/bin/python" ]; then
  osascript -e 'display alert "BetterLanScan" message "Runtime not installed. Run setup.sh in the project folder first."' >/dev/null 2>&1
  exit 1
fi
exec "$VENV/bin/python" "$DIR/app.py" "$@"
LAUNCHER
chmod +x "$APP/Contents/MacOS/BetterLanScan"

if [ -f "$ROOT/assets/AppIcon.icns" ]; then
  cp "$ROOT/assets/AppIcon.icns" "$RES/AppIcon.icns"
fi

# Sign ONLY the bundle wrapper (no Qt frameworks inside → signatures stay intact).
codesign --force --sign - "$APP" 2>/dev/null || true

echo ""
echo "Built: $APP"
echo "Launch:  open \"$APP\"   (or double-click in Finder)"
