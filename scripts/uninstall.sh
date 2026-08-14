#!/usr/bin/env bash
# Cleanly remove NVBroadcast.  Run:  nvbroadcast uninstall   (or this script)
set -uo pipefail

INSTALL_DIR="${NVB_HOME:-$HOME/.local/share/nvbroadcast}"
BIN_DIR="$HOME/.local/bin"
APPS="$HOME/.local/share/applications/nvbroadcast.desktop"
AUTOSTART="$HOME/.config/autostart/nvbroadcast.desktop"

if [[ -t 1 ]]; then G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; X=$'\e[0m'
else G=""; Y=""; C=""; B=""; X=""; fi

if [[ "${1:-}" != "--yes" && "${1:-}" != "-y" ]]; then
  printf "This removes NVBroadcast (app, virtual-camera config, and %s).\n" "$INSTALL_DIR"
  read -rp "Continue? [y/N] " a
  [[ "$a" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }
fi

# stop anything running
pkill -f "python -m app" 2>/dev/null || true
pkill -f "python -m ui"  2>/dev/null || true
[[ -x "$INSTALL_DIR/scripts/mic_denoise.sh" ]] && \
  "$INSTALL_DIR/scripts/mic_denoise.sh" stop >/dev/null 2>&1 || true

# menu entry, autostart, launcher
rm -f "$APPS" "$AUTOSTART" "$BIN_DIR/nvbroadcast"
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
printf "  ${G}✓${X} removed menu entry, autostart and launcher\n"

# virtual-camera config (needs sudo)
if [[ -f /etc/modprobe.d/nvbroadcast-v4l2loopback.conf || \
      -f /etc/modules-load.d/nvbroadcast-v4l2loopback.conf ]]; then
  printf "  removing virtual-camera config (sudo)…\n"
  sudo rm -f /etc/modprobe.d/nvbroadcast-v4l2loopback.conf \
             /etc/modules-load.d/nvbroadcast-v4l2loopback.conf 2>/dev/null || true
  sudo modprobe -r v4l2loopback 2>/dev/null || true
  printf "  ${G}✓${X} virtual-camera config removed\n"
fi

# the app itself (venv + repo). Do this last; cd out first.
cd "$HOME"
rm -rf "$INSTALL_DIR"
printf "  ${G}✓${X} removed %s\n" "$INSTALL_DIR"

printf "\n${G}${B}NVBroadcast uninstalled.${X}\n"
printf "${Y}Note:${X} the ${C}v4l2loopback-dkms${X} system package was left installed ${C}(other apps may use it)${X}.\n"
printf "      Remove it yourself with: ${C}sudo apt remove v4l2loopback-dkms${X}\n\n"
