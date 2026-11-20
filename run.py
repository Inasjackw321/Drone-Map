#!/usr/bin/env python3
"""Start Drone Map.

    python run.py            # live: reads the Telegram channels
    python run.py --demo     # demo: replays a scripted attack night, no network needed
"""
import argparse
import logging
import os

import uvicorn

from dronemap.engine import Config
from dronemap.server import create_app


def main() -> None:
    ap = argparse.ArgumentParser(description="Drone Map - live air-threat map from Telegram channels")
    ap.add_argument("--demo", action="store_true", help="replay a scripted scenario instead of live data")
    ap.add_argument("--host", default=os.environ.get("DRONEMAP_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", os.environ.get("DRONEMAP_PORT", "8000"))))
    ap.add_argument("--source", choices=["web", "telethon", "both"], default=None,
                    help="where to read Telegram from (default: web preview)")
    ap.add_argument("--log", default="info")
    args = ap.parse_args()

    logging.basicConfig(level=args.log.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)       # one line per channel fetch is too noisy
    cfg = Config.from_env(mode="demo" if args.demo else None, source=args.source)
    uvicorn.run(create_app(cfg), host=args.host, port=args.port, log_level=args.log, proxy_headers=True)


if __name__ == "__main__":
    main()
