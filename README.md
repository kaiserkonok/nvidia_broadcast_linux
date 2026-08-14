# nvidiabroadcast-linux

NVIDIA Broadcast-style real-time camera/mic processing for Linux.

Goal: background replace/blur that **feels real** (alpha matting, no color spill,
no flicker, scene-integrated) + audio denoise, exposed as a virtual camera
(v4l2loopback) and virtual mic (PipeWire null sink) usable in any app.

## Layout
- `daemon/` – video pipeline: capture -> matting -> composite -> v4l2loopback
- `audio/`  – PipeWire mic -> DeepFilterNet denoise -> virtual mic (planned)
- `models/` – model weights + TensorRT engine cache
- `ui/`     – web control panel (live preview + settings) + Flask API
- `app/`    – system-tray applet (the desktop app)
- `scripts/`– setup, launchers, camera/loopback config

## Usage

**First time (once):** configure the virtual camera for OBS/browsers. Run in a
terminal so it can ask for your password (kernel module config, one time only —
it installs a persistent config so it never asks again):

```bash
./scripts/run_ui.sh          # sets up the camera, then launches the web panel
./scripts/install_desktop.sh # adds "NVBroadcast" to your app menu
```

**Every day:** launch **NVBroadcast** from your app menu (or `./scripts/run_tray.sh`).
It lives in the system tray:
- **Start/Stop Camera** – grabs the webcam only while active
- **Background** – Off / Blur / Color / Image
- **Open Control Panel…** – full preview + blur slider + image upload (web UI)
- **Quit**

In any app (OBS, Zoom, Meet, Discord) pick the **"Broadcast Virtual Camera"**.
In OBS: *Sources -> Video Capture Device (V4L2) -> Broadcast Virtual Camera*
(start NVBroadcast **before** opening OBS).

Optional: `AUTOSTART=1 ./scripts/install_desktop.sh` to launch the tray on login.

## Status
Phase 0-1 done (real-time matting @30fps), web control panel, OBS-compatible
virtual camera, system-tray desktop app. Next: Phase 2 realism pass; audio.
