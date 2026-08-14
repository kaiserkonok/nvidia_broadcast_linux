#!/usr/bin/env bash
# Start / stop the DeepFilterNet noise-cancelling virtual microphone.
# Runs the PipeWire filter-chain in its own process; killing it removes the
# "NVBroadcast Microphone" source. No sudo needed.
#
#   scripts/mic_denoise.sh start | stop | status
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PLUGIN="$ROOT/audio/lib/libdeep_filter_ladspa.so"
TEMPLATE="$ROOT/audio/nvbroadcast-mic.conf"
RUNTIME_CONF="/tmp/nvbroadcast-mic.conf"
PIDFILE="/tmp/nvbroadcast-mic.pid"
LOG="/tmp/nvbroadcast-mic.log"

is_running() {
    [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null
}

start() {
    [[ -f "$PLUGIN" ]] || { echo "DeepFilterNet plugin missing: $PLUGIN" >&2; exit 1; }
    command -v pipewire >/dev/null 2>&1 || { echo "pipewire not found" >&2; exit 1; }
    if is_running; then echo "mic denoise already running"; return 0; fi

    sed "s#@PLUGIN@#${PLUGIN}#g" "$TEMPLATE" > "$RUNTIME_CONF"
    setsid pipewire -c "$RUNTIME_CONF" >"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    # give it a moment; verify the source actually appeared
    for _ in $(seq 1 25); do
        if pactl list sources short 2>/dev/null | grep -q NVBroadcast_Mic; then
            echo "NVBroadcast Microphone ready (pid $(cat "$PIDFILE"))"
            return 0
        fi
        is_running || break
        sleep 0.2
    done
    echo "mic denoise failed to start — see $LOG" >&2
    tail -5 "$LOG" 2>/dev/null >&2
    stop >/dev/null 2>&1
    exit 1
}

stop() {
    if is_running; then kill "$(cat "$PIDFILE")" 2>/dev/null; fi
    pkill -f "pipewire -c ${RUNTIME_CONF}" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "mic denoise stopped"
}

case "${1:-}" in
    start)  start ;;
    stop)   stop ;;
    status) is_running && echo running || echo stopped ;;
    *)      echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
