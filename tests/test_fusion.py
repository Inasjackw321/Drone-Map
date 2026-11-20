import random

from dronemap.demo import SCRIPT
from dronemap.engine import Config, Engine
from dronemap.fusion import MsgRef, run_fusion
from dronemap.parser import parse_message
from dronemap.store import RawMessage

T0 = 1_700_000_000
CH = {
    "kpszsu": {"tier": "official", "regions": []},
    "sumyregion": {"tier": "regional", "regions": ["sumy"]},
    "inforomen": {"tier": "regional", "regions": ["sumy"]},
    "PoltavaRadar": {"tier": "regional", "regions": ["poltava"]},
    "kyiv_airdef": {"tier": "regional", "regions": ["kyiv", "kyiv_city"]},
    "totallzrada": {"tier": "aggregator", "regions": []},
    "monikppy": {"tier": "aggregator", "regions": []},
    "war_monitor": {"tier": "aggregator", "regions": []},
    "UkraineAlarmSignal": {"tier": "official", "regions": []},
}


def fuse(msgs, at_min):
    items = []
    for i, m in enumerate(msgs):
        t, ch, text = m[:3]
        msg_id = m[3] if len(m) > 3 else i + 1
        meta = CH[ch]
        items.append((MsgRef(ch, msg_id, T0 + t * 60, meta["tier"], text),
                      parse_message(text, meta["regions"], meta["tier"])))
    return run_fusion(items, CH, None, T0 + at_min * 60)


def places(track):
    return [p["place"] for p in track["points"]]


def test_reports_from_different_channels_chain_into_one_track():
    snap = fuse([
        (0, "sumyregion", "🛵 3 шахеди повз Білопілля, курс на Ворожбу"),
        (5, "inforomen", "Шахеди в районі Ворожби, рухаються на Конотоп"),
        (14, "kpszsu", "БпЛА на Сумщині, курсом на Конотоп"),
    ], 15)
    assert len(snap["tracks"]) == 1
    t = snap["tracks"][0]
    assert places(t) == ["Bilopillia", "Vorozhba"]          # coarse region report does not move it back
    assert t["dest"]["name"] == "Konotop" and t["count"] == 3
    assert {s["channel"] for s in t["sources"]} == {"sumyregion", "inforomen", "kpszsu"}
    assert t["confirmed"] and t["confidence"] > 0.9


def test_far_apart_reports_stay_separate():
    snap = fuse([
        (0, "sumyregion", "Шахед над Шосткою"),
        (2, "PoltavaRadar", "Шахед над Кременчуком"),
    ], 3)
    assert len(snap["tracks"]) == 2


def test_speed_gate_rejects_impossible_jump():
    # 200 km in 3 minutes is impossible for a Shahed
    snap = fuse([(0, "sumyregion", "Шахед над Шосткою"), (3, "sumyregion", "Шахед над Охтиркою")], 4)
    assert len(snap["tracks"]) == 2


def test_different_drone_types_are_not_merged():
    snap = fuse([(0, "PoltavaRadar", "Орлан над Полтавою"), (1, "PoltavaRadar", "Шахед над Полтавою")], 2)
    assert sorted(t["threat"] for t in snap["tracks"]) == ["recon", "shahed"]


def test_aggregator_only_is_unconfirmed_until_corroborated():
    snap = fuse([(0, "totallzrada", "Шахед над Кропивницьким")], 1)
    t = snap["tracks"][0]
    assert not t["confirmed"] and t["confidence"] <= 0.35
    assert snap["stats"] == {}                                # unconfirmed tracks are not counted

    snap = fuse([(0, "totallzrada", "Шахед над Полтавою"),
                 (3, "PoltavaRadar", "Шахед над Полтавою, курс на Решетилівку")], 4)
    assert len(snap["tracks"]) == 1 and snap["tracks"][0]["confirmed"]


def test_three_aggregators_agreeing_confirm():
    snap = fuse([(0, "totallzrada", "Шахед над Полтавою"), (1, "monikppy", "Шахед над Полтавою"),
                 (2, "war_monitor", "Шахед над Полтавою")], 3)
    assert snap["tracks"][0]["confirmed"]


def test_kill_decrements_then_ends_track():
    snap = fuse([
        (0, "kyiv_airdef", "3 шахеди повз Бровари в напрямку Києва"),
        (2, "kyiv_airdef", "Мінус 1 над Броварами"),
    ], 3)
    t = snap["tracks"][0]
    assert t["count"] == 2 and t["status"] == "active" and t["destroyed"] == 1
    snap = fuse([
        (0, "kyiv_airdef", "Шахед повз Бровари в напрямку Києва"),
        (2, "kyiv_airdef", "Мінус шахед над Броварами"),
    ], 3)
    assert snap["tracks"][0]["status"] == "ended" and snap["tracks"][0]["ended"] == "destroyed"


def test_aggregator_cannot_end_a_track():
    snap = fuse([(0, "kyiv_airdef", "Шахед над Броварами"), (1, "totallzrada", "Мінус шахед над Броварами")], 2)
    assert snap["tracks"][0]["status"] == "active"


def test_all_clear_ends_tracks_in_region():
    snap = fuse([(0, "PoltavaRadar", "Шахед над Полтавою"),
                 (5, "UkraineAlarmSignal", "🟢 Відбій тривоги в Полтавська область")], 6)
    assert snap["tracks"][0]["ended"] == "all clear"


def test_tracks_go_stale_then_disappear():
    msgs = [(0, "PoltavaRadar", "Шахед над Полтавою")]
    assert fuse(msgs, 10)["tracks"][0]["status"] == "active"
    assert fuse(msgs, 40)["tracks"][0]["status"] == "stale"
    assert fuse(msgs, 120)["tracks"] == []


def test_destination_only_report_attaches_to_heading_track():
    snap = fuse([
        (0, "PoltavaRadar", "Шахед над Карлівкою, курс на Полтаву"),
        (6, "kpszsu", "БпЛА курсом на Полтаву"),
    ], 7)
    assert len(snap["tracks"]) == 1 and len(snap["tracks"][0]["sources"]) == 2


def test_order_of_arrival_does_not_matter():
    msgs = [(t, ch, text, i) for i, (t, ch, text) in enumerate(SCRIPT) if ch in CH]
    a = fuse(msgs, 60)
    shuffled = msgs[:]
    random.Random(4).shuffle(shuffled)
    b = fuse(shuffled, 60)
    strip = lambda s: [(t["id"], t["threat"], t["status"], places(t)) for t in s["tracks"]]
    assert strip(a) == strip(b)


def test_demo_scenario_end_to_end():
    e = Engine(Config(mode="demo"))
    e.store.upsert([RawMessage(ch, 1000 + i, T0 + t * 60, text) for i, (t, ch, text) in enumerate(SCRIPT) if t <= 45])
    snap = e.rebuild(now=T0 + 45 * 60)
    by_threat = {}
    for t in snap["tracks"]:
        by_threat.setdefault(t["threat"], []).append(t)
    # the Kursk group is one long track through Sumy and Chernihiv regions
    long_shahed = max(by_threat["shahed"], key=lambda t: len(t["points"]))
    assert {"Bilopillia", "Konotop", "Bakhmach", "Nizhyn"} <= set(places(long_shahed))
    assert len(long_shahed["sources"]) >= 6
    cruise = by_threat["cruise"][0]
    assert {"Znamianka", "Smila", "Cherkasy", "Rzhyshchiv"} <= set(places(cruise))
    assert any(not t["confirmed"] for t in snap["tracks"])     # the aggregator-only report
    assert any(e["kind"] == "explosion" for e in snap["events"])
    assert snap["alerts"] and snap["banners"]
