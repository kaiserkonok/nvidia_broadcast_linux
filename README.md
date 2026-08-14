# nvidiabroadcast-linux

NVIDIA Broadcast-style real-time camera/mic processing for Linux.

Goal: background replace/blur that **feels real** (alpha matting, no color spill,
no flicker, scene-integrated) + audio denoise, exposed as a virtual camera
(v4l2loopback) and virtual mic (PipeWire null sink) usable in any app.

## Layout
- `daemon/` – video pipeline: capture -> matting -> composite -> v4l2loopback
- `audio/`  – PipeWire mic -> DeepFilterNet denoise -> virtual mic (planned)
- `models/` – model weights + TensorRT engine cache
- `app/`    – native desktop app (Qt window + system tray)
- `ui/`     – optional headless web control panel (Flask) — `python -m ui`
- `scripts/`– setup, launchers, camera/loopback config

## Usage

**Install (once):** add the app to your menu:

```bash
./scripts/install_desktop.sh   # adds "NVBroadcast" to your app menu
```

**Just launch NVBroadcast** from your app menu (or `./scripts/run_app.sh`). It's a
native window with a live preview + system-tray icon:
- **Start/Stop Camera** – grabs the webcam only while active
- **Background** – Off / Blur / Color / Image (native image picker, blur slider)
- Closing the window hides it to the tray; **Quit** from the tray to exit

The app configures the virtual camera itself — the first time (or if the loopback
ever needs repair) it shows a **graphical password prompt** (kernel module config,
made persistent so it rarely asks again). No terminal needed.

In OBS / Zoom / Meet / Discord pick the **"Broadcast Virtual Camera"**.

*(Headless/remote alternative: `./scripts/run_ui.sh` runs the same pipeline with a
browser control panel instead of the native window.)*

In any app (OBS, Zoom, Meet, Discord) pick the **"Broadcast Virtual Camera"**.
In OBS: *Sources -> Video Capture Device (V4L2) -> Broadcast Virtual Camera*
(start NVBroadcast **before** opening OBS).

Optional: `AUTOSTART=1 ./scripts/install_desktop.sh` to launch the tray on login.

## Status
Phase 0-1 done (real-time matting @30fps), web control panel, OBS-compatible
virtual camera, system-tray desktop app. Next: Phase 2 realism pass; audio.
