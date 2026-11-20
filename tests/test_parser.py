import pytest

from dronemap.gazetteer import GAZETTEER
from dronemap.parser import parse_message


def one(text, prefer=(), tier="regional"):
    r = parse_message(text, prefer, tier)
    assert len(r.sightings) == 1, (text, r.sightings)
    return r.sightings[0]


def label(ref):
    return ref.place.key if ref else None


# ------------------------------------------------------------------ gazetteer

@pytest.mark.parametrize("text,key", [
    ("над полтавою", "poltava"), ("в кременчуці", "kremenchuk"), ("у шостці", "shostka"),
    ("кривого рогу", "kryvyi_rih"), ("білу церкву", "bila_tserkva"), ("столицю", "kyiv"),
    ("києва", "kyiv"), ("харкову", "kharkiv"), ("харькова", "kharkiv"), ("одессу", "odesa"),
    ("сумщині", "obl_sumy"), ("полтавська область", "obl_poltava"), ("сумах", "sumy"),
    ("білгород-дністровського", "bilhorod_dnistrovskyi"), ("кременчуцьке водосховище", "kremenchuk_reservoir"),
    ("пятихатки", "piatykhatky"), ("кам'янським", "kamianske"), ("чорного моря", "black_sea"),
])
def test_place_forms(text, key):
    matches = GAZETTEER.find(text)
    assert matches and GAZETTEER.resolve(matches[0]).key == key


def test_ambiguous_place_prefers_channel_region():
    m = GAZETTEER.find("над золочевом")[0]
    assert GAZETTEER.resolve(m, ["lviv"]).key == "zolochiv_lv"
    assert GAZETTEER.resolve(m, ["kharkiv"]).key == "zolochiv_kh"


def test_no_false_place_in_common_words():
    assert GAZETTEER.find("працює ппо, будьте обережні") == []


# ------------------------------------------------------------------ threat types

@pytest.mark.parametrize("text,threat", [
    ("🛵 Шахед над Полтавою", "shahed"),
    ("Мопед над Полтавою", "shahed"),
    ("Ударні БпЛА над Полтавою", "shahed"),
    ("БпЛА над Полтавою", "uav"),
    ("Реактивний шахед над Полтавою", "jet_shahed"),
    ("Гербера над Полтавою", "gerbera"),
    ("Орлан над Краматорськом", "recon"),
    ("Ланцет над Нікополем", "lancet"),
    ("Молнія над Херсоном", "molniya"),
    ("FPV над Бериславом", "fpv"),
    ("Крилаті ракети над Смілою", "cruise"),
    ("Х-101 над Смілою", "cruise"),
    ("Ракета над Смілою", "missile"),
    ("Балістика на Харків", "ballistic"),
    ("Швидкісна ціль на Запоріжжя", "ballistic"),
    ("Кинджал на Київ", "kinzhal"),
    ("КАБи на Харків", "kab"),
])
def test_threat_types(text, threat):
    assert one(text).threat == threat


# ------------------------------------------------------------------ roles

def test_current_and_destination():
    s = one("Група ударних БпЛА на Сумщині, курсом на Конотоп")
    assert label(s.pos) == "obl_sumy" and label(s.dest) == "konotop" and s.group


def test_bare_kurs_is_destination():
    s = one("3 мопеди над Буринню, курс Конотоп")
    assert label(s.pos) == "buryn" and label(s.dest) == "konotop" and s.count == 3


def test_povz_is_not_origin():
    s = one("🛵 3 шахеди повз Білопілля, курс на Ворожбу")
    assert label(s.pos) == "bilopillia" and s.origin is None and label(s.dest) == "vorozhba"


def test_origin_and_destination():
    s = one("Реактивний шахед з Бєлгородщини на Харків", ("kharkiv",))
    assert label(s.origin) == "belgorod" and label(s.dest) == "kharkiv" and s.pos is None


def test_arrow_route():
    s = one("2 мопеди Конотоп → Бахмач")
    assert label(s.pos) == "konotop" and label(s.dest) == "bakhmach" and s.count == 2


def test_hyphen_route():
    s = one("Кременчук - Глобине, 2 мопеди", ("poltava",))
    assert label(s.pos) == "kremenchuk" and label(s.dest) == "hlobyne"


def test_abbreviation_does_not_split_destination():
    s = one("Шахед в напрямку м. Суми")
    assert label(s.dest) == "sumy"


def test_direction_offset_inside_region():
    s = one("БпЛА на півночі Сумщини, курсом на Чернігівщину")
    c = GAZETTEER.places["obl_sumy"]
    assert s.pos.lat > c.lat + 0.3 and "north" in s.pos.label


def test_compass_heading():
    s = one("Орлан в районі Слов'янська, рухається на північ")
    assert s.heading == 0.0
    s = one("Шахед над Ромнами, курс північно-західний")
    assert s.heading == 315.0


@pytest.mark.parametrize("text,n", [("Шахед х3 над Полтавою", 3), ("дві ракети над Смілою", 2),
                                    ("10 шахедів на Одещині", 10), ("Шахед (2) над Полтавою", 2)])
def test_counts(text, n):
    assert one(text).count == n


def test_path_narrative_keeps_waypoints():
    s = one("Шахеди повз Ромни, Недригайлів, курс на Лебедин")
    assert [label(v) for v in s.via] == ["romny"] and label(s.pos) == "nedryhailiv"


def test_multiline_inherits_type():
    r = parse_message("Шахеди:\nРомни → Лубни\nШостка", ("sumy",))
    assert [(label(s.pos), label(s.dest), s.threat) for s in r.sightings] == [
        ("romny", "lubny", "shahed"), ("shostka", None, "shahed")]


def test_continuation_line_fills_destination():
    r = parse_message("3 шахеди на Сумщині\nкурсом на Ромни")
    assert len(r.sightings) == 1 and label(r.sightings[0].dest) == "romny"


# ------------------------------------------------------------------ events & noise

def test_kill_event():
    r = parse_message("Мінус 1 над Броварами", ("kyiv",))
    assert not r.sightings and r.events[0].kind == "kill" and r.events[0].place.place.key == "brovary"


def test_explosion_event():
    r = parse_message("💥 Вибухи в Одесі, працює ППО", ("odesa",))
    assert not r.sightings and r.events[0].kind == "explosion"


def test_possible_explosions_are_a_threat_not_an_explosion():
    r = parse_message("Можливі вибухи на Харківщині, загроза КАБ")
    assert all(e.kind != "explosion" for e in r.events)


def test_alert_on_off():
    assert parse_message("🔴 Повітряна тривога в Сумська область").alerts_on == {"sumy"}
    assert parse_message("🟢 Відбій тривоги в Сумська область").alerts_off == {"sumy"}


def test_regional_channel_all_clear_without_place():
    assert parse_message("Відбій", ("poltava",), "regional").alerts_off == {"poltava"}


def test_aviation_banner():
    r = parse_message("Зліт МіГ-31К! Загроза застосування Кинджалів по всій території України", (), "official")
    assert ("aviation" in [k for k, _ in r.banners]) and not r.sightings


def test_threat_area():
    r = parse_message("Загроза балістики для Харківщини", (), "official")
    assert r.events[0].kind == "threat" and r.events[0].threat == "ballistic" and not r.sightings


def test_summary_is_ignored():
    r = parse_message("У ніч на 20 листопада противник атакував 80 ударними БпЛА. Збито 65 на Сумщині, Харківщині")
    assert r.summary and not r.sightings and not r.events


def test_spam_line_ignored():
    r = parse_message("Підписуйтесь на канал Полтава 24/7 https://t.me/x")
    assert not r.sightings


def test_unrelated_text():
    assert not parse_message("Доброго ранку, Полтава! Гарного дня").relevant


# ------------------------------------------------------------------ patterns seen in real channel posts

def test_alert_system_district_list():
    r = parse_message("🔴 Червоний рівень тривоги\n• Конотопський район (Сумська обл.)\n• Шосткинський район (Сумська обл.)")
    assert r.alerts_on == {"sumy"}
    r = parse_message("🟢 Відбій тривоги\n• Луцький район (Волинська обл.)\n• Ковельський район (Волинська обл.)")
    assert r.alerts_off == {"volyn"}
    # red level lifted, yellow remains: the alert stays on
    assert not parse_message("🟡 Відбій червоної тривоги\n• Полтавський район (Полтавська обл.)").alerts_off


def test_regional_alert_without_known_place_uses_channel_region():
    assert parse_message("🔴 Сумський район — повітряна тривога, червоний рівень", ("sumy",)).alerts_on == {"sumy"}
    assert parse_message("🟡 Повітряна тривога в Подільському районі!", ("odesa",)).alerts_on == {"odesa"}


def test_alert_system_threat_notice_is_area_not_target():
    r = parse_message("🛸 Ізюм (Харківська обл.)\nЗагроза застосування БПЛА. Перейдіть в укриття!", (), "official")
    assert not r.sightings
    assert [(e.kind, e.place.place.key) for e in r.events] == [("threat", "izium")]


def test_parenthesis_clarifies_destination():
    s = one("🚀Ракети з Тернопільщини на північ Івано-Франківщини (Бурштин)", (), "official")
    assert label(s.origin) == "obl_ternopil" and label(s.dest) == "burshtyn"


def test_slash_alternatives_share_role():
    r = parse_message("❗️ 2 групи крилатих ракет повз Машівку на Царичанку/Кобеляки.", ("poltava",))
    s = r.sightings[0]
    assert s.threat == "cruise" and s.count == 2 and label(s.pos) == "mashivka" and label(s.dest) == "tsarychanka"


def test_jet_drone_slang_and_emoji():
    assert one("🏍 Реактивний БпЛА на Івано-Франківськ з півдня", (), "official").threat == "jet_shahed"
    assert one("Реактив в сторону Теплодара", ("odesa",)).threat == "jet_shahed"
    assert one("3 Реактивних курс Мерефа", ("kharkiv",)).threat == "jet_shahed"
    assert not parse_message("Реактивні системи залпового вогню обстріляли Херсон").sightings


def test_village_from_geonames_in_channel_region():
    s = one("+1 Шахед курсом на Савинці", ("kharkiv",))
    assert s.dest.place.name == "Savyntsi" and s.dest.place.oblast == "kharkiv"
    s = one("Р. Шахед курсом на Безлюдовку", ("kharkiv",))      # Russian spelling
    assert s.dest.place.name == "Bezliudivka"
    s = one("ракета через Лисичу Балку на Петраківку", ("cherkasy",))
    assert s.pos.place.name == "Lysycha Balka" and s.dest.place.name == "Petrakivka"


def test_village_needs_capital_and_context():
    # lower-case common word that is also a village name somewhere
    assert not parse_message("шахед курсом на мирне", ("kharkiv",)).sightings
    # a village name with no location word in front is not trusted
    r = parse_message("Шахед. Савинці відпочивають", ("kharkiv",))
    assert all(s.pos is None or s.pos.place.kind != "V" for s in r.sightings)


def test_kamianets_genitive_and_spaced_hyphen():
    s = one("Ракети в районі Камʼянця Подільського")
    assert label(s.pos) == "kamianets_podilskyi"
    s = one("🚀 Ракета повз Камʼянець - Подільський")
    assert label(s.pos) == "kamianets_podilskyi"


def test_news_aftermath_is_not_a_live_target():
    r = parse_message("Внаслідок атаки росіян ракетами зранку по Сумах, постраждалих та загиблих немає.", ("sumy",))
    assert not r.sightings and not r.events


def test_list_of_towns_is_several_targets_but_povz_is_a_path():
    r = parse_message("Балістика на Київ. Ракети: Суми, Полтава")
    assert {label(s.pos) for s in r.sightings if s.pos} == {"sumy", "poltava"}
    s = one("Шахеди повз Ромни, Недригайлів, курс на Лебедин")
    assert [label(v) for v in s.via] == ["romny"]


def test_launch_notice_from_russia_is_not_a_track():
    r = parse_message("Балістика з Брянська", (), "official")
    assert not r.sightings and r.banners


def test_clear_report():
    r = parse_message("Кременчук поки чисто.", ("poltava",))
    assert [p.place.key for p in r.clear_places] == ["kremenchuk"]
    assert parse_message("В області чисто.", ("poltava",)).clear_oblasts == {"poltava"}


def test_huge_count_is_a_total_not_a_group():
    assert one("До 50 крилатих ракет над Житомирщиною").count is None


def test_long_commentary_is_ignored():
    text = ("сразу быстро напишу вам мысли: это явно не был самый масштабный обстрел, как там пугали некоторые, "
            "ракеты летели на Киев, Львов и Хмельницкий, но большая часть была сбита, и это хорошая новость для всех нас, "
            "держитесь")
    assert not parse_message(text).sightings


def test_launch_site_list_is_a_notice():
    r = parse_message("Пуски шахедів: Міллерово, Гвардійське", (), "official")
    assert not r.sightings and r.banners


def test_city_adjective_is_not_a_village():
    r = parse_message("Шахед на Харківське шосе", ("kharkiv",))
    assert all(s.dest is None or s.dest.place.name != "Kharkivske" for s in r.sightings)
