#!/bin/bash
# One-shot setup: create the runtime, build the icon, build the .app bundle.
#
# The Python runtime is installed to ~/Library/Application Support so that the
# GUI-launched app can read it (the project folder under ~/Documents is
# TCC-protected and unreadable to a sandboxed GUI app).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"

# Pick a Python 3.11–3.13 (PySide6 wheels; 3.14 not yet supported).
PYBIN=""
for c in python3.13 python3.12 python3.11; do
  if command -v "$c" >/dev/null 2>&1; then PYBIN="$c"; break; fi
done
if [ -z "$PYBIN" ]; then
  echo "Need Python 3.11–3.13 (e.g. 'brew install python@3.13')." >&2
  exit 1
fi
echo "Using $PYBIN"

echo "Creating runtime venv → $VENV"
mkdir -p "$(dirname "$VENV")"
"$PYBIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
echo "Installing dependencies (PySide6 + pyobjc)…"
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements.txt"

echo "Generating app icon…"
"$VENV/bin/python" "$ROOT/make_icon.py" || echo "  (icon step skipped)"

echo "Building BetterLanScan.app…"
bash "$ROOT/build_app.sh"

echo ""
echo "✅  Done.  Launch the app:"
echo "    open \"$ROOT/dist/BetterLanScan.app\""
echo ""
echo "On first launch, grant Location access when prompted so Wi-Fi scans can"
echo "show network names (System Settings ▸ Privacy & Security ▸ Location)."
