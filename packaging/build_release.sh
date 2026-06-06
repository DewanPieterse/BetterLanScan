#!/bin/bash
# Build the GitHub-release DMG: ad-hoc-signed, self-contained BetterLanScan.app
# with custom drag-to-Applications installer background.
#
# Ad-hoc signing (not Developer ID) means Gatekeeper shows the normal
# "unidentified developer" prompt rather than "app is damaged" — good enough
# for free GitHub/Homebrew distribution. For zero warnings you'd notarize
# instead (see packaging/sign_and_notarize.sh).
#
# Output: dist_release/BetterLanScan-<version>.dmg  (+ prints sha256 for the Cask)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-1.0.0}"
SRC_APP="$ROOT/dist_standalone/BetterLanScan.app"
ENT="$ROOT/packaging/entitlements.plist"
OUT="$ROOT/dist_release/BetterLanScan-${VERSION}.dmg"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"
DMGBUILD="$VENV/bin/dmgbuild"

if [ ! -d "$SRC_APP" ]; then
  echo "App not built. Run packaging/build_dist.sh first." >&2
  exit 1
fi

if [ ! -x "$DMGBUILD" ]; then
  echo "Installing dmgbuild…"
  "$VENV/bin/pip" install --quiet dmgbuild
fi

WORK="$(mktemp -d /tmp/bls_rel.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/BetterLanScan.app"

# Stage outside iCloud-synced ~/Documents (strips FinderInfo xattrs).
ditto --norsrc --noextattr --noqtn "$SRC_APP" "$APP"

echo "▸ Ad-hoc signing (inside-out, hardened runtime)…"
find "$APP" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 \
  | while IFS= read -r -d '' f; do codesign --force -s - "$f"; done
find "$APP" -type d -name "*.framework" -print0 \
  | while IFS= read -r -d '' fw; do codesign --force -s - "$fw"; done
codesign --force --options runtime --entitlements "$ENT" -s - \
  "$APP/Contents/MacOS/BetterLanScan"
codesign --force --options runtime --entitlements "$ENT" -s - "$APP"
codesign --verify --deep --strict "$APP"

# Point dmg_settings at the staged (signed) app
export BLS_ROOT="$ROOT"

# Temporarily swap in the signed app so dmgbuild picks it up
ORIG_APP="$ROOT/dist_standalone/BetterLanScan.app"
BACKUP="$WORK/BetterLanScan_orig.app"
ditto "$ORIG_APP" "$BACKUP"
ditto "$APP" "$ORIG_APP"

echo "▸ Building installer DMG…"
mkdir -p "$ROOT/dist_release"
rm -f "$OUT"
"$DMGBUILD" -s "$ROOT/packaging/dmg_settings.py" \
  "BetterLanScan $VERSION" "$OUT"

# Restore original
rm -rf "$ORIG_APP"; ditto "$BACKUP" "$ORIG_APP"

echo "▸ Ad-hoc signing DMG…"
codesign --force -s - "$OUT"

SHA=$(shasum -a 256 "$OUT" | awk '{print $1}')
echo ""
echo "Built:  $OUT"
echo "size:   $(du -h "$OUT" | cut -f1)"
echo "sha256: $SHA"
echo ""
echo "Put that sha256 into the Cask (Casks/betterlanscan.rb)."
