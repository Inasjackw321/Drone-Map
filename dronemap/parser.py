"""Turn a Ukrainian / Russian air-raid monitoring message into structured observations.

The parser is deliberately rule-based: every decision can be traced back to a regex,
and the rules are covered by tests (tests/test_parser.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .gazetteer import GAZETTEER, NEIGHBORS, UKRAINE_OBLASTS, Place, destination, haversine
from .settlements import SETTLEMENTS

# --------------------------------------------------------------------------- threats

THREATS: dict[str, dict] = {
    #  key          family     spec  label                    speed km/h
    "kinzhal":    {"family": "missile", "spec": 4, "label": "Kinzhal",        "speed": 4000},
    "ballistic":  {"family": "missile", "spec": 3, "label": "Ballistic missile", "speed": 3000},
    "cruise":     {"family": "missile", "spec": 3, "label": "Cruise missile", "speed": 800},
    "missile":    {"family": "missile", "spec": 1, "label": "Missile",        "speed": 900},
    "kab":        {"family": "kab",     "spec": 2, "label": "Guided bomb (KAB)", "speed": 450},
    "jet_shahed": {"family": "drone",   "spec": 4, "label": "Jet Shahed (Geran-3)", "speed": 450},
    "gerbera":    {"family": "drone",   "spec": 3, "label": "Gerbera decoy",  "speed": 160},
    "lancet":     {"family": "drone",   "spec": 3, "label": "Lancet",         "speed": 110},
    "molniya":    {"family": "drone",   "spec": 3, "label": "Molniya",        "speed": 120},
    "fpv":        {"family": "drone",   "spec": 3, "label": "FPV drone",      "speed": 100},
    "recon":      {"family": "drone",   "spec": 3, "label": "Recon UAV (Orlan/ZALA)", "speed": 130},
    "shahed":     {"family": "drone",   "spec": 2, "label": "Shahed",         "speed": 190},
    "uav":        {"family": "drone",   "spec": 1, "label": "UAV (type unknown)", "speed": 190},
}

_W = r"(?<![\w-])"  # left word boundary that treats hyphen as part of a word

THREAT_PATTERNS: list[tuple[str, re.Pattern]] = [(k, re.compile(p)) for k, p in [
    ("kinzhal", _W + r"(?:кинджал\w*|кинжал\w*|[хx]-?47\w*|kinzhal)"),
    ("ballistic", _W + r"(?:балісти\w*|баллисти\w*|іскандер\w*|искандер\w*|кн-?23|kn-?23|[сc]-?[34]00\b|"
                  r"швидкісн\w*\s+ціл\w*|високошвидкісн\w*\s+ціл\w*|скоростн\w*\s+цел\w*|высокоскоростн\w*\s+цел\w*|ballistic\w*|iskander)"),
    ("cruise", _W + r"(?:крилат\w*|крылат\w*|калібр\w*|калибр\w*|[хx]-?(?:101|555|59|69|22|32|55)\b|"
               r"онікс\w*|оникс\w*|циркон\w*|cruise)"),
    ("missile", _W + r"(?:ракет\w*|missile\w*)|🚀"),
    ("kab", _W + r"(?:каб(?:и|ів|ами|ах|ом|а)?(?![\w])|умпк|авіабомб\w*|авиабомб\w*|"
            r"керован\w*\s+(?:авіа)?бомб\w*|управляем\w*\s+(?:авиа)?бомб\w*|фаб-?\d+)"),
    ("jet_shahed", _W + r"(?:реактивн\w*\s+(?:шахед\w*|шахід\w*|герань|герані|бпла|дрон\w*|безпілот\w*|беспилот\w*)|"
                   r"шахед-?238|герань-?3|geran-?3|shahed-?238|"
                   r"реактив\w*(?!\w)(?!\s+(?:систем\w*|артилер\w*|снаряд\w*|залп\w*|літак\w*|самол\w*)))|🏍"),
    ("gerbera", _W + r"(?:гербер\w*|gerbera|імітатор\w*|имитатор\w*|дрон\w*-приман\w*|приманк\w*)"),
    ("lancet", _W + r"(?:ланцет\w*|lancet)"),
    ("molniya", _W + r"(?:молні[яїюєй]\w*|молни[яиюей]\w*|блискавк\w*|molniya)"),
    ("fpv", _W + r"(?:fpv|фпв)(?![a-zа-я])"),
    ("recon", _W + r"(?:орлан\w*|zala(?![a-z])|зала(?![\w])|суперкам\w*|supercam|"
              r"розвідувальн\w*\s+(?:бпла|дрон\w*|безпілот\w*)|разведывательн\w*\s+(?:бпла|дрон\w*|беспилот\w*)|"
              r"розвідник\w*|мохаджер\w*|mohajer|форпост\w*)"),
    ("shahed", _W + r"(?:шахед\w*|шахід\w*|шаhед\w*|герань\w*|герані\w*|мопед\w*|shahed\w*|geran\w*|бензинов\w*|поршнев\w*|"
               r"звичайн\w*\s+(?:бпла|дрон\w*|безпілот\w*|шахед\w*)|обычн\w*\s+(?:бпла|дрон\w*|беспилот\w*|шахед\w*)|"
               r"ударн\w*\s+(?:бпла|дрон\w*|безпілот\w*|беспилот\w*))|🛵"),
    ("uav", _W + r"(?:бпла|безпілот\w*|беспилот\w*|дрон\w*|uav|бла(?![\w])|італмас\w*|италмас\w*)|🛸"),
]]

# --------------------------------------------------------------------------- event cues

KILL_RE = re.compile(_W + r"(?:збит\w*|збил\w*|знищен\w*|знищил\w*|мінус\w*|сбит\w*|сбил\w*|уничтож\w*|"
                     r"подавлен\w*|приземлил\w*|ліквідов\w*|минус\w*)|➖")
EXPL_RE = re.compile(_W + r"(?:вибух\w*|прил[іеё]т\w*|взрыв\w*|влучан\w*|влучив\w*|попадан\w*|детонац\w*)|💥")
POSSIBLE_RE = re.compile(_W + r"(?:можлив\w*|ймовірн\w*|возможн\w*|вероятн\w*)")
THREAT_AREA_RE = re.compile(_W + r"(?:загроз\w*|небезпек\w*|угроз\w*|опасн\w*)")
ALLCLEAR_RE = re.compile(_W + r"(?:відбій|відбою|отбой|отбоя)|🟢")
ALERT_RE = re.compile(_W + r"(?:тривог\w*|тревог\w*)")
AVIATION_RE = re.compile(_W + r"(?:міг-?31\w*|миг-?31\w*|ту-?95\w*|ту-?160\w*|ту-?22\w*|су-?34\w*|су-?35\w*|"
                         r"тактичн\w*\s+авіац\w*|тактическ\w*\s+авиац\w*|стратегічн\w*\s+авіац\w*|"
                         r"стратегическ\w*\s+авиац\w*|бортів\s+ту|бомбардувальник\w*)")
TAKEOFF_RE = re.compile(_W + r"(?:зліт|злет|зльот|піднят\w*|піднял\w*|взлет\w*|в\s+повітрі|в\s+воздухе|активн\w*)")
SUMMARY_RE = re.compile(r"(?:у|в)\s+ніч\s+на\s+\d|станом\s+на\s+\d|протягом\s+(?:доби|ночі)|за\s+(?:минулу\s+)?добу|"
                        r"в\s+ночь\s+на\s+\d|за\s+сутки|загалом\s+(?:збито|знешкоджено)|всього\s+(?:збито|знешкоджено)|"
                        r"результати\s+(?:роботи|відбиття)|вчора\b")
NEWS_RE = re.compile(_W + r"(?:внаслідок|постраждал\w*|загибл\w*|загинул\w*|поранен\w*|пошкоджен\w*|зруйнован\w*|"
                     r"дснс|рятувальник\w*|наслідк\w*|травмован\w*|госпіталізован\w*|пострадав\w*|погиб\w*|"
                     r"поврежден\w*|разрушен\w*|последстви\w*|спасател\w*|постраждалих|жертв\w*)")
PATH_CUE = re.compile(_W + r"(?:повз|через|минає|минули|пролітає\w*|пролетів|пролетіли|проходить|прошел|прошли|мимо|вздовж|уздовж)")
FOOTER_RE = re.compile(r"(?:підписатис[яь]|підпишись|підписуйтесь|подписаться|подпишись|подписывайтесь|"
                       r"підтримати\s+(?:канал|адміна|нас)|надіслати\s+новину|прислать\s+новость)(?![\w']).*$", re.M)
SPAM_RE = re.compile(r"підпис|подпис|реклам|донат|задонат|монобанк|https?://|t\.me/|@\w{4,}|розіграш|розыгрыш")
MOVE_CUE_RE = re.compile(_W + r"(?:курс\w*|напрям\w*|направлен\w*|над|повз|через|районі|районе|рухає\w*|летить|летять|"
                         r"летит|летят|бік|сторону|підльот\w*|подлет\w*)|→|➡")

# --------------------------------------------------------------------------- roles

DEST_CUE = re.compile(
    r"(?<![\w'])(?:курс\w*\s+(?:на|до|у|в)|курс\w*\s*[-:–—]|курс\w*|у\s+напрям\w*(?:\s+на)?|в\s+напрям\w*(?:\s+на)?|напрям\w*(?:\s+на|\s+до)?|"
    r"в\s+бік|у\s+бік|убік|в\s+сторону|у\s+сторону|в\s+направлени\w*|направлени\w*(?:\s+на)?|"
    r"на\s+підльот\w*\s+до|підлітає\s+до|підлітають\s+до|на\s+подлете\s+к|"
    r"(?:летить|летять|летит|летят|рухається|рухаються|рухаєтся|движется|движутся|прямує|прямують|йде|йдуть|ідуть|"
    r"заходить|заходять|залітає|залітають|повертає|повернув\w*|розвернув\w*|змінив\w*\s+курс|"
    r"полетів|полетіли|полетел\w*)\s+(?:на|до|в|у|к)|(?:далі|дальше)(?:\s+(?:ймовірно|можливо|напевно|мабуть|вероятно|возможно|на))?|до|к|→|➡️?|⏩|->|=>|—>|–>|>>)\s*$")
ORIGIN_CUE = re.compile(
    r"(?<![\w'])(?:з|із|зі|від|з\s+боку|з\s+напрямку|з\s+акваторії|з\s+території|з\s+району|с\s+направления|"
    r"со\s+стороны|с|из|из\s+района|вилет\w*\s+(?:з|із)|пуск\w*\s+(?:з|із|с)|запуск\w*\s+(?:з|із|с))\s*$")
CURRENT_CUE = re.compile(
    r"(?<![\w'])(?:над|в\s+районі|у\s+районі|районі|в\s+р-ні|у\s+р-ні|р-н|р-ні|біля|поблизу|неподалік|повз|через|в|у|"
    r"в\s+районе|районе|около|возле|рядом\s+с|вблизи|по|околиц\w*|на\s+околиц\w*|на\s+межі\s+з?|між|поміж|между)\s*$")
NA_CUE = re.compile(r"(?<![\w])на\s*$")
HYPHEN_CUE = re.compile(r"[-–—]\s*$")
ABBREV_TAIL = re.compile(r"(?:(?<![\w])(?:м|с|смт|сел|г|пгт|н\.\s?п|нп|ст|обл|р-н)\.?\s*|[«\"(]\s*)$")

DIR_WORD = (r"північно-східн\w*|північно-західн\w*|південно-східн\w*|південно-західн\w*|"
            r"північн\w*\s+сх\w*|північн\w*\s+зах\w*|південн\w*\s+сх\w*|південн\w*\s+зах\w*|"
            r"північ\w*|півноч\w*|південь|південн\w*|півдн\w*|захід|західн\w*|заход\w*|схід|східн\w*|сход\w*|центр\w*|"
            r"северо-восток\w*|северо-запад\w*|юго-восток\w*|юго-запад\w*|север\w*|юг\w*|южн\w*|запад\w*|восток\w*")
OFFSET_LOC = re.compile(rf"(?:на|в|у)\s+(?P<dir>{DIR_WORD})(?:\s+частин\w*)?\s*$")
OFFSET_REL = re.compile(r"(?P<dir>північніше|південніше|західніше|східніше|північно-західніше|північно-східніше|"
                        r"південно-західніше|південно-східніше|севернее|южнее|западнее|восточнее)\s*(?:від\s+|от\s+)?$")
OFFSET_REL2 = re.compile(rf"на\s+(?P<dir>{DIR_WORD})\s+(?:від|от)\s*$")
KM_OFFSET = re.compile(
    rf"(?:(?:за|в|у|на\s+відстані|на\s+расстоянии)\s+)?(?:~|≈|близько\s+|около\s+|приблизно\s+)?(?P<km>\d{{1,3}})\s*"
    rf"(?:-?ти\s+)?(?:км|кілометр\w*|километр\w*)\.?"
    rf"(?:\s+(?:на\s+)?(?P<dir>{DIR_WORD}|північніше|південніше|західніше|східніше|севернее|южнее|западнее|восточнее))?"
    rf"(?:\s+(?:від|от|до))?\s*$")

HEADING_RES = [
    re.compile(rf"курс\w*\s+(?:на\s+)?(?P<dir>{DIR_WORD})(?!\s+(?:від|от)(?![\w]))"),
    re.compile(rf"(?P<dir>{DIR_WORD})\s+курс\w*"),
    re.compile(rf"(?:рухає\w*|летить|летять|летит|летят|движ\w*|повертає|повернув\w*|напрям\w*|направлени\w*)\s+"
               rf"(?:на\s+)?(?P<dir>{DIR_WORD})(?!\s+(?:від|от)(?![\w]))"),
    re.compile(rf"(?:у|в)\s+(?P<dir>{DIR_WORD})\s+напрям\w*"),
]
FROM_DIR_RE = re.compile(r"(?<![\w'])(?:з|із|зі|с|со)\s+(?P<dir>півночі|півдня|сходу|заходу|північного\s+сходу|північного\s+заходу|"
                         r"південного\s+сходу|південного\s+заходу|севера|юга|востока|запада|северо-востока|"
                         r"северо-запада|юго-востока|юго-запада)(?![\w])")

NUM_WORDS = {
    "один": 1, "одна": 1, "одне": 1, "одного": 1, "два": 2, "дві": 2, "две": 2, "пара": 2, "пару": 2, "двоє": 2,
    "три": 3, "троє": 3, "чотири": 4, "четыре": 4, "п'ять": 5, "пять": 5, "шість": 6, "шесть": 6,
    "сім": 7, "семь": 7, "вісім": 8, "восемь": 8, "дев'ять": 9, "девять": 9, "десять": 10,
}
COUNT_BEFORE = re.compile(
    r"(?:^|[\s(+~≈])(?P<n>\d{1,3}|" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")\s*(?:х|x|×|шт\.?|-?ти|-?ох|-?а)?\s*"
    r"(?:ударн\w*|реактивн\w*|ворож\w*|крилат\w*|балістичн\w*|розвідувальн\w*|групи|групп\w*)?\s*$")
COUNT_AFTER = re.compile(r"^\w*\s*(?:[хx×]\s*(?P<a>\d{1,3})(?!\d)|\((?P<b>\d{1,3})\)|[-–]\s*(?P<c>\d{1,3})\s*(?:шт|од)\b)")
GROUP_RE = re.compile(_W + r"(?:груп\w*|кілька|декілька|несколько|рій|зграя)")
# "новий реактивний БпЛА", "+1 шахед", "ще 2 шахеди", "ещё один": a new object, not the one already tracked.
# Only right before a threat word (or at the start of a line), so "Новий Буг" or "Нова Каховка" do not count.
NEW_WORD = r"(?:нов(?:ий|а|і|е|их|ого|ый|ая|ые)|ще\s+(?:один|одна|одне|\d{1,2}|кілька|декілька|пара|пару)|" \
           r"еще\s+(?:один|одна|одно|\d{1,2}|несколько|пара|пару)|\+\s?\d{1,2})"
NEW_BEFORE = re.compile(r"(?:(?<![\w'])" + NEW_WORD + r"|\+)\s*(?:[хx×]\s*)?(?:ударн\w*\s+|ворож\w*\s+)?$")
NEW_START = re.compile(r"^\W{0,3}" + NEW_WORD + r"(?![\w'])")


def dir_to_deg(word: str) -> float | None:
    w = word.replace(" ", "")
    north = w.startswith(("півн", "північ", "сев"))
    south = w.startswith(("півд", "юг", "юж"))
    east = "сх" in w or "вост" in w
    west = "зах" in w or "запад" in w
    if w.startswith("центр"):
        return None
    if north and east:
        return 45.0
    if north and west:
        return 315.0
    if south and east:
        return 135.0
    if south and west:
        return 225.0
    if north:
        return 0.0
    if south:
        return 180.0
    if east:
        return 90.0
    if west:
        return 270.0
    return None


# --------------------------------------------------------------------------- data classes

@dataclass
class PlaceRef:
    place: Place
    role: str            # current | dest | origin
    lat: float
    lon: float
    precision: str       # point | region
    label: str           # human readable, e.g. "north of Sumy region"
    start: int = 0
    dist_km: float | None = None   # "за 30 км від X": that far from the place, direction unknown

    def as_dict(self) -> dict:
        return {"key": self.place.key, "name": self.label, "lat": round(self.lat, 4), "lon": round(self.lon, 4),
                "precision": self.precision, "oblast": self.place.oblast}


@dataclass
class Sighting:
    threat: str
    count: int | None = None
    group: bool = False
    pos: PlaceRef | None = None
    via: list[PlaceRef] = field(default_factory=list)
    dest: PlaceRef | None = None
    origin: PlaceRef | None = None
    heading: float | None = None
    text: str = ""
    own_threat: bool = True
    new: bool = False      # "новий шахед", "+1 реактивний", "ще один": another object, not an update


@dataclass
class AreaEvent:
    kind: str            # explosion | kill | threat
    threat: str | None
    place: PlaceRef | None
    count: int | None = None
    text: str = ""


@dataclass
class ParsedMessage:
    sightings: list[Sighting] = field(default_factory=list)
    events: list[AreaEvent] = field(default_factory=list)
    alerts_on: set[str] = field(default_factory=set)      # raion ids ("UA5902") or oblast keys ("sumy")
    alerts_off: set[str] = field(default_factory=set)
    alert_level: str = "red"                                # red | yellow
    alert_levels: dict[str, str] = field(default_factory=dict)   # per unit, when a post mixes levels
    banners: list[tuple[str, str]] = field(default_factory=list)   # (kind, text)
    threats: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    summary: bool = False
    clear_places: list[PlaceRef] = field(default_factory=list)
    clear_oblasts: set[str] = field(default_factory=set)
    bare_places: list[PlaceRef] = field(default_factory=list)
    ru_zones: list[tuple[PlaceRef, str]] = field(default_factory=list)   # (place, drone|missile) from Russian sources
    ru_clear: list[PlaceRef] = field(default_factory=list)
    threats_cleared: list[str] = field(default_factory=list)         # "відбій загрози балістики"
    bare_new: bool = False         # the follow-up is about another object ("Ще один з Херсонщини ...")

    @property
    def relevant(self) -> bool:
        return bool(self.sightings or self.events or self.alerts_on or self.alerts_off or self.banners
                    or self.clear_places or self.clear_oblasts or self.ru_zones or self.ru_clear or self.threats_cleared)


# --------------------------------------------------------------------------- helpers

_APOS = re.compile(r"[’ʼ`´‘ʹ]")


def normalize(text: str) -> str:
    t = text.replace(" ", " ").replace("​", "")
    t = _APOS.sub("'", t)
    t = t.lower().replace("ё", "е")
    t = re.sub(r"(?<=[а-яіїєґ'])i|i(?=[а-яіїєґ])", "і", t)   # latin i typed inside Ukrainian words
    t = re.sub(r"(?<=[а-яіїєґ])c|c(?=[а-яіїєґ])", "с", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t


_ABBR_END = re.compile(r"(?:^|[\s(])(?:м|с|смт|сел|г|пгт|обл|р-н|н\.п|нп|ст|вул|ул|ім|т\.ч|напр)\.$")


def split_segments(t: str) -> list[str]:
    parts = re.split(r"\n+|;|•|▪️|▪|🔹|🔸|🔻|(?<=[!?])\s+|\s+\|\s+", t)
    out: list[str] = []
    for p in parts:
        buf = ""
        for c in re.split(r"(?<=\.)\s+", p):
            if buf and _ABBR_END.search(buf):
                buf += " " + c
            else:
                if buf:
                    out.append(buf)
                buf = c
        if buf:
            out.append(buf)
    clean = []
    for s in out:
        s = s.strip(" .,-—–:*_")
        if s:
            clean.append(s)
    return clean


def find_threats(seg: str) -> list[tuple[str, int, int]]:
    found = [(key, m.start(), m.end()) for key, rx in THREAT_PATTERNS for m in rx.finditer(seg)]
    # drop generic matches covered by a more specific one ("ударні бпла" -> shahed, not uav)
    result = [f for f in found
              if not any(o is not f and o[1] <= f[1] and f[2] <= o[2]
                         and THREATS[o[0]]["spec"] > THREATS[f[0]]["spec"] for o in found)]
    return sorted(result, key=lambda f: f[1])


def best_by_family(threats: list[str]) -> list[str]:
    best: dict[str, str] = {}
    for t in threats:
        fam = THREATS[t]["family"]
        if fam not in best or THREATS[t]["spec"] > THREATS[best[fam]]["spec"]:
            best[fam] = t
    order = {"missile": 0, "kab": 1, "drone": 2}
    return sorted(best.values(), key=lambda t: order[THREATS[t]["family"]])


def extract_count(seg: str, threat_spans: list[tuple[str, int, int]]) -> tuple[int | None, bool]:
    count = None
    for _, s, e in threat_spans:
        mb = COUNT_BEFORE.search(seg[max(0, s - 30):s])
        if mb:
            n = mb.group("n")
            count = int(n) if n.isdigit() else NUM_WORDS.get(n)
        else:
            ma = COUNT_AFTER.search(seg[s:e + 12])
            if ma:
                count = int(ma.group("a") or ma.group("b") or ma.group("c"))
        if count:
            break
    if count is None:
        m = re.search(r"(?<!\d)(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s*шт", seg)     # "(8 шт)", "8-10шт"
        if m:
            count = int(m.group(1))
    if count is not None and not (1 <= count <= 30):
        count = None                                  # larger numbers are nightly totals, not one group
    group = bool(GROUP_RE.search(seg))
    return count, group


def _offset_label(place: Place, deg: float | None) -> str:
    if deg is None:
        return place.name
    names = {0: "north", 45: "north-east", 90: "east", 135: "south-east", 180: "south",
             225: "south-west", 270: "west", 315: "north-west"}
    return f"{names[int(deg)]} of {place.name}"


BETWEEN_CUE = re.compile(r"(?<![\w'])(?:між|поміж|между)\s*$")
BETWEEN_GAP = re.compile(r"^\s*(?:та|і|й|и|and|,|/|-|–)\s*$")
SEP_GAP = re.compile(r"^\s*(?:[/,]|або|чи|та|і|й|и|или|and|or)?\s*$")
PAREN_GAP = re.compile(r"^\s*\(\s*$")
BORDER_CUE = re.compile(r"(?<![\w'])(?:вздовж|уздовж|по|на|біля)?\s*(?:меж[іеюа]\w*|кордон\w*)\s+(?:з|із|с)\s*$")
LOOKBACK_DEST = re.compile(r"(?<![\w'])(?:курс\w*|напрям\w*|направлен\w*|бік|сторону|на)(?![\w'])|→|➡")
OFFSET_ACC = re.compile(r"^на\s+(?:північ|південь|захід|схід|північний|південний|север|юг|запад|восток)")
LOCALITY_CUE = re.compile(r"(?<![\w'])(?:в\s+районі|у\s+районі|біля|поблизу|повз|над|в\s+районе|около|возле)\s+[а-яіїєґ']")
NOT_HERE_RE = re.compile(r"чист|без\s+загроз|не\s+фіксу|втрачен|не\s+спостеріга|загроз\w*\s+нема")
CLEAR_RE = re.compile(r"(?<![\w'])(?:чисто|чистота|загрозу\s+знято|загроза\s+минула)(?![\w'])")


def classify_place(seg: str, start: int, end: int, place: Place, prev_end: int | None) -> tuple[PlaceRef, bool]:
    """Return the place with its role, and whether the role came from an explicit cue word."""
    prefix = seg[max(0, start - 60):start]
    prefix = ABBREV_TAIL.sub("", prefix).rstrip()
    lat, lon, precision = place.lat, place.lon, place.precision
    label = place.name
    offset_dest = False
    dist_km = None
    km = KM_OFFSET.search(prefix)
    if km and 1 <= int(km.group("km")) <= 150:
        # "за 15 км від Кременчука", "в 10 км на південь від Полтави": a position, not an origin
        d = float(km.group("km"))
        deg = dir_to_deg(km.group("dir")) if km.group("dir") else None
        if deg is not None:
            lat, lon = destination(place.lat, place.lon, deg, d)
            label = f"{int(d)} km {_offset_label(place, deg)}"
        elif d > 8:
            dist_km = d
            label = f"{int(d)} km from {place.name}"
        return PlaceRef(place, "current", lat, lon, precision, label, start, dist_km), True
    m = OFFSET_LOC.search(prefix) or OFFSET_REL.search(prefix) or OFFSET_REL2.search(prefix)
    if m:
        deg = dir_to_deg(m.group("dir"))
        if deg is not None:
            dist = 55 if place.is_region else 15
            lat, lon = destination(place.lat, place.lon, deg, dist)
            label = _offset_label(place, deg)
        # "на північ Сумщини" (accusative) = heading there; "на півночі Сумщини" (locative) = there now
        offset_dest = bool(OFFSET_ACC.match(m.group(0))) and m.re is OFFSET_LOC
        prefix = prefix[:m.start()].rstrip()
    word = seg[start:end]
    role, explicit = "current", True
    if offset_dest or DEST_CUE.search(prefix):
        role = "dest"
    elif BORDER_CUE.search(prefix):
        role = "border"                    # "уздовж кордону з Білоруссю": near that border, not inside the country
    elif ORIGIN_CUE.search(prefix):
        role = "origin"
    elif NA_CUE.search(prefix):
        # "на Сумщині" (locative) = current position; "на Ромни"/"на Сумщину" (accusative) = destination
        role = "current" if word.endswith(("і", "ї")) or word.endswith("щине") else "dest"
    elif CURRENT_CUE.search(prefix):
        role = "current"
    elif HYPHEN_CUE.search(prefix) and prev_end is not None and start - prev_end <= 5:
        role = "dest"
    else:
        explicit = m is not None            # "на півночі Сумщини" is an explicit location
    return PlaceRef(place, role, lat, lon, precision, label, start), explicit


ROUTE_AFTER = re.compile(r"^\s*(?:→|➡️?|->|=>|—>|–>|>>|-|–|—)\s*\S")
CAPS_RE = re.compile(r"[A-ZА-ЯІЇЄҐЁ][\w'’ʼ`]*(?:-[\w'’ʼ`]+)*")


def locate(seg: str, prefer_oblasts, village_prefer=(), caps: set[str] | None = None,
           nationwide: bool = False) -> list[PlaceRef]:
    """Find places in a segment and work out what each one means (current position, destination, origin).

    Curated gazetteer places are always used; villages from the GeoNames index only when the
    context makes clear they are places (see settlements.py).
    """
    matches: list[tuple[int, int, Place, bool]] = []      # start, end, place, is_village
    for m in GAZETTEER.find(seg):
        matches.append((m.start, m.end, GAZETTEER.resolve(m, prefer_oblasts), False))
    if SETTLEMENTS.loaded and caps is not None:
        taken = [(a, b) for a, b, _, _ in matches]
        neighbors = [n for o in village_prefer for n in NEIGHBORS.get(o, []) if n not in village_prefer]
        for vm in SETTLEMENTS.find(seg, taken):
            first = re.match(r"[\w'-]+", seg[vm.start:vm.end]).group(0)
            if first not in caps:
                continue
            st = SETTLEMENTS.resolve(vm, list(village_prefer), nationwide, neighbors)
            if st is not None:
                matches.append((vm.start, vm.end, st.place(), True))
    matches.sort(key=lambda x: x[0])

    refs: list[PlaceRef] = []
    ends: list[int] = []
    for start, end, place, is_village in matches:
        prev = refs[-1] if refs else None
        prev_end = ends[-1] if ends else None
        ref, explicit = classify_place(seg, start, end, place, prev_end)
        gap = seg[prev_end:start] if prev_end is not None else seg[:start]
        if prev is not None and PAREN_GAP.match(gap):
            # "Ізюм (Харківська обл.)" / "на північ Франківщини (Бурштин)": one place, keep the precise one
            keep = ref if ref.precision == "point" and prev.precision != "point" else prev
            keep.role = prev.role
            refs[-1] = keep
            ends[-1] = end
            continue
        if (prev is not None and BETWEEN_GAP.match(gap) and prev.precision == "point" and ref.precision == "point"
                and BETWEEN_CUE.search(ABBREV_TAIL.sub("", seg[max(0, prev.start - 20):prev.start]).rstrip())
                and haversine(prev.lat, prev.lon, ref.lat, ref.lon) < 70):
            # "між Ніжином та Носівкою": one target somewhere between the two
            refs[-1] = PlaceRef(prev.place, "current", (prev.lat + ref.lat) / 2, (prev.lon + ref.lon) / 2, "point",
                                f"between {prev.place.name} and {place.name}", prev.start)
            ends[-1] = end
            continue
        sep = prev is not None and SEP_GAP.match(gap)
        if is_village and not (explicit or sep or ROUTE_AFTER.match(seg[end:end + 4])
                               or _after_threat_word(seg[:start])):
            continue                                    # a capitalised word that merely looks like a village
        if not explicit:
            if sep:
                ref.role = prev.role                        # "на Царичанку/Кобеляки", "повз Ромни, Лебедин"
            elif LOOKBACK_DEST.search(gap):
                ref.role = "dest"                           # "курсом на Коломак/Чутове" with Коломак unknown
        refs.append(ref)
        ends.append(end)
    return refs


def _after_threat_word(prefix: str) -> bool:
    """'ракета Бандурове на Бурти': a place name right after the threat word."""
    tail = prefix[-30:]
    return any(e >= len(tail) - 1 for _, _, e in find_threats(tail))


def alert_units(refs: list[PlaceRef], fallback) -> set[str]:
    """Where an alert applies: a district ("Конотопський район"), a city ("Харків"), or a whole oblast."""
    units = set()
    for r in refs:
        if r.place.kind == "A":
            units.add(r.place.key[1:])                     # district
        elif r.place.oblast in ("kyiv_city", "sevastopol"):
            units.add(r.place.oblast)                      # Kyiv / Sevastopol have their own polygon
        elif r.place.kind == "R" and _ukr(r.place.oblast):
            units.add(r.place.oblast)                      # whole oblast
        elif _ukr(r.place.oblast):
            units.add("c:" + r.place.key)                  # a city or community: just that place
    return units or set(fallback)


ALERT_HEAD = re.compile(r"^(?:🔴|🟡|🟢|відбій|червоний рівень|жовтий рівень|повітряна тривога)")


def alert_sections(norm: str) -> list[tuple[str, str]]:
    """Split an alert-feed post into (action, text) sections; action is red / yellow / off / none."""
    sections: list[list[str]] = []
    for line in norm.split("\n"):
        line = line.strip()
        if not line:
            continue
        if ALERT_HEAD.match(line) or not sections:
            sections.append([line])
        else:
            sections[-1].append(line)
    out = []
    for lines in sections:
        text = "\n".join(lines)
        head = lines[0]
        if "відбій червон" in head:
            action = "yellow"                     # red lifted, yellow level remains
        elif head.startswith("🟢") or "відбій" in head:
            action = "off"
        elif head.startswith("🟡") or "жовт" in head:
            action = "yellow"
        elif head.startswith("🔴") or ALERT_RE.search(head) or "червон" in head:
            action = "red"
        else:
            action = "none"
        out.append((action, text))
    # a single-zone post puts the place in the header and the level on the next line:
    # "🔴 Ізюмський район (Харківська обл.) / Червоний рівень тривоги. Прямуйте в укриття!"
    merged: list[tuple[str, str]] = []
    for action, text in out:
        if merged and action == merged[-1][0] and not GAZETTEER.find(text):
            continue                              # the level line repeats the header's action
        merged.append((action, text))
    return merged


def alert_level(text: str) -> str:
    """UkraineAlarmSignal: 🔴 red level (sirens) / 🟡 yellow level; "відбій червоної" drops red to yellow."""
    return "yellow" if ("жовт" in text or "відбій червон" in text or "🟡" in text) else "red"


def _ukr(oblast: str) -> bool:
    return oblast in UKRAINE_OBLASTS


# --------------------------------------------------------------------------- Russian-side sources

RU_DANGER_RE = re.compile(_W + r"(?:опасност\w*|тревог\w*|угроз\w*|атак\w*|беспилотн\w*\s+опасност\w*|налет\w*)")
RU_CLEAR_RE = re.compile(_W + r"(?:отбой|отбоя|отменен\w*|снят\w*)")
RU_MISSILE_RE = re.compile(_W + r"(?:ракетн\w*|ракет\w*)")
OFFSET_BARE = re.compile(rf"^\s*(?P<dir>{DIR_WORD})\s*$")


def parse_russia(text: str, prefer_oblasts) -> ParsedMessage:
    """Russian-side warnings ("Брянская область / Опасность по БПЛА", "Отбой опасности по БПЛА").

    They describe areas where Ukrainian drones or missiles are expected over Russia and the occupied
    territory. They become danger zones on a separate layer and never feed Ukrainian targets or alerts.
    """
    res = ParsedMessage()
    norm = normalize(text)
    if len(norm) > 300:                                # commentary / propaganda posts
        return res
    refs = []
    for seg in split_segments(norm):
        for r in locate(seg, prefer_oblasts, prefer_oblasts, {normalize(w) for w in CAPS_RE.findall(text)}):
            prefix = seg[:r.start].strip()
            m = OFFSET_BARE.match(prefix)                # "Юг Ростовской области"
            deg = dir_to_deg(m.group("dir")) if m else None
            if deg is not None and r.place.is_region:
                r.lat, r.lon = destination(r.place.lat, r.place.lon, deg, 120 if r.place.kind == "R" else 25)
                r.label = _offset_label(r.place, deg)
            refs.append(r)
    if not refs:
        return res
    res.places = list(dict.fromkeys(r.label for r in refs))
    # a region qualifier after a town or district ("Клинцы / Брянская область") only says where it is
    points = [r for r in refs if r.place.kind != "R"]
    zones = points if points else refs
    if RU_CLEAR_RE.search(norm):
        res.ru_clear = zones
        return res
    kind = "missile" if RU_MISSILE_RE.search(norm) and not find_threats(norm.replace("ракетн", "")) else "drone"
    # this channel posts bare place names while a danger is on; a danger word is not required
    res.ru_zones = [(r, kind) for r in zones]
    res.threats = ["missile" if kind == "missile" else "uav"]
    return res


LOG_LINE = re.compile(r"^\W*(\d{1,2})[:.](\d{2})(?!\d)")


def chronological(text: str) -> str:
    """Put a newest-first log ("◻️ 23:48 Транзит на Запоріжжя / ◻️ 23:44 с. Настасівка / ...") in time order,
    so the route reads from where the target was to where it went."""
    lines = text.split("\n")
    stamped = [(i, int(m.group(1)) * 60 + int(m.group(2))) for i, line in enumerate(lines)
               if (m := LOG_LINE.match(line)) and int(m.group(1)) < 24]
    if len(stamped) < 3:
        return text
    times = [t for _, t in stamped]
    newest_first = times[0] != times[-1] and all((a - b) % 1440 < 720 for a, b in zip(times, times[1:]))
    if not newest_first:
        return text
    pos = [i for i, _ in stamped]
    for i, line in zip(pos, [lines[i] for i in reversed(pos)]):
        lines[i] = line
    return "\n".join(lines)


# --------------------------------------------------------------------------- main entry

def parse_message(text: str, prefer_oblasts: list[str] | tuple = (), tier: str = "regional") -> ParsedMessage:
    res = ParsedMessage()
    if not text or not text.strip():
        return res
    prefer_oblasts = list(prefer_oblasts)
    if tier == "russia":
        return parse_russia(text, prefer_oblasts)
    text = chronological(text)
    norm = FOOTER_RE.sub("", normalize(text))      # "Підписатися на <channel> | Запоріжжя UA" is not a place
    if len(norm) > 1200 or SUMMARY_RE.search(norm):
        res.summary = True
        res.threats = best_by_family([t for t, _, _ in find_threats(norm)])
        return res

    segments = split_segments(norm)
    # regions named anywhere in the message help resolve village names ("на Харківщині ... на Савинці")
    named = [GAZETTEER.resolve(m, prefer_oblasts).oblast for seg in segments for m in GAZETTEER.find(seg)]
    village_prefer = list(dict.fromkeys(list(prefer_oblasts) + [o for o in named if not o.startswith(("ru_", "sea"))]))
    caps = {normalize(w).strip("-") for w in CAPS_RE.findall(text)}
    seg_refs = {i: locate(seg, prefer_oblasts, village_prefer, caps, nationwide=not prefer_oblasts)
                for i, seg in enumerate(segments)}
    if tier == "regional" and prefer_oblasts:
        # A regional observer reports what is over its own area. A town far from it ("Затока" in a
        # Dnipro channel, which means a local spot, not the resort near Odesa) is not a position,
        # unless it is a major city or the post names that region.
        near = set(prefer_oblasts) | {n for o in prefer_oblasts for n in NEIGHBORS.get(o, [])}
        near |= {r.place.oblast for refs in seg_refs.values() for r in refs if r.place.kind == "R"}
        if "kyiv" in near or "kyiv_city" in near:
            near |= {"kyiv", "kyiv_city"}
        for i, refs in seg_refs.items():
            seg_refs[i] = [r for r in refs if not (r.role in ("current", "border") and _ukr(r.place.oblast)
                                                   and r.place.kind not in ("C", "R") and r.place.oblast not in near)]
    msg_threat_list: list[str] = []
    for seg in segments:
        msg_threat_list += [t for t, _, _ in find_threats(seg)]
    msg_threats = best_by_family(msg_threat_list)
    res.threats = msg_threats
    all_refs = [r for i in range(len(segments)) for r in seg_refs[i]]
    res.places = list(dict.fromkeys(r.label for r in all_refs))
    single_region = prefer_oblasts if tier == "regional" and len(prefer_oblasts) <= 2 else []

    # ---- alert-system style posts: one or more sections, each a header and a list of districts
    #      ("🟡 Відбій червоної тривоги / • A / 🟢 Відбій тривоги / • B / • C" = A stays yellow, B and C clear)
    if not msg_threats or (ALERT_RE.search(norm) and not MOVE_CUE_RE.search(norm)
                           and not any(r.role == "dest" for r in all_refs)):
        if ALLCLEAR_RE.search(norm) or "відбій" in norm or ALERT_RE.search(norm):
            sections = alert_sections(norm)
            for i, (action, sec_text) in enumerate(sections):
                refs_here = [r for seg in split_segments(sec_text) for r in locate(seg, prefer_oblasts, village_prefer, caps)
                             if _ukr(r.place.oblast)]
                fallback = single_region if len(sections) == 1 else []
                units = alert_units(refs_here, fallback)
                if action == "off":
                    res.alerts_off.update(units)
                elif action in ("red", "yellow"):
                    res.alerts_on.update(units)
                    for u in units:
                        res.alert_levels[u] = action
                    res.alert_level = action
            return res

    # ---- "в області чисто", "Кременчук поки чисто"
    if CLEAR_RE.search(norm) and not msg_threats and tier != "aggregator":
        res.clear_places = [r for r in all_refs if _ukr(r.place.oblast)]
        if not res.clear_places:
            res.clear_oblasts = set(single_region)
        return res

    # ---- "Відбій загрози балістики": the threat is over, clear its warnings
    if msg_threats and THREAT_AREA_RE.search(norm) and (ALLCLEAR_RE.search(norm) or "відбій" in norm or "знято" in norm):
        res.threats_cleared = msg_threats
        return res

    # ---- threat notices without any movement ("Загроза застосування БПЛА. Перейдіть в укриття!")
    if msg_threats and THREAT_AREA_RE.search(norm) and not MOVE_CUE_RE.search(norm) and not KILL_RE.search(norm):
        if AVIATION_RE.search(norm) and TAKEOFF_RE.search(norm):
            res.banners.append(("aviation", norm))
        ukr = [r for r in all_refs if _ukr(r.place.oblast)]
        # a district qualifier in parentheses is already merged into the town by locate()
        for r in ukr:
            res.events.append(AreaEvent("threat", msg_threats[0], r, None, norm[:200]))
        if not ukr:
            res.banners.append(("threat:" + msg_threats[0], norm))
        return res

    distinct = {t for t in msg_threat_list}
    inherited: list[str] = msg_threats[:1] if len(distinct) == 1 else []
    pending_banners: list[tuple[str, str]] = []
    is_news = bool(NEWS_RE.search(norm))            # aftermath / news report: feed only, nothing live to plot
    header: PlaceRef | None = None                  # "Сумщина:" line heading a list of reports

    for i, seg in enumerate(segments):
        if SPAM_RE.search(seg) and not find_threats(seg):
            continue
        if len(seg) > 220:
            continue                                  # prose / commentary, not a live report line
        tspans = find_threats(seg)
        seg_threats = best_by_family([t for t, _, _ in tspans])
        refs = seg_refs[i]
        if (not seg_threats and refs and i + 1 < len(segments) and all(r.precision == "region" for r in refs)
                and (seg.rstrip().endswith(":") or len(seg) <= 24) and not ALLCLEAR_RE.search(seg)
                and not CLEAR_RE.search(seg)):
            header = refs[-1]                         # the lines below are in this region
            header.role = "current"
            continue
        if seg_threats:
            inherited = seg_threats
        threats_here = seg_threats or inherited

        heading = None
        for rx in HEADING_RES:
            hm = rx.search(seg)
            if hm:
                heading = dir_to_deg(hm.group("dir"))
                if heading is not None:
                    break
        if heading is None:
            fm = FROM_DIR_RE.search(seg)
            if fm:
                d = dir_to_deg(fm.group("dir"))
                heading = (d + 180) % 360 if d is not None else None

        has_move_cue = bool(MOVE_CUE_RE.search(seg)) or any(r.role in ("dest", "origin") for r in refs)
        is_allclear = bool(ALLCLEAR_RE.search(seg))
        is_alert = bool(ALERT_RE.search(seg)) and not is_allclear
        is_possible = bool(POSSIBLE_RE.search(seg))
        is_threat_area = bool(THREAT_AREA_RE.search(seg)) or (is_possible and not has_move_cue)
        is_kill = bool(KILL_RE.search(seg))
        is_expl = bool(EXPL_RE.search(seg)) and not is_possible and not is_kill

        # ---- air-raid alert state (region level)
        if is_allclear:
            if "червон" not in seg:
                res.alerts_off.update(alert_units(refs, single_region))
            if not threats_here or not has_move_cue:
                continue
        if is_alert:
            res.alerts_on.update(alert_units(refs, single_region))
            res.alert_level = alert_level(seg)

        # ---- aviation notices
        if AVIATION_RE.search(seg) and (TAKEOFF_RE.search(seg) or is_threat_area):
            res.banners.append(("aviation", seg))
            if not refs:
                continue

        current = [r for r in refs if r.role == "current"]
        if not current:
            current = [r for r in refs if r.role == "border" and _ukr(r.place.oblast)]
        dests = [r for r in refs if r.role == "dest"]
        origins = [r for r in refs if r.role == "origin"]
        if header is not None and not current and (dests or origins):
            current = [header]                        # "Сумщина: / БпЛА курсом на Шалигине"

        if is_news and not is_expl:
            continue
        # ---- shot down / explosions
        if is_kill:
            count, _ = extract_count(seg, tspans)
            kill_places = current or refs or ([header] if header is not None else [])
            for r in kill_places[-1:]:
                res.events.append(AreaEvent("kill", threats_here[0] if threats_here else None, r, count, seg))
            if not kill_places and threats_here:
                res.events.append(AreaEvent("kill", threats_here[0], None, count, seg))
            continue
        if is_expl:
            for r in (current or refs):
                if _ukr(r.place.oblast):
                    res.events.append(AreaEvent("explosion", threats_here[0] if threats_here else None, r, None, seg))
            if not dests or is_news:
                continue

        if is_threat_area and not (current and has_move_cue and not is_possible) and not dests:
            if threats_here:
                ukr = [r for r in refs if _ukr(r.place.oblast)]
                for r in ukr:
                    res.events.append(AreaEvent("threat", threats_here[0], r, None, seg))
                if not ukr:
                    res.banners.append(("threat:" + threats_here[0], seg))
            continue
        if is_alert and not has_move_cue:
            continue

        if not threats_here:
            continue
        if not (current or dests or origins):
            if heading is not None and res.sightings and res.sightings[-1].heading is None:
                res.sightings[-1].heading = heading       # "курс північно-західний" on its own line
            elif not refs and seg_threats and single_region and len(single_region) == 1 \
                    and LOCALITY_CUE.search(seg) and "україн" not in seg:
                # local channel, local place we do not know: place it in the channel's region
                c = GAZETTEER.oblast_center.get(single_region[0])
                if c is not None:
                    pos = PlaceRef(c, "current", c.lat, c.lon, "region", f"{c.name} (place not on map)")
                    count, group = extract_count(seg, tspans)
                    for th in threats_here:
                        res.sightings.append(Sighting(th, count, group, pos, [], None, None, heading, seg, True))
            elif not refs and seg_threats:
                pending_banners.append(("threat:" + seg_threats[0], seg))
            continue

        count, group = extract_count(seg, tspans)
        is_new = bool(NEW_START.search(seg)) or any(NEW_BEFORE.search(seg[max(0, s - 25):s]) for _, s, _ in tspans)
        point_current = [r for r in current if r.precision == "point"]
        dest = dests[0] if dests else None
        origin = origins[0] if origins else None
        if not dest and (origin is not None or current) and all(
                r.place.kind == "F" or not _ukr(r.place.oblast) for r in (current or [origin])):
            pending_banners.append(("threat:" + threats_here[0], seg))     # launch site, no target yet
            continue

        # several regions in one line ("ракети на Сумщині та Харківщині") are separate groups
        if not point_current and len(current) > 1:
            for r in current:
                for th in threats_here:
                    res.sightings.append(Sighting(th, count, group, r, [], dest, origin, heading, seg, bool(seg_threats),
                                                  is_new))
            continue

        # a bare list of towns is several targets; "повз A, B" is one target's path
        if len(point_current) > 1 and not PATH_CUE.search(seg):
            for r in point_current:
                for th in threats_here:
                    res.sightings.append(Sighting(th, count, group, r, [], dest, origin, heading, seg, bool(seg_threats),
                                                  is_new))
            continue

        if point_current:
            pos, via = point_current[-1], point_current[:-1]
        elif current:
            pos, via = current[-1], []
        else:
            pos, via = None, []

        # continuation line: no own threat word, fills an empty slot of the previous sighting
        prev = res.sightings[-1] if res.sightings else None
        if prev is not None and not seg_threats and count is None and not is_new:
            filled = False
            if dest and prev.dest is None and pos is None:
                prev.dest = dest
                filled = True
            if pos and prev.pos is None:
                prev.pos = pos
                prev.via += via
                if dest and prev.dest is None:
                    prev.dest = dest
                filled = True
            elif pos and prev.pos is not None and prev.dest is None and dest is None and pos.precision == "point":
                prev.via.append(prev.pos)                   # "повз Ворожбу" on the next line: it moved on
                prev.pos = pos
                filled = True
            if heading is not None and prev.heading is None:
                prev.heading = heading
            if filled:
                continue

        for th in threats_here:
            res.sightings.append(Sighting(
                threat=th, count=count, group=group, pos=pos, via=list(via), dest=dest, origin=origin,
                heading=heading, text=seg, own_threat=bool(seg_threats), new=is_new))

    if pending_banners and not res.sightings and not res.events:
        res.banners += pending_banners[:1]
    # a short follow-up that only names places ("Гостомель"): the fusion step links it to the
    # channel's previous report
    if not msg_threats and not res.relevant and all_refs and len(norm) <= 80 and not NOT_HERE_RE.search(norm):
        res.bare_places = all_refs
        res.bare_new = any(NEW_START.search(seg) for seg in segments)
    return res
