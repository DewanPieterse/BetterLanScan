#!/bin/bash
# Dev runner — launches the app directly from source using the runtime venv.
# Run this from a normal Terminal window (it must be in your GUI session).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/Library/Application Support/BetterLanScan/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Runtime not installed. Run ./setup.sh first." >&2
  exit 1
fi
exec "$VENV/bin/python" "$ROOT/app.py" "$@"
