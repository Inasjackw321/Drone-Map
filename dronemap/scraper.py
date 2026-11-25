"""Reads public Telegram channels through the web preview at https://t.me/s/<channel>.

No account or API key is needed. Every channel is polled on its own schedule with jitter,
exponential back-off on errors, a global rate limiter and Retry-After handling for 429s.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from .store import RawMessage, Store

log = logging.getLogger("dronemap.scraper")

# lxml is faster, but Python's built-in parser works everywhere
HTML_PARSER = "lxml" if importlib.util.find_spec("lxml") else "html.parser"

BASE = "https://t.me/s/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept-Language": "uk,ru;q=0.8,en;q=0.6",
}
POLL_SECONDS = {"official": 20, "recon": 30, "regional": 40, "aggregator": 75}


@dataclass
class SourceStatus:
    handle: str
    tier: str
    state: str = "pending"          # pending | ok | error | no_preview
    last_fetch: float | None = None
    last_ok: float | None = None
    last_post_ts: float | None = None
    posts_seen: int = 0
    error: str | None = None
    failures: int = 0
    next_due: float = field(default=0.0)
    via: str = "web"
    newest_id: int = 0

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("handle", "tier", "state", "last_fetch", "last_ok", "last_post_ts",
                                               "posts_seen", "error", "via")}


def parse_channel_html(html: str, channel: str) -> tuple[list[RawMessage], bool]:
    """Return (messages, has_preview)."""
    soup = BeautifulSoup(html, HTML_PARSER)
    if soup.select_one(".tgme_channel_history") is None and soup.select_one(".tgme_widget_message") is None:
        return [], False
    out: list[RawMessage] = []
    for wrap in soup.select(".tgme_widget_message[data-post]"):
        post = wrap.get("data-post", "")
        if "/" not in post:
            continue
        try:
            msg_id = int(post.rsplit("/", 1)[1])
        except ValueError:
            continue
        if "service_message" in (wrap.get("class") or []):
            continue
        t_el = wrap.select_one(".tgme_widget_message_date time[datetime]") or wrap.select_one("time[datetime]")
        if t_el is None:
            continue
        try:
            ts = datetime.fromisoformat(t_el["datetime"].replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        txt_el = wrap.select_one(".tgme_widget_message_text")
        if txt_el is None:
            continue
        for br in txt_el.find_all("br"):
            br.replace_with("\n")
        text = txt_el.get_text().strip()
        if text:
            out.append(RawMessage(channel, msg_id, ts, text))
    return out, True


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval

    def penalize(self, seconds: float) -> None:
        self._next = max(self._next, time.monotonic() + seconds)


class WebScraper:
    def __init__(self, channels: list[dict], store: Store, on_change, poll_scale: float = 1.0,
                 backfill_hours: float = 3.0, concurrency: int = 6, rate: float = 2.5,
                 history_hours: float = 0.0, on_history=None, history_rate: float = 0.7,
                 history_pages: int = 12):
        self.store = store
        self.on_change = on_change
        self.poll_scale = poll_scale
        self.backfill_s = backfill_hours * 3600
        self.history_s = history_hours * 3600
        self.on_history = on_history
        self.history_limiter = RateLimiter(history_rate)
        self.history_pages = history_pages
        self.sem = asyncio.Semaphore(concurrency)
        self.limiter = RateLimiter(rate)
        self.status: dict[str, SourceStatus] = {}
        now = time.time()
        for i, ch in enumerate(channels):
            st = SourceStatus(ch["handle"], ch["tier"])
            st.next_due = now + i * 0.3          # stagger the first round
            self.status[ch["handle"]] = st
        self._client: httpx.AsyncClient | None = None
        self.stopped = False
        self._warned = 0

    def _interval(self, st: SourceStatus) -> float:
        base = POLL_SECONDS.get(st.tier, 60) * self.poll_scale
        if st.state == "no_preview":
            return 30 * 60
        if st.failures:
            return min(600.0, base * (2 ** min(st.failures, 5)))
        return base * random.uniform(0.85, 1.15)

    async def _get(self, url: str) -> httpx.Response:
        await self.limiter.wait()
        assert self._client is not None
        return await self._client.get(url)

    async def fetch_channel(self, st: SourceStatus) -> None:
        async with self.sem:
            st.last_fetch = time.time()
            try:
                r = await self._get(BASE + st.handle)
                if r.status_code == 429:
                    wait = float(r.headers.get("Retry-After", "30") or 30)
                    self.limiter.penalize(min(wait, 120))
                    raise RuntimeError(f"rate limited ({wait:.0f}s)")
                if r.status_code in (301, 302) or (r.status_code == 200 and "/s/" not in str(r.url)):
                    st.state, st.error, st.failures = "no_preview", "channel has web preview disabled", 0
                    return
                r.raise_for_status()
                msgs, has_preview = parse_channel_html(r.text, st.handle)
                if not has_preview:
                    st.state, st.error, st.failures = "no_preview", "channel has web preview disabled or is private", 0
                    return
                # first run: page back until we cover the backfill window
                if st.last_ok is None and msgs:
                    pages = 0
                    while pages < 3 and min(m.ts for m in msgs) > time.time() - self.backfill_s:
                        before = min(m.msg_id for m in msgs)
                        r2 = await self._get(f"{BASE}{st.handle}?before={before}")
                        if r2.status_code != 200:
                            break
                        older, _ = parse_channel_html(r2.text, st.handle)
                        if not older:
                            break
                        msgs = older + msgs
                        pages += 1
                if msgs:
                    st.newest_id = max(st.newest_id, max(m.msg_id for m in msgs))
                cutoff = time.time() - self.backfill_s
                msgs = [m for m in msgs if m.ts >= cutoff]
                changed = self.store.upsert(msgs)
                st.posts_seen = max(st.posts_seen, len(msgs))
                if msgs:
                    st.last_post_ts = max(m.ts for m in msgs)
                st.state, st.error, st.failures, st.last_ok = "ok", None, 0, time.time()
                if changed:
                    self.on_change()
            except Exception as e:  # noqa: BLE001 - one bad channel must never stop the others
                st.failures += 1
                st.state = "error"
                st.error = f"{type(e).__name__}: {e}"[:200]
                if st.failures == 1:
                    self._warned += 1
                    if self._warned <= 3:
                        log.warning("could not read @%s: %s", st.handle, st.error)
            finally:
                st.next_due = time.time() + self._interval(st)

    def summary(self) -> str:
        states = [st.state for st in self.status.values() if st.via == "web"]
        ok, err = states.count("ok"), states.count("error")
        nop = states.count("no_preview")
        text = f"read {ok} of {len(states)} channels"
        if nop:
            text += f", {nop} without web preview"
        if err:
            text += f", {err} failing"
        return text

    async def _report(self) -> None:
        """Say in the terminal how the first round went, and keep warning while nothing works."""
        while any(st.state == "pending" for st in self.status.values() if st.via == "web"):
            await asyncio.sleep(2)
        log.info("Telegram: %s", self.summary())
        while not self.stopped:
            states = [st for st in self.status.values() if st.via == "web"]
            if states and not any(st.state == "ok" for st in states):
                errs = [st.error for st in states if st.error]
                log.error("Telegram cannot be reached (%s). Is t.me blocked on this network or by a VPN/"
                          "firewall? Open https://t.me/s/kpszsu in your browser to check.", errs[0] if errs else "?")
            await asyncio.sleep(300)

    async def _history_channel(self, st: SourceStatus, cutoff: float) -> int:
        """Page one channel back to `cutoff`, stopping early at posts that are already stored."""
        before = self.store.oldest_id_since(st.handle, time.time() - self.backfill_s - 600)
        if before is None and st.newest_id:
            before = st.newest_id + 1                   # quiet channel: nothing in the live window
        added = 0
        for _ in range(self.history_pages):
            if not before or self.stopped:
                break
            await self.history_limiter.wait()
            r = await self._get(f"{BASE}{st.handle}?before={before}")
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "30") or 30)
                self.limiter.penalize(min(wait, 120))
                self.history_limiter.penalize(min(wait, 120) * 2)
                break
            if r.status_code != 200:
                break
            older, _ = parse_channel_html(r.text, st.handle)
            older = [m for m in older if m.msg_id < before]
            if not older:
                break
            keep = [m for m in older if m.ts >= cutoff]
            changed = self.store.upsert(keep)
            added += changed
            if len(keep) < len(older) or (keep and not changed):
                break                                   # reached the cutoff, or history we already have
            before = min(m.msg_id for m in older)
        return added

    async def backfill_history(self) -> None:
        """After the first live round, quietly read further back so the heatmap covers the last day.

        Uses its own slow rate on top of the shared limiter, so live polling keeps priority.
        """
        if self.history_s <= self.backfill_s:
            return
        while any(st.state == "pending" for st in self.status.values() if st.via == "web"):
            await asyncio.sleep(2)
        await asyncio.sleep(5)
        order = {"official": 0, "recon": 1, "regional": 2, "aggregator": 3}
        total = 0
        for st in sorted(self.status.values(), key=lambda s: order.get(s.tier, 9)):
            if self.stopped:
                return
            if st.via != "web" or st.state != "ok":
                continue
            try:
                total += await self._history_channel(st, time.time() - self.history_s)
            except Exception as e:  # noqa: BLE001
                log.debug("history for @%s failed: %s", st.handle, e)
        log.info("heatmap: read %d older posts (last %.0f h)", total, self.history_s / 3600)
        if self.on_history is not None and total:
            await self.on_history()

    async def run(self) -> None:
        asyncio.create_task(self._report())
        asyncio.create_task(self.backfill_history())
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True,
                                     limits=httpx.Limits(max_connections=8)) as client:
            self._client = client
            running: set[asyncio.Task] = set()
            while not self.stopped:
                now = time.time()
                for st in self.status.values():
                    if st.next_due <= now and st.via == "web" and not any(t.get_name() == st.handle for t in running):
                        st.next_due = now + 3600       # reserved until the fetch reschedules it
                        task = asyncio.create_task(self.fetch_channel(st), name=st.handle)
                        running.add(task)
                        task.add_done_callback(running.discard)
                await asyncio.sleep(0.5)
