#!/usr/bin/env bash
# Launch the NVBroadcast tray applet (the desktop app).
# Uses the SYSTEM python3 (needs gi/Gtk/AppIndicator, not the venv).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 app/tray.py "$@"
