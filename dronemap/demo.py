"""Demo mode: replays a scripted, realistic attack night so the app can be tried without Telegram access.

Times are minutes relative to the scenario start. When the demo starts, the first 40 minutes are
loaded as history; the rest arrive in real time. The scenario then loops.
"""
from __future__ import annotations

import asyncio
import random
import time

from .store import RawMessage, Store

HISTORY_MIN = 40

SCRIPT: list[tuple[float, str, str]] = [
    # --- alerts
    (0.5, "UkraineAlarmSignal", "🔴 Повітряна тривога в Сумська область"),
    (1.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Чернігівська область"),
    (4.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Одеська область"),
    (8.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Полтавська область"),
    (10.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Київська область"),
    (10.2, "UkraineAlarmSignal", "🔴 Повітряна тривога в м. Київ"),
    (14.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Харківська область"),
    (16.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Донецька область"),
    (23.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Вінницька область"),
    (26.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Дніпропетровська область"),
    (30.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Кіровоградська область"),
    (33.0, "UkraineAlarmSignal", "🔴 Повітряна тривога в Черкаська область"),

    # --- Track A: Shahed group Kursk -> Sumy region -> Chernihiv region -> Kyiv  (~3 km/min)
    (1.5, "kpszsu", "Група ударних БпЛА з Курщини на Сумщину."),
    (5.0, "sumyregion", "🛵 3 шахеди повз Білопілля, курс на Ворожбу"),
    (9.0, "inforomen", "Шахеди в районі Ворожби, рухаються на Конотоп"),
    (11.0, "rdsprostir", "3 мопеди над Буринню, курс Конотоп"),
    (15.0, "monikppy", "3 мопеди Конотоп → Бахмач"),
    (18.0, "kpszsu", "БпЛА на півночі Сумщини, курсом на Чернігівщину."),
    (22.0, "RadarChernihiv", "🛵 Шахеди над Бахмачем, курс на Ніжин"),
    (30.0, "tactychna_rukavuchkaa", "3 шахеди над Борзною, курс на Ніжин"),
    (40.0, "my_safety_Chernigiv", "3 шахеди Ніжин, курс на Бровари"),
    (52.0, "horizon_of_war_Official", "Шахеди в районі Козельця, курс на Бровари"),
    (54.0, "kpszsu", "БпЛА на Київщині, курсом на Бровари."),
    (64.0, "monitoring_kyiv", "3 шахеди повз Бровари в напрямку Києва"),
    (65.5, "kyiv_airdef", "Мінус 1 над Броварами"),
    (68.0, "shahedradar", "2 шахеди над Троєщиною"),
    (69.5, "monitoring_kyiv", "Мінус шахед над Дарницею"),
    (71.0, "kyiv_airdef", "Мінус 1 над Києвом. Чисто"),
    (73.0, "UkraineAlarmSignal", "🟢 Відбій тривоги в м. Київ"),

    # --- Track B: Shaheds from the Black Sea -> Odesa
    (3.0, "kpszsu", "Група БпЛА з акваторії Чорного моря курсом на Одещину."),
    (10.0, "odessa_inform", "🛵 2 шахеди з Чорного моря на Затоку"),
    (18.0, "delta_odesa", "Шахеди над Затокою, курс на Овідіополь"),
    (25.0, "temporis_odesa", "2 шахеди Овідіополь → Одеса"),
    (31.0, "odessa_knight", "Шахеди на підльоті до Одеси"),
    (41.0, "odessaveter", "💥 Вибухи в Одесі, працює ППО"),
    (41.5, "ReniHub", "Вибухи в Одесі"),

    # --- Track C: Shahed Kharkiv region -> Poltava -> Myrhorod
    (6.0, "kpszsu", "БпЛА на Харківщині курсом на Красноград."),
    (12.0, "kharkov_media", "Шахед повз Красноград, курс на Карлівку"),
    (20.0, "PoltavaRadar", "🛵 Шахед в районі Карлівки, курсом на Полтаву"),
    (27.0, "ppopoltavanightfighters", "Мопед над Машівкою, рухається в бік Полтави"),
    (35.0, "rozvidkaneba", "Шахед на Полтавщині, рухається в напрямку Полтави"),
    (38.0, "PoltavaRanger", "Шахед над Полтавою, курс на Решетилівку"),
    (45.0, "kremen_sv", "Шахед повз Решетилівку на Миргород"),
    (53.0, "PoltavaRadar", "Шахед в районі Великої Багачки, курс на Миргород"),

    # --- Cruise missiles Kirovohrad -> Cherkasy -> Kyiv region (~13 km/min)
    (31.0, "kpszsu", "Крилаті ракети в Кіровоградській області курсом на Черкащину!"),
    (33.0, "krop_vanek", "🚀 2 ракети повз Знам'янку, курс на Смілу"),
    (38.5, "cherkasy_nebbo", "Ракети над Смілою курсом на Черкаси"),
    (41.0, "cherkasy_nebbo", "2 крилаті в районі Черкас, напрямок Канів"),
    (45.0, "kyiv_nebo", "Крилаті ракети на Київщині, повз Ржищів в напрямку Обухова"),
    (46.0, "kpszsu", "Ракети курсом на Київ!"),
    (47.5, "kyiv_airdef", "Ракета над Обуховом, курс на Київ"),
    (49.0, "monitoring_kyiv", "Збито 2 ракети над Києвом"),

    # --- Ballistic threat & strike on Zaporizhzhia
    (40.5, "kpszsu", "Загроза застосування балістичного озброєння з півдня!"),
    (42.5, "kpszsu", "Швидкісна ціль на Запоріжжя!"),
    (43.5, "zaborzp", "💥 Вибух у Запоріжжі"),

    # --- KAB on Sumy / Kharkiv
    (20.0, "kpszsu", "Пуски КАБ на Сумщину."),
    (25.0, "kharkov_media", "КАБи на Харків!"),
    (26.0, "place_kharkiv", "💥 Вибухи у Харкові, приліт КАБ в районі Салтівки"),

    # --- Recon UAV (Orlan) over Donetsk region
    (15.0, "kramatorsk_radar", "Орлан над Краматорськом, курс на Слов'янськ"),
    (27.0, "operatyvnyi_donbas", "Орлан в районі Слов'янська, рухається на північ"),
    (38.0, "kramatorsk_radar", "Орлан повз Святогірськ"),
    (49.0, "operatyvnyi_donbas", "Орлан біля Святогірська, курс на Лиман"),

    # --- Lancet near Nikopol
    (33.0, "nikalert", "Ланцет у районі Нікополя"),
    (36.0, "nikalert", "Ланцет над Марганцем"),

    # --- Molniya / FPV in Kherson region
    (31.0, "kherson_non_drone", "Молнія над Антонівкою, курс на Херсон"),
    (35.0, "pivden_FPV", "FPV-дрони над Бериславом"),

    # --- Gerbera decoys Chernihiv region -> Vyshhorod -> Kyiv
    (12.0, "ShahedChernihiv", "Гербери в районі Козельця, курс на Остер"),
    (19.0, "PhantomChe", "Гербера над Остром"),
    (26.0, "Northern_Sich_ukr", "2 гербери повз Остер на Вишгород"),
    (36.0, "kyiv_nebo", "Гербери над Вишгородом"),
    (42.0, "monitoring_kyiv", "2 гербери над Оболонню"),
    (43.5, "kyiv_airdef", "Мінус 1 над Оболонню"),
    (47.0, "kyiv_airdef", "Мінус гербера над Києвом"),

    # --- Jet Shahed into Kharkiv
    (37.0, "kharkivlife", "Реактивний шахед з Бєлгородщини на Харків"),
    (39.0, "kharkov_media", "Реактивний шахед над Харковом, курс на Мерефу"),
    (40.0, "cxidua", "Мінус реактивний над Мерефою"),

    # --- Generic UAV in Vinnytsia region
    (24.0, "vin_info_ppo", "БпЛА на Вінниччині, курсом на Калинівку"),
    (30.0, "vin_info_ppo", "БпЛА повз Калинівку в напрямку Хмільника"),
    (44.0, "vin_info_ppo", "БпЛА в районі Хмільника, курс на Старокостянтинів"),

    # --- Aggregator-only report: stays unconfirmed
    (28.0, "totallzrada", "Шахед над Кропивницьким"),

    # --- MiG-31K banner and all-clear
    (39.0, "kpszsu", "Зліт МіГ-31К! Загроза застосування Кинджалів по всій території України."),
    (34.0, "UkraineAlarmSignal", "🟢 Відбій тривоги в Сумська область"),
    (52.0, "UkraineAlarmSignal", "🟢 Відбій тривоги в Одеська область"),

    # --- a nightly summary (ignored for the map, shown in the feed)
    (2.0, "kpszsu", "У ніч на 20 листопада противник атакував 80 ударними БпЛА типу Shahed. "
                    "Станом на 08:30 збито/подавлено 65 БпЛА на півночі, сході та півдні країни."),
]
SCENARIO_LEN_MIN = max(t for t, _, _ in SCRIPT) + 12


def demo_history(channels: dict, weights: dict | None, days: int = 28, seed: int = 7) -> list[dict]:
    """Heatmap history for demo mode: the scripted night replayed on earlier nights.

    Each night keeps a random share of the posts, so nights differ in size and the map shows
    hot and cooler areas. Only used with --demo.
    """
    from .fusion import MsgRef, build_fusion
    from .parser import parse_message

    rng = random.Random(seed)
    now = time.time()
    items = []
    for k in range(1, days + 1):
        base = now - k * 86400 + rng.uniform(1.5, 6) * 3600
        keep = rng.uniform(0.35, 0.95)
        for idx, (t, ch, text) in enumerate(SCRIPT):
            meta = channels.get(ch)
            if meta is None or rng.random() > keep:
                continue
            ref = MsgRef(ch, k * 10000 + idx, base + t * 60, meta.get("tier", "aggregator"), text)
            items.append((ref, parse_message(text, meta.get("regions", []), ref.tier)))
    return build_fusion(items, channels, weights).heat_points()


class DemoSource:
    def __init__(self, store: Store, on_change, status: dict):
        self.store = store
        self.on_change = on_change
        self.status = status
        self.stopped = False

    def _publish(self, base: float, items: list[tuple[int, tuple[float, str, str]]]) -> None:
        msgs = [RawMessage(ch, 1000 + idx, base + t * 60, text) for idx, (t, ch, text) in items]
        if msgs:
            self.store.upsert(msgs)
            now = time.time()
            for m in msgs:
                st = self.status.get(m.channel)
                if st:
                    st.state, st.last_ok, st.last_fetch = "ok", now, now
                    st.last_post_ts = max(st.last_post_ts or 0, m.ts)
                    st.posts_seen += 1
                    st.via = "demo"
            self.on_change()

    async def run(self) -> None:
        indexed = list(enumerate(SCRIPT))
        while not self.stopped:
            self.store.clear()
            for st in self.status.values():
                st.state, st.via, st.posts_seen, st.last_post_ts = "ok", "demo", 0, None
            base = time.time() - HISTORY_MIN * 60
            self._publish(base, [it for it in indexed if it[1][0] <= HISTORY_MIN])
            pending = sorted([it for it in indexed if it[1][0] > HISTORY_MIN], key=lambda it: it[1][0])
            for item in pending:
                delay = base + item[1][0] * 60 - time.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                self._publish(base, [item])
            await asyncio.sleep(max(0.0, base + SCENARIO_LEN_MIN * 60 - time.time()))
