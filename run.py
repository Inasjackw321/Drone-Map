#!/usr/bin/env python3
"""Start Drone Map.

    python run.py            # live: reads the Telegram channels
    python run.py --demo     # demo: replays a scripted attack night, no network needed
"""
import argparse
import logging
import os
import socket
import threading
import webbrowser

import uvicorn

from dronemap.engine import Config
from dronemap.server import create_app


def lan_ip() -> str | None:
    """This computer's address on the local network (for opening the map on a phone)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))        # no packet is sent; this only picks the interface
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Drone Map - live air-threat map from Telegram channels")
    ap.add_argument("--demo", action="store_true", help="replay a scripted scenario instead of live data")
    ap.add_argument("--host", default=os.environ.get("DRONEMAP_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", os.environ.get("DRONEMAP_PORT", "8000"))))
    ap.add_argument("--source", choices=["web", "telethon", "both"], default=None,
                    help="where to read Telegram from (default: web preview)")
    ap.add_argument("--no-browser", action="store_true", default=bool(os.environ.get("DRONEMAP_NO_BROWSER")),
                    help="do not open the map in a browser on start")
    ap.add_argument("--log", default="info")
    args = ap.parse_args()

    logging.basicConfig(level=args.log.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)       # one line per channel fetch is too noisy
    cfg = Config.from_env(mode="demo" if args.demo else None, source=args.source)

    local_url = f"http://localhost:{args.port}"

    def on_ready() -> None:
        lines = ["", "  Drone Map is running" + (" (demo data)" if args.demo else ""),
                 f"  Open in your browser:  {local_url}"]
        ip = lan_ip() if args.host in ("0.0.0.0", "::") else None
        if ip:
            lines.append(f"  On a phone (same Wi-Fi): http://{ip}:{args.port}")
        lines += ["  Keep this window open. Press Ctrl+C to stop.", ""]
        print("\n".join(lines), flush=True)
        if not args.no_browser:
            threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()

    uvicorn.run(create_app(cfg, on_ready=on_ready), host=args.host, port=args.port, log_level=args.log,
                proxy_headers=True)


if __name__ == "__main__":
    main()
