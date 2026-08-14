#!/usr/bin/env bash
# Launch the NVBroadcast desktop app (Qt window + system tray).
# Runs in the venv (has PySide6 + torch + cv2). Camera setup is handled inside
# the app (graphical password prompt via pkexec if a reload is ever needed).
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m app "$@"
