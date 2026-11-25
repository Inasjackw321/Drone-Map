"""Orchestrates sources -> store -> parser -> fusion and keeps the latest snapshot."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .fusion import MsgRef, build_fusion
from .gazetteer import OBLAST_NAMES
from .occupied import Occupied
from .parser import THREATS, ParsedMessage, parse_message
from .scraper import SourceStatus, WebScraper
from .store import Store

log = logging.getLogger("dronemap.engine")

HERE = Path(__file__).parent


@dataclass
class Config:
    mode: str = "live"                    # live | demo
    db_path: str = "data/dronemap.db"
    channels_path: str = str(HERE / "channels.json")
    window_hours: float = 4.0             # replay window for the picture
    keep_hours: float = 48.0              # raw messages are kept this long
    history_hours: float = 24.0           # on start, read this far back for the heatmap (0 = off)
    heat_days: float = 28.0               # the heatmap keeps observed positions this long
    poll_scale: float = 1.0
    source: str = "web"                   # web | telethon | both
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session: str = "data/dronemap"

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        c = cls(
            mode=os.environ.get("DRONEMAP_MODE", "live"),
            db_path=os.environ.get("DRONEMAP_DB", "data/dronemap.db"),
            channels_path=os.environ.get("DRONEMAP_CHANNELS", str(HERE / "channels.json")),
            window_hours=float(os.environ.get("DRONEMAP_WINDOW_HOURS", "4")),
            history_hours=float(os.environ.get("DRONEMAP_HISTORY_HOURS", "24")),
            heat_days=float(os.environ.get("DRONEMAP_HEAT_DAYS", "28")),
            poll_scale=float(os.environ.get("DRONEMAP_POLL_SCALE", "1")),
            source=os.environ.get("DRONEMAP_SOURCE", "web"),
            tg_api_id=int(os.environ["TG_API_ID"]) if os.environ.get("TG_API_ID") else None,
            tg_api_hash=os.environ.get("TG_API_HASH") or None,
            tg_session=os.environ.get("TG_SESSION", "data/dronemap"),
        )
        for k, v in overrides.items():
            if v is not None:
                setattr(c, k, v)
        return c


def load_channels(path: str) -> tuple[list[dict], dict, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tiers = data["tiers"]
    seen, channels = set(), []
    for ch in data["channels"]:
        h = ch["handle"].lstrip("@")
        if h.lower() in seen:
            continue
        seen.add(h.lower())
        ch = {**ch, "handle": h}
        ch.setdefault("name", None)
        ch.setdefault("regions", [])
        channels.append(ch)
    return channels, tiers, {k: v["weight"] for k, v in tiers.items()}


@dataclass
class Engine:
    cfg: Config
    channels: list[dict] = field(default_factory=list)
    tiers: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)

    def __post_init__(self):
        self.channels, self.tiers, self.weights = load_channels(self.cfg.channels_path)
        self.by_handle = {c["handle"]: c for c in self.channels}
        self.store = Store(":memory:" if self.cfg.mode == "demo" else self.cfg.db_path)
        self.status: dict[str, SourceStatus] = {c["handle"]: SourceStatus(c["handle"], c["tier"]) for c in self.channels}
        self._dirty = asyncio.Event()
        self._parse_cache: dict[tuple, ParsedMessage] = {}
        self.snapshot: dict = {"version": 0, "tracks": [], "events": [], "alerts": [], "banners": [], "feed": [],
                               "stats": {}, "generated_at": time.time(), "mode": self.cfg.mode}
        self.version = 0
        self._last_hash = ""
        self.last_rebuild_ms = 0.0
        self.started = time.time()
        self._tasks: list[asyncio.Task] = []
        db_dir = Path(self.cfg.db_path).parent if self.cfg.db_path != ":memory:" else Path("data")
        self.occupied = Occupied(str(db_dir / "occupied.geojson"))
        self.update = {"current": __version__, "latest": None, "available": False}

    # ----------------------------------------------------------------- rebuild
    def notify(self) -> None:
        self._dirty.set()

    def parse(self, channel: str, msg_id: int, text: str) -> ParsedMessage:
        key = (channel, msg_id, hashlib.md5(text.encode()).hexdigest())
        p = self._parse_cache.get(key)
        if p is None:
            ch = self.by_handle.get(channel, {})
            p = parse_message(text, ch.get("regions", []), ch.get("tier", "aggregator"))
            self._parse_cache[key] = p
        return p

    def rebuild(self, now: float | None = None) -> dict:
        t0 = time.perf_counter()
        now = now or time.time()
        window = self.cfg.window_hours * 3600
        long_window = max(window, 12 * 3600)              # alert state needs the whole alert history
        msgs = [m for m in self.store.since(now - long_window)
                if m.ts >= now - window or self.by_handle.get(m.channel, {}).get("alerts")]
        items = []
        live_keys = set()
        for m in msgs:
            if m.channel not in self.by_handle:
                continue
            tier = self.by_handle[m.channel]["tier"]
            parsed = self.parse(m.channel, m.msg_id, m.text)
            live_keys.add((m.channel, m.msg_id, hashlib.md5(m.text.encode()).hexdigest()))
            items.append((MsgRef(m.channel, m.msg_id, m.ts, tier, m.text), parsed))
        if len(self._parse_cache) > 2 * max(1000, len(live_keys)):
            self._parse_cache = {k: v for k, v in self._parse_cache.items() if k in live_keys}
        fusion = build_fusion(items, self.by_handle, self.weights, now)
        snap = fusion.snapshot(now)
        digest = hashlib.md5(json.dumps({k: snap[k] for k in ("tracks", "events", "alerts", "banners", "feed")},
                                        sort_keys=True, default=str).encode()).hexdigest()
        if digest != self._last_hash:
            self.version += 1
            self._last_hash = digest
            self.store.add_heat(fusion.heat_points())
        snap.update({"version": self.version, "generated_at": now, "mode": self.cfg.mode,
                     "messages_in_window": len(items), "app": self.update})
        self.snapshot = snap
        self.last_rebuild_ms = (time.perf_counter() - t0) * 1000
        return snap

    # ----------------------------------------------------------------- heatmap history
    def replay_history(self, hours: float | None = None) -> int:
        """Replay every stored post (not only the live window) into the heatmap history.

        Runs on start and after the scraper has read further back. The live rebuild only covers the
        last few hours, so this is what fills the heatmap with posts read while the map was closed.
        """
        t0 = time.perf_counter()
        since = time.time() - (hours or self.cfg.keep_hours) * 3600
        items = []
        for m in self.store.since(since):
            ch = self.by_handle.get(m.channel)
            if ch is None:
                continue
            parsed = parse_message(m.text, ch.get("regions", []), ch.get("tier", "aggregator"))
            items.append((MsgRef(m.channel, m.msg_id, m.ts, ch["tier"], m.text), parsed))
        rows = build_fusion(items, self.by_handle, self.weights).heat_points()
        self.store.add_heat(rows)
        log.info("heatmap: replayed %d posts into %d positions in %.1fs", len(items), len(rows),
                 time.perf_counter() - t0)
        return len(rows)

    async def replay_history_async(self) -> None:
        try:
            await asyncio.to_thread(self.replay_history)
        except Exception:                              # noqa: BLE001
            log.exception("heatmap replay failed")

    def heatmap_view(self, hours: float, kind: str = "all", tz_offset_min: int = 0,
                     confirmed_only: bool = True) -> dict:
        """Heatmap cells plus the numbers behind them, for the last `hours`.

        kind: all (drones, missiles and guided bombs) | drone | missile | kab | explosion
        tz_offset_min: the viewer's Date.getTimezoneOffset(), so daily bars start at local midnight.
        """
        now = time.time()
        since = now - hours * 3600
        families = {"all": ("drone", "missile", "kab"), "drone": ("drone",), "missile": ("missile",),
                    "kab": ("kab",)}.get(kind)
        rows = []
        for r in self.store.heat_since(since, confirmed_only):
            if kind == "explosion" and r[0] == "explosion":
                rows.append(r)
            elif families and r[0] == "track" and r[1] in families:
                rows.append(r)

        step = 3600 if hours <= 48 else 86400
        shift = -tz_offset_min * 60                   # local time = UTC + shift
        def bucket(ts: float) -> int:
            return int((ts + shift) // step * step - shift)
        series: dict[int, dict[str, int]] = {}
        b = bucket(since)
        while b <= now:
            series[b] = {}
            b += step

        cells: dict[tuple[float, float], list] = {}
        by_threat: dict[str, int] = {}
        by_oblast: dict[str, int] = {}
        by_place: dict[tuple[str, str], list] = {}
        for _kind, family, threat, ts, lat, lon, place, oblast, weight in rows:
            key = (round(lat, 3), round(lon, 3))
            c = cells.setdefault(key, [key[0], key[1], 0.0])
            c[2] += weight
            label = family if kind in ("all", "explosion") else threat
            s = series.setdefault(bucket(ts), {})
            s[label] = s.get(label, 0) + 1
            if threat:
                by_threat[threat] = by_threat.get(threat, 0) + 1
            if oblast:
                by_oblast[oblast] = by_oblast.get(oblast, 0) + 1
            pk = (place or "", oblast or "")
            pe = by_place.setdefault(pk, [0, lat, lon])
            pe[0] += 1

        weights = sorted(c[2] for c in cells.values())
        # saturate at a high percentile: a few hot spots must not wash out the rest, and a busy night
        # must not paint the whole country white
        scale = weights[min(len(weights) - 1, int(len(weights) * 0.97))] if weights else 1.0
        first = self.store.heat_first_ts()
        top_places = sorted(by_place.items(), key=lambda kv: -kv[1][0])[:10]
        return {
            "hours": hours, "kind": kind, "from": since, "to": now, "step": step,
            "history_since": first, "partial": first is None or first > since + hours * 360,
            "observations": len(rows), "places": len(cells), "scale": max(1.0, scale),
            "points": [[c[0], c[1], round(c[2], 2)] for c in cells.values()],
            "series": [{"t": t, **v} for t, v in sorted(series.items()) if since - step < t <= now],
            "by_threat": [{"threat": k, "label": THREATS.get(k, {}).get("label", k), "n": n}
                          for k, n in sorted(by_threat.items(), key=lambda kv: -kv[1])],
            "by_oblast": [{"oblast": k, "name": OBLAST_NAMES.get(k, k), "n": n}
                          for k, n in sorted(by_oblast.items(), key=lambda kv: -kv[1])[:10]],
            "top_places": [{"place": p, "oblast": OBLAST_NAMES.get(o, o), "n": v[0],
                            "lat": round(v[1], 4), "lon": round(v[2], 4)} for (p, o), v in top_places],
        }

    async def _rebuild_loop(self) -> None:
        last_prune = 0.0
        while True:
            try:
                await asyncio.wait_for(self._dirty.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            self._dirty.clear()
            await asyncio.sleep(0.3)                  # debounce bursts of incoming posts
            try:
                await asyncio.to_thread(self.rebuild)
            except Exception:                          # noqa: BLE001
                log.exception("rebuild failed")
            if time.time() - last_prune > 3600:
                self.store.prune(time.time() - self.cfg.keep_hours * 3600)
                self.store.prune_heat(time.time() - (self.cfg.heat_days + 2) * 86400)
                last_prune = time.time()

    async def _update_loop(self) -> None:
        """Tell the user when main on GitHub has a newer version than the one running."""
        if os.environ.get("DRONEMAP_NO_UPDATE_CHECK"):
            return
        url = os.environ.get("DRONEMAP_UPDATE_URL",
                             "https://raw.githubusercontent.com/Inasjackw321/Drone-Map/main/dronemap/__init__.py")
        import re
        import httpx
        as_tuple = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
        while True:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(url)
                m = re.search(r'__version__\s*=\s*"([\d.]+)"', r.text) if r.status_code == 200 else None
                if m:
                    latest = m.group(1)
                    self.update = {"current": __version__, "latest": latest,
                                   "available": as_tuple(latest) > as_tuple(__version__)}
                    if self.update["available"]:
                        log.warning("A newer Drone Map (%s) is available: run start.bat / start.sh or git pull", latest)
            except Exception as e:  # noqa: BLE001 - never let the update check disturb the map
                log.debug("update check failed: %s", e)
            await asyncio.sleep(6 * 3600)

    # ----------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        loop_tasks = [self._rebuild_loop(), self.occupied.run(), self._update_loop()]
        if self.cfg.mode == "demo":
            from .demo import DemoSource, demo_history
            self.store.add_heat(demo_history(self.by_handle, self.weights, days=int(self.cfg.heat_days)))
            loop_tasks.append(DemoSource(self.store, self.notify, self.status).run())
        else:
            loop_tasks.append(self.replay_history_async())     # posts kept from earlier runs
            use_tg = self.cfg.source in ("telethon", "both") and self.cfg.tg_api_id and self.cfg.tg_api_hash
            if self.cfg.source in ("web", "both") or not use_tg:
                scraper = WebScraper(self.channels, self.store, self.notify, self.cfg.poll_scale,
                                     backfill_hours=min(self.cfg.window_hours, 4),
                                     history_hours=min(self.cfg.history_hours, self.cfg.keep_hours),
                                     on_history=self.replay_history_async)
                scraper.status = self.status
                now = time.time()
                for i, st in enumerate(self.status.values()):
                    st.next_due = now + i * 0.3
                loop_tasks.append(scraper.run())
            if use_tg:
                from .telethon_source import TelethonSource
                def no_preview_only(status):
                    # web preview first; the API covers channels whose preview is disabled
                    return [h for h, st in status.items() if st.state == "no_preview" or st.via == "telegram-api"]
                loop_tasks.append(TelethonSource(self.cfg.tg_api_id, self.cfg.tg_api_hash, self.cfg.tg_session,
                                                 self.channels, self.store, self.notify, self.status,
                                                 select=no_preview_only if self.cfg.source == "both" else None).run())
        self.rebuild()
        self._tasks = [asyncio.create_task(c) for c in loop_tasks]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()

    # ----------------------------------------------------------------- views
    def sources_view(self) -> dict:
        groups = []
        for key, tier in sorted(self.tiers.items(), key=lambda kv: kv[1].get("order", 9)):
            rows = []
            for c in self.channels:
                if c["tier"] != key:
                    continue
                st = self.status[c["handle"]]
                rows.append({**st.as_dict(), "name": c.get("name"), "area": c.get("area")})
            groups.append({"tier": key, "label": tier["label"], "description": tier["description"],
                           "weight": tier["weight"], "channels": rows})
        return {"groups": groups, "mode": self.cfg.mode}

    def health(self) -> dict:
        states: dict[str, int] = {}
        for st in self.status.values():
            states[st.state] = states.get(st.state, 0) + 1
        newest = max((st.last_ok or 0 for st in self.status.values()), default=0)
        return {"ok": True, "mode": self.cfg.mode, "version": self.version, "app": self.update, "uptime_s": round(time.time() - self.started),
                "sources": states, "channels": len(self.channels), "last_source_ok": newest or None,
                "rebuild_ms": round(self.last_rebuild_ms, 1),
                "messages_in_window": self.snapshot.get("messages_in_window", 0)}
