"""Fuse parsed messages from many channels into tracks, events and alerts.

The whole picture is rebuilt by replaying the recent message window in time order.
That makes the result deterministic, robust to channels being polled at different times
(out-of-order arrival), to edited posts, and to restarts.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .gazetteer import GAZETTEER, OBLAST_NAMES, angle_diff, bearing, destination, haversine
from .parser import THREATS, AreaEvent, ParsedMessage, PlaceRef, Sighting, _ukr  # noqa: F401

# How long after the last report a new report can still continue the same track (minutes)
ASSOC_WINDOW = {"drone": 50, "missile": 15, "kab": 10, "ballistic": 6, "kinzhal": 6, "jet_shahed": 30}
# speed used for gating; ballistic reports never chain far, so they are not gated at their physical speed
GATE_SPEED = {"ballistic": 1200, "kinzhal": 1200}
# A track turns "stale" (faded on the map) after this many minutes without reports
STALE_AFTER = {"drone": 30, "missile": 15, "kab": 8, "ballistic": 6, "kinzhal": 6, "recon": 40,
               "lancet": 25, "fpv": 15, "molniya": 20, "jet_shahed": 20}
# ...and is removed after this many minutes
DROP_AFTER = {k: v * 2.5 for k, v in STALE_AFTER.items()}
ENDED_VISIBLE_MIN = 10
EVENT_TTL_MIN = {"explosion": 45, "kill": 30, "threat": 20}
RU_ZONE_TTL_MIN = 90
BANNER_TTL_MIN = 40
ALERT_TTL_MIN = 24 * 60

DEFAULT_WEIGHTS = {"official": 0.9, "recon": 0.7, "regional": 0.55, "aggregator": 0.15}

# Where attacks come from: the border with Russia, the front line, Crimea and the sea. A report
# that only says "heading to X" puts the target a short way before X, on the side it most likely
# comes from, instead of dropping it or parking it in the middle of the region.
HOSTILE_ANCHORS = [
    (52.30, 33.20), (52.10, 34.10),                    # Bryansk border
    (51.40, 34.60), (51.20, 35.40),                    # Kursk border
    (50.60, 35.90), (50.40, 36.90), (50.20, 37.90),    # Belgorod border
    (49.90, 39.50),                                    # Voronezh / Luhansk
    (49.70, 37.80), (49.00, 37.90), (48.30, 37.20),    # front: Kupiansk, Lyman, Pokrovsk
    (47.85, 36.80), (47.66, 36.26), (47.45, 35.30),    # Velyka Novosilka, Huliaipole, Vasylivka
    (46.80, 33.50), (46.60, 32.70), (46.50, 31.60),    # Dnipro river line, Kinburn spit
    (45.00, 33.60), (45.10, 35.40), (46.05, 38.15),    # Crimea west / east, Azov coast
    (45.40, 31.20),                                    # Black Sea off Odesa
]
# local channels report "на X" when a drone is roughly this close; short-range drones much closer
APPROACH_KM = {"drone": 15, "fpv": 4, "molniya": 6, "lancet": 8}
IMPLIED_CUE = re.compile(r"уважн|увага|обережн|⚠|❗|‼|повз|через|над\b|курс|кружля|крутит|летить|рух")


def approach_bearing(lat: float, lon: float) -> float:
    """Direction of travel of a target arriving at (lat, lon) from the nearest hostile area."""
    a = min(HOSTILE_ANCHORS, key=lambda p: haversine(p[0], p[1], lat, lon))
    return bearing(a[0], a[1], lat, lon)


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

    def heading_estimate(self) -> float | None:
        last = self.last
        if self.dest is not None and haversine(last.lat, last.lon, self.dest.lat, self.dest.lon) > 5:
            return bearing(last.lat, last.lon, self.dest.lat, self.dest.lon)
        if self.heading is not None and self.heading_ts >= self.last_ts - 15 * 60:
            return self.heading
        pts = [p for p in self.points if p.precision in ("point", "approx", "region", "origin")]
        for prev in reversed(pts[:-1]):
            if haversine(prev.lat, prev.lon, last.lat, last.lon) > 5:
                return bearing(prev.lat, prev.lon, last.lat, last.lon)
        return self.heading

    def speed_estimate(self) -> float | None:
        pts = [p for p in self.points if p.precision == "point"]
        if len(pts) < 2:
            return None
        a, b = pts[-2], pts[-1]
        dt = (b.ts - a.ts) / 3600
        if dt < 1 / 60:
            return None
        v = haversine(a.lat, a.lon, b.lat, b.lon) / dt
        return v if 20 <= v <= 5000 else None

    def add_point(self, p: TrackPoint) -> None:
        if not self.points:
            self.points.append(p)
            return
        last = self.points[-1]
        if last.precision == "inbound" and p.precision != "inbound":
            self.points[-1] = p          # replace a guessed position with a real one
            return
        if p.precision in ("region", "origin", "approx") and last.precision == "point" and \
                haversine(last.lat, last.lon, p.lat, p.lon) < 130:
            return                        # coarse report refreshes the track but does not move it back
        if p.precision == "region" and last.precision == "approx" and haversine(last.lat, last.lon, p.lat, p.lon) < 130:
            return                        # an estimate near the destination beats the middle of the region
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
        self.events: list[dict] = []
        self.alerts: dict[str, dict] = {}
        self.banners: list[dict] = []
        self.feed: list[dict] = []
        self._last_threat: dict[str, tuple[str, float]] = {}
        self.ru_zones: dict[str, dict] = {}
        self._alert_channels: set[str] | None = None

    # ------------------------------------------------------------------ helpers
    def _sets_alerts(self, channel: str) -> bool:
        """Air-raid alert state comes from the official alert feed (channels marked "alerts").
        Other channels' "тривога" posts lag and rarely say when it ends."""
        if self._alert_channels is None:
            self._alert_channels = {h for h, c in self.channels.items() if c.get("alerts")}
        if self._alert_channels:
            return channel in self._alert_channels
        return self._tier(channel) in ("official", "regional")

    def _tier(self, channel: str) -> str:
        return self.channels.get(channel, {}).get("tier", "aggregator")

    @staticmethod
    def _tid(channel: str, msg_id: int, idx: int, threat: str) -> str:
        return hashlib.sha1(f"{channel}/{msg_id}/{idx}/{threat}".encode()).hexdigest()[:10]

    def _active(self, ts: float):
        for t in self.tracks:
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
        if s.dest is not None and hdg is not None and not coarse:
            # a group reported heading somewhere else entirely is a different group
            if angle_diff(hdg, bearing(pos.lat, pos.lon, s.dest.lat, s.dest.lon)) > (100 if missile else 110):
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
            t.dest = s.dest
        elif t.dest is not None and haversine(t.last.lat, t.last.lon, t.dest.lat, t.dest.lon) < 12:
            t.dest = None                       # arrived
        if s.heading is not None:
            t.heading, t.heading_ts = s.heading, ref.ts
        if s.origin is not None and t.origin is None:
            t.origin = s.origin
        t.sources.setdefault(ref.channel, ref.tier)
        t.refs.append(ref)

    @staticmethod
    def estimate(s: Sighting) -> PlaceRef | None:
        """Best guess of a target's position when the report does not pin it down.

        * "від Близнюків на Юріївку": it has just passed a known town, a little way towards the target
        * "в 50 км від Львова, курс на Львів": that far out, on the side it comes from
        * "Сумщина: БпЛА курсом на Шалигине" / "Шахед на Полтаву": a drone shortly before the place,
          on the side it approaches from (stated heading, origin, region it is in, or the nearest
          hostile area)
        """
        pos, dest, origin = s.pos, s.dest, s.origin
        if pos is not None and pos.precision == "point" and not pos.dist_km:
            return None
        drone = THREATS[s.threat]["family"] == "drone"
        if (drone and origin is not None and origin.precision == "point" and _ukr(origin.place.oblast)
                and origin.place.kind != "F"):
            lat, lon = origin.lat, origin.lon
            if dest is not None:
                d = haversine(lat, lon, dest.lat, dest.lon)
                lat, lon = destination(lat, lon, bearing(lat, lon, dest.lat, dest.lon), min(8.0, d * 0.3))
            return PlaceRef(origin.place, "current", lat, lon, "approx", f"past {origin.place.name}", origin.start)
        if pos is not None and pos.dist_km:
            if dest is not None and dest.place.key != pos.place.key:
                return None
            travel = s.heading if s.heading is not None else approach_bearing(pos.place.lat, pos.place.lon)
            lat, lon = destination(pos.place.lat, pos.place.lon, (travel + 180) % 360, pos.dist_km)
            return PlaceRef(pos.place, "current", lat, lon, "approx", pos.label, pos.start)
        if not drone or dest is None or dest.precision != "point" or not _ukr(dest.place.oblast):
            return None
        travel = s.heading
        if travel is None and origin is not None and haversine(origin.lat, origin.lon, dest.lat, dest.lon) > 20:
            travel = bearing(origin.lat, origin.lon, dest.lat, dest.lon)
        if (travel is None and pos is not None and pos.place.oblast != dest.place.oblast
                and haversine(pos.lat, pos.lon, dest.lat, dest.lon) > 40):
            travel = bearing(pos.lat, pos.lon, dest.lat, dest.lon)      # in one region, heading into the next
        if travel is None:
            travel = approach_bearing(dest.lat, dest.lon)
        lat, lon = destination(dest.lat, dest.lon, (travel + 180) % 360, _lookup(APPROACH_KM, s.threat))
        return PlaceRef(dest.place, "current", lat, lon, "approx", f"approaching {dest.place.name}", dest.start)

    def on_sighting(self, s: Sighting, ref: MsgRef, idx: int, used: set[str]) -> None:
        ts = ref.ts
        pos_ref = s.pos
        precision = None
        est = self.estimate(s)
        if est is not None:
            pos_ref = est
        elif pos_ref is None and s.origin is not None:
            pos_ref, precision = s.origin, "origin"
        pos = self._point(pos_ref, ts, ref.channel, precision) if pos_ref else None
        via = [self._point(v, ts, ref.channel) for v in s.via]

        best, best_cost, best_by_dest = None, None, False
        for t in self._active(ts):
            if t.id in used:
                continue
            c = self._cost(t, s, pos_ref, ts) if pos_ref is not None else None
            by_dest = False
            if s.pos is None and s.dest is not None:
                cd = self._cost_dest_only(t, s, ts)          # same destination as a known track
                if cd is not None and (c is None or cd < c):
                    c, by_dest = cd, True
            if c is not None and (best_cost is None or c < best_cost):
                best, best_cost, best_by_dest = t, c, by_dest

        if best is None:
            if pos is None:
                # "heading to X" without a position: a useful early warning for missiles, bombs and
                # ballistic threats, but for drones it would only add a placeholder next to the real one
                if s.dest is None or THREATS[s.threat]["family"] == "drone" or ref.tier == "aggregator":
                    return
                pos = self._point(s.dest, ts, ref.channel, "inbound")
            elif ref.tier == "aggregator" and pos.precision != "point":
                return                     # an aggregator's "somewhere in the region" or a guess only confirms targets
            t = Track(self._tid(ref.channel, ref.msg_id, idx, s.threat), s.threat, ts, ts)
            self.tracks.append(t)
            best = t
        elif best_by_dest and pos is not None and pos.precision == "approx" and best.last.precision == "point":
            pos = None                     # matched by destination: keep the observed position, not a guess
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
        for t in self.tracks:
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
            "kind": kind, "threat": ev.threat, "key": p.place.key, "place": p.label, "lat": round(p.lat, 4),
            "lon": round(p.lon, 4), "precision": p.precision, "ts": ref.ts, "last_ts": ref.ts,
            "sources": {ref.channel: ref.tier}, "text": ev.text[:200],
        })

    # ------------------------------------------------------------------ main loop
    def on_clear(self, parsed: ParsedMessage, ref: MsgRef) -> None:
        """'Кременчук чисто' / 'в області чисто': end tracks there (alerts stay as they are)."""
        for t in self.tracks:
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

    def on_russia(self, ref: MsgRef, parsed: ParsedMessage) -> None:
        """Danger zones over Russia / occupied territory reported by Russian-side channels."""
        for r, kind in parsed.ru_zones:
            p = r.place
            if p.kind == "A":
                unit = p.key[1:]                       # Ukrainian raion id -> raion polygon
            elif p.kind == "R":
                unit = p.oblast                        # region key -> region polygon
            else:
                unit = None                            # town -> circle
            key = r.label
            prev = self.ru_zones.get(key)
            self.ru_zones[key] = {
                "key": key, "name": r.label, "kind": kind, "unit": unit, "oblast": p.oblast,
                "lat": round(r.lat, 4), "lon": round(r.lon, 4), "precision": "point" if unit is None else "area",
                "since": prev["since"] if prev else ref.ts, "last_ts": ref.ts, "channel": ref.channel,
                "text": ref.text[:200],
            }
        for r in parsed.ru_clear:
            for k, z in list(self.ru_zones.items()):
                if k == r.label or (r.place.kind == "R" and z["oblast"] == r.place.oblast):
                    del self.ru_zones[k]

    def process(self, ref: MsgRef, parsed: ParsedMessage) -> None:
        if ref.tier == "russia":
            self.on_russia(ref, parsed)
            if parsed.relevant:
                self.feed.append({"channel": ref.channel, "id": ref.msg_id, "ts": ref.ts, "tier": ref.tier,
                                  "text": ref.text[:500], "threats": parsed.threats, "places": parsed.places[:8],
                                  "kinds": ["danger over Russia" if parsed.ru_zones else "all clear (Russia)"]})
            return
        used: set[str] = set()
        sightings = list(parsed.sightings)
        # terse follow-up ("Гостомель") continues what this channel reported a few minutes ago
        last = self._last_threat.get(ref.channel)
        if parsed.bare_places and ref.tier != "aggregator":
            cur = [r for r in parsed.bare_places if r.role == "current"]
            dst = [r for r in parsed.bare_places if r.role == "dest"]
            org = [r for r in parsed.bare_places if r.role == "origin"]
            threat = None
            if last and ref.ts - last[1] <= 12 * 60:
                threat = last[0]
            elif self.channels.get(ref.channel, {}).get("implied") and (
                    dst or org or (any(r.precision == "point" for r in cur) and IMPLIED_CUE.search(ref.text.lower()))):
                # local channels whose terse "⚠️ на Михайлівку з Полтавської" / "Сарни - уважно!" always means a drone
                threat = self.channels[ref.channel]["implied"]
            if threat in THREATS:
                pos = next((r for r in reversed(cur) if r.precision == "point"), cur[-1] if cur else None)
                sightings.append(Sighting(threat, pos=pos, dest=dst[0] if dst else None,
                                          origin=org[0] if org else None, text=ref.text, own_threat=False))
                self._last_threat[ref.channel] = (threat, ref.ts)     # "Далі Малин" ... "Далі Коростень"
        for i, s in enumerate(sightings):
            self.on_sighting(s, ref, i, used)
        if parsed.sightings:
            self._last_threat[ref.channel] = (parsed.sightings[-1].threat, ref.ts)
        if (parsed.clear_places or parsed.clear_oblasts) and ref.tier != "aggregator":
            self.on_clear(parsed, ref)
        if parsed.threats_cleared and ref.tier != "aggregator":
            # "відбій загрози балістики": drop that threat's notices and threat areas
            gone = {"threat:" + t for t in parsed.threats_cleared}
            self.banners = [b for b in self.banners if b["kind"] not in gone or b["ts"] > ref.ts]
            self.events = [e for e in self.events if not (e["kind"] == "threat" and e.get("threat") in parsed.threats_cleared)]
        threat_notes = {ev.threat for ev in parsed.events if ev.kind == "threat" and ev.threat}
        if len(threat_notes) == 1 and not parsed.sightings:
            # "Тривога — Золотоніський район. Загроза ударних БпЛА." then "⚠️ на Михайлівку"
            self._last_threat[ref.channel] = (threat_notes.pop(), ref.ts)
        for ev in parsed.events:
            if ev.kind == "kill":
                self.on_kill(ev, ref)
            elif ev.place is not None:
                self._add_event(ev.kind, ev, ref)
        if ref.tier != "aggregator" and self._sets_alerts(ref.channel):
            for unit in parsed.alerts_on:
                raion = GAZETTEER.raions.get(unit)
                city = GAZETTEER.places.get(unit[2:]) if unit.startswith("c:") else None
                if raion is not None:
                    kind, oblast, name, center = "raion", raion.oblast, raion.name, raion
                elif city is not None:
                    kind, oblast, name, center = "city", city.oblast, city.name, city
                else:
                    kind, oblast, name = "oblast", unit, OBLAST_NAMES.get(unit, unit)
                    center = GAZETTEER.oblast_center.get(unit) or (GAZETTEER.places.get("kyiv") if unit == "kyiv_city" else None)
                prev = self.alerts.get(unit)
                self.alerts[unit] = {"id": unit, "kind": kind, "oblast": oblast, "name": name,
                                     "level": parsed.alert_levels.get(unit, parsed.alert_level),
                                     "since": prev["since"] if prev else ref.ts, "last_ts": ref.ts, "channel": ref.channel,
                                     "lat": center.lat if center else None, "lon": center.lon if center else None}
            for unit in parsed.alerts_off:
                self.alerts.pop(unit, None)
                if unit in OBLAST_NAMES:                      # whole oblast cleared: its districts too
                    for k in [k for k, a in self.alerts.items() if a["oblast"] == unit]:
                        self.alerts.pop(k, None)
            cleared_oblasts = {u for u in parsed.alerts_off if u in OBLAST_NAMES}
            if cleared_oblasts:
                self.on_all_clear(cleared_oblasts, ref)
        if ref.tier != "aggregator":
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
            if parsed.alerts_off or parsed.clear_places or parsed.clear_oblasts or parsed.threats_cleared:
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

    # ------------------------------------------------------------------ duplicates
    def _same_object(self, a: Track, b: Track) -> bool:
        """Two live tracks that are most likely one group reported by different channels."""
        comp = compatibility(a.threat, b.threat)
        # two different specific types (Shahed / Gerbera) reported separately are different objects;
        # only a generic "БпЛА" / "ракета" report folds into a specific one
        if comp is None or comp > 0.15 or abs(a.last_ts - b.last_ts) > 25 * 60:
            return False
        pa, pb = a.last, b.last
        d = haversine(pa.lat, pa.lon, pb.lat, pb.lon)
        coarse = {pa.precision, pb.precision} & {"region", "origin"}
        approx = "approx" in {pa.precision, pb.precision}
        if {pa.precision, pb.precision} & {"inbound"}:
            inb, other = (a, b) if pa.precision == "inbound" else (b, a)
            near_dest = other.dest is not None and haversine(other.dest.lat, other.dest.lon, inb.last.lat, inb.last.lon) < 35
            return near_dest or haversine(other.last.lat, other.last.lon, inb.last.lat, inb.last.lon) < 25
        ha, hb = a.heading_estimate(), b.heading_estimate()
        # continuation: one was heading to a place and the other has since been reported near it
        older, newer = (a, b) if a.last_ts <= b.last_ts else (b, a)
        if (older.dest is not None and newer.last.precision in ("point", "approx") and newer.last_ts - older.last_ts <= 20 * 60
                and newer.first_ts >= older.last_ts - 5 * 60       # it appeared as the other went quiet
                and (ha is None or hb is None or angle_diff(ha, hb) < 90)   # and flies on the same way
                and haversine(older.dest.lat, older.dest.lon, newer.last.lat, newer.last.lon) < (50 if a.family == "drone" else 40)):
            return True
        # same corridor: same region, same direction, reported close in time; only a weakly
        # supported duplicate is folded in, two well-established groups stay apart
        if (a.family == "drone" and not coarse and ha is not None and hb is not None and angle_diff(ha, hb) < 45
                and d < 80 and pa.oblast == pb.oblast and abs(a.last_ts - b.last_ts) <= 15 * 60
                and min(len(a.sources), len(b.sources)) <= 3):
            return True
        limit = (110 if coarse else 40 if approx else 30) if a.family == "drone" else (150 if coarse else 80 if approx else 60)
        if d > limit:
            return False
        if coarse:
            return pa.oblast == pb.oblast or d < 60
        if ha is not None and hb is not None and angle_diff(ha, hb) > 75 and d > 8:
            return False                        # close but flying different ways: two groups
        return True

    def _absorb(self, keep: Track, other: Track) -> None:
        keep.sources = {**other.sources, **keep.sources}
        keep.refs = sorted(keep.refs + other.refs, key=lambda r: r.ts)
        if other.last_ts > keep.last_ts and (other.last.precision == "point" or keep.last.precision != "point"):
            keep.add_point(other.last)
            if other.dest is not None:
                keep.dest = other.dest
            if other.heading is not None:
                keep.heading, keep.heading_ts = other.heading, other.heading_ts
        keep.last_ts = max(keep.last_ts, other.last_ts)
        keep.first_ts = min(keep.first_ts, other.first_ts)
        if keep.dest is None:
            keep.dest = other.dest
        if other.count and (not keep.count or other.count > keep.count):
            keep.count = other.count                # the same group: take the larger estimate, never the sum
        keep.group = keep.group or other.group
        if THREATS[other.threat]["spec"] > THREATS[keep.threat]["spec"] and compatibility(keep.threat, other.threat) is not None:
            keep.threat = other.threat
        keep.destroyed = max(keep.destroyed, other.destroyed)

    def merge_duplicates(self, now: float) -> None:
        live = [t for t in self.tracks if t.ended is None and now - t.last_ts <= _lookup(STALE_AFTER, t.threat) * 60]
        # the best-supported, most precise track absorbs the others
        rank = {"point": 0, "approx": 1}
        live.sort(key=lambda t: (rank.get(t.last.precision, 2), -len(t.sources), -t.last_ts))
        gone: set[str] = set()
        for i, a in enumerate(live):
            if a.id in gone:
                continue
            for b in live[i + 1:]:
                if b.id not in gone and self._same_object(a, b):
                    self._absorb(a, b)
                    gone.add(b.id)
        if gone:
            self.tracks = [t for t in self.tracks if t.id not in gone]

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
            hdg = t.heading_estimate()
            tracks_out.append({
                "id": t.id, "threat": t.threat, "family": t.family, "label": THREATS[t.threat]["label"],
                "count": t.count, "group": t.group, "status": status, "ended": t.ended,
                "lat": round(last.lat, 4), "lon": round(last.lon, 4), "precision": last.precision,
                "place": last.label, "oblast": last.oblast,
                "heading": round(hdg, 1) if hdg is not None else None,
                "speed_kmh": round(t.speed_estimate()) if t.speed_estimate() else None,
                "nominal_speed_kmh": THREATS[t.threat]["speed"],
                "dest": t.dest.as_dict() if t.dest else None,
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
        ru_zones = sorted((z for z in self.ru_zones.values() if now - z["last_ts"] < RU_ZONE_TTL_MIN * 60),
                          key=lambda z: -z["last_ts"])
        return {
            "tracks": tracks_out, "events": events, "alerts": alerts, "banners": banners, "ru_zones": ru_zones,
            "feed": self.feed[-150:][::-1], "stats": stats,
        }


def run_fusion(items: list[tuple[MsgRef, ParsedMessage]], channels: dict, weights: dict | None, now: float) -> dict:
    fusion = Fusion(channels, weights)
    next_merge = None
    for ref, parsed in sorted(items, key=lambda it: (it[0].ts, it[0].channel, it[0].msg_id)):
        if next_merge is None:
            next_merge = ref.ts + 300
        elif ref.ts >= next_merge:               # every 5 minutes of reports, fold duplicates together
            fusion.merge_duplicates(ref.ts)
            next_merge = ref.ts + 300
        fusion.process(ref, parsed)
    fusion.merge_duplicates(now)
    return fusion.snapshot(now)
