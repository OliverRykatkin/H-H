"""Kommun → riksdagsvalkrets (2026) ur Valmyndighetens slutliga RD-fil.

    python web/scripts/geo/build_kommun_valkrets.py   → web/scripts/geo/kommun_valkrets.json

Valdistrikten bär (länskod, kretskod); valkretsarna i mandatfördelningen identifieras
genom att matcha summan av distriktens röster mot valkretsens totaltAntalRoster.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import mandatorn_model.val_feed as vf  # noqa: E402
from fetch_election_2026 import VALKRETS_MAPPING  # noqa: E402

OUT = Path(__file__).with_name("kommun_valkrets.json")


def main() -> int:
    idx = vf.fetch_index(2026)
    rel, md5 = vf.find_rd_file(idx, preliminary=False)
    data = vf.download_file(2026, rel, expected_md5=md5)
    mf = vf.extract_mandatfordelning(data)["valomrade"]
    rf = vf.extract_rostfordelning(data)["valdistrikt"]
    votes = collections.Counter()
    kommun_krets = collections.defaultdict(set)
    for d in rf:
        key = (d["lankod"], d["kretskod"])
        votes[key] += int(d.get("totaltAntalRoster") or 0)
        kommun_krets[d["kommunkod"]].add(key)
    by_total = {int(v["totaltAntalRoster"]): VALKRETS_MAPPING[v["namnValkrets"]] for v in mf["valkretsLista"]}
    krets_name = {}
    for key, n in votes.items():
        if n not in by_total:
            raise SystemExit(f"Ingen valkrets med {n} röster för {key}")
        krets_name[key] = by_total[n]
    out = {}
    for kod, keys in sorted(kommun_krets.items()):
        names = sorted({krets_name[k] for k in keys})
        if len(names) != 1:
            raise SystemExit(f"Kommun {kod} i flera valkretsar: {names}")
        out[kod] = names[0]
    OUT.write_text(json.dumps({"source": rel, "kommun_valkrets": out}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"{len(out)} kommuner → {len(set(out.values()))} valkretsar → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
