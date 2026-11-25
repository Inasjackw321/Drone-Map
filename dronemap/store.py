"""SQLite message store. Raw posts are kept so the whole picture can be rebuilt at any time."""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawMessage:
    channel: str
    msg_id: int
    ts: float
    text: str


class Store:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS messages (
                channel TEXT NOT NULL, msg_id INTEGER NOT NULL, ts REAL NOT NULL, text TEXT NOT NULL,
                fetched REAL NOT NULL, PRIMARY KEY (channel, msg_id))""")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts)")
            # long-term history for the heatmap: one row per observed position (see Fusion.heat_points)
            self._db.execute("""CREATE TABLE IF NOT EXISTS heat (
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, family TEXT NOT NULL, threat TEXT NOT NULL,
                ts REAL NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, place TEXT, oblast TEXT,
                weight REAL NOT NULL, confirmed INTEGER NOT NULL)""")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_heat_ts ON heat(ts)")
            self._db.commit()
        self.revision = 0

    def upsert(self, msgs: list[RawMessage]) -> int:
        """Insert new messages / update edited ones. Returns how many rows changed."""
        changed = 0
        now = time.time()
        with self._lock:
            cur = self._db.cursor()
            for m in msgs:
                row = cur.execute("SELECT text FROM messages WHERE channel=? AND msg_id=?",
                                  (m.channel, m.msg_id)).fetchone()
                if row is None:
                    cur.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (m.channel, m.msg_id, m.ts, m.text, now))
                    changed += 1
                elif row[0] != m.text:
                    cur.execute("UPDATE messages SET text=?, fetched=? WHERE channel=? AND msg_id=?",
                                (m.text, now, m.channel, m.msg_id))
                    changed += 1
            self._db.commit()
        if changed:
            self.revision += 1
        return changed

    def since(self, ts: float) -> list[RawMessage]:
        with self._lock:
            rows = self._db.execute("SELECT channel, msg_id, ts, text FROM messages WHERE ts >= ? ORDER BY ts",
                                    (ts,)).fetchall()
        return [RawMessage(*r) for r in rows]

    def last_id(self, channel: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT MAX(msg_id) FROM messages WHERE channel=?", (channel,)).fetchone()
        return row[0] or 0

    def prune(self, older_than: float) -> None:
        with self._lock:
            self._db.execute("DELETE FROM messages WHERE ts < ?", (older_than,))
            self._db.commit()

    # ------------------------------------------------------------------ heatmap history
    def add_heat(self, rows: list[dict]) -> None:
        """Insert observed positions; a row that is already there keeps the most specific type."""
        if not rows:
            return
        with self._lock:
            self._db.executemany(
                """INSERT INTO heat VALUES (:key,:kind,:family,:threat,:ts,:lat,:lon,:place,:oblast,:weight,:confirmed)
                   ON CONFLICT(key) DO UPDATE SET threat=excluded.threat, weight=excluded.weight,
                   place=excluded.place, oblast=excluded.oblast, confirmed=MAX(confirmed, excluded.confirmed)""",
                rows)
            self._db.commit()

    def heat_since(self, ts: float, confirmed_only: bool = True) -> list[tuple]:
        """(kind, family, threat, ts, lat, lon, place, oblast, weight) rows newer than ts."""
        q = "SELECT kind, family, threat, ts, lat, lon, place, oblast, weight FROM heat WHERE ts >= ?"
        if confirmed_only:
            q += " AND confirmed = 1"
        with self._lock:
            return self._db.execute(q + " ORDER BY ts", (ts,)).fetchall()

    def heat_first_ts(self) -> float | None:
        with self._lock:
            row = self._db.execute("SELECT MIN(ts) FROM heat").fetchone()
        return row[0]

    def prune_heat(self, older_than: float) -> None:
        with self._lock:
            self._db.execute("DELETE FROM heat WHERE ts < ?", (older_than,))
            self._db.commit()

    def first_ts(self) -> float | None:
        with self._lock:
            row = self._db.execute("SELECT MIN(ts) FROM messages").fetchone()
        return row[0]

    def oldest_id_since(self, channel: str, ts: float) -> int | None:
        """The oldest stored post of a channel that is newer than ts."""
        with self._lock:
            row = self._db.execute("SELECT MIN(msg_id) FROM messages WHERE channel=? AND ts >= ?",
                                   (channel, ts)).fetchone()
        return row[0]

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM messages")
            self._db.commit()
        self.revision += 1
