#!/usr/bin/env bash
# (Re)create the v4l2loopback virtual camera used as our output device.
#
# For best consumer compatibility we want exclusive_caps=1, which makes the
# device present as a plain *capture* camera to apps once we start producing.
# Chromium-based browsers (Meet, Discord web) HIDE loopback devices that also
# advertise output caps, and OBS is happier with capture-only too.
#
# Usage:
#   ./scripts/bootstrap_loopback.sh            # ensure a good device exists
#   RELOAD=1 ./scripts/bootstrap_loopback.sh   # force reload with correct caps
#
# RELOAD unloads the module (closes ALL current loopback users) and reloads it,
# so quit anything using a virtual camera first. Requires sudo.
set -euo pipefail

CARD_LABEL="Broadcast Virtual Camera"
VIDEO_NR="${VIDEO_NR:-10}"

load() {
    echo "[bootstrap] loading v4l2loopback (nr=$VIDEO_NR, exclusive_caps=1)"
    sudo modprobe v4l2loopback \
        video_nr="$VIDEO_NR" \
        card_label="$CARD_LABEL" \
        exclusive_caps=1
}

caps_ok() {
    # 1 (or Y) in the first slot means exclusive_caps is on
    local c
    c=$(cat /sys/module/v4l2loopback/parameters/exclusive_caps 2>/dev/null | cut -d, -f1)
    [[ "$c" == "1" || "$c" == "Y" ]]
}

if lsmod | grep -q '^v4l2loopback'; then
    if caps_ok && [[ -e "/dev/video${VIDEO_NR}" ]]; then
        echo "[bootstrap] already loaded with exclusive_caps=1 — nothing to do"
    elif [[ "${RELOAD:-0}" == "1" ]]; then
        echo "[bootstrap] reloading module with correct caps…"
        sudo modprobe -r v4l2loopback
        load
    else
        echo "[bootstrap] WARNING: v4l2loopback is loaded WITHOUT exclusive_caps=1."
        echo "            Browsers/OBS may not see the camera cleanly."
        echo "            Fix (closes current virtual cameras):"
        echo "              RELOAD=1 ./scripts/bootstrap_loopback.sh"
    fi
else
    load
fi

if [[ -e "/dev/video${VIDEO_NR}" ]]; then
    echo "[bootstrap] ready: /dev/video${VIDEO_NR} ($(cat /sys/devices/virtual/video4linux/video${VIDEO_NR}/name 2>/dev/null))"
else
    echo "[bootstrap] ERROR: /dev/video${VIDEO_NR} not present" >&2
    exit 1
fi
