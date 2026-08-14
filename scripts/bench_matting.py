"""Benchmark the matting processor on real webcam frames + dump before/after.

Reports steady-state ms/frame (after warmup) and equivalent FPS, and writes
sample images to scratch so edge quality can be eyeballed.
"""
from __future__ import annotations

import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from daemon.config import Config
from daemon.processor import MattingProcessor

OUT_DIR = "/tmp/claude-1000/-home-kaiserkonok-computer-programming-nvidiabroadcast/9b60fd29-3f0a-40ee-a99a-93404611d3d5/scratchpad"


def grab_frames(cfg: Config, n: int):
    cap = cv2.VideoCapture(cfg.cam_device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cfg.fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    frames = []
    for _ in range(n):
        ok, bgr = cap.read()
        if ok:
            frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def save_rgb(name, rgb):
    cv2.imwrite(f"{OUT_DIR}/{name}", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def main():
    cfg = Config()
    frames = grab_frames(cfg, 80)
    if len(frames) < 20:
        print(f"FAIL: only grabbed {len(frames)} webcam frames")
        return 1
    print(f"grabbed {len(frames)} frames @ {frames[0].shape[1]}x{frames[0].shape[0]}")

    mp = MattingProcessor()

    # warmup (cudnn autotune, lazy alloc) — feed the recurrent net a few frames
    for f in frames[:15]:
        mp.process(f)
    torch.cuda.synchronize()

    # timed run
    times = []
    for f in frames[15:]:
        t = time.perf_counter()
        out = mp.process(f)
        torch.cuda.synchronize()
        times.append((time.perf_counter() - t) * 1000.0)
    times = np.array(times)
    print(f"blur bg: {times.mean():5.2f} ms/frame "
          f"(p50 {np.percentile(times,50):.2f}, p95 {np.percentile(times,95):.2f}) "
          f"-> {1000.0/times.mean():.1f} fps")

    # dump before/after for eyeballing
    ref = frames[-1]
    save_rgb("bench_before.png", ref)
    mp.set_blur(14.0)
    save_rgb("bench_after_blur.png", mp.process(ref))
    mp.set_color((0, 177, 64))   # chroma-green to expose spill/edges harshly
    save_rgb("bench_after_green.png", mp.process(ref))
    print(f"wrote before/after images to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
