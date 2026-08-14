#!/usr/bin/env bash
# Privileged step: (re)load v4l2loopback with exclusive_caps=1 and install a
# persistent config so every future boot is correct. Must run as root — invoked
# by setup_camera.sh via `sudo` (in a terminal) or `pkexec` (graphical popup).
# Idempotent.
set -e

VIDEO_NR="${1:-10}"
CARD_LABEL="${2:-Broadcast Virtual Camera}"

cat > /etc/modprobe.d/nvbroadcast-v4l2loopback.conf <<CONF
# nvidiabroadcast-linux: OBS-compatible virtual camera
options v4l2loopback video_nr=${VIDEO_NR} card_label="${CARD_LABEL}" exclusive_caps=1
CONF
echo v4l2loopback > /etc/modules-load.d/nvbroadcast-v4l2loopback.conf

modprobe -r v4l2loopback 2>/dev/null || true
modprobe v4l2loopback
