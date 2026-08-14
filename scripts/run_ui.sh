#!/usr/bin/env bash
# One command to rule them all: make the virtual camera OBS-ready, then launch
# the app. First run may ask for your password once (to configure the kernel
# loopback); after that it's automatic and needs no sudo, even across reboots.
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Ensure the virtual camera exists and is capture-only (OBS-compatible).
if ! ./scripts/setup_camera.sh; then
    rc=$?
    if [[ $rc -eq 2 ]]; then
        echo
        echo ">> Please close OBS (or whatever is using the virtual camera) and"
        echo ">> run ./scripts/run_ui.sh again."
    fi
    exit $rc
fi

# 2. Launch the control panel + pipeline.
PORT="${1:-8137}"
echo
echo ">> Control panel: http://localhost:${PORT}"
echo ">> In OBS: Sources -> Video Capture Device (V4L2) -> 'Broadcast Virtual Camera'"
echo
exec .venv/bin/python -m ui --port "${PORT}"
