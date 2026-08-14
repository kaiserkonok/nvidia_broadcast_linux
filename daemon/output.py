"""Virtual camera output via pyvirtualcam -> v4l2loopback.

Accepts RGB uint8 frames (H, W, 3) and pushes them to the loopback device so any
app (Zoom/Meet/OBS/Discord) sees them as a normal webcam.

Stability note: with exclusive_caps=1 this v4l2loopback version resets the
device to an unusable "no format" state when a producer disconnects, so the
NEXT start can't open it for output. Setting the `keep_format` control to 1
right after we open pins the format, so it survives across start/stop cycles.
"""
from __future__ import annotations

import subprocess

import pyvirtualcam

from .config import Config


class VirtualCam:
    def __init__(self, cfg: Config, width: int, height: int, fps: float):
        self.cfg = cfg
        self.width = width
        self.height = height
        self.fps = fps
        self.cam: pyvirtualcam.Camera | None = None

    def open(self) -> "VirtualCam":
        try:
            self.cam = pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=int(round(self.fps)) or 30,
                device=self.cfg.out_device,
                fmt=pyvirtualcam.PixelFormat.RGB,
                print_fps=False,
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Could not open virtual camera {self.cfg.out_device} for output "
                f"({e}). The loopback device needs reconfiguring — run "
                f"`./scripts/run_ui.sh` once in a terminal to repair it."
            ) from e
        # Pin the negotiated format so it persists across start/stop (no sudo).
        self._keep_format()
        return self

    def _keep_format(self):
        try:
            subprocess.run(
                ["v4l2-ctl", "-d", self.cfg.out_device, "-c", "keep_format=1"],
                check=False, capture_output=True, timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            pass  # best-effort; not fatal

    def send(self, rgb, pace: bool = True):
        assert self.cam is not None, "call open() first"
        self.cam.send(rgb)
        # Pace only if nothing upstream is already pacing us (e.g. a threaded
        # camera that blocks until a fresh frame). Double-pacing halves the fps.
        if pace:
            self.cam.sleep_until_next_frame()

    def close(self):
        if self.cam is not None:
            self.cam.close()
            self.cam = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
