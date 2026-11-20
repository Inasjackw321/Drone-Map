#!/usr/bin/env python3
"""Build dronemap/data/settlements.tsv.gz from the GeoNames dump for Ukraine.

    curl -O https://download.geonames.org/export/dump/UA.zip && unzip UA.zip
    python scripts/build_settlements.py UA.txt

GeoNames data is licensed under CC BY 4.0 (https://www.geonames.org).
"""
import csv
import gzip
import re
import sys
from pathlib import Path

ADMIN1 = {
    "01": "cherkasy", "02": "chernihiv", "03": "chernivtsi", "04": "dnipro", "05": "donetsk",
    "06": "ivano_frankivsk", "07": "kharkiv", "08": "kherson", "09": "khmelnytskyi", "10": "kirovohrad",
    "11": "crimea", "12": "kyiv_city", "13": "kyiv", "14": "luhansk", "15": "lviv", "16": "mykolaiv",
    "17": "odesa", "18": "poltava", "19": "rivne", "20": "crimea", "21": "sumy", "22": "ternopil",
    "23": "vinnytsia", "24": "volyn", "25": "zakarpattia", "26": "zaporizhzhia", "27": "zhytomyr",
}
KEEP = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLS", "PPLF"}
CYR = re.compile(r"^[а-яіїєґё' \-]+$")


def main(src: str, out: str = "dronemap/data/settlements.tsv.gz") -> None:
    rows = 0
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(src, encoding="utf-8") as f, gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as g:
        g.write("# GeoNames (CC BY 4.0) populated places of Ukraine: id oblast lat lon population fcode name names\n")
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) < 15 or r[6] != "P" or r[7] not in KEEP:
                continue
            oblast = ADMIN1.get(r[10])
            if not oblast:
                continue
            names = []
            for n in [r[1]] + r[3].split(","):
                n = n.strip().lower().replace("’", "'").replace("ʼ", "'").replace("`", "'").replace("ё", "е")
                if len(n) >= 4 and CYR.match(n) and n not in names:
                    names.append(n)
            if not names:
                continue
            g.write("\t".join([r[0], oblast, f"{float(r[4]):.4f}", f"{float(r[5]):.4f}", r[14] or "0", r[7],
                               r[1], "|".join(names)]) + "\n")
            rows += 1
    print(f"wrote {rows} settlements to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
