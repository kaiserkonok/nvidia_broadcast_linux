"""Main capture -> process -> output loop with an FPS meter.

Capture runs in its own thread (ThreadedCamera) so GPU work never blocks on the
webcam. Processing is wrapped so a single bad frame degrades to passthrough
instead of killing the whole pipeline. Pacing comes solely from the camera
(one fresh frame per iteration), so the virtual-cam output is not double-paced.
"""
from __future__ import annotations

import signal
import threading
import time

import cv2

from .capture import ThreadedCamera
from .config import Config
from .output import VirtualCam
from .processor import Passthrough, Processor


class Pipeline:
    def __init__(self, cfg: Config, processor: Processor | None = None,
                 on_frame=None):
        self.cfg = cfg
        self.processor = processor or Passthrough()
        # Optional preview tap: called with each output RGB frame (H,W,3 uint8).
        self.on_frame = on_frame
        self._stop = False
        # live metrics (instantaneous, not cumulative-from-start)
        self.fps = 0.0
        self.proc_ms = 0.0
        self._warned = False

    def stop(self, *_):
        self._stop = True

    def _safe_process(self, rgb):
        try:
            return self.processor.process(rgb)
        except Exception as e:  # never let one frame kill the loop
            if not self._warned:
                print(f"[pipeline] processor error (falling back to passthrough): {e}")
                self._warned = True
            return rgb

    def run(self):
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self.stop)
            signal.signal(signal.SIGTERM, self.stop)

        cam = ThreadedCamera(self.cfg).open()
        w, h, fps = cam.actual
        fps = fps if fps and fps > 0 else self.cfg.fps
        print(f"[capture] {self.cfg.cam_device} -> {w}x{h} @ {fps:.0f}fps")

        vcam = VirtualCam(self.cfg, w, h, fps).open()
        print(f"[output]  -> {self.cfg.out_device} ({w}x{h} @ {fps:.0f}fps)")
        print("[pipeline] running — Ctrl-C to stop")

        n = 0
        t_prev = time.perf_counter()
        try:
            for rgb in cam.frames():
                if self._stop:
                    break
                if self.cfg.mirror:
                    rgb = cv2.flip(rgb, 1)

                ts = time.perf_counter()
                out = self._safe_process(rgb)
                pm = (time.perf_counter() - ts) * 1000.0

                vcam.send(out, pace=False)          # camera already paces us
                if self.on_frame is not None:
                    self.on_frame(out)

                # instantaneous EMA metrics
                now = time.perf_counter()
                dt = now - t_prev
                t_prev = now
                self.proc_ms = 0.9 * self.proc_ms + 0.1 * pm
                if dt > 0:
                    self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)

                n += 1
                if n % self.cfg.log_every == 0:
                    print(f"[pipeline] {n} frames | {self.fps:5.1f} fps "
                          f"| proc {self.proc_ms:5.2f} ms/frame")
        finally:
            vcam.close()
            cam.close()
            self.processor.close()
            print(f"[pipeline] stopped after {n} frames")
