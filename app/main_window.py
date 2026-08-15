"""NVBroadcast main window (Qt).

Live preview on the left, controls on the right. Talks only to a
PipelineController via signals/slots — no video/GPU code lives here.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from .audio import AudioController
from .pipeline_controller import PipelineController

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def brand_icon() -> QtGui.QIcon:
    """The NVBroadcast logo as a QIcon (PNG for reliability, SVG fallback),
    falling back to a stock theme icon if the assets are missing."""
    for name in ("logo-256.png", "logo.svg"):
        p = os.path.join(_ASSETS, name)
        if os.path.exists(p):
            ic = QtGui.QIcon(p)
            if not ic.isNull():
                return ic
    return QtGui.QIcon.fromTheme("camera-web")

COLORS = [
    (46, 204, 113), (0, 177, 64), (52, 152, 219), (155, 89, 182),
    (231, 76, 60), (241, 196, 15), (236, 240, 241), (20, 20, 24),
]

STYLE = """
QWidget { background:#0d0f14; color:#e7ecf3; font-size:14px; }
#panel { background:#161a22; border:1px solid #252b36; border-radius:12px; }
#preview { background:#000; border:1px solid #252b36; border-radius:12px; }
QLabel#h2 { color:#8b94a3; font-size:11px; font-weight:600; }
QPushButton { background:#1e2530; border:1px solid #252b36; border-radius:9px;
              padding:9px 12px; }
QPushButton:hover { border-color:#54a0ff; }
QPushButton:checked { background:#54a0ff; color:#04121f; border-color:#54a0ff;
                      font-weight:600; }
QPushButton#primary { background:#2ecc71; color:#04140a; font-weight:700;
                      border:none; padding:12px; font-size:15px; }
QPushButton#primary[running="true"] { background:#e74c3c; color:#1a0505; }
QSlider::groove:horizontal { height:5px; background:#252b36; border-radius:3px; }
QSlider::handle:horizontal { background:#54a0ff; width:16px; margin:-6px 0;
                             border-radius:8px; }
"""


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, controller: PipelineController, audio: AudioController):
        super().__init__()
        self.controller = controller
        self.audio = audio
        self.settings = QtCore.QSettings("NVBroadcast", "NVBroadcast")
        self._mode = "blur"
        self._last_color = COLORS[0]
        self._last_image = ""
        self.setWindowTitle("NVBroadcast")
        self.setWindowIcon(brand_icon())
        self.resize(1024, 600)
        self.setStyleSheet(STYLE)
        self._allow_close = False

        self._build_ui()
        self._wire()
        self._restore()                                    # load saved settings
        self._on_denoise_changed(self.audio.is_running())  # reflect current state

    # ---- layout -----------------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # preview
        self.preview = QtWidgets.QLabel()
        self.preview.setObjectName("preview")
        self.preview.setMinimumSize(480, 270)
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                   QtWidgets.QSizePolicy.Policy.Expanding)
        self.preview.setText("Press Start")
        root.addWidget(self.preview, 1)

        # control panel
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(300)
        col = QtWidgets.QVBoxLayout(panel)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(12)

        self.start_btn = QtWidgets.QPushButton("Start Camera")
        self.start_btn.setObjectName("primary")
        col.addWidget(self.start_btn)

        self.status = QtWidgets.QLabel("○ Stopped")
        self.status.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.status)

        col.addSpacing(6)
        col.addWidget(self._h2("BACKGROUND"))
        modes = QtWidgets.QGridLayout()
        modes.setSpacing(6)
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_buttons = {}
        mode_items = [("Off", "none"), ("Blur", "blur"), ("Studio", "studio"),
                      ("Color", "color"), ("Image", "image")]
        for i, (label, key) in enumerate(mode_items):
            b = QtWidgets.QPushButton(label)
            b.setCheckable(True)
            b.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                            QtWidgets.QSizePolicy.Policy.Fixed)
            if key == "blur":
                b.setChecked(True)
            if key == "studio":
                b.setToolTip("Dark studio backdrop with a soft light behind you")
            self.mode_group.addButton(b)
            self.mode_buttons[key] = b
            b.clicked.connect(lambda _=False, k=key: self._on_mode(k))
            modes.addWidget(b, i // 3, i % 3)
        col.addLayout(modes)

        # blur controls
        self.blur_box = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(self.blur_box)
        bl.setContentsMargins(0, 0, 0, 0)
        self.blur_label = QtWidgets.QLabel("Blur strength · 14")
        self.blur_label.setStyleSheet("color:#8b94a3;")
        self.blur_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.blur_slider.setRange(2, 40)
        self.blur_slider.setValue(14)
        bl.addWidget(self.blur_label)
        bl.addWidget(self.blur_slider)
        col.addWidget(self.blur_box)

        # color swatches
        self.color_box = QtWidgets.QWidget()
        cg = QtWidgets.QGridLayout(self.color_box)
        cg.setContentsMargins(0, 0, 0, 0)
        for i, c in enumerate(COLORS):
            sw = QtWidgets.QPushButton()
            sw.setFixedSize(32, 32)
            sw.setStyleSheet(
                f"background:rgb{c}; border:2px solid transparent; border-radius:8px;")
            sw.clicked.connect(lambda _=False, col_=c: self._on_color(col_))
            cg.addWidget(sw, i // 4, i % 4)
        col.addWidget(self.color_box)

        # image picker
        self.image_box = QtWidgets.QWidget()
        ib = QtWidgets.QVBoxLayout(self.image_box)
        ib.setContentsMargins(0, 0, 0, 0)
        self.image_btn = QtWidgets.QPushButton("Choose image…")
        ib.addWidget(self.image_btn)
        col.addWidget(self.image_box)

        # studio backdrop controls
        self.studio_box = QtWidgets.QWidget()
        sb = QtWidgets.QVBoxLayout(self.studio_box)
        sb.setContentsMargins(0, 0, 0, 0)
        self.glow_label = QtWidgets.QLabel("Studio glow · 100%")
        self.glow_label.setStyleSheet("color:#8b94a3;")
        self.glow_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.glow_slider.setRange(0, 150)     # 0..1.5
        self.glow_slider.setValue(100)
        self.warmth_label = QtWidgets.QLabel("Warmth · neutral")
        self.warmth_label.setStyleSheet("color:#8b94a3;")
        self.warmth_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.warmth_slider.setRange(-100, 100)   # cool .. warm
        self.warmth_slider.setValue(0)
        for wdg in (self.glow_label, self.glow_slider, self.warmth_label, self.warmth_slider):
            sb.addWidget(wdg)
        col.addWidget(self.studio_box)

        col.addSpacing(10)
        col.addWidget(self._h2("ENHANCE"))
        self.realism_chk = QtWidgets.QCheckBox("Photoreal edges")
        self.realism_chk.setChecked(True)
        self.realism_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.realism_chk)

        self.relight_chk = QtWidgets.QCheckBox("Studio Light")
        self.relight_chk.setChecked(True)
        self.relight_chk.setToolTip(
            "Auto-fix bad room lighting on your face — works in every mode")
        self.relight_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.relight_chk)

        self.relight_box = QtWidgets.QWidget()
        rlb = QtWidgets.QVBoxLayout(self.relight_box)
        rlb.setContentsMargins(0, 0, 0, 0)
        self.relight_label = QtWidgets.QLabel("Light intensity · 60%")
        self.relight_label.setStyleSheet("color:#8b94a3;")
        self.relight_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.relight_slider.setRange(0, 100)
        self.relight_slider.setValue(60)
        rlb.addWidget(self.relight_label)
        rlb.addWidget(self.relight_slider)
        col.addWidget(self.relight_box)

        self.cleanup_chk = QtWidgets.QCheckBox("Video Cleanup")
        self.cleanup_chk.setToolTip("Brighten low light + remove webcam noise")
        self.cleanup_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.cleanup_chk)

        self.cleanup_box = QtWidgets.QWidget()
        clb = QtWidgets.QVBoxLayout(self.cleanup_box)
        clb.setContentsMargins(0, 0, 0, 0)
        self.ll_label = QtWidgets.QLabel("Low-light · 60%")
        self.ll_label.setStyleSheet("color:#8b94a3;")
        self.ll_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.ll_slider.setRange(0, 100)
        self.ll_slider.setValue(60)
        self.dn_label = QtWidgets.QLabel("Denoise · 50%")
        self.dn_label.setStyleSheet("color:#8b94a3;")
        self.dn_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dn_slider.setRange(0, 100)
        self.dn_slider.setValue(50)
        for wdg in (self.ll_label, self.ll_slider, self.dn_label, self.dn_slider):
            clb.addWidget(wdg)
        col.addWidget(self.cleanup_box)

        self.eye_chk = QtWidgets.QCheckBox("Eye Contact  (beta)")
        self.eye_chk.setToolTip("Experimental — nudges your eyes toward the camera")
        self.eye_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.eye_chk)

        self.eye_box = QtWidgets.QWidget()
        eb = QtWidgets.QVBoxLayout(self.eye_box)
        eb.setContentsMargins(0, 0, 0, 0)
        self.eye_label = QtWidgets.QLabel("Gaze strength · 50%")
        self.eye_label.setStyleSheet("color:#8b94a3;")
        self.eye_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.eye_slider.setRange(0, 100)
        self.eye_slider.setValue(50)
        eb.addWidget(self.eye_label)
        eb.addWidget(self.eye_slider)
        col.addWidget(self.eye_box)

        self.autoframe_chk = QtWidgets.QCheckBox("Auto-Frame")
        self.autoframe_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.autoframe_chk)

        self.zoom_box = QtWidgets.QWidget()
        zb = QtWidgets.QVBoxLayout(self.zoom_box)
        zb.setContentsMargins(0, 0, 0, 0)
        self.zoom_label = QtWidgets.QLabel("Framing")
        self.zoom_label.setStyleSheet("color:#8b94a3;")
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(100, 170)   # tightness padding %
        self.zoom_slider.setValue(115)
        zb.addWidget(self.zoom_label)
        zb.addWidget(self.zoom_slider)
        col.addWidget(self.zoom_box)
        self.zoom_box.setVisible(False)

        self.vig_label = QtWidgets.QLabel("Vignette")
        self.vig_label.setStyleSheet("color:#8b94a3;")
        self.vig_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vig_slider.setRange(0, 60)       # 0..0.60
        self.vig_slider.setValue(0)
        col.addWidget(self.vig_label)
        col.addWidget(self.vig_slider)

        col.addSpacing(4)
        col.addWidget(self._h2("QUALITY"))
        qrow = QtWidgets.QHBoxLayout()
        qrow.setSpacing(6)
        self.q_bal = QtWidgets.QPushButton("Fast")
        self.q_best = QtWidgets.QPushButton("Best")
        self.q_ultra = QtWidgets.QPushButton("Ultra")
        self.q_bal.setToolTip("MobileNetV3 — lightest")
        self.q_best.setToolTip("RVM ResNet-50 — sharp edges, real-time")
        self.q_ultra.setToolTip("BiRefNet — SOTA quality, ~12 fps (first use downloads the model)")
        self.q_group = QtWidgets.QButtonGroup(self)
        for b, key in ((self.q_bal, "balanced"), (self.q_best, "best"), (self.q_ultra, "ultra")):
            b.setCheckable(True)
            b.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                            QtWidgets.QSizePolicy.Policy.Fixed)
            self.q_group.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._on_quality(k))
            qrow.addWidget(b)
        self.q_best.setChecked(True)
        col.addLayout(qrow)

        col.addSpacing(10)
        col.addWidget(self._h2("MICROPHONE"))
        self.denoise_chk = QtWidgets.QCheckBox("Remove background noise")
        self.denoise_chk.setStyleSheet("color:#8b94a3;")
        col.addWidget(self.denoise_chk)

        col.addStretch(1)
        hint = QtWidgets.QLabel(
            "In OBS / Zoom / Meet pick “Broadcast Virtual Camera”.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b94a3; font-size:12px;")
        col.addWidget(hint)

        root.addWidget(panel)
        self._show_mode_panels("blur")

    def _h2(self, text):
        lab = QtWidgets.QLabel(text)
        lab.setObjectName("h2")
        return lab

    # ---- wiring -----------------------------------------------------------
    def _wire(self):
        self.start_btn.clicked.connect(self._toggle)
        self.blur_slider.valueChanged.connect(self._on_blur)
        self.image_btn.clicked.connect(self._choose_image)
        self.glow_slider.valueChanged.connect(self._on_glow)
        self.warmth_slider.valueChanged.connect(self._on_warmth)
        self.realism_chk.toggled.connect(self._on_realism)
        self.relight_chk.toggled.connect(self._on_relight_toggle)
        self.relight_slider.valueChanged.connect(self._on_relight_strength)
        self.cleanup_chk.toggled.connect(self._on_cleanup_toggle)
        self.ll_slider.valueChanged.connect(self._on_cleanup_ll)
        self.dn_slider.valueChanged.connect(self._on_cleanup_dn)
        self.eye_chk.toggled.connect(self._on_eye_toggle)
        self.eye_slider.valueChanged.connect(self._on_eye_strength)
        self.autoframe_chk.toggled.connect(self._on_autoframe)
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        self.vig_slider.valueChanged.connect(self._on_vignette)
        self.denoise_chk.toggled.connect(self._on_denoise)
        self.audio.changed.connect(self._on_denoise_changed)
        self.audio.error.connect(self._on_error)

        c = self.controller
        c.frameReady.connect(self._on_frame)
        c.stats.connect(self._on_stats)
        c.statusText.connect(self._on_status_text)
        c.runningChanged.connect(self._on_running)
        c.error.connect(self._on_error)

    # ---- settings persistence ---------------------------------------------
    def _restore(self):
        s = self.settings
        self.blur_slider.setValue(int(s.value("blur", 14)))
        self.glow_slider.setValue(int(s.value("studio_glow", 100)))
        self.warmth_slider.setValue(int(s.value("studio_warmth", 0)))
        self.vig_slider.setValue(int(s.value("vignette", 0)))
        self.zoom_slider.setValue(int(s.value("zoom", 115)))
        self.realism_chk.setChecked(s.value("realism", True, type=bool))
        self.relight_chk.setChecked(s.value("relight", True, type=bool))
        self.relight_slider.setValue(int(s.value("relight_strength", 60)))
        self.relight_box.setVisible(self.relight_chk.isChecked())
        self.cleanup_chk.setChecked(s.value("cleanup", False, type=bool))
        self.ll_slider.setValue(int(s.value("cleanup_ll", 60)))
        self.dn_slider.setValue(int(s.value("cleanup_dn", 50)))
        self.cleanup_box.setVisible(self.cleanup_chk.isChecked())
        self.eye_chk.setChecked(s.value("eyecontact", False, type=bool))
        self.eye_slider.setValue(int(s.value("eyecontact_strength", 50)))
        self.eye_box.setVisible(self.eye_chk.isChecked())
        self.autoframe_chk.setChecked(s.value("autoframe", False, type=bool))
        {"balanced": self.q_bal, "best": self.q_best, "ultra": self.q_ultra}.get(
            s.value("quality", "best"), self.q_best).setChecked(True)
        self._mode = s.value("mode", "blur")
        self._last_image = s.value("image", "")
        self.mode_buttons.get(self._mode, self.mode_buttons["blur"]).setChecked(True)
        self._show_mode_panels(self._mode)

    def _persist(self):
        s = self.settings
        s.setValue("blur", self.blur_slider.value())
        s.setValue("studio_glow", self.glow_slider.value())
        s.setValue("studio_warmth", self.warmth_slider.value())
        s.setValue("vignette", self.vig_slider.value())
        s.setValue("zoom", self.zoom_slider.value())
        s.setValue("realism", self.realism_chk.isChecked())
        s.setValue("relight", self.relight_chk.isChecked())
        s.setValue("relight_strength", self.relight_slider.value())
        s.setValue("cleanup", self.cleanup_chk.isChecked())
        s.setValue("cleanup_ll", self.ll_slider.value())
        s.setValue("cleanup_dn", self.dn_slider.value())
        s.setValue("eyecontact", self.eye_chk.isChecked())
        s.setValue("eyecontact_strength", self.eye_slider.value())
        s.setValue("autoframe", self.autoframe_chk.isChecked())
        s.setValue("quality", self._quality_key())
        s.setValue("mode", self._mode)
        s.setValue("image", self._last_image)

    def _quality_key(self):
        if self.q_ultra.isChecked():
            return "ultra"
        return "balanced" if self.q_bal.isChecked() else "best"

    def _apply_all(self):
        """Push every current UI value to a freshly-started processor."""
        c = self.controller
        c.set_quality(self._quality_key())
        c.set_realism(self.realism_chk.isChecked())
        c.set_relight(self.relight_chk.isChecked())
        c.set_relight_strength(self.relight_slider.value() / 100.0)
        c.set_cleanup(self.cleanup_chk.isChecked())
        c.set_cleanup_strength(self.ll_slider.value() / 100.0)
        c.set_cleanup_denoise(self.dn_slider.value() / 100.0)
        c.set_eyecontact(self.eye_chk.isChecked())
        c.set_eyecontact_strength(self.eye_slider.value() / 100.0)
        c.set_autoframe(self.autoframe_chk.isChecked())
        c.set_zoom(self.zoom_slider.value() / 100.0)
        c.set_vignette(self.vig_slider.value() / 100.0)
        c.set_blur(float(self.blur_slider.value()))
        c.set_studio_glow(self.glow_slider.value() / 100.0)
        c.set_studio_warmth(self.warmth_slider.value() / 100.0)
        if self._mode == "color":
            c.set_color(self._last_color)
        elif self._mode == "image" and self._last_image:
            c.set_image(self._last_image)
        c.set_mode(self._mode)

    # ---- slots ------------------------------------------------------------
    @QtCore.Slot()
    def _toggle(self):
        if self.controller.is_running():
            self.controller.stop()
        else:
            self.start_btn.setEnabled(False)
            self.controller.start()

    def _on_mode(self, key):
        self._mode = key
        self._show_mode_panels(key)
        self.controller.set_mode(key)
        self._persist()

    def _show_mode_panels(self, key):
        self.blur_box.setVisible(key == "blur")
        self.color_box.setVisible(key == "color")
        self.image_box.setVisible(key == "image")
        self.studio_box.setVisible(key == "studio")

    def _on_blur(self, v):
        self.blur_label.setText(f"Blur strength · {v}")
        self.controller.set_blur(float(v))
        self._persist()

    def _on_color(self, c):
        self._last_color = c
        self.controller.set_color(c)

    def _on_glow(self, v):
        self.glow_label.setText(f"Studio glow · {v}%")
        self.controller.set_studio_glow(v / 100.0)
        self._persist()

    def _on_warmth(self, v):
        tag = "neutral" if v == 0 else (f"warm +{v}" if v > 0 else f"cool {v}")
        self.warmth_label.setText(f"Warmth · {tag}")
        self.controller.set_studio_warmth(v / 100.0)
        self._persist()

    def _on_realism(self, on):
        self.controller.set_realism(on)
        self._persist()

    def _on_relight_toggle(self, on):
        self.relight_box.setVisible(on)
        self.controller.set_relight(on)
        self._persist()

    def _on_relight_strength(self, v):
        self.relight_label.setText(f"Light intensity · {v}%")
        self.controller.set_relight_strength(v / 100.0)
        self._persist()

    def _on_cleanup_toggle(self, on):
        self.cleanup_box.setVisible(on)
        self.controller.set_cleanup(on)
        self._persist()

    def _on_cleanup_ll(self, v):
        self.ll_label.setText(f"Low-light · {v}%")
        self.controller.set_cleanup_strength(v / 100.0)
        self._persist()

    def _on_cleanup_dn(self, v):
        self.dn_label.setText(f"Denoise · {v}%")
        self.controller.set_cleanup_denoise(v / 100.0)
        self._persist()

    def _on_eye_toggle(self, on):
        self.eye_box.setVisible(on)
        self.controller.set_eyecontact(on)
        self._persist()

    def _on_eye_strength(self, v):
        self.eye_label.setText(f"Gaze strength · {v}%")
        self.controller.set_eyecontact_strength(v / 100.0)
        self._persist()

    def _on_autoframe(self, on):
        self.zoom_box.setVisible(on)
        self.controller.set_autoframe(on)
        self._persist()

    def _on_zoom(self, v):
        self.controller.set_zoom(v / 100.0)
        self._persist()

    def _on_vignette(self, v):
        self.vig_label.setText(f"Vignette · {v}%" if v else "Vignette")
        self.controller.set_vignette(v / 100.0)
        self._persist()

    def _on_quality(self, key):
        self.controller.set_quality(key)
        self._persist()

    def _choose_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose background image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self._last_image = path
            self.controller.set_image(path)
            self._persist()

    @QtCore.Slot(QtGui.QImage)
    def _on_frame(self, img):
        pix = QtGui.QPixmap.fromImage(img).scaled(
            self.preview.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pix)

    @QtCore.Slot(float, float)
    def _on_stats(self, fps, ms):
        self.status.setText(f"● Running · {fps:.0f} fps · {ms:.1f} ms/frame")

    @QtCore.Slot(str)
    def _on_status_text(self, text):
        if text != "Running":
            self.status.setText(text)
            if text not in ("Stopped",):
                self.preview.setText(text)

    @QtCore.Slot(bool)
    def _on_running(self, running):
        self.start_btn.setEnabled(True)
        if running:
            self._apply_all()   # push saved/current settings to the fresh processor
        self.start_btn.setText("Stop Camera" if running else "Start Camera")
        self.start_btn.setProperty("running", "true" if running else "false")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if not running:
            self.status.setText("○ Stopped")
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("Press Start")

    def _on_denoise(self, on):
        self.denoise_chk.setEnabled(False)
        self.denoise_chk.setText("Remove background noise  (starting…)" if on
                                 else "Remove background noise  (stopping…)")
        self.audio.set_enabled(on)

    @QtCore.Slot(bool)
    def _on_denoise_changed(self, running):
        self.denoise_chk.blockSignals(True)
        self.denoise_chk.setChecked(running)
        self.denoise_chk.blockSignals(False)
        self.denoise_chk.setEnabled(True)
        self.denoise_chk.setText(
            "Remove background noise  ✓" if running else "Remove background noise")

    @QtCore.Slot(str)
    def _on_error(self, msg):
        self.start_btn.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "NVBroadcast", msg)

    # ---- close-to-tray ----------------------------------------------------
    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.hide()
