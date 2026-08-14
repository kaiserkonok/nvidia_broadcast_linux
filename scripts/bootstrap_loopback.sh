#!/usr/bin/env bash
# (Re)create the v4l2loopback virtual camera used as our output device.
# Idempotent: if a loopback named "Broadcast Virtual Camera" already exists,
# it does nothing. Requires sudo (module load).
set -euo pipefail

CARD_LABEL="Broadcast Virtual Camera"
VIDEO_NR="${VIDEO_NR:-10}"   # -> /dev/video10

if ! lsmod | grep -q '^v4l2loopback'; then
    echo "[bootstrap] loading v4l2loopback (nr=$VIDEO_NR)"
    sudo modprobe v4l2loopback \
        video_nr="$VIDEO_NR" \
        card_label="$CARD_LABEL" \
        exclusive_caps=1        # exclusive_caps=1 -> apps see it as a capture cam
else
    echo "[bootstrap] v4l2loopback already loaded"
fi

if [[ -e "/dev/video${VIDEO_NR}" ]]; then
    echo "[bootstrap] ready: /dev/video${VIDEO_NR} ($(cat /sys/devices/virtual/video4linux/video${VIDEO_NR}/name 2>/dev/null))"
else
    echo "[bootstrap] ERROR: /dev/video${VIDEO_NR} not present" >&2
    exit 1
fi
