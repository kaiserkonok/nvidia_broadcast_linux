"""Entry point:  python -m daemon [options]

Phase 0: passthrough webcam -> virtual camera.
"""
from __future__ import annotations

import argparse

from .config import Config
from .pipeline import Pipeline
from .processor import Passthrough

WEIGHTS = "models/weights/rvm_mobilenetv3.pth"


def build_processor(args):
    if args.mode == "none":
        return Passthrough()
    from .processor import MattingProcessor

    mp = MattingProcessor(WEIGHTS, downsample_ratio=args.downsample)
    if args.mode == "blur":
        mp.set_blur(args.blur_sigma)
    elif args.mode == "image":
        if not args.bg:
            raise SystemExit("--mode image requires --bg <path>")
        mp.set_image(args.bg)
    elif args.mode == "color":
        mp.set_color(tuple(int(c) for c in args.color.split(",")))
    return mp


def main():
    cfg = Config()
    p = argparse.ArgumentParser(prog="daemon", description="NVBroadcast-linux video pipeline")
    p.add_argument("--cam", default=cfg.cam_device, help="capture device")
    p.add_argument("--out", default=cfg.out_device, help="v4l2loopback output device")
    p.add_argument("--width", type=int, default=cfg.width)
    p.add_argument("--height", type=int, default=cfg.height)
    p.add_argument("--fps", type=int, default=cfg.fps)
    p.add_argument("--mirror", action="store_true", help="horizontal flip (selfie)")
    p.add_argument("--mode", choices=["none", "blur", "image", "color"],
                   default="blur", help="background mode")
    p.add_argument("--blur-sigma", type=float, default=14.0)
    p.add_argument("--bg", default=None, help="background image path (mode=image)")
    p.add_argument("--color", default="30,30,30", help="R,G,B for mode=color")
    p.add_argument("--downsample", type=float, default=0.25,
                   help="RVM downsample_ratio (0.25 for 720p, 0.375 for lower res)")
    args = p.parse_args()

    cfg.cam_device = args.cam
    cfg.out_device = args.out
    cfg.width, cfg.height, cfg.fps = args.width, args.height, args.fps
    cfg.mirror = args.mirror

    Pipeline(cfg, build_processor(args)).run()


if __name__ == "__main__":
    main()
