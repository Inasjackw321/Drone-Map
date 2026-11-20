"""Turn a Ukrainian / Russian air-raid monitoring message into structured observations.

The parser is deliberately rule-based: every decision can be traced back to a regex,
and the rules are covered by tests (tests/test_parser.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .gazetteer import GAZETTEER, NEIGHBORS, Place, destination
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
                  r"швидкісн\w*\s+ціл\w*|скоростн\w*\s+цел\w*|ballistic\w*|iskander)"),
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
    ("shahed", _W + r"(?:шахед\w*|шахід\w*|шаhед\w*|герань\w*|герані\w*|мопед\w*|shahed\w*|geran\w*|"
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
    r"полетів|полетіли|полетел\w*)\s+(?:на|до|в|у|к)|до|к|→|➡️?|⏩|->|=>|—>|–>|>>)\s*$")
ORIGIN_CUE = re.compile(
    r"(?<![\w'])(?:з|із|зі|від|з\s+боку|з\s+напрямку|з\s+акваторії|з\s+території|з\s+району|с\s+направления|"
    r"со\s+стороны|с|из|из\s+района|вилет\w*\s+(?:з|із)|пуск\w*\s+(?:з|із|с)|запуск\w*\s+(?:з|із|с))\s*$")
CURRENT_CUE = re.compile(
    r"(?<![\w'])(?:над|в\s+районі|у\s+районі|районі|в\s+р-ні|у\s+р-ні|р-н|р-ні|біля|поблизу|неподалік|повз|через|в|у|"
    r"в\s+районе|районе|около|возле|рядом\s+с|вблизи|по|околиц\w*|на\s+околиц\w*|на\s+межі\s+з?)\s*$")
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

HEADING_RES = [
    re.compile(rf"курс\w*\s+(?:на\s+)?(?P<dir>{DIR_WORD})(?!\s+(?:від|от)(?![\w]))"),
    re.compile(rf"(?P<dir>{DIR_WORD})\s+курс\w*"),
    re.compile(rf"(?:рухає\w*|летить|летять|летит|летят|движ\w*|повертає|повернув\w*|напрям\w*|направлени\w*)\s+"
               rf"(?:на\s+)?(?P<dir>{DIR_WORD})(?!\s+(?:від|от)(?![\w]))"),
    re.compile(rf"(?:у|в)\s+(?P<dir>{DIR_WORD})\s+напрям\w*"),
]
FROM_DIR_RE = re.compile(r"(?:з|із|с|со)\s+(?P<dir>півночі|півдня|сходу|заходу|північного\s+сходу|північного\s+заходу|"
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
    alerts_on: set[str] = field(default_factory=set)
    alerts_off: set[str] = field(default_factory=set)
    banners: list[tuple[str, str]] = field(default_factory=list)   # (kind, text)
    threats: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    summary: bool = False
    clear_places: list[PlaceRef] = field(default_factory=list)
    clear_oblasts: set[str] = field(default_factory=set)
    bare_places: list[PlaceRef] = field(default_factory=list)

    @property
    def relevant(self) -> bool:
        return bool(self.sightings or self.events or self.alerts_on or self.alerts_off or self.banners
                    or self.clear_places or self.clear_oblasts)


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


SEP_GAP = re.compile(r"^\s*(?:[/,]|або|чи|та|і|й|и|или|and|or)?\s*$")
PAREN_GAP = re.compile(r"^\s*\(\s*$")
BORDER_CUE = re.compile(r"(?<![\w'])(?:вздовж|уздовж|по|на|біля)?\s*(?:меж[іеюа]\w*|кордон\w*)\s+(?:з|із|с)\s*$")
LOOKBACK_DEST = re.compile(r"(?<![\w'])(?:курс\w*|напрям\w*|направлен\w*|бік|сторону|на)(?![\w'])|→|➡")
OFFSET_ACC = re.compile(r"^на\s+(?:північ|південь|захід|схід|північний|південний|север|юг|запад|восток)")
LOCALITY_CUE = re.compile(r"(?<![\w'])(?:в\s+районі|у\s+районі|біля|поблизу|повз|над|в\s+районе|около|возле)\s+[а-яіїєґ']")
CLEAR_RE = re.compile(r"(?<![\w'])(?:чисто|чистота|загрозу\s+знято|загроза\s+минула)(?![\w'])")


def classify_place(seg: str, start: int, end: int, place: Place, prev_end: int | None) -> tuple[PlaceRef, bool]:
    """Return the place with its role, and whether the role came from an explicit cue word."""
    prefix = seg[max(0, start - 60):start]
    prefix = ABBREV_TAIL.sub("", prefix).rstrip()
    lat, lon, precision = place.lat, place.lon, place.precision
    label = place.name
    offset_dest = False
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
        role = "current"
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


def _ukr(oblast: str) -> bool:
    return not oblast.startswith(("ru_", "sea"))


# --------------------------------------------------------------------------- main entry

def parse_message(text: str, prefer_oblasts: list[str] | tuple = (), tier: str = "regional") -> ParsedMessage:
    res = ParsedMessage()
    if not text or not text.strip():
        return res
    prefer_oblasts = list(prefer_oblasts)
    norm = normalize(text)
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
    msg_threat_list: list[str] = []
    for seg in segments:
        msg_threat_list += [t for t, _, _ in find_threats(seg)]
    msg_threats = best_by_family(msg_threat_list)
    res.threats = msg_threats
    all_refs = [r for i in range(len(segments)) for r in seg_refs[i]]
    res.places = list(dict.fromkeys(r.label for r in all_refs))
    msg_oblasts = list(dict.fromkeys(r.place.oblast for r in all_refs if _ukr(r.place.oblast)))
    single_region = prefer_oblasts if tier == "regional" and len(prefer_oblasts) <= 2 else []

    # ---- alert-system style posts: a header line and a list of districts
    if not msg_threats or (ALERT_RE.search(norm) and not MOVE_CUE_RE.search(norm)):
        if ALLCLEAR_RE.search(norm):
            if "червон" not in norm:                       # "відбій червоної тривоги" = yellow level remains
                res.alerts_off.update(msg_oblasts or single_region)
            return res
        if ALERT_RE.search(norm):
            res.alerts_on.update(msg_oblasts or single_region)
            return res

    # ---- "в області чисто", "Кременчук поки чисто"
    if CLEAR_RE.search(norm) and not msg_threats and tier != "aggregator":
        res.clear_places = [r for r in all_refs if _ukr(r.place.oblast)]
        if not res.clear_places:
            res.clear_oblasts = set(single_region)
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

    inherited: list[str] = msg_threats[:1] if len(msg_threats) == 1 else []
    pending_banners: list[tuple[str, str]] = []
    is_news = bool(NEWS_RE.search(norm))            # aftermath / news report: feed only, nothing live to plot

    for i, seg in enumerate(segments):
        if SPAM_RE.search(seg) and not find_threats(seg):
            continue
        if len(seg) > 220:
            continue                                  # prose / commentary, not a live report line
        tspans = find_threats(seg)
        seg_threats = best_by_family([t for t, _, _ in tspans])
        if seg_threats:
            inherited = seg_threats
        threats_here = seg_threats or inherited
        refs = seg_refs[i]

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

        oblasts = list(dict.fromkeys(r.place.oblast for r in refs if _ukr(r.place.oblast)))
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
                res.alerts_off.update(oblasts or single_region)
            if not threats_here or not has_move_cue:
                continue
        if is_alert:
            res.alerts_on.update(oblasts or single_region)

        # ---- aviation notices
        if AVIATION_RE.search(seg) and (TAKEOFF_RE.search(seg) or is_threat_area):
            res.banners.append(("aviation", seg))
            if not refs:
                continue

        current = [r for r in refs if r.role == "current"]
        dests = [r for r in refs if r.role == "dest"]
        origins = [r for r in refs if r.role == "origin"]

        if is_news and not is_expl:
            continue
        # ---- shot down / explosions
        if is_kill:
            count, _ = extract_count(seg, tspans)
            kill_places = current or refs
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
        point_current = [r for r in current if r.precision == "point"]
        dest = dests[0] if dests else None
        origin = origins[0] if origins else None
        if not current and not dest and origin is not None and not _ukr(origin.place.oblast):
            pending_banners.append(("threat:" + threats_here[0], seg))     # launch notice, no target yet
            continue

        # several regions in one line ("ракети на Сумщині та Харківщині") are separate groups
        if not point_current and len(current) > 1:
            for r in current:
                for th in threats_here:
                    res.sightings.append(Sighting(th, count, group, r, [], dest, origin, heading, seg, bool(seg_threats)))
            continue

        # a bare list of towns is several targets; "повз A, B" is one target's path
        if len(point_current) > 1 and not PATH_CUE.search(seg):
            for r in point_current:
                for th in threats_here:
                    res.sightings.append(Sighting(th, count, group, r, [], dest, origin, heading, seg, bool(seg_threats)))
            continue

        if point_current:
            pos, via = point_current[-1], point_current[:-1]
        elif current:
            pos, via = current[-1], []
        else:
            pos, via = None, []

        # continuation line: no own threat word, fills an empty slot of the previous sighting
        prev = res.sightings[-1] if res.sightings else None
        if prev is not None and not seg_threats and count is None:
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
                heading=heading, text=seg, own_threat=bool(seg_threats)))

    if pending_banners and not res.sightings and not res.events:
        res.banners += pending_banners[:1]
    # a short follow-up that only names places ("Гостомель"): the fusion step links it to the
    # channel's previous report
    if not msg_threats and not res.relevant and all_refs and len(norm) <= 80:
        res.bare_places = all_refs
    return res
