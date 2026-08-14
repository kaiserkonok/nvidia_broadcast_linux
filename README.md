# nvidiabroadcast-linux

NVIDIA Broadcast-style real-time camera/mic processing for Linux.

Goal: background replace/blur that **feels real** (alpha matting, no color spill,
no flicker, scene-integrated) + audio denoise, exposed as a virtual camera
(v4l2loopback) and virtual mic (PipeWire null sink) usable in any app.

## Layout
- `daemon/` – video pipeline: capture -> matting -> composite -> v4l2loopback
- `audio/`  – PipeWire mic -> DeepFilterNet denoise -> virtual mic
- `models/` – model weights + TensorRT engine cache
- `ui/`     – control app (preview + settings)
- `scripts/`– setup: v4l2loopback + null-sink bootstrap

## Status
Phase 0: toolchain + plumbing.
