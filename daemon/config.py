"""Runtime configuration for the video pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    # Capture (physical webcam)
    cam_device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = "MJPG"  # webcam delivers MJPG at 720p30
    # V4L2 driver buffers. Must be >=2: with MJPG a single buffer can't capture
    # frame N+1 while we hold N, which silently halves the rate to 15fps. The
    # threaded grabber drains continuously, so 2 keeps latency low with no loss.
    buffersize: int = 2

    # Output (v4l2loopback virtual camera)
    out_device: str = "/dev/video10"

    # Pipeline
    mirror: bool = False  # horizontal flip (selfie view)
    log_every: int = 60   # frames between FPS log lines
