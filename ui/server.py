"""Local web control panel: live preview + background controls.

Runs the video pipeline in a background thread (webcam -> matting/composite ->
v4l2loopback) and serves:
  - a browser control page at /
  - an MJPEG preview of the processed output at /stream.mjpg
  - a small JSON control API the page calls to switch background live

The preview and the virtual-camera output are the *same* processed frames, so
what you see in the browser is exactly what Zoom/Meet/OBS receive.
"""
from __future__ import annotations

import os
import threading
import time

import cv2
from flask import Flask, Response, jsonify, request

UI_DIR = os.path.dirname(os.path.abspath(__file__))

from daemon.config import Config
from daemon.pipeline import Pipeline
from daemon.processor import MattingProcessor

WEIGHTS = "models/weights/rvm_mobilenetv3.pth"
UPLOAD_DIR = "/tmp/nvbroadcast_bg"


class Engine:
    """Owns the pipeline thread, the live processor, and the latest preview JPEG."""

    def __init__(self, cfg: Config, preview_width: int = 720, preview_q: int = 70):
        self.cfg = cfg
        self.preview_width = preview_width
        self.preview_q = preview_q
        self.processor = MattingProcessor(downsample_ratio=0.25)
        self.processor.set_blur(14.0)

        self._jpeg: bytes | None = None
        self._lock = threading.Lock()

        self.pipeline = Pipeline(cfg, self.processor, on_frame=self._on_frame)
        self._thread: threading.Thread | None = None

    def _on_frame(self, rgb):
        h, w = rgb.shape[:2]
        if w > self.preview_width:
            s = self.preview_width / w
            rgb = cv2.resize(rgb, (self.preview_width, int(h * s)))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, self.preview_q])
        if ok:
            with self._lock:
                self._jpeg = buf.tobytes()

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    @property
    def fps(self) -> float:
        return self.pipeline.fps

    def start(self):
        self._thread = threading.Thread(target=self.pipeline.run, daemon=True)
        self._thread.start()

    def stop(self):
        self.pipeline.stop()


def create_app(engine: Engine) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        with open(os.path.join(UI_DIR, "index.html"), encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")

    @app.route("/stream.mjpg")
    def stream():
        def gen():
            boundary = b"--frame"
            while True:
                jpg = engine.latest_jpeg()
                if jpg is None:
                    time.sleep(0.03)
                    continue
                yield (boundary + b"\r\nContent-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
                       + jpg + b"\r\n")
                time.sleep(1 / 60)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/status")
    def status():
        p = engine.processor
        return jsonify(
            fps=round(engine.fps, 1),
            proc_ms=round(engine.pipeline.proc_ms, 1),
            enabled=p.enabled,
            mode=p.compositor.mode,
            blur=p.compositor.blur_sigma,
        )

    @app.route("/api/mode", methods=["POST"])
    def set_mode():
        engine.processor.set_mode(request.json["mode"])
        return ("", 204)

    @app.route("/api/blur", methods=["POST"])
    def set_blur():
        engine.processor.set_blur(float(request.json["sigma"]))
        return ("", 204)

    @app.route("/api/color", methods=["POST"])
    def set_color():
        c = request.json["rgb"]
        engine.processor.set_color((c[0], c[1], c[2]))
        return ("", 204)

    @app.route("/api/bg", methods=["POST"])
    def set_bg():
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        f = request.files["file"]
        path = os.path.join(UPLOAD_DIR, "bg_" + f.filename)
        f.save(path)
        engine.processor.set_image(path)
        return ("", 204)

    return app
