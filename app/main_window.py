"""NVBroadcast main window (Qt).

Live preview on the left, controls on the right. Talks only to a
PipelineController via signals/slots — no video/GPU code lives here.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .pipeline_controller import PipelineController

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
    def __init__(self, controller: PipelineController):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("NVBroadcast")
        self.setWindowIcon(QtGui.QIcon.fromTheme("camera-web"))
        self.resize(1024, 600)
        self.setStyleSheet(STYLE)
        self._allow_close = False

        self._build_ui()
        self._wire()

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
        modes = QtWidgets.QHBoxLayout()
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.mode_buttons = {}
        for label, key in [("Off", "none"), ("Blur", "blur"),
                           ("Color", "color"), ("Image", "image")]:
            b = QtWidgets.QPushButton(label)
            b.setCheckable(True)
            if key == "blur":
                b.setChecked(True)
            self.mode_group.addButton(b)
            self.mode_buttons[key] = b
            b.clicked.connect(lambda _=False, k=key: self._on_mode(k))
            modes.addWidget(b)
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
            sw.clicked.connect(lambda _=False, col_=c: self.controller.set_color(col_))
            cg.addWidget(sw, i // 4, i % 4)
        col.addWidget(self.color_box)

        # image picker
        self.image_box = QtWidgets.QWidget()
        ib = QtWidgets.QVBoxLayout(self.image_box)
        ib.setContentsMargins(0, 0, 0, 0)
        self.image_btn = QtWidgets.QPushButton("Choose image…")
        ib.addWidget(self.image_btn)
        col.addWidget(self.image_box)

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

        c = self.controller
        c.frameReady.connect(self._on_frame)
        c.stats.connect(self._on_stats)
        c.statusText.connect(self._on_status_text)
        c.runningChanged.connect(self._on_running)
        c.error.connect(self._on_error)

    # ---- slots ------------------------------------------------------------
    @QtCore.Slot()
    def _toggle(self):
        if self.controller.is_running():
            self.controller.stop()
        else:
            self.start_btn.setEnabled(False)
            self.controller.start()

    def _on_mode(self, key):
        self._show_mode_panels(key)
        self.controller.set_mode(key)

    def _show_mode_panels(self, key):
        self.blur_box.setVisible(key == "blur")
        self.color_box.setVisible(key == "color")
        self.image_box.setVisible(key == "image")

    def _on_blur(self, v):
        self.blur_label.setText(f"Blur strength · {v}")
        self.controller.set_blur(float(v))

    def _choose_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose background image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.controller.set_image(path)

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
        self.start_btn.setText("Stop Camera" if running else "Start Camera")
        self.start_btn.setProperty("running", "true" if running else "false")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        if not running:
            self.status.setText("○ Stopped")
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("Press Start")

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
