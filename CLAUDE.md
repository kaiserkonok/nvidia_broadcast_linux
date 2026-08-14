# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

NVBroadcast for Linux — a from-scratch NVIDIA Broadcast equivalent: real-time
GPU background blur/replace with photoreal alpha matting, plus DeepFilterNet mic
denoise, exposed as a virtual camera + virtual mic that any app can select.

## Commands

Everything runs from the venv (`.venv`), which has torch (cu128), PySide6, opencv, pyvirtualcam.

```bash
# Native desktop app (Qt window + system tray) — the main entry point
.venv/bin/python -m app            # or ./scripts/run_app.sh

# Headless video pipeline (no GUI); good for debugging the core
.venv/bin/python -m daemon --mode blur --mirror        # blur | image | color | none
.venv/bin/python -m daemon --mode image --bg some.jpg

# Optional browser control panel (Flask) instead of the Qt window
.venv/bin/python -m ui             # http://localhost:8137

# Mic denoise (independent of video; pure PipeWire, no Python)
./scripts/mic_denoise.sh start|stop|status

# Virtual camera setup (needs root; self-heals, persistent). run_ui.sh calls it.
./scripts/setup_camera.sh          # sudo in a terminal, pkexec when launched from GUI

# Install / uninstall / update (end-user flow, clones to ~/.local/share/nvbroadcast)
curl -fsSL https://raw.githubusercontent.com/kaiserkonok/nvidia_broadcast_linux/master/install.sh | bash
nvbroadcast uninstall
nvbroadcast update                 # fast git pull, NOT a reinstall (scripts/update.sh)
```

### Verification (there is no pytest suite — these scripts are how you check things)

```bash
.venv/bin/python scripts/verify_loopback.py    # webcam -> loopback plumbing is live
.venv/bin/python scripts/bench_matting.py      # ms/frame + before/after PNGs to scratch
.venv/bin/python scripts/compare_realism.py    # naive-vs-realism composites on real webcam
```

## Architecture

Two independent domains that share only the app shell and the install tooling:

### Video (Python, GPU) — `daemon/` + `app/`
Pipeline: **capture → matting → composite → v4l2loopback virtual camera**, GPU-resident end to end (one upload per frame, one download at the end).

- `daemon/pipeline.py` — the loop. Uses `ThreadedCamera` so GPU work never blocks on `cap.read()`. Wraps `processor.process()` so one bad frame degrades to passthrough instead of killing the loop. Pacing comes only from capture (`vcam.send(pace=False)`).
- `daemon/processor.py` — the `Processor` seam. `MattingProcessor` does upload → `Matting.infer` → `Compositor.composite` → download. `Passthrough` is the plumbing-only variant. **New video features slot in here without touching the loop.**
- `daemon/matting.py` + `daemon/rvm/` — Robust Video Matting (vendored, GPL-3.0). Recurrent + fp16; returns `(fgr, pha)` = decontaminated foreground + soft alpha. Keeps temporal state across frames.
- `daemon/compositor.py` — `out = fgr*pha + bg*(1-pha)` plus the **Phase 2 realism stages** (matte erosion/feather, light-wrap via screen blend). Realism is on by default; toggle via `set_realism()`.
- `daemon/output.py` — pyvirtualcam → `/dev/video10`. On open it sets `keep_format=1` (see gotchas).
- `app/` — the Qt app: `pipeline_controller.py` runs the pipeline in a worker thread and hands frames/stats to the GUI via Qt signals (never call the pipeline from the GUI thread). `main_window.py` = window, `qt_app.py` = main + tray. The whole app is one venv process.
- `ui/` — optional Flask control panel reusing the same pipeline; MJPEG preview. Not used by the desktop app.

### Audio (no Python in the signal path) — `audio/` + `scripts/mic_denoise.sh`
DeepFilterNet's **LADSPA plugin run inside a PipeWire filter-chain** (`audio/nvbroadcast-mic.conf`, loaded via `pipewire -c`). `mic_denoise.sh` starts/stops that process, creating a source named "NVBroadcast Microphone". `app/audio.py` is just a thin Qt wrapper that shells out to the script. There is no Python audio loop — this is deliberate (native, low-latency).

## Critical gotchas (these caused real, hard-to-debug failures)

- **Virtual camera needs `exclusive_caps=1`.** Strict consumers (OBS, GStreamer, Chromium) reject a loopback that also advertises output caps ("not a capture device"). `ffmpeg`/OpenCV are lenient and will read it anyway — so "cv2 can read it" does NOT prove OBS can.
- **`keep_format=1` is required for start/stop.** With `exclusive_caps=1` this v4l2loopback version resets the device to an unusable "no-format" state when a producer disconnects, so the *next* start can't open it for output. Setting the `keep_format` control (no sudo) pins the format so it survives. Done in `output.py` and `setup_camera.sh`.
- **`CAP_PROP_BUFFERSIZE` must be ≥ 2.** With MJPG, a single buffer silently halves capture to 15fps.
- **Reconfiguring the loopback needs root** (`modprobe`), so it can only be *built*, not run/verified, without a password — `setup_camera.sh` uses `sudo` (terminal) or `pkexec` (GUI). `setup_camera.sh` probes real producer usability, not just the flag, and only reloads when needed.
- **Blackwell (sm_120) needs torch cu128** (stable wheels include sm_120; system `nvcc` version is irrelevant).
- **Large binaries are git-ignored** (`.venv`, `models/weights/*.pth`, `audio/lib/*.so`) and fetched by `install.sh`/`update.sh`. Don't commit them.
- **Two locations exist:** the dev repo (where commits are made) and the installed clone at `~/.local/share/nvbroadcast` (what the menu launches). To update the installed app: `nvbroadcast update`.

## Git

Remote `origin` = `git@github.com:kaiserkonok/nvidia_broadcast_linux.git` (branch `master`); push there. The project is GPL-3.0 because the vendored RVM model is GPL-3.0.
