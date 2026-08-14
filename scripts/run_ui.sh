#!/usr/bin/env bash
# Launch the web control panel. Ensures the loopback exists first.
set -euo pipefail
cd "$(dirname "$0")/.."

# make sure the virtual camera is present (no-op if already loaded)
if [[ ! -e /dev/video10 ]]; then
    ./scripts/bootstrap_loopback.sh
fi

PORT="${1:-8137}"
echo "Opening control panel at http://localhost:${PORT}"
exec .venv/bin/python -m ui --port "${PORT}"
