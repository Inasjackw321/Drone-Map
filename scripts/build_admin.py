#!/usr/bin/env python3
"""Build web/data/admin.json: Ukrainian raions and oblasts, western Russian regions, neighbours.

Sources (download first, see README "Map data"):
  * Ukrainian raions: OCHA COD-AB (valid 2023-02-01), one file per oblast: <ocha_dir>/UAxx.geojson
  * Russian regions:  geoBoundaries gbOpen RUS ADM1 (OpenStreetMap, ODbL)
  * Belarus/Moldova:  geoBoundaries gbOpen ADM0

    python scripts/build_admin.py <ocha_dir> RUS1.geojson BLR0.geojson MDA0.geojson
"""
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import polylabel, unary_union

OBLAST_BY_PCODE = {
    "UA01": "crimea", "UA05": "vinnytsia", "UA07": "volyn", "UA12": "dnipro", "UA14": "donetsk",
    "UA18": "zhytomyr", "UA21": "zakarpattia", "UA23": "zaporizhzhia", "UA26": "ivano_frankivsk",
    "UA32": "kyiv", "UA35": "kirovohrad", "UA44": "luhansk", "UA46": "lviv", "UA48": "mykolaiv",
    "UA51": "odesa", "UA53": "poltava", "UA56": "rivne", "UA59": "sumy", "UA61": "ternopil",
    "UA63": "kharkiv", "UA65": "kherson", "UA68": "khmelnytskyi", "UA71": "cherkasy",
    "UA73": "chernivtsi", "UA74": "chernihiv", "UA80": "kyiv_city", "UA85": "sevastopol",
}

# western Russia: ISO code -> (key, Russian name)
RUSSIA = {
    "RU-BEL": ("ru_bel", "Белгородская обл."), "RU-KRS": ("ru_krs", "Курская обл."), "RU-BRY": ("ru_bry", "Брянская обл."),
    "RU-VOR": ("ru_vor", "Воронежская обл."), "RU-ROS": ("ru_ros", "Ростовская обл."), "RU-KDA": ("ru_kda", "Краснодарский край"),
    "RU-ORL": ("ru_orl", "Орловская обл."), "RU-KLU": ("ru_klu", "Калужская обл."), "RU-TUL": ("ru_tul", "Тульская обл."),
    "RU-MOS": ("ru_mos", "Московская обл."), "RU-MOW": ("ru_mow", "Москва"), "RU-LIP": ("ru_lip", "Липецкая обл."),
    "RU-TAM": ("ru_tam", "Тамбовская обл."), "RU-SMO": ("ru_smo", "Смоленская обл."), "RU-RYA": ("ru_rya", "Рязанская обл."),
    "RU-STA": ("ru_sta", "Ставропольский край"), "RU-VGG": ("ru_vgg", "Волгоградская обл."), "RU-SAR": ("ru_sar", "Саратовская обл."),
    "RU-PNZ": ("ru_pnz", "Пензенская обл."), "RU-VLG": ("ru_vlg", "Вологодская обл."), "RU-LEN": ("ru_len", "Ленинградская обл."),
    "RU-SPE": ("ru_spe", "Санкт-Петербург"), "RU-TVE": ("ru_tve", "Тверская обл."), "RU-YAR": ("ru_yar", "Ярославская обл."),
    "RU-NIZ": ("ru_niz", "Нижегородская обл."), "RU-TA": ("ru_ta", "Татарстан"), "RU-BA": ("ru_ba", "Башкортостан"),
    "RU-AST": ("ru_ast", "Астраханская обл."), "RU-KL": ("ru_kl", "Калмыкия"), "RU-SAM": ("ru_sam", "Самарская обл."),
    "RU-ULY": ("ru_uly", "Ульяновская обл."), "RU-MO": ("ru_mo", "Мордовия"), "RU-CU": ("ru_cu", "Чувашия"),
    "RU-IVA": ("ru_iva", "Ивановская обл."), "RU-VLA": ("ru_vla", "Владимирская обл."), "RU-KOS": ("ru_kos", "Костромская обл."),
    "RU-NGR": ("ru_ngr", "Новгородская обл."), "RU-PSK": ("ru_psk", "Псковская обл."), "RU-AD": ("ru_ad", "Адыгея"),
    "RU-KC": ("ru_kc", "Карачаево-Черкесия"), "RU-KB": ("ru_kb", "Кабардино-Балкария"), "RU-SE": ("ru_se", "Северная Осетия"),
    "RU-CE": ("ru_ce", "Чечня"), "RU-DA": ("ru_da", "Дагестан"), "RU-IN": ("ru_in", "Ингушетия"), "RU-ORE": ("ru_ore", "Оренбургская обл."),
    "RU-PER": ("ru_per", "Пермский край"), "RU-UD": ("ru_ud", "Удмуртия"), "RU-KIR": ("ru_kir", "Кировская обл."),
    "RU-ME": ("ru_me", "Марий Эл"), "RU-KR": ("ru_kr", "Карелия"), "RU-MUR": ("ru_mur", "Мурманская обл."),
    "RU-ARK": ("ru_ark", "Архангельская обл."), "RU-KO": ("ru_ko", "Коми"), "RU-KGD": ("ru_kgd", "Калининградская обл."),
    "RU-SVE": ("ru_sve", "Свердловская обл."), "RU-CHE": ("ru_che", "Челябинская обл."),
}


def rnd(geom, nd):
    """Round coordinates to keep the file small (3 decimals = ~100 m)."""
    def r(c):
        if isinstance(c[0], (list, tuple)):
            return [r(x) for x in c]
        return [round(c[0], nd), round(c[1], nd)]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def label_point(geom):
    poly = max(geom.geoms, key=lambda p: p.area) if geom.geom_type == "MultiPolygon" else geom
    p = polylabel(poly, tolerance=0.01)
    return [round(p.x, 3), round(p.y, 3)]


def feat(geom, props, tol, nd=3):
    g = geom.simplify(tol, preserve_topology=True)
    return {"type": "Feature", "properties": {**props, "label": label_point(geom)}, "geometry": rnd(g, nd)}


def main(ocha_dir, rus, blr, mda, out="web/data/admin.json"):
    raions, by_oblast, ob_names = [], {}, {}
    for p in sorted(Path(ocha_dir).glob("UA*.geojson")):
        for f in json.load(open(p, encoding="utf-8"))["features"]:
            pr = f["properties"]
            geom = shape(f["geometry"]).buffer(0)
            ob = OBLAST_BY_PCODE[pr["ADM1_PCODE"]]
            by_oblast.setdefault(pr["ADM1_PCODE"], []).append(geom)
            ob_names[pr["ADM1_PCODE"]] = pr["ADM1_UA"]
            name = pr["ADM2_UA"].replace("’", "'")
            raions.append(feat(geom, {"id": pr["ADM2_PCODE"], "name": name, "name_en": pr["ADM2_EN"], "oblast": ob}, 0.003))
    oblasts = []
    for code, geoms in by_oblast.items():
        geom = unary_union(geoms).buffer(0.0005).buffer(-0.0005)
        oblasts.append(feat(geom, {"id": code, "key": OBLAST_BY_PCODE[code], "name": ob_names[code]}, 0.004))
    russia = []
    for f in json.load(open(rus, encoding="utf-8"))["features"]:
        iso = f["properties"]["shapeISO"]
        if iso not in RUSSIA:
            continue
        key, name = RUSSIA[iso]
        geom = shape(f["geometry"]).buffer(0)
        russia.append(feat(geom, {"id": iso, "key": key, "name": name, "name_en": f["properties"]["shapeName"]}, 0.02))
    neighbors = []
    for path, name in ((blr, "Беларусь"), (mda, "Молдова")):
        for f in json.load(open(path, encoding="utf-8"))["features"]:
            neighbors.append(feat(shape(f["geometry"]).buffer(0), {"name": name}, 0.01))
    data = {
        "attribution": "Raions: OCHA COD-AB (CC BY-IGO); Russia, Belarus, Moldova: geoBoundaries / OpenStreetMap (ODbL)",
        "raions": {"type": "FeatureCollection", "features": raions},
        "oblasts": {"type": "FeatureCollection", "features": oblasts},
        "russia": {"type": "FeatureCollection", "features": russia},
        "neighbors": {"type": "FeatureCollection", "features": neighbors},
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    # small index for the parser: raion and Russian region names with their label points
    index = {"raions": [{k: f["properties"][k] for k in ("id", "name", "name_en", "oblast", "label")} for f in raions],
             "russia": [{k: f["properties"][k] for k in ("id", "key", "name", "name_en", "label")} for f in russia]}
    with open("dronemap/data/regions.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=0)
    print(f"wrote {out}: {len(raions)} raions, {len(oblasts)} oblasts, {len(russia)} Russian regions, "
          f"{Path(out).stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:])
