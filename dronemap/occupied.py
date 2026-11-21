"""Occupied territory of Ukraine (DeepState map), from the daily mirror at github.com/cyterat/deepstate-map-data.

Fetched at run time and cached in data/occupied.geojson, so the map still shows the last known
line when offline. Coordinates are rounded to ~100 m to keep the payload small.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger("dronemap.occupied")

URL = "https://raw.githubusercontent.com/cyterat/deepstate-map-data/main/data/deepstatemap_data_{date}.geojson"
REFRESH_S = 6 * 3600


def _round(coords, nd=3):
    if isinstance(coords[0], (list, tuple)):
        return [_round(c, nd) for c in coords]
    return [round(coords[0], nd), round(coords[1], nd)]


class Occupied:
    def __init__(self, cache_path: str = "data/occupied.geojson"):
        self.path = Path(cache_path)
        self.data: dict = {"type": "FeatureCollection", "features": [], "date": None}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass

    async def fetch_once(self, client: httpx.AsyncClient) -> bool:
        today = datetime.now(timezone.utc).date()
        for back in range(0, 10):
            day = today - timedelta(days=back)
            if self.data.get("date") == day.isoformat():
                return True                                      # already have the newest file
            try:
                r = await client.get(URL.format(date=day.strftime("%Y%m%d")))
            except httpx.HTTPError as e:
                log.warning("occupied areas: %s", e)
                return False
            if r.status_code == 404:
                continue
            if r.status_code != 200:
                log.warning("occupied areas: HTTP %s", r.status_code)
                return False
            src = r.json()
            feats = [{"type": "Feature", "properties": {},
                      "geometry": {"type": f["geometry"]["type"], "coordinates": _round(f["geometry"]["coordinates"])}}
                     for f in src.get("features", []) if f.get("geometry")]
            self.data = {"type": "FeatureCollection", "features": feats, "date": day.isoformat(),
                         "source": "DeepState via github.com/cyterat/deepstate-map-data"}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, separators=(",", ":")), encoding="utf-8")
            log.info("occupied areas updated (%s)", day)
            return True
        return False

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            while True:
                ok = await self.fetch_once(client)
                await asyncio.sleep(REFRESH_S if ok else 900)

    def updated(self) -> float:
        return self.path.stat().st_mtime if self.path.exists() else time.time()
