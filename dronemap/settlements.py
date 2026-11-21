"""Village / small-town lookup built from GeoNames (32k populated places of Ukraine).

Regional observers name small villages ("курсом на Савинці", "повз Мажарку"). The curated
gazetteer cannot list them all, so this index matches any settlement by its stem, which covers
Ukrainian and Russian case endings without storing every word form.

To keep false positives away, a village only counts when (enforced by the parser):
  * it is capitalised in the original post,
  * it is introduced by a location word (на, над, повз, курсом на, →, ...) or follows another place,
  * it lies in the channel's region or in a region named in the same message
    (nationwide channels: only unique, larger settlements).
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

from .gazetteer import Place

DATA = Path(__file__).parent / "data" / "settlements.tsv.gz"

# case endings, longest first (Ukrainian + Russian)
ENDINGS = sorted({
    "ами", "ями", "ого", "ому", "ими", "ою", "ею", "єю", "ів", "їв", "ях", "ах", "ям", "ам", "им", "ім", "их",
    "ій", "ої", "ой", "ом", "ем", "ов", "ей", "ую", "юю", "ая", "ое", "ые", "ый", "ий",
    "а", "я", "у", "ю", "і", "ї", "и", "е", "є", "о", "ь", "й", "ы",
}, key=len, reverse=True)
NOM_STRIP = ("ий", "ій", "ая", "ое", "ый", "ые", "ія")   # two-letter nominative endings
NOM_STRIP1 = tuple("аяеєоиіїьйы")

# words that are also village names but appear in alerts as ordinary words
STOP = {
    "мирне", "нове", "поле", "гай", "лука", "кут", "зоря", "перемога", "ставки", "степове", "широке", "високе",
    "зелене", "красне", "сонячне", "вишневе", "садове", "лісове", "польове", "озерне", "дачне", "світле", "чисте",
    "веселе", "привільне", "дружба", "надія", "воля", "поляна", "діброва", "хутір", "слобода", "ліски", "балка",
    "заря", "победа", "мир", "весна", "жовтневе", "червоне", "першотравневе", "ракета", "курс", "радар", "небо",
    "тиша", "спокій", "загроза", "тривога", "відбій", "увага", "україна", "росія", "шахед", "дрон", "мопед",
    "орлан", "ланцет", "гербера", "калібр", "кинджал", "циркон", "оникс", "онікс", "іскандер", "граніт",
    "новий", "нова", "новое", "старе", "степ", "дорога", "вокзал", "центр", "північне", "південне", "західне",
    "східне", "заводське", "робоче", "шкільне", "лиман", "затока", "острів", "гора", "долина", "річка",
    "промінь", "маяк", "сокіл", "орел", "лебедине", "калинове", "виноградне", "кринички", "колос", "ясне",
}


def _stem_name(word: str) -> str:
    for e in NOM_STRIP:
        if word.endswith(e) and len(word) - len(e) >= 3:
            return word[:-len(e)]
    if word.endswith(NOM_STRIP1) and len(word) > 4:
        return word[:-1]
    return word


def _alternations(stem: str) -> set[str]:
    """Undo common stem alternations: Мажарц(і)->Мажарк(а), Харков(а)->Харків, Кременц(я)->Кременец(ь)."""
    out = {stem}
    if stem.endswith("ц"):
        out.add(stem[:-1] + "к")
        out.add(stem[:-1] + "ец")
    if stem.endswith("ов"):
        out.add(stem[:-2] + "ів")
    if stem.endswith("ол"):
        out.add(stem[:-2] + "іл")
    if stem.endswith("ев"):
        out.add(stem[:-2] + "ів")
    if len(stem) > 3 and stem[-1] == "к" and stem[-2] not in "аеєиіїоуюя":
        out.add(stem[:-1] + "ок")
    if stem.endswith("з"):
        out.add(stem[:-1] + "г")             # Ріг -> Розі
    return out


def word_stems(word: str) -> set[str]:
    stems = set()
    for e in ENDINGS + [""]:
        if word.endswith(e) and len(word) - len(e) >= 3:
            stems |= _alternations(word[:len(word) - len(e)] if e else word)
    return stems


@dataclass(frozen=True)
class Settlement:
    gid: str
    oblast: str
    lat: float
    lon: float
    population: int
    fcode: str
    name: str

    def place(self) -> Place:
        return Place("s" + self.gid, self.name, self.lat, self.lon, self.oblast, "V")


@dataclass
class VillageMatch:
    start: int
    end: int
    candidates: list[Settlement]


WORD_RE = re.compile(r"[а-яіїєґё']+(?:-[а-яіїєґё']+)*")


class Settlements:
    def __init__(self, path: Path = DATA):
        self.items: list[Settlement] = []
        self.single: dict[str, list[int]] = {}             # stem -> settlements (one-word names)
        self.multi: dict[tuple[str, ...], list[int]] = {}  # stems of each word -> settlements
        self.loaded = False
        if path.exists():
            self._load(path)

    @staticmethod
    def _adjective_stems() -> tuple[str, ...]:
        """Stems of curated city/region names: villages named "Харківське", "Сумське" are mostly the
        ordinary adjective ("харківський напрямок"), so they are not matched."""
        from .gazetteer import DATA as GDATA
        stems = set()
        for line in GDATA.splitlines():
            parts = [p.strip() for p in line.split(";")]
            if len(parts) != 7 or parts[5] not in ("C", "R"):
                continue
            for tok in parts[6].split(","):
                tok = tok.strip()
                if tok and not tok.startswith("/"):
                    base = re.split(r"[~* ]", tok)[0].replace("'", "")
                    if len(base) >= 3:
                        stems.add(base)
        return tuple(sorted(stems))

    def _load(self, path: Path) -> None:
        adj = self._adjective_stems()
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                gid, oblast, lat, lon, pop, fcode, name, names = line.rstrip("\n").split("\t")
                idx = len(self.items)
                self.items.append(Settlement(gid, oblast, float(lat), float(lon), int(pop or 0), fcode, name))
                for n in names.split("|"):
                    parts = [p for p in re.split(r"\s+", n) if p]
                    if not parts or n in STOP:
                        continue
                    if len(parts) == 1:
                        st = _stem_name(parts[0])
                        if st.endswith(("ськ", "зьк", "цьк", "ск")) and st.replace("'", "").startswith(adj):
                            continue
                        if len(st) >= 4:
                            self.single.setdefault(st, []).append(idx)
                    elif len(parts) <= 3:
                        key = tuple(_stem_name(p) for p in parts)
                        self.multi.setdefault(key, []).append(idx)
        self.loaded = True

    def find(self, text: str, taken: list[tuple[int, int]]) -> list[VillageMatch]:
        words = [(m.start(), m.end(), m.group(0)) for m in WORD_RE.finditer(text)]
        out: list[VillageMatch] = []
        i = 0
        while i < len(words):
            matched = False
            for n in (3, 2):
                if i + n > len(words):
                    continue
                span = (words[i][0], words[i + n - 1][1])
                if any(span[0] < te and span[1] > ts for ts, te in taken):
                    continue
                stems = [word_stems(w[2]) for w in words[i:i + n]]
                cands: list[int] = []
                for key, idxs in self._multi_candidates(stems):
                    cands += idxs
                if cands:
                    out.append(VillageMatch(span[0], span[1], [self.items[c] for c in dict.fromkeys(cands)]))
                    i += n
                    matched = True
                    break
            if matched:
                continue
            s, e, w = words[i]
            if len(w) >= 4 and w not in STOP and not any(s < te and e > ts for ts, te in taken):
                cands = []
                for st in word_stems(w):
                    cands += self.single.get(st, [])
                if cands:
                    out.append(VillageMatch(s, e, [self.items[c] for c in dict.fromkeys(cands)]))
            i += 1
        return out

    def _multi_candidates(self, stems: list[set[str]]):
        if len(stems) == 2:
            for a in stems[0]:
                for b in stems[1]:
                    if (a, b) in self.multi:
                        yield (a, b), self.multi[(a, b)]
        elif len(stems) == 3:
            for a in stems[0]:
                for b in stems[1]:
                    for c in stems[2]:
                        if (a, b, c) in self.multi:
                            yield (a, b, c), self.multi[(a, b, c)]

    @staticmethod
    def resolve(m: VillageMatch, prefer: list[str], nationwide_ok: bool, neighbors: list[str] = ()) -> Settlement | None:
        local = [c for c in m.candidates if c.oblast in prefer]
        if local:
            best = max(local, key=lambda c: (c.fcode.startswith("PPLA"), c.population))
            if nationwide_ok and best.population < 1000 and not best.fcode.startswith("PPLA"):
                # a nationwide post naming a region: "на Дніпропетровщині від Близнюків" means the town
                # just across the border, not a hamlet of the same name deep inside the region
                big = [c for c in m.candidates if c.oblast in neighbors
                       and (c.population >= 3000 or c.fcode.startswith("PPLA"))]
                if len(big) == 1:
                    return big[0]
            return best
        near = [c for c in m.candidates if c.oblast in neighbors]
        if 0 < len(near) <= 2:                  # just across a region border, and not a common name
            return max(near, key=lambda c: c.population)
        if nationwide_ok:
            big = [c for c in m.candidates if c.population >= 1000 or c.fcode.startswith("PPLA")]
            if len(big) == 1 and len(m.candidates) <= 3:
                return big[0]
        return None


SETTLEMENTS = Settlements()
