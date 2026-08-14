"""Webcam capture via V4L2/OpenCV.

Yields frames as contiguous uint8 RGB arrays (H, W, 3). We request MJPG so the
webcam can hit 720p30; OpenCV decodes to BGR and we convert to RGB once here so
every downstream stage (matting, compositing, virtual cam) speaks RGB.

`Camera` is the simple synchronous grabber (used by benchmarks). The live
pipeline uses `ThreadedCamera`, which reads the webcam in its own thread and
hands the pipeline the *latest* frame the moment one is ready -- so GPU
processing never blocks waiting on `cap.read()` (the classic OpenCV stall).
"""
from __future__ import annotations

import threading

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
        # >=2 buffers: 1 silently halves MJPG to 15fps (can't capture N+1 while
        # holding N). The threaded grabber keeps latency low regardless.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.cfg.buffersize)
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


class ThreadedCamera(Camera):
    """Non-blocking camera: a background thread keeps the newest frame ready.

    The pipeline calls `read()` which blocks only until a *fresh* frame arrives,
    so processing runs at camera rate without paying the capture latency inline.
    """

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self._latest = None
        self._seq = 0
        self._cv = threading.Condition()
        self._stop = False
        self._thread: threading.Thread | None = None

    def open(self) -> "ThreadedCamera":
        super().open()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop:
            ok, bgr = self.cap.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            with self._cv:
                self._latest = rgb
                self._seq += 1
                self._cv.notify_all()

    def read(self, last_seq: int, timeout: float = 1.0):
        """Block until a frame newer than `last_seq` is available.

        Returns (frame, seq) or (None, last_seq) on timeout.
        """
        with self._cv:
            if not self._cv.wait_for(lambda: self._seq > last_seq, timeout=timeout):
                return None, last_seq
            return self._latest, self._seq

    def frames(self):
        seq = 0
        while not self._stop:
            frame, seq = self.read(seq)
            if frame is not None:
                yield frame

    def close(self):
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        super().close()
