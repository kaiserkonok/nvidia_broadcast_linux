"""Launch the web control panel:  python -m ui  ->  http://localhost:8080"""
from __future__ import annotations

import argparse

from daemon.config import Config

from .server import Engine, create_app


def main():
    p = argparse.ArgumentParser(prog="ui", description="NVBroadcast-linux control panel")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8137)  # 8080 is often taken
    p.add_argument("--cam", default=None, help="override capture device")
    p.add_argument("--out", default=None, help="override loopback device")
    args = p.parse_args()

    cfg = Config()
    if args.cam:
        cfg.cam_device = args.cam
    if args.out:
        cfg.out_device = args.out
    cfg.mirror = True  # selfie view feels natural in a preview

    engine = Engine(cfg)
    engine.start()
    app = create_app(engine)
    print(f"\n  Control panel:  http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
