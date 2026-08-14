"""Phase 0 self-test: prove the virtual camera actually emits real frames.

Runs the passthrough pipeline in a background thread for a couple of seconds,
opens the loopback device as a *consumer* (like Zoom would), and checks that the
frames coming out are non-blank and change over time (i.e. live, not a freeze).
"""
from __future__ import annotations

import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, __file__.rsplit("/", 2)[0])  # project root

from daemon.config import Config
from daemon.pipeline import Pipeline


def main() -> int:
    cfg = Config()
    pipe = Pipeline(cfg)
    t = threading.Thread(target=pipe.run, daemon=True)
    t.start()
    time.sleep(2.0)  # let capture+output warm up

    # Open the loopback the way a consumer app would. Try by-path then by-index,
    # with a couple of retries while the producer starts streaming.
    idx = int("".join(ch for ch in cfg.out_device if ch.isdigit()) or "0")
    cap = None
    for target in (cfg.out_device, idx):
        for _ in range(5):
            c = cv2.VideoCapture(target, cv2.CAP_V4L2)
            if c.isOpened():
                cap = c
                break
            c.release()
            time.sleep(0.3)
        if cap is not None:
            break
    if cap is None:
        print(f"FAIL: cannot open loopback {cfg.out_device} as consumer")
        pipe.stop()
        return 1

    frames = []
    t_end = time.time() + 2.0
    while time.time() < t_end:
        ok, f = cap.read()
        if ok and f is not None:
            frames.append(f)
    cap.release()
    pipe.stop()
    time.sleep(0.3)

    if len(frames) < 5:
        print(f"FAIL: only read {len(frames)} frames from loopback")
        return 1

    means = [float(f.mean()) for f in frames]
    diffs = [
        float(np.abs(frames[i].astype(np.int16) - frames[i - 1]).mean())
        for i in range(1, len(frames))
    ]
    live = max(diffs) > 1.0          # content changes -> not frozen
    nonblank = np.mean(means) > 5.0  # not an all-black feed

    print(f"read {len(frames)} frames | mean brightness {np.mean(means):.1f} "
          f"| max interframe delta {max(diffs):.2f}")
    if live and nonblank:
        print("PASS: loopback carries a live, non-blank feed")
        return 0
    print(f"FAIL: live={live} nonblank={nonblank}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
