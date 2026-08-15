#!/usr/bin/env bash
# Install NVBroadcast as a real desktop app (menu entry + optional autostart).
# User-local only — no sudo. Re-runnable.
#
#   ./scripts/install_desktop.sh            # add to app menu
#   AUTOSTART=1 ./scripts/install_desktop.sh  # also launch tray on login
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd -P)"

APPS_DIR="$HOME/.local/share/applications"
DESKTOP="$APPS_DIR/nvbroadcast.desktop"
mkdir -p "$APPS_DIR"

write_entry() {
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=NVBroadcast
GenericName=Virtual Camera
Comment=Real-time background replace/blur virtual camera (system tray)
Exec=${ROOT}/scripts/run_app.sh
Icon=${ROOT}/assets/logo-256.png
Terminal=false
Categories=AudioVideo;Video;
Keywords=camera;webcam;background;blur;virtual;broadcast;
StartupNotify=false
EOF
    chmod +x "$1"
}

write_entry "$DESKTOP"
echo "[install] menu entry: $DESKTOP"

if [[ "${AUTOSTART:-0}" == "1" ]]; then
    AUTO_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTO_DIR"
    write_entry "$AUTO_DIR/nvbroadcast.desktop"
    echo "[install] autostart on login enabled: $AUTO_DIR/nvbroadcast.desktop"
fi

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "[install] done — 'NVBroadcast' is now in your app menu."
echo "[install] (search for it in Activities, or run ./scripts/run_tray.sh)"
