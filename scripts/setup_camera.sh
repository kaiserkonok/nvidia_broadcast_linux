#!/usr/bin/env bash
# Make the virtual camera work with strict consumers like OBS.
#
# The reliable config is a CLEAN load of v4l2loopback with exclusive_caps=1.
# This script PROBES whether the device actually accepts a producer (not just
# whether the flag is set — the device can be in a corrupted state where the
# flag looks right but every open fails). If the probe fails it does a clean
# reload and installs a persistent config so every future boot is correct.
#
# First run may ask for your password once. After that it's a no-op needing no
# sudo, even across reboots.
#
# Exit 0 = ready. Exit 2 = another app (e.g. OBS) is holding the device; close
# it and re-run.
set -uo pipefail
cd "$(dirname "$0")/.."

VIDEO_NR=10
CARD_LABEL="Broadcast Virtual Camera"
DEV="/dev/video${VIDEO_NR}"
MODPROBE_CONF="/etc/modprobe.d/nvbroadcast-v4l2loopback.conf"
LOAD_CONF="/etc/modules-load.d/nvbroadcast-v4l2loopback.conf"
PY="${PY:-.venv/bin/python}"

# Probe: can OUR producer actually open the device for output? This is the real
# test of usability, not the exclusive_caps flag.
probe_producer() {
    [[ -e "$DEV" ]] || return 1
    "$PY" - "$DEV" <<'PYEOF' >/dev/null 2>&1
import sys, pyvirtualcam
try:
    c = pyvirtualcam.Camera(width=1280, height=720, fps=30, device=sys.argv[1],
                            fmt=pyvirtualcam.PixelFormat.RGB, print_fps=False)
    c.close()
except Exception:
    sys.exit(1)
PYEOF
}

if probe_producer; then
    echo "[camera] $DEV is ready (producer probe passed)"
    exit 0
fi

echo "[camera] virtual camera not usable yet — configuring for OBS…"

# Free the device: stop our own producers (never touches OBS/other apps).
pkill -f "python -m ui" 2>/dev/null || true
pkill -f "python -m daemon" 2>/dev/null || true

# If some OTHER app still holds it, we can't reload.
if lsmod | grep -q '^v4l2loopback'; then
    holders=$(fuser "$DEV" 2>/dev/null || true)
    if [[ -n "${holders// /}" ]]; then
        echo "[camera] $DEV is held by another app (PID:$holders) — close it (e.g. OBS) and re-run."
        exit 2
    fi
fi

echo "[camera] a one-time password prompt is needed to configure the kernel camera module."

# One sudo batch: persistent config + clean reload.
sudo bash -s <<EOF
set -e
cat > "$MODPROBE_CONF" <<CONF
# nvidiabroadcast-linux: OBS-compatible virtual camera
options v4l2loopback video_nr=${VIDEO_NR} card_label="${CARD_LABEL}" exclusive_caps=1
CONF
echo v4l2loopback > "$LOAD_CONF"
modprobe -r v4l2loopback 2>/dev/null || true
modprobe v4l2loopback
EOF
rc=$?
[[ $rc -eq 0 ]] || { echo "[camera] module reload failed (rc=$rc)"; exit 1; }

# Pin the format so it survives producer disconnects (this version otherwise
# resets to an unusable state between start/stop). No sudo needed. Set BEFORE
# the probe negotiates a format, so that format gets kept.
v4l2-ctl -d "$DEV" -c keep_format=1 2>/dev/null || true

if probe_producer; then
    echo "[camera] $DEV ready (exclusive_caps=1, keep_format=1) — stable across start/stop"
    exit 0
fi
echo "[camera] ERROR: device still not usable after reload." >&2
echo "[camera] Please report the output of: v4l2-ctl -d $DEV --info" >&2
exit 1
