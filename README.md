<div align="center">

# 🎥 NVBroadcast for Linux

### Real-time, **real-looking** virtual background for any Linux app.

A from-scratch, open-source take on NVIDIA Broadcast — GPU-accelerated background
blur & replacement with **soft, film-quality edges** (real alpha matting, not a
cheap cut-out), served to Zoom, Meet, OBS, Discord and anything else as a normal webcam.

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux-informational.svg)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20RTX-76b900.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)

<!-- Add a demo here: drop a short screen-capture at docs/demo.gif and uncomment:
<img src="docs/demo.gif" width="720" alt="NVBroadcast demo">
-->

</div>

---

## ⚡ Install

```bash
curl -fsSL https://raw.githubusercontent.com/kaiserkonok/nvidia_broadcast_linux/master/install.sh | bash
```

That's it. It installs everything, adds **NVBroadcast** to your app menu, and sets
up the virtual camera. Launch it, pick a background, and select **“Broadcast
Virtual Camera”** in your video app.

> Uninstall just as easily: **`nvbroadcast uninstall`**

---

## ✨ Features

- 🪄 **Background blur / replace / solid color** — switch live, no restart
- 🧠 **Actually-real edges** — per-pixel alpha matting keeps individual hairs and
  soft motion; the subject is decontaminated of background color spill, so it
  doesn't look pasted on
- ⚡ **Real-time** — ~30 fps at 720p, GPU-resident end to end (RTX)
- 🎛️ **Native desktop app** — live preview, controls, and a **system-tray** icon
  (closes to tray, like the real thing)
- 🎙️ **Mic noise removal** — RTX-Voice-style denoise (DeepFilterNet) exposed as a
  virtual microphone; kills keyboard, fan and room noise, keeps your voice natural
- 🔌 **Works everywhere** — appears as a normal V4L2 webcam (and virtual mic) in
  OBS, Zoom, Meet, Discord, browsers…
- 🛠️ **Self-configuring** — sets up the `v4l2loopback` virtual camera for you, with
  a graphical password prompt only when it truly needs one

---

## 🔬 How it looks real

Cheap “virtual backgrounds” use a binary person/background mask → hard, jagged
edges and chewed-off hair. NVBroadcast uses **video matting**:

1. **Alpha matte, not a mask** — each pixel gets an opacity `0.0–1.0`, so hair
   strands and soft edges blend naturally.
2. **Foreground decontamination** — the model estimates your true foreground
   color separately, removing the background color halo around your edges.
3. **Temporal stability** — a recurrent model keeps the matte steady frame to
   frame instead of shimmering.

Powered by [Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting),
composited on the GPU.

---

## 🖥️ Usage

Open **NVBroadcast** from your app menu (or run `nvbroadcast`):

- **Start/Stop Camera** — the webcam is used only while active
- **Background** — Off · Blur (with strength) · Color · Image
- **Remove background noise** — flip it on, then pick **“NVBroadcast Microphone”** in your call app
- Close the window to tuck it into the **tray**; **Quit** from the tray to exit

Then in OBS / Zoom / Meet / Discord, choose **“Broadcast Virtual Camera.”**
In OBS specifically: *Sources → Video Capture Device (V4L2) → Broadcast Virtual Camera*
(start NVBroadcast **before** OBS).

---

## 📦 Requirements

- Linux with a modern kernel (tested on Ubuntu 24.04 / GNOME)
- **NVIDIA RTX GPU** + recent driver (CUDA 12.8-capable)
- `apt`-based distro for the one-command installer (other distros: install
  `v4l2loopback-dkms`, `v4l-utils`, `python3-venv` and run `scripts/run_app.sh`)

---

## 🗺️ Roadmap

- [x] Real-time background matting (blur / image / color)
- [x] Native desktop app + system tray
- [x] One-command install / uninstall
- [x] **Realism pass** — light-wrap + edge feathering (color-match & grain next)
- [x] **Mic denoise** — RTX-Voice-style noise removal (DeepFilterNet) → virtual mic
- [ ] Auto-frame & eye-contact
- [ ] TensorRT engine for even lower latency

---

## 🧹 Uninstall

```bash
nvbroadcast uninstall
```

Removes the app, menu entry, launcher and virtual-camera config. (The shared
`v4l2loopback` system package is left in place — remove it yourself if unused.)

---

## 🙏 Credits & License

- Matting model: [Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting) (Peter Lin et al.)
- Virtual camera: [v4l2loopback](https://github.com/umlaeute/v4l2loopback) · [pyvirtualcam](https://github.com/letmaik/pyvirtualcam)

Licensed under **GPL-3.0** (the vendored matting model is GPL-3.0). See [LICENSE](LICENSE).
