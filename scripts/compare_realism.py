"""Eyeball the Phase 2 realism pass: naive composite vs realism, side by side.

Captures real webcam frames, warms up the recurrent matte, then renders the same
frame with realism OFF and ON for a few backgrounds and writes comparison PNGs.
"""
from __future__ import annotations

import os
import subprocess
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from daemon.config import Config
from daemon.matting import Matting
from daemon.compositor import Compositor

OUT = "/tmp/claude-1000/-home-kaiserkonok-computer-programming-nvidiabroadcast/9b60fd29-3f0a-40ee-a99a-93404611d3d5/scratchpad"


def grab(n=45):
    subprocess.run(["pkill", "-f", "python -m app"], check=False)
    subprocess.run(["pkill", "-f", "python -m ui"], check=False)
    subprocess.run(["v4l2-ctl", "-d", "/dev/video0", "-c", "auto_exposure=3"], check=False)
    cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    frames = []
    for _ in range(n):
        ok, bgr = cap.read()
        if ok:
            frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def to_bgr(t):  # (3,H,W) float -> HWC uint8 BGR
    a = (t.clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).cpu().numpy())
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)


def gradient_bg(h=720, w=1280):
    top = np.array([28, 42, 70]); bot = np.array([210, 150, 90])  # RGB
    ramp = np.linspace(0, 1, h)[:, None, None]
    img = (top * (1 - ramp) + bot * ramp).astype(np.uint8)
    img = np.repeat(img, w, axis=1)
    cv2.imwrite(f"{OUT}/scene_bg.png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return f"{OUT}/scene_bg.png"


def main():
    frames = grab()
    if len(frames) < 10:
        print("FAIL: could not grab webcam frames"); return 1
    print(f"grabbed {len(frames)} frames")

    mat = Matting("models/weights/rvm_mobilenetv3.pth")
    for f in frames[:-1]:            # warm up recurrent state
        mat.infer(_up(f, mat))
    src = _up(frames[-1], mat)
    fgr, pha = mat.infer(src)
    src3 = src[0]

    comp = Compositor()
    cases = [
        ("green", lambda c: c.set_color((0, 177, 64))),
        ("warm",  lambda c: c.set_color((220, 150, 90))),
        ("scene", lambda c: c.set_image(gradient_bg())),
    ]
    for name, setup in cases:
        setup(comp)
        comp.realism = False
        naive = to_bgr(comp.composite(fgr, pha, src3))
        comp.realism = True
        comp._pha_prev = None
        real = to_bgr(comp.composite(fgr, pha, src3))
        bar = np.full((naive.shape[0], 6, 3), 40, np.uint8)
        cv2.imwrite(f"{OUT}/realism_{name}.png", np.hstack([naive, bar, real]))
    print(f"wrote comparisons to {OUT} (left = naive, right = realism)")
    return 0


def _up(rgb, mat):
    t = torch.from_numpy(rgb).to(mat.device).permute(2, 0, 1).unsqueeze(0).float().div_(255.0)
    return t


if __name__ == "__main__":
    raise SystemExit(main())
