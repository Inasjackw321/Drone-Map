"""Optional second source: reads channels through the Telegram API with Telethon.

Use it for channels whose web preview is disabled, or for lower latency.
Enable by setting TG_API_ID and TG_API_HASH (from https://my.telegram.org) and running
`python -m dronemap.telethon_login` once to create the session file.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .store import RawMessage, Store

log = logging.getLogger("dronemap.telethon")


class TelethonSource:
    def __init__(self, api_id: int, api_hash: str, session: str, channels: list[dict], store: Store,
                 on_change, status: dict, backfill_hours: float = 3.0, select=None):
        self.api_id, self.api_hash, self.session = api_id, api_hash, session
        self.channels = channels
        self.store = store
        self.on_change = on_change
        self.status = status            # shared SourceStatus dict from the web scraper
        self.backfill_s = backfill_hours * 3600
        # select(status) -> list of handles to read this round; default: every channel
        self.select = select or (lambda status: [c["handle"] for c in channels])
        self.stopped = False

    async def run(self) -> None:
        try:
            from telethon import TelegramClient  # type: ignore
            from telethon.errors import FloodWaitError  # type: ignore
        except ImportError:
            log.error("telethon is not installed: pip install telethon")
            return
        client = TelegramClient(self.session, self.api_id, self.api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            log.error("Telethon session is not authorised. Run: python -m dronemap.telethon_login")
            return
        log.info("Telethon source connected")
        entities: dict[str, object] = {}
        while not self.stopped:
            handles = self.select(self.status)
            for h in handles:
                if h in self.status:
                    self.status[h].via = "telegram-api"
            for h in handles:
                st = self.status.get(h)
                try:
                    if h not in entities:
                        entities[h] = await client.get_entity(h)
                    min_id = self.store.last_id(h)
                    msgs = []
                    async for m in client.iter_messages(entities[h], limit=50, min_id=min_id):
                        if not m.message:
                            continue
                        ts = m.date.timestamp()
                        if ts < time.time() - self.backfill_s:
                            break
                        msgs.append(RawMessage(h, m.id, ts, m.message))
                    if msgs and self.store.upsert(msgs):
                        self.on_change()
                    if st:
                        st.state, st.error, st.failures, st.last_ok = "ok", None, 0, time.time()
                        st.last_fetch = time.time()
                        if msgs:
                            st.last_post_ts = max(m.ts for m in msgs)
                except FloodWaitError as e:
                    log.warning("flood wait %ss", e.seconds)
                    await asyncio.sleep(min(e.seconds, 300))
                except Exception as e:  # noqa: BLE001
                    if st:
                        st.state, st.error = "error", f"{type(e).__name__}: {e}"[:200]
                        st.failures += 1
                await asyncio.sleep(0.4)
            await asyncio.sleep(5)
        await client.disconnect()
