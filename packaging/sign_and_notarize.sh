#!/bin/bash
# Step 2 & 3 — Developer ID sign (hardened runtime) + notarize + staple,
# producing a notarized .dmg ready to ship.
#
# IMPORTANT: this project lives in iCloud-synced ~/Documents, whose sync daemon
# constantly re-stamps com.apple.FinderInfo onto framework directories — which
# codesign rejects. So we first copy the app into a NON-synced temp workspace
# with `ditto --noextattr` (strips all that metadata) and sign there.
#
# PREREQS (one-time, on YOUR machine with YOUR paid Apple Developer account):
#   1. Create a "Developer ID Application" certificate (Xcode ▸ Settings ▸
#      Accounts, or developer.apple.com). Find its exact name with:
#        security find-identity -v -p codesigning
#   2. Store a notarytool credential profile once:
#        xcrun notarytool store-credentials BLS-NOTARY \
#          --apple-id "you@example.com" --team-id "TEAMID" \
#          --password "app-specific-password"   # appleid.apple.com ▸ App-Specific Passwords
#
# USAGE:
#   export DEV_ID="Developer ID Application: Your Name (TEAMID)"
#   export NOTARY_PROFILE="BLS-NOTARY"
#   packaging/sign_and_notarize.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_APP="$ROOT/dist_standalone/BetterLanScan.app"
ENT="$ROOT/packaging/entitlements.plist"
OUT_DMG="$ROOT/dist_standalone/BetterLanScan-1.0.0.dmg"

: "${DEV_ID:?Set DEV_ID to your 'Developer ID Application: Name (TEAMID)' identity}"
: "${NOTARY_PROFILE:=}"

if [ ! -d "$SRC_APP" ]; then
  echo "App not found. Run packaging/build_dist.sh first." >&2
  exit 1
fi

WORK="$(mktemp -d /tmp/bls_sign.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/BetterLanScan.app"
DMG="$WORK/BetterLanScan-1.0.0.dmg"

echo "▸ Staging app into non-synced workspace (stripping xattrs)…"
ditto --norsrc --noextattr --noqtn "$SRC_APP" "$APP"

sign_one() { codesign --force --options runtime --timestamp -s "$DEV_ID" "$1"; }

echo "▸ Signing nested code (inside-out, hardened runtime)…"
find "$APP" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 \
  | while IFS= read -r -d '' f; do sign_one "$f"; done
find "$APP" -type d -name "*.framework" -print0 \
  | while IFS= read -r -d '' fw; do sign_one "$fw"; done
find "$APP/Contents" -type f -perm -111 ! -name "*.py" -print0 2>/dev/null \
  | while IFS= read -r -d '' bin; do
      file "$bin" | grep -q "Mach-O" && sign_one "$bin" || true
    done

echo "▸ Signing main executable + app with entitlements…"
codesign --force --options runtime --timestamp \
  --entitlements "$ENT" -s "$DEV_ID" "$APP/Contents/MacOS/BetterLanScan"
codesign --force --options runtime --timestamp \
  --entitlements "$ENT" -s "$DEV_ID" "$APP"

echo "▸ Verifying signature…"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "▸ Building DMG…"
STAGE="$WORK/dmg"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/BetterLanScan.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "BetterLanScan" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp -s "$DEV_ID" "$DMG"

if [ -z "$NOTARY_PROFILE" ]; then
  cp "$DMG" "$OUT_DMG"
  echo ""
  echo "⚠️  NOTARY_PROFILE not set — signed but NOT notarized."
  echo "    Notarize manually, then staple:"
  echo "      xcrun notarytool submit \"$OUT_DMG\" --keychain-profile <profile> --wait"
  echo "      xcrun stapler staple \"$OUT_DMG\""
  echo "Signed DMG: $OUT_DMG"
  exit 0
fi

echo "▸ Submitting to Apple notary service (a few minutes)…"
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait

echo "▸ Stapling ticket to app, then rebuilding the shipped DMG…"
xcrun stapler staple "$APP"
rm -f "$DMG"
rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/BetterLanScan.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "BetterLanScan" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp -s "$DEV_ID" "$DMG"
xcrun stapler staple "$DMG"

cp "$DMG" "$OUT_DMG"
echo ""
echo "✅  Notarized & stapled.  Ship this:"
echo "    $OUT_DMG"
echo "Verify on any Mac:  spctl -a -vvv --type open --context context:primary-signature \"$OUT_DMG\""
