"""Main capture -> process -> output loop with an FPS meter."""
from __future__ import annotations

import signal
import threading
import time

import cv2

from .capture import Camera
from .config import Config
from .output import VirtualCam
from .processor import Passthrough, Processor


class Pipeline:
    def __init__(self, cfg: Config, processor: Processor | None = None):
        self.cfg = cfg
        self.processor = processor or Passthrough()
        self._stop = False

    def stop(self, *_):
        self._stop = True

    def run(self):
        # Signal handlers can only be installed from the main thread; the
        # self-test runs the pipeline in a worker thread and stops it manually.
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self.stop)
            signal.signal(signal.SIGTERM, self.stop)

        cam = Camera(self.cfg).open()
        w, h, fps = cam.actual
        fps = fps if fps and fps > 0 else self.cfg.fps
        print(f"[capture] {self.cfg.cam_device} -> {w}x{h} @ {fps:.0f}fps")

        vcam = VirtualCam(self.cfg, w, h, fps).open()
        print(f"[output]  -> {self.cfg.out_device} ({w}x{h} @ {fps:.0f}fps)")
        print("[pipeline] running — Ctrl-C to stop")

        n = 0
        t0 = time.perf_counter()
        proc_ms = 0.0
        try:
            for rgb in cam.frames():
                if self._stop:
                    break
                if self.cfg.mirror:
                    rgb = cv2.flip(rgb, 1)

                ts = time.perf_counter()
                out = self.processor.process(rgb)
                proc_ms += (time.perf_counter() - ts) * 1000.0

                vcam.send(out)
                n += 1
                if n % self.cfg.log_every == 0:
                    dt = time.perf_counter() - t0
                    print(
                        f"[pipeline] {n} frames | "
                        f"{n / dt:5.1f} fps | proc {proc_ms / n:5.2f} ms/frame"
                    )
        finally:
            vcam.close()
            cam.close()
            self.processor.close()
            print(f"[pipeline] stopped after {n} frames")
