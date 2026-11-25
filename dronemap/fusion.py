"""Fuse parsed messages from many channels into tracks, events and alerts.

The whole picture is rebuilt by replaying the recent message window in time order.
That makes the result deterministic, robust to channels being polled at different times
(out-of-order arrival), to edited posts, and to restarts.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .gazetteer import GAZETTEER, OBLAST_NAMES, angle_diff, bearing, haversine
from .parser import THREATS, AreaEvent, ParsedMessage, PlaceRef, Sighting  # noqa: F401

# How long after the last report a new report can still continue the same track (minutes)
ASSOC_WINDOW = {"drone": 50, "missile": 15, "kab": 10, "ballistic": 6, "kinzhal": 6, "jet_shahed": 30}
# speed used for gating; ballistic reports never chain far, so they are not gated at their physical speed
GATE_SPEED = {"ballistic": 1200, "kinzhal": 1200}
# A track turns "stale" (faded on the map) after this many minutes without reports
STALE_AFTER = {"drone": 30, "missile": 15, "kab": 8, "ballistic": 6, "kinzhal": 6, "recon": 40,
               "lancet": 25, "fpv": 15, "molniya": 20, "jet_shahed": 20}
# ...and is removed after this many minutes
DROP_AFTER = {k: v * 2.5 for k, v in STALE_AFTER.items()}
# tracks silent for longer than this can no longer change (keeps long replays fast)
OPEN_HORIZON_MIN = max(DROP_AFTER.values())
ENDED_VISIBLE_MIN = 10
EVENT_TTL_MIN = {"explosion": 45, "kill": 30, "threat": 20}
BANNER_TTL_MIN = 40
ALERT_TTL_MIN = 6 * 60

DEFAULT_WEIGHTS = {"official": 0.9, "recon": 0.7, "regional": 0.55, "aggregator": 0.15}


def _lookup(table: dict, threat: str) -> float:
    return table.get(threat, table.get(THREATS[threat]["family"], 30))


def compatibility(a: str, b: str) -> float | None:
    """Penalty for merging two threat types into one track, or None if they cannot be the same object."""
    if a == b:
        return 0.0
    fa, fb = THREATS[a]["family"], THREATS[b]["family"]
    if fa != fb:
        return None
    pair = {a, b}
    if pair & {"uav", "missile"}:
        return 0.15
    if pair <= {"shahed", "gerbera"}:
        return 0.3
    if pair <= {"shahed", "jet_shahed"}:
        return 0.4
    if pair <= {"ballistic", "kinzhal"}:
        return 0.3
    return None


@dataclass
class TrackPoint:
    ts: float
    lat: float
    lon: float
    precision: str   # point | region | origin | inbound
    label: str
    oblast: str
    channel: str

    def as_dict(self) -> dict:
        return {"ts": self.ts, "lat": round(self.lat, 4), "lon": round(self.lon, 4),
                "precision": self.precision, "place": self.label}


@dataclass
class MsgRef:
    channel: str
    msg_id: int
    ts: float
    tier: str
    text: str


@dataclass
class Track:
    id: str
    threat: str
    first_ts: float
    last_ts: float
    points: list[TrackPoint] = field(default_factory=list)
    count: int | None = None
    group: bool = False
    dest: PlaceRef | None = None
    dest_ts: float = 0.0
    origin: PlaceRef | None = None
    heading: float | None = None
    heading_ts: float = 0.0
    sources: dict[str, str] = field(default_factory=dict)
    refs: list[MsgRef] = field(default_factory=list)
    ended: str | None = None
    ended_ts: float | None = None
    destroyed: int = 0

    @property
    def family(self) -> str:
        return THREATS[self.threat]["family"]

    @property
    def last(self) -> TrackPoint:
        return self.points[-1]

    def dest_reached(self) -> bool:
        """The reported destination no longer says where the target is going."""
        if self.dest is None:
            return False
        last = self.last
        seen_since = last.ts > self.dest_ts             # a later report, not the one that named the destination
        if haversine(last.lat, last.lon, self.dest.lat, self.dest.lon) < (12 if seen_since else 5):
            return True
        # "курсом на Чернігівщину" is done once the target is later seen inside that region:
        # a bearing to the region's centre point would then point anywhere, even backwards.
        # ("на південь Сумщини" names a part of the region and keeps its own point.)
        whole_region = self.dest.precision == "region" and self.dest.label == self.dest.place.name
        return whole_region and seen_since and last.precision == "point" and last.oblast == self.dest.place.oblast

    def motion(self) -> tuple[float, float] | None:
        """(bearing, time) of the flown path: from the last observed fix back to one at least 10 km away.

        A longer baseline than the last hop keeps the direction steady when two channels name
        neighbouring villages for the same position.
        """
        last = self.last
        if last.precision not in ("point", "region"):
            return None
        for prev in reversed(self.points[:-1]):
            if prev.precision == "inbound":
                continue
            d = haversine(prev.lat, prev.lon, last.lat, last.lon)
            need = 10 if prev.precision == "point" and last.precision == "point" else 40
            if d >= need and last.ts - prev.ts <= 90 * 60:
                return bearing(prev.lat, prev.lon, last.lat, last.lon), last.ts
        return None

    def heading_info(self) -> tuple[float | None, str | None]:
        """Where the target is going and why we think so: 'dest', 'reported' or 'track'.

        The newest report of intent wins (a destination or a course like "курс північно-західний").
        If the target has since been seen moving clearly the other way, the flown path wins,
        so an icon never keeps pointing back at a place the target already passed.
        """
        last = self.last
        cands: list[tuple[float, int, float, str]] = []      # ts, priority, heading, source
        if self.dest is not None and not self.dest_reached() and \
                haversine(last.lat, last.lon, self.dest.lat, self.dest.lon) > 5:
            cands.append((self.dest_ts, 1, bearing(last.lat, last.lon, self.dest.lat, self.dest.lon), "dest"))
        if self.heading is not None and self.heading_ts >= self.last_ts - 20 * 60:
            cands.append((self.heading_ts, 0, self.heading, "reported"))
        mot = self.motion()
        pick = max(cands) if cands else None
        if mot is not None:
            m_hdg, m_ts = mot
            if pick is None or (m_ts > pick[0] + 30 and angle_diff(m_hdg, pick[2]) > 100):
                return m_hdg, "track"
        if pick is not None:
            return pick[2], pick[3]
        if self.origin is not None and haversine(self.origin.lat, self.origin.lon, last.lat, last.lon) > 30:
            return bearing(self.origin.lat, self.origin.lon, last.lat, last.lon), "track"
        return None, None

    def heading_estimate(self) -> float | None:
        return self.heading_info()[0]

    def add_point(self, p: TrackPoint) -> None:
        if not self.points:
            self.points.append(p)
            return
        last = self.points[-1]
        if last.precision == "inbound" and p.precision != "inbound":
            self.points[-1] = p          # replace a guessed position with a real one
            return
        if p.precision in ("region", "origin") and last.precision == "point" and \
                haversine(last.lat, last.lon, p.lat, p.lon) < 130:
            return                        # coarse report refreshes the track but does not move it back
        if haversine(last.lat, last.lon, p.lat, p.lon) < 3:
            if p.precision == "point" and last.precision != "point":
                self.points[-1] = p
            return
        self.points.append(p)


class Fusion:
    def __init__(self, channels: dict[str, dict], weights: dict[str, float] | None = None):
        self.channels = channels
        self.weights = weights or DEFAULT_WEIGHTS
        self.tracks: list[Track] = []
        self._open: list[Track] = []          # tracks that can still receive reports
        self._pruned_at = 0.0
        self.events: list[dict] = []
        self.alerts: dict[str, dict] = {}
        self.banners: list[dict] = []
        self.feed: list[dict] = []
        self._last_threat: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------------ helpers
    def _tier(self, channel: str) -> str:
        return self.channels.get(channel, {}).get("tier", "aggregator")

    @staticmethod
    def _tid(channel: str, msg_id: int, idx: int, threat: str) -> str:
        return hashlib.sha1(f"{channel}/{msg_id}/{idx}/{threat}".encode()).hexdigest()[:10]

    def _prune(self, ts: float) -> None:
        if ts - self._pruned_at < 300:
            return
        self._pruned_at = ts
        self._open = [t for t in self._open if t.ended is None and ts - t.last_ts <= OPEN_HORIZON_MIN * 60]

    def _active(self, ts: float):
        for t in self._open:
            window = _lookup(ASSOC_WINDOW, t.threat)
            if t.points and t.last.precision in ("origin", "inbound"):
                window = min(window, 20)        # a launch area or a bare "heading to X" goes cold quickly
            if t.ended is None and ts - t.last_ts <= window * 60 and ts >= t.last_ts - 300:
                yield t

    @staticmethod
    def _point(ref: PlaceRef, ts: float, channel: str, precision: str | None = None) -> TrackPoint:
        return TrackPoint(ts, ref.lat, ref.lon, precision or ref.precision, ref.label, ref.place.oblast, channel)

    # ------------------------------------------------------------------ association
    def _cost(self, t: Track, s: Sighting, pos: PlaceRef, ts: float) -> float | None:
        comp = compatibility(t.threat, s.threat)
        if comp is None:
            return None
        last = t.last
        if last.precision == "inbound" and comp > 0.15:
            return None                        # never seen yet: do not guess across drone types
        dt_h = max(0.0, ts - t.last_ts) / 3600
        d = haversine(last.lat, last.lon, pos.lat, pos.lon)
        sp = lambda k: GATE_SPEED.get(k, THREATS[k]["speed"])  # noqa: E731
        # a generic report ("ракета") cannot borrow the speed of a more specific track (ballistic)
        speed = min(sp(t.threat), sp(s.threat)) if comp else sp(t.threat)
        coarse = pos.precision != "point" or last.precision != "point"
        missile = t.family == "missile"
        if last.precision == "origin":
            slack = 160                        # "from Kursk region" = somewhere along a long border
        elif coarse:
            slack = 90
        else:
            slack = 40 if missile else 30     # missile reports lag behind the missile
        allowed = speed * dt_h * (1.15 if missile else 1.3) + slack
        if d > allowed:
            return None
        cost = d / allowed + comp
        hdg = t.heading_estimate()
        if hdg is not None and d > 25 and not coarse:
            ang = angle_diff(hdg, bearing(last.lat, last.lon, pos.lat, pos.lon))
            if ang > (95 if missile else 120):
                return None
            cost += ang / 240
        if s.dest is not None and hdg is not None and missile and not coarse:
            # a missile group reported heading somewhere else is a different group
            if angle_diff(hdg, bearing(pos.lat, pos.lon, s.dest.lat, s.dest.lon)) > 100:
                return None
        if s.dest is not None and hdg is not None and pos.precision != "point" and last.precision == "point":
            # a region-wide post ("Миколаївщина: реактивний на Баштанку") whose destination lies behind a
            # target we have seen at a town is about another object; it must not turn this one around
            if angle_diff(hdg, bearing(last.lat, last.lon, s.dest.lat, s.dest.lon)) > 100:
                return None
        if t.dest is not None and haversine(pos.lat, pos.lon, t.dest.lat, t.dest.lon) < 30:
            cost -= 0.3
        if s.dest is not None and t.dest is not None and haversine(s.dest.lat, s.dest.lon, t.dest.lat, t.dest.lon) < 30:
            cost -= 0.15
        if s.count and t.count and max(s.count, t.count) >= 3 * min(s.count, t.count):
            cost += 0.25
        return cost

    def _cost_dest_only(self, t: Track, s: Sighting, ts: float) -> float | None:
        comp = compatibility(t.threat, s.threat)
        if comp is None or comp > 0.15 or s.dest is None:
            return None
        if t.dest is not None and haversine(t.dest.lat, t.dest.lon, s.dest.lat, s.dest.lon) < 35:
            return 0.2 + comp
        last = t.last
        d = haversine(last.lat, last.lon, s.dest.lat, s.dest.lon)
        if d > 350:
            return None
        hdg = t.heading_estimate()
        if hdg is None:
            return 0.9 + comp if d < 120 else None
        ang = angle_diff(hdg, bearing(last.lat, last.lon, s.dest.lat, s.dest.lon))
        if ang > 50:
            return None
        return 0.5 + ang / 180 + comp

    def _apply(self, t: Track, s: Sighting, ref: MsgRef, pos: TrackPoint | None, via: list[TrackPoint]) -> None:
        before = t.points[-1] if t.points else None
        for v in via:
            t.add_point(v)
        if pos is not None:
            t.add_point(pos)
        t.last_ts = max(t.last_ts, ref.ts)
        # only a report that actually saw the object (has a position) may refine its type
        if (s.pos is not None or s.via) and THREATS[s.threat]["spec"] > THREATS[t.threat]["spec"]:
            t.threat = s.threat
        if s.count:
            t.count = s.count
        t.group = t.group or s.group
        if s.dest is not None:
            t.dest, t.dest_ts = s.dest, ref.ts
        elif t.dest is not None and (t.dest_reached() or self._passed_dest(t, before)):
            t.dest = None
        if s.heading is not None:
            t.heading, t.heading_ts = s.heading, ref.ts
        if s.origin is not None and t.origin is None:
            t.origin = s.origin
        t.sources.setdefault(ref.channel, ref.tier)
        t.refs.append(ref)

    @staticmethod
    def _passed_dest(t: Track, before: TrackPoint | None) -> bool:
        """The newest fix moved away from the reported destination: it was passed or the target turned."""
        last = t.last
        if before is None or before is last or before.precision != "point" or last.precision != "point":
            return False
        if haversine(before.lat, before.lon, last.lat, last.lon) < 8:
            return False
        moved = bearing(before.lat, before.lon, last.lat, last.lon)
        to_dest = bearing(last.lat, last.lon, t.dest.lat, t.dest.lon)
        return angle_diff(moved, to_dest) > 110

    @staticmethod
    def _same_new(t: Track, s: Sighting, pos: PlaceRef | None, ts: float) -> bool:
        """A "new target" post may only join a track that started minutes ago from the same news
        (the post repeated, or reposted by another channel), never an older track."""
        if ts - t.first_ts > 15 * 60:
            return False
        if s.dest is not None and t.dest is not None and haversine(s.dest.lat, s.dest.lon, t.dest.lat, t.dest.lon) < 35:
            return True
        return pos is not None and pos.precision == "point" and t.last.precision == "point" and \
            haversine(pos.lat, pos.lon, t.last.lat, t.last.lon) < 25

    def on_sighting(self, s: Sighting, ref: MsgRef, idx: int, used: set[str]) -> None:
        ts = ref.ts
        pos_ref = s.pos
        precision = None
        if pos_ref is None and s.origin is not None:
            pos_ref, precision = s.origin, "origin"
        pos = self._point(pos_ref, ts, ref.channel, precision) if pos_ref else None
        via = [self._point(v, ts, ref.channel) for v in s.via]

        best, best_cost = None, None
        for t in self._active(ts):
            if t.id in used:
                continue
            if s.new and not self._same_new(t, s, pos_ref, ts):
                continue
            if pos_ref is not None:
                c = self._cost(t, s, pos_ref, ts)
            else:
                c = self._cost_dest_only(t, s, ts)
            if c is not None and (best_cost is None or c < best_cost):
                best, best_cost = t, c

        if best is None:
            if pos is None:
                if s.dest is None:
                    return
                pos = self._point(s.dest, ts, ref.channel, "inbound")
            t = Track(self._tid(ref.channel, ref.msg_id, idx, s.threat), s.threat, ts, ts)
            self.tracks.append(t)
            self._open.append(t)
            best = t
        used.add(best.id)
        self._apply(best, s, ref, pos, via)

    # ------------------------------------------------------------------ events
    def on_kill(self, ev: AreaEvent, ref: MsgRef) -> None:
        if ev.place is not None:
            self._add_event("kill", ev, ref)
        if ref.tier == "aggregator" or ev.place is None:
            return
        radius = 40 if ev.place.precision == "point" else 110
        best, best_d = None, None
        for t in self._active(ref.ts):
            if ev.threat and compatibility(t.threat, ev.threat) is None:
                continue
            d = haversine(t.last.lat, t.last.lon, ev.place.lat, ev.place.lon)
            if d <= radius and (best_d is None or d < best_d):
                best, best_d = t, d
        if best is None:
            return
        best.sources.setdefault(ref.channel, ref.tier)
        best.refs.append(ref)
        n = ev.count or 1
        if best.count and best.count > n:
            best.count -= n
            best.destroyed += n
            best.last_ts = max(best.last_ts, ref.ts)
        else:
            best.destroyed += best.count or 1
            best.ended, best.ended_ts = "destroyed", ref.ts

    def on_all_clear(self, oblasts: set[str], ref: MsgRef) -> None:
        for t in self._open:
            if t.ended is None and t.last.oblast in oblasts and ref.ts - t.last_ts > 60 and ref.ts >= t.last_ts:
                t.ended, t.ended_ts = "all clear", ref.ts

    def _add_event(self, kind: str, ev: AreaEvent, ref: MsgRef) -> None:
        p = ev.place
        for e in reversed(self.events):
            if ref.ts - e["ts"] > 15 * 60:
                break
            if e["kind"] == kind and e["key"] == p.place.key and e.get("threat") == ev.threat:
                e["sources"].setdefault(ref.channel, ref.tier)
                e["last_ts"] = ref.ts
                return
        self.events.append({
            "kind": kind, "threat": ev.threat, "key": p.place.key, "place": p.label, "oblast": p.place.oblast,
            "lat": round(p.lat, 4),
            "lon": round(p.lon, 4), "precision": p.precision, "ts": ref.ts, "last_ts": ref.ts,
            "sources": {ref.channel: ref.tier}, "text": ev.text[:200],
        })

    # ------------------------------------------------------------------ main loop
    def on_clear(self, parsed: ParsedMessage, ref: MsgRef) -> None:
        """'Кременчук чисто' / 'в області чисто': end tracks there (alerts stay as they are)."""
        for t in self._open:
            if t.ended is not None or ref.ts < t.last_ts + 60:
                continue
            last = t.last
            hit = last.oblast in parsed.clear_oblasts
            for p in parsed.clear_places:
                if p.precision == "region":
                    hit = hit or last.oblast == p.place.oblast
                else:
                    hit = hit or haversine(last.lat, last.lon, p.lat, p.lon) < 35
            if hit:
                t.ended, t.ended_ts = "reported clear", ref.ts

    def process(self, ref: MsgRef, parsed: ParsedMessage) -> None:
        self._prune(ref.ts)
        used: set[str] = set()
        sightings = list(parsed.sightings)
        # terse follow-up ("Гостомель") continues what this channel reported a few minutes ago
        last = self._last_threat.get(ref.channel)
        if parsed.bare_places and last and ref.ts - last[1] <= 8 * 60 and ref.tier != "aggregator":
            cur = [r for r in parsed.bare_places if r.role == "current"]
            dst = [r for r in parsed.bare_places if r.role == "dest"]
            sightings.append(Sighting(last[0], pos=cur[-1] if cur else None, dest=dst[0] if dst else None,
                                      text=ref.text, own_threat=False, new=parsed.bare_new))
        for i, s in enumerate(sightings):
            self.on_sighting(s, ref, i, used)
        if parsed.sightings:
            self._last_threat[ref.channel] = (parsed.sightings[-1].threat, ref.ts)
        if (parsed.clear_places or parsed.clear_oblasts) and ref.tier != "aggregator":
            self.on_clear(parsed, ref)
        for ev in parsed.events:
            if ev.kind == "kill":
                self.on_kill(ev, ref)
            elif ev.place is not None:
                self._add_event(ev.kind, ev, ref)
        if ref.tier != "aggregator":
            for o in parsed.alerts_on:
                center = GAZETTEER.oblast_center.get(o) or (GAZETTEER.places.get("kyiv") if o == "kyiv_city" else None)
                prev = self.alerts.get(o)
                self.alerts[o] = {"oblast": o, "name": OBLAST_NAMES.get(o, o), "since": prev["since"] if prev else ref.ts,
                                  "last_ts": ref.ts, "channel": ref.channel,
                                  "lat": center.lat if center else None, "lon": center.lon if center else None}
            for o in parsed.alerts_off:
                self.alerts.pop(o, None)
            if parsed.alerts_off:
                self.on_all_clear(parsed.alerts_off, ref)
            # nationwide banners: official / reconnaissance channels, or a regional
            # channel warning about ballistic or Kinzhal launches
            banners = [b for b in parsed.banners if (ref.tier in ("official", "recon")
                       or b[0] in ("threat:ballistic", "threat:kinzhal")) and len(ref.text) <= 220]
            if banners:
                # one banner per message, most important kind first, original wording
                kinds = [k for k, _ in banners]
                kind = "aviation" if "aviation" in kinds else kinds[0]
                text = " ".join(ref.text.split())[:220]
                key = f"{ref.channel}/{ref.msg_id}"
                if not any(b["text"] == text and ref.ts - b["ts"] < 10 * 60 for b in self.banners):
                    self.banners.append({"key": key, "kind": kind, "kinds": kinds, "text": text, "ts": ref.ts,
                                         "channel": ref.channel, "tier": ref.tier})
        if parsed.relevant or parsed.threats:
            kinds = []
            if parsed.sightings:
                kinds.append("target")
            kinds += sorted({e.kind for e in parsed.events})
            if parsed.alerts_on:
                kinds.append("alert")
            if parsed.alerts_off or parsed.clear_places or parsed.clear_oblasts:
                kinds.append("all clear")
            if parsed.banners:
                kinds.append("notice")
            if parsed.summary:
                kinds.append("summary")
            self.feed.append({"channel": ref.channel, "id": ref.msg_id, "ts": ref.ts, "tier": ref.tier,
                              "text": ref.text[:500], "threats": parsed.threats, "places": parsed.places[:8],
                              "kinds": kinds})

    # ------------------------------------------------------------------ output
    def confidence(self, t: Track) -> tuple[float, bool]:
        non_agg = [tier for tier in t.sources.values() if tier != "aggregator"]
        agg = [tier for tier in t.sources.values() if tier == "aggregator"]
        if not non_agg:
            return min(0.35, 0.12 * len(agg)), len(agg) >= 3
        miss = 1.0
        for tier in non_agg:
            miss *= 1 - self.weights.get(tier, 0.5)
        for _ in agg:
            miss *= 1 - self.weights.get("aggregator", 0.15)
        return min(0.99, 1 - miss), True

    def snapshot(self, now: float) -> dict:
        tracks_out = []
        for t in self.tracks:
            age = now - t.last_ts
            if t.ended:
                if now - (t.ended_ts or t.last_ts) > ENDED_VISIBLE_MIN * 60:
                    continue
                status = "ended"
            elif age > _lookup(DROP_AFTER, t.threat) * 60:
                continue
            elif age > _lookup(STALE_AFTER, t.threat) * 60:
                status = "stale"
            else:
                status = "active"
            conf, confirmed = self.confidence(t)
            last = t.last
            hdg, hdg_src = t.heading_info()
            dest = t.dest if t.dest is not None and not t.dest_reached() else None
            tracks_out.append({
                "id": t.id, "threat": t.threat, "family": t.family, "label": THREATS[t.threat]["label"],
                "count": t.count, "group": t.group, "status": status, "ended": t.ended,
                "lat": round(last.lat, 4), "lon": round(last.lon, 4), "precision": last.precision,
                "place": last.label, "oblast": last.oblast,
                "heading": round(hdg, 1) if hdg is not None else None,
                "heading_source": hdg_src,
                "dest": dest.as_dict() if dest else None,
                "origin": t.origin.as_dict() if t.origin else None,
                "points": [p.as_dict() for p in t.points[-40:]],
                "first_seen": t.first_ts, "last_seen": t.last_ts, "age_s": round(age),
                "confidence": round(conf, 2), "confirmed": confirmed, "destroyed": t.destroyed,
                "sources": [{"channel": ch, "tier": tier, "name": self.channels.get(ch, {}).get("name") or "@" + ch}
                            for ch, tier in t.sources.items()],
                "messages": [{"channel": r.channel, "id": r.msg_id, "ts": r.ts, "text": r.text[:300]}
                             for r in t.refs[-8:]][::-1],
            })
        prio = {"kinzhal": 0, "ballistic": 1, "cruise": 2, "missile": 3, "kab": 4, "jet_shahed": 5}
        tracks_out.sort(key=lambda x: (x["status"] != "active", prio.get(x["threat"], 9), -x["last_seen"]))

        events = []
        for e in self.events:
            if now - e["last_ts"] > EVENT_TTL_MIN.get(e["kind"], 30) * 60:
                continue
            ev = {k: v for k, v in e.items() if k != "sources"}
            ev["sources"] = [{"channel": ch, "tier": tier} for ch, tier in e["sources"].items()]
            ev["confirmed"] = any(tier != "aggregator" for tier in e["sources"].values())
            events.append(ev)

        alerts = [a for a in self.alerts.values() if now - a["last_ts"] < ALERT_TTL_MIN * 60]
        alerts.sort(key=lambda a: a["since"])
        banners = [b for b in self.banners if now - b["ts"] < BANNER_TTL_MIN * 60][-6:][::-1]

        stats: dict[str, dict] = {}
        for t in tracks_out:
            if t["status"] != "active" or not t["confirmed"]:
                continue
            st = stats.setdefault(t["threat"], {"tracks": 0, "objects": 0})
            st["tracks"] += 1
            st["objects"] += t["count"] or 1
        return {
            "tracks": tracks_out, "events": events, "alerts": alerts, "banners": banners,
            "feed": self.feed[-150:][::-1], "stats": stats,
        }


    # ------------------------------------------------------------------ history (heatmap)
    def heat_points(self) -> list[dict]:
        """Observed positions for the long-term heatmap.

        Only real fixes count (a named village or town). Region centre points would paint false hot
        spots in the middle of every oblast. For missiles and guided bombs, the reported target of a
        not-yet-seen inbound weapon counts at a lower weight, since that is often all a post says.
        Each row has a stable key, so recording the same report again only updates it.
        """
        out: list[dict] = []
        for t in self.tracks:
            conf, confirmed = self.confidence(t)
            n = min(t.count or 1, 6)
            for p in t.points:
                if p.precision == "point":
                    w = float(n)
                elif p.precision == "inbound" and t.family in ("missile", "kab"):
                    w = 0.6 * n
                else:
                    continue
                out.append({"key": f"{t.family}|{int(p.ts)}|{p.lat:.3f}|{p.lon:.3f}", "kind": "track",
                            "family": t.family, "threat": t.threat, "ts": p.ts, "lat": p.lat, "lon": p.lon,
                            "place": p.label, "oblast": p.oblast, "weight": w, "confirmed": int(confirmed)})
        for e in self.events:
            if e["kind"] != "explosion" or e["precision"] != "point":
                continue
            confirmed = any(tier != "aggregator" for tier in e["sources"].values())
            out.append({"key": f"explosion|{int(e['ts'])}|{e['key']}", "kind": "explosion",
                        "family": THREATS[e["threat"]]["family"] if e.get("threat") else "unknown",
                        "threat": e.get("threat") or "", "ts": e["ts"], "lat": e["lat"], "lon": e["lon"],
                        "place": e["place"], "oblast": e["oblast"], "weight": 1.0, "confirmed": int(confirmed)})
        return out


def build_fusion(items: list[tuple[MsgRef, ParsedMessage]], channels: dict, weights: dict | None) -> Fusion:
    fusion = Fusion(channels, weights)
    for ref, parsed in sorted(items, key=lambda it: (it[0].ts, it[0].channel, it[0].msg_id)):
        fusion.process(ref, parsed)
    return fusion


def run_fusion(items: list[tuple[MsgRef, ParsedMessage]], channels: dict, weights: dict | None, now: float) -> dict:
    return build_fusion(items, channels, weights).snapshot(now)
