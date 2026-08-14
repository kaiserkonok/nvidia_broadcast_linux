"""Virtual camera output via pyvirtualcam -> v4l2loopback.

Accepts RGB uint8 frames (H, W, 3) and pushes them to the loopback device so any
app (Zoom/Meet/OBS/Discord) sees them as a normal webcam.
"""
from __future__ import annotations

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
        self.cam = pyvirtualcam.Camera(
            width=self.width,
            height=self.height,
            fps=int(round(self.fps)) or 30,
            device=self.cfg.out_device,
            fmt=pyvirtualcam.PixelFormat.RGB,
            print_fps=False,
        )
        return self

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
