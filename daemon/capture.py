"""Webcam capture via V4L2/OpenCV.

Yields frames as contiguous uint8 RGB arrays (H, W, 3). We request MJPG so the
webcam can hit 720p30; OpenCV decodes to BGR and we convert to RGB once here so
every downstream stage (matting, compositing, virtual cam) speaks RGB.
"""
from __future__ import annotations

import cv2

from .config import Config


class Camera:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cap: cv2.VideoCapture | None = None

    def open(self) -> "Camera":
        cap = cv2.VideoCapture(self.cfg.cam_device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open camera {self.cfg.cam_device}")
        fourcc = cv2.VideoWriter_fourcc(*self.cfg.fourcc)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        # Small buffer -> lower latency (we always want the freshest frame).
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap = cap
        return self

    @property
    def actual(self) -> tuple[int, int, float]:
        c = self.cap
        return (
            int(c.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(c.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            c.get(cv2.CAP_PROP_FPS),
        )

    def frames(self):
        """Generator of RGB uint8 frames."""
        assert self.cap is not None, "call open() first"
        while True:
            ok, bgr = self.cap.read()
            if not ok:
                break
            yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
