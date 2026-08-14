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

    # Output (v4l2loopback virtual camera)
    out_device: str = "/dev/video10"

    # Pipeline
    mirror: bool = False  # horizontal flip (selfie view)
    log_every: int = 60   # frames between FPS log lines
