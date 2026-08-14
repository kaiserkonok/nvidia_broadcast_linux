"""Qt-friendly wrapper around the video pipeline.

Runs the capture->matting->composite->virtual-camera loop in a worker thread and
delivers frames + stats to the GUI via Qt signals (queued across threads, so the
GUI thread never touches the pipeline directly). Also handles the one-time
camera setup (which may pop a graphical password dialog via pkexec).
"""
from __future__ import annotations

import os
import subprocess
import threading

import numpy as np
from PySide6 import QtCore, QtGui

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS = os.path.join(PROJECT_ROOT, "models", "weights", "rvm_mobilenetv3.pth")
SETUP = os.path.join(PROJECT_ROOT, "scripts", "setup_camera.sh")


class PipelineController(QtCore.QObject):
    frameReady = QtCore.Signal(QtGui.QImage)
    stats = QtCore.Signal(float, float)      # fps, proc_ms
    statusText = QtCore.Signal(str)          # human-readable state
    runningChanged = QtCore.Signal(bool)
    error = QtCore.Signal(str)

    def __init__(self, cfg=None):
        super().__init__()
        from daemon.config import Config
        self.cfg = cfg or Config()
        self.cfg.mirror = True
        self._processor = None
        self._pipeline = None
        self._thread: threading.Thread | None = None
        self._n = 0

    # ---- lifecycle --------------------------------------------------------
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._pipeline is not None:
            self._pipeline.stop()
        if self._thread is not None:
            self._thread.join(timeout=4)
            self._thread = None

    def _run(self):
        try:
            self.statusText.emit("Preparing camera…")
            r = subprocess.run([SETUP], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                msg = (r.stderr or r.stdout or "").strip()[-400:]
                self.error.emit("Couldn't set up the virtual camera.\n" + msg)
                return

            self.statusText.emit("Loading model…")
            proc = self._ensure_processor()
            if hasattr(proc, "matting"):
                proc.matting.reset()

            from daemon.pipeline import Pipeline
            self._pipeline = Pipeline(self.cfg, proc, on_frame=self._on_frame)
            self._n = 0
            self.runningChanged.emit(True)
            self.statusText.emit("Running")
            self._pipeline.run()          # blocks until stop()
        except Exception as e:            # noqa: BLE001 - surface to the UI
            self.error.emit(str(e))
        finally:
            self._pipeline = None
            self.runningChanged.emit(False)
            self.statusText.emit("Stopped")

    def _ensure_processor(self):
        if self._processor is None:
            from daemon.processor import MattingProcessor
            self._processor = MattingProcessor(WEIGHTS)
            self._processor.set_blur(14.0)
        return self._processor

    # ---- per-frame --------------------------------------------------------
    def _on_frame(self, rgb: np.ndarray):
        h, w = rgb.shape[:2]
        # Copy into a QImage that owns its buffer (rgb is reused next frame).
        img = QtGui.QImage(rgb.data, w, h, 3 * w,
                           QtGui.QImage.Format.Format_RGB888).copy()
        self.frameReady.emit(img)
        self._n += 1
        if self._n % 10 == 0 and self._pipeline is not None:
            self.stats.emit(self._pipeline.fps, self._pipeline.proc_ms)

    # ---- controls (thread-safe: simple attribute setters) -----------------
    def set_mode(self, mode: str):
        if self._processor:
            self._processor.set_mode(mode)

    def set_blur(self, sigma: float):
        if self._processor:
            self._processor.set_blur(sigma)

    def set_color(self, rgb):
        if self._processor:
            self._processor.set_color(rgb)

    def set_image(self, path: str):
        if self._processor:
            self._processor.set_image(path)

    def set_realism(self, on: bool):
        if self._processor:
            self._processor.set_realism(on)
