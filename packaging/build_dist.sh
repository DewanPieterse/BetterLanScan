#!/bin/bash
# Step 1 of 3 — build the self-contained app with PyInstaller.
# Output: dist_standalone/BetterLanScan.app  (embeds Python + Qt + pyobjc)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "Runtime venv missing. Run ./setup.sh first." >&2
  exit 1
fi
"$PY" -c "import PyInstaller" 2>/dev/null || "$PY" -m pip install --quiet pyinstaller

cd "$ROOT"
echo "Regenerating icon…"
"$PY" make_icon.py || true

echo "Building self-contained app…"
"$PY" -m PyInstaller packaging/BetterLanScan.spec --noconfirm \
  --distpath dist_standalone --workpath build_pyi

APP="$ROOT/dist_standalone/BetterLanScan.app"
echo "Stripping extended attributes…"
xattr -cr "$APP"

echo ""
echo "Built: $APP"
echo "Next:  packaging/sign_and_notarize.sh"
