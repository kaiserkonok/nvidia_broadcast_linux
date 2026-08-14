"""Mic-denoise control: toggles the DeepFilterNet virtual microphone.

Independent of the video pipeline — it just starts/stops the PipeWire
filter-chain via scripts/mic_denoise.sh. Runs the (slightly slow) start/stop off
the GUI thread and reports state back via Qt signals.
"""
from __future__ import annotations

import os
import subprocess
import threading

from PySide6 import QtCore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "mic_denoise.sh")


class AudioController(QtCore.QObject):
    changed = QtCore.Signal(bool)     # denoise running?
    error = QtCore.Signal(str)

    def is_running(self) -> bool:
        try:
            r = subprocess.run([SCRIPT, "status"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() == "running"
        except (OSError, subprocess.SubprocessError):
            return False

    def set_enabled(self, on: bool):
        threading.Thread(target=self._apply, args=(on,), daemon=True).start()

    def _apply(self, on: bool):
        try:
            r = subprocess.run([SCRIPT, "start" if on else "stop"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            self.error.emit(str(e))
            self.changed.emit(self.is_running())
            return
        running = self.is_running()
        if on and not running:
            self.error.emit((r.stderr or r.stdout or "Failed to start mic denoise").strip()[-300:])
        self.changed.emit(running)
