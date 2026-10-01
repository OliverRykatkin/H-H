"""
Hämtar de invalda riksdagsledamöterna 2026 ur Valmyndighetens slutliga RD-fil och
skriver data/elected_2026.json (DECISIONS D10: kandidatsidorna visar de invalda tills
kandidatlistorna för 2030 finns).

Enligt D8 sparas bara namn, kandidatnummer, parti, valkrets och valgrund — inte ålder
eller hemkommun.

Användning:
    python fetch_elected_2026.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mandatorn_model.val_feed as vf
from fetch_election_2026 import VALKRETS_MAPPING

OUT = Path(__file__).parent / "data" / "elected_2026.json"


def main() -> int:
    idx = vf.fetch_index(2026)
    rel, md5 = vf.find_rd_file(idx, preliminary=False)
    vo = vf.extract_mandatfordelning(vf.download_file(2026, rel, expected_md5=md5))["valomrade"]
    members = []
    for party in vo["valda"]["partiLedamoterLista"]:
        for m in party["ledamoter"]:
            members.append({
                "namn": m["namn"],
                "kandidatnummer": int(m["kandidatnummer"]),
                "parti": party.get("partiforkortning") or party["partibeteckning"],
                "valkrets": VALKRETS_MAPPING.get(m["valkretsnamn"], m["valkretsnamn"]),
                "valgrund": m.get("valgrundText", ""),
            })
    members.sort(key=lambda m: (m["valkrets"], m["parti"], m["namn"]))
    OUT.write_text(json.dumps({"source": rel, "members": members}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"{len(members)} ledamöter → {OUT}")
    return 0 if len(members) == 349 else 1


if __name__ == "__main__":
    sys.exit(main())
