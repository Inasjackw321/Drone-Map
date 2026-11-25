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


def test_terse_follow_up_continues_channel_report():
    CH["monitoring_kyiv"] = {"tier": "regional", "regions": ["kyiv", "kyiv_city"]}
    snap = fuse([(0, "monitoring_kyiv", "🚀 Крилата ракета над Димером"),
                 (2, "monitoring_kyiv", "Гостомель")], 3)
    assert len(snap["tracks"]) == 1 and places(snap["tracks"][0]) == ["Dymer", "Hostomel"]


def test_clear_report_ends_nearby_track():
    snap = fuse([(0, "PoltavaRadar", "Шахед над Кременчуком"), (5, "PoltavaRadar", "Кременчук чисто")], 6)
    assert snap["tracks"][0]["ended"] == "reported clear"


def test_generic_missile_does_not_ride_ballistic_speed():
    snap = fuse([(0, "kpszsu", "Балістика на Київ"), (3, "kpszsu", "Ракета над Львовом")], 4)
    assert len(snap["tracks"]) == 2


# ---------------------------------------------------------------- direction


def test_passed_destination_no_longer_steers_the_heading():
    # reported heading for Mashivka, then seen over Poltava, which is beyond it: it flew past
    snap = fuse([
        (0, "PoltavaRadar", "Шахед над Карлівкою, курс на Машівку"),
        (10, "PoltavaRadar", "Шахед над Полтавою"),
    ], 11)
    t = snap["tracks"][0]
    assert places(t) == ["Karlivka", "Poltava"]
    assert t["dest"] is None
    assert t["heading_source"] == "track"
    assert 270 <= t["heading"] <= 320                         # still flying west-north-west, not back to Mashivka


def test_region_destination_is_done_once_inside_the_region():
    CH["RadarChernihiv"] = {"tier": "regional", "regions": ["chernihiv"]}
    snap = fuse([
        (0, "kpszsu", "БпЛА на півночі Сумщини, курсом на Чернігівщину."),
        (12, "RadarChernihiv", "Шахеди над Бахмачем"),
    ], 13)
    t = snap["tracks"][0]
    assert t["place"] == "Bakhmach" and t["dest"] is None
    assert t["heading_source"] == "track" and 240 <= t["heading"] <= 330


def test_newer_reported_course_wins_over_older_destination():
    snap = fuse([
        (0, "PoltavaRadar", "Шахед над Полтавою, курс на Решетилівку"),
        (5, "PoltavaRadar", "Шахед над Полтавою, курс північний"),
    ], 6)
    t = snap["tracks"][0]
    assert t["heading"] == 0 and t["heading_source"] == "reported"


def test_destination_named_in_the_same_post_is_kept_even_when_close():
    CH["kherson_non_drone"] = {"tier": "regional", "regions": ["kherson"]}
    snap = fuse([(0, "kherson_non_drone", "Молнія над Антонівкою, курс на Херсон")], 1)
    t = snap["tracks"][0]
    assert t["dest"]["name"] == "Kherson" and t["heading_source"] == "dest"


def test_no_speed_is_published():
    snap = fuse([(0, "PoltavaRadar", "Шахед над Карлівкою, курс на Полтаву"),
                 (8, "PoltavaRadar", "Шахед над Машівкою, курс на Полтаву")], 9)
    assert not any("speed" in k for t in snap["tracks"] for k in t)


def test_heading_follows_reports_in_the_demo_night():
    """Every moving track in the scripted night points within 90° of its last flown leg."""
    from dronemap.gazetteer import angle_diff, bearing, haversine
    e = Engine(Config(mode="demo"))
    e.store.upsert([RawMessage(ch, 1000 + i, T0 + t * 60, text) for i, (t, ch, text) in enumerate(SCRIPT) if t <= 45])
    snap = e.rebuild(now=T0 + 45 * 60)
    checked = 0
    for t in snap["tracks"]:
        pts = [p for p in t["points"] if p["precision"] == "point"]
        if t["status"] != "active" or t["heading"] is None or len(pts) < 2:
            continue
        a, b = pts[-2], pts[-1]
        if haversine(a["lat"], a["lon"], b["lat"], b["lon"]) < 10:
            continue
        assert angle_diff(bearing(a["lat"], a["lon"], b["lat"], b["lon"]), t["heading"]) < 90, t["place"]
        checked += 1
    assert checked >= 4


# ---------------------------------------------------------------- heatmap history


def test_heat_points_skip_region_centres_and_dedupe():
    items = []
    for i, (t, ch, text) in enumerate([
        (0, "kpszsu", "БпЛА на Сумщині"),                                   # region only: no heat
        (1, "sumyregion", "🛵 3 шахеди повз Білопілля, курс на Ворожбу"),
        (5, "inforomen", "Шахеди в районі Ворожби, рухаються на Конотоп"),
    ]):
        meta = CH[ch]
        items.append((MsgRef(ch, i + 1, T0 + t * 60, meta["tier"], text), parse_message(text, meta["regions"], meta["tier"])))
    from dronemap.fusion import build_fusion
    rows = build_fusion(items, CH, None).heat_points()
    assert sorted(r["place"] for r in rows) == ["Bilopillia", "Vorozhba"]
    assert all(r["weight"] == 3 and r["confirmed"] for r in rows)
    e = Engine(Config(mode="demo"))
    e.store.add_heat(rows)
    e.store.add_heat(rows)                                   # recording the same reports again adds nothing
    assert len(e.store.heat_since(0)) == 2


def test_heatmap_view_periods_and_kinds():
    from dronemap.demo import demo_history
    e = Engine(Config(mode="demo"))
    e.store.add_heat(demo_history(e.by_handle, e.weights, days=28))
    day, week, month = (e.heatmap_view(h, "all", -120) for h in (24, 7 * 24, 28 * 24))
    assert 0 < day["observations"] < week["observations"] < month["observations"]
    assert len(day["series"]) in (24, 25) and day["step"] == 3600
    assert len(week["series"]) in (7, 8) and month["step"] == 86400
    assert not month["partial"]
    assert {s for row in month["series"] for s in row if s != "t"} <= {"drone", "missile", "kab"}
    missiles = e.heatmap_view(28 * 24, "missile")
    assert missiles["observations"] and all(b["threat"] in ("cruise", "ballistic", "missile", "kinzhal")
                                            for b in missiles["by_threat"])
    drones = e.heatmap_view(28 * 24, "drone")
    assert {"shahed", "gerbera", "recon"} <= {b["threat"] for b in drones["by_threat"]}
    assert drones["observations"] + missiles["observations"] + e.heatmap_view(28 * 24, "kab")["observations"] \
        == month["observations"]
    assert e.heatmap_view(28 * 24, "explosion")["observations"] > 0


def test_new_target_post_starts_its_own_track():
    snap = fuse([
        (0, "PoltavaRadar", "Шахед над Карлівкою, курс на Полтаву"),
        (16, "kpszsu", "+1 шахед курсом на Полтаву"),
    ], 17)
    assert len(snap["tracks"]) == 2
    # the same news repeated a few minutes later (or by another channel) is still one target
    snap = fuse([
        (0, "PoltavaRadar", "+1 шахед курсом на Полтаву"),
        (3, "totallzrada", "+1 шахед курсом на Полтаву"),
    ], 4)
    assert len(snap["tracks"]) == 1


def test_region_post_with_destination_behind_does_not_turn_a_track_around():
    snap = fuse([
        (0, "PoltavaRadar", "Шахед над Карлівкою, курс на Машівку"),
        (10, "PoltavaRadar", "Шахед над Полтавою"),
        (12, "kpszsu", "БпЛА на Полтавщині, курсом на Карлівку"),
    ], 13)
    seen = next(t for t in snap["tracks"] if t["place"] == "Poltava")
    assert seen["heading_source"] == "track" and 270 <= seen["heading"] <= 320
    assert len(snap["tracks"]) == 2
