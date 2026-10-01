"""Hämta facit för mandatberäkningens golden tests ur Valmyndighetens resultatfiler.

    python tools/fetch_golden.py 2022 2026   → tests/golden/riksdag_<år>.json

Per valkrets: antal fasta mandat, giltiga röster, röster per parti (alla partier) och
Valmyndighetens officiella fasta mandat och utjämningsmandat per parti.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import mandatorn_model.val_feed as vf  # noqa: E402

OUT = REPO / "tests" / "golden"


def _key(entry: dict) -> str:
    return entry.get("partiforkortning") or f"p{entry.get('partikod')}"


def build(year: int) -> dict:
    idx = vf.fetch_index(year)
    rel, md5 = vf.find_rd_file(idx, preliminary=False)
    mf = vf.extract_mandatfordelning(vf.download_file(year, rel, expected_md5=md5))
    vo = mf["valomrade"]
    rp = vo["rostfordelning"]["rosterPaverkaMandat"]
    out = {
        "year": year, "source": rel, "total_seats": int(vo.get("totaltAntalMandat") or 349),
        "valid_votes": int(rp["antalRoster"]),
        "national_votes": {_key(p): int(p["antalRoster"]) for p in rp["partiRoster"]},
        "official_total": {_key(p): int(p["antalMandat"]) for p in vo["mandatfordelning"]["partiLista"]
                           if int(p["antalMandat"])},
        "constituencies": [],
    }
    for vk in vo["valkretsLista"]:
        vrp = vk["rostfordelning"]["rosterPaverkaMandat"]
        plist = (vk.get("mandatfordelning") or {}).get("partiLista") or []
        out["constituencies"].append({
            "name": vk["namnValkrets"],
            "fixed_seats": int(vk.get("totaltAntalFastaMandat") or sum(int(p["antalFastaMandat"]) for p in plist)),
            "valid_votes": int(vrp["antalRoster"]),
            "votes": {_key(p): int(p["antalRoster"]) for p in vrp["partiRoster"]},
            "official_fixed": {_key(p): int(p["antalFastaMandat"]) for p in plist if int(p["antalFastaMandat"])},
            "official_adjustment": {_key(p): int(p["antalUtjamningsmandat"]) for p in plist
                                    if int(p["antalUtjamningsmandat"])},
        })
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for year in map(int, sys.argv[1:] or ["2022", "2026"]):
        data = build(year)
        path = OUT / f"riksdag_{year}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        n_fixed = sum(sum(c["official_fixed"].values()) for c in data["constituencies"])
        n_adj = sum(sum(c["official_adjustment"].values()) for c in data["constituencies"])
        print(f"{year}: {len(data['constituencies'])} valkretsar, {n_fixed} fasta + {n_adj} utjämning, "
              f"totalt {data['official_total']} → {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
