#!/usr/bin/env python3
"""NVBroadcast system-tray applet (the desktop app).

Runs with the SYSTEM python3 (needs gi/Gtk/AppIndicator, which live outside the
venv). It is intentionally lightweight: it does NOT import torch/cv2. It manages
the heavy video pipeline as a child process (the venv `python -m ui`) and
controls it over the pipeline's HTTP API — start/stop the camera, switch the
background, open the full control panel.

Start = spawn the pipeline (which grabs the webcam and produces the virtual
camera). Stop = terminate it (releasing the webcam). This mirrors how NVIDIA
Broadcast lives in the tray and only uses the camera while active.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
PORT = int(os.environ.get("NVB_PORT", "8137"))
BASE = f"http://127.0.0.1:{PORT}"
UI_LOG = "/tmp/nvbroadcast_ui.log"

MODES = [("Off", "none"), ("Blur", "blur"), ("Color", "color"), ("Image", "image")]


class Tray:
    def __init__(self, auto_start: bool = True):
        self.proc: subprocess.Popen | None = None
        self.mode = "blur"
        self.fps = 0.0

        self.ind = AppIndicator.Indicator.new(
            "nvbroadcast",
            "camera-web",  # themed icon present on this system
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("NVBroadcast")

        self.menu = Gtk.Menu()
        self._build_menu()
        self.ind.set_menu(self.menu)

        # Auto-start after the icon is up (defer so the tray appears instantly).
        if auto_start:
            GLib.timeout_add(200, self._startup)

    # ---- menu -------------------------------------------------------------
    def _build_menu(self):
        self.status_item = Gtk.MenuItem(label="○ Stopped")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.toggle_item = Gtk.MenuItem(label="Start Camera")
        self.toggle_item.connect("activate", self.on_toggle)
        self.menu.append(self.toggle_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        bg = Gtk.MenuItem(label="Background")
        submenu = Gtk.Menu()
        self.mode_items = {}
        group = None
        for label, key in MODES:
            item = Gtk.RadioMenuItem(label=label, group=group)
            group = item
            if key == self.mode:
                item.set_active(True)
            item.connect("activate", self.on_mode, key)
            submenu.append(item)
            self.mode_items[key] = item
        bg.set_submenu(submenu)
        self.menu.append(bg)

        panel = Gtk.MenuItem(label="Open Control Panel…")
        panel.connect("activate", self.on_open_panel)
        self.menu.append(panel)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()

    # ---- startup / camera readiness ---------------------------------------
    def _startup(self):
        # Make sure the virtual camera is usable. If it needs the one-time
        # terminal setup (kernel reload w/ sudo), say so instead of failing mute.
        if self._ensure_camera():
            self.start_pipeline()
            GLib.timeout_add(1000, self._poll_status)
        else:
            self.status_item.set_label("⚠ Run ./scripts/run_ui.sh once")
            self.toggle_item.set_label("Start Camera")
        return False  # one-shot

    def _ensure_camera(self) -> bool:
        try:
            r = subprocess.run(
                [os.path.join(PROJECT_ROOT, "scripts", "setup_camera.sh")],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
            )
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # ---- pipeline process -------------------------------------------------
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start_pipeline(self):
        if self.running():
            return
        # kill any stray instances so we own the webcam
        subprocess.run(["pkill", "-f", "python -m ui"], check=False)
        subprocess.run(["pkill", "-f", "python -m daemon"], check=False)
        log = open(UI_LOG, "w")
        self.proc = subprocess.Popen(
            [VENV_PY, "-m", "ui", "--port", str(PORT)],
            cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT,
        )

    def stop_pipeline(self):
        if self.proc is not None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    # ---- actions ----------------------------------------------------------
    def on_toggle(self, _):
        if self.running():
            self.stop_pipeline()
        elif self._ensure_camera():
            self.start_pipeline()
        else:
            self.status_item.set_label("⚠ Run ./scripts/run_ui.sh once")
            return
        self._refresh_labels()

    def on_mode(self, item, key):
        if not item.get_active():
            return
        self.mode = key
        self._api_post("/api/mode", {"mode": key})

    def on_open_panel(self, _):
        subprocess.Popen(["xdg-open", BASE])

    def on_quit(self, _):
        self.stop_pipeline()
        Gtk.main_quit()

    # ---- status -----------------------------------------------------------
    def _poll_status(self):
        if self.running():
            st = self._api_get("/api/status")
            if st:
                self.fps = st.get("fps", 0.0)
                mode = "none" if not st.get("enabled", True) else st.get("mode", self.mode)
                if mode in self.mode_items and not self.mode_items[mode].get_active():
                    self.mode_items[mode].set_active(True)
        self._refresh_labels()
        return True  # keep polling

    def _refresh_labels(self):
        if self.running():
            self.status_item.set_label(f"● Running · {self.fps:.0f} fps")
            self.toggle_item.set_label("Stop Camera")
            self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        else:
            self.status_item.set_label("○ Stopped")
            self.toggle_item.set_label("Start Camera")

    # ---- tiny HTTP client -------------------------------------------------
    def _api_get(self, path):
        try:
            with urllib.request.urlopen(BASE + path, timeout=0.8) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def _api_post(self, path, body):
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                BASE + path, data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=0.8)
        except (urllib.error.URLError, OSError):
            pass


def main():
    import sys
    check = "--check" in sys.argv
    Tray(auto_start=not check)
    if check:
        # Build UI, then quit shortly — validates the tray without the pipeline.
        GLib.timeout_add(1200, Gtk.main_quit)
        print("tray --check: indicator + menu built OK")
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
