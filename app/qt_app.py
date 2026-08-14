"""NVBroadcast desktop app: window + system tray, one process.

The whole app (GUI, tray, and the GPU pipeline in a worker thread) runs in the
venv Python. Closing the window hides to tray; Quit really exits.
"""
from __future__ import annotations

import os
import signal
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6 import QtGui, QtWidgets  # noqa: E402

from .main_window import MainWindow  # noqa: E402
from .pipeline_controller import PipelineController  # noqa: E402


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("NVBroadcast")
    app.setQuitOnLastWindowClosed(False)  # closing the window hides to tray
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    controller = PipelineController()
    win = MainWindow(controller)

    # ---- system tray ------------------------------------------------------
    icon = QtGui.QIcon.fromTheme("camera-web")
    tray = QtWidgets.QSystemTrayIcon(icon, app)
    tray.setToolTip("NVBroadcast")
    menu = QtWidgets.QMenu()
    act_show = menu.addAction("Show / Hide")
    act_toggle = menu.addAction("Stop Camera")  # label tracks running state
    menu.addSeparator()
    act_quit = menu.addAction("Quit")
    tray.setContextMenu(menu)
    tray.setVisible(True)

    def toggle_window():
        if win.isVisible():
            win.hide()
        else:
            win.showNormal()
            win.raise_()
            win.activateWindow()

    def on_tray_activated(reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            toggle_window()

    def on_toggle_camera():
        if controller.is_running():
            controller.stop()
        else:
            controller.start()

    def on_running_changed(running):
        act_toggle.setText("Stop Camera" if running else "Start Camera")

    def do_quit():
        controller.stop()
        win._allow_close = True
        tray.hide()
        app.quit()

    act_show.triggered.connect(toggle_window)
    act_toggle.triggered.connect(on_toggle_camera)
    act_quit.triggered.connect(do_quit)
    tray.activated.connect(on_tray_activated)
    controller.runningChanged.connect(on_running_changed)

    win.show()

    if os.environ.get("NVB_SMOKE"):
        # Build everything and exit shortly, without the pipeline — for testing.
        from PySide6 import QtCore
        QtCore.QTimer.singleShot(1200, app.quit)
        print("qt smoke: window + tray built OK")
        sys.exit(app.exec())

    controller.start()  # auto-start, like opening NVIDIA Broadcast
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
