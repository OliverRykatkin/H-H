"""
Hämtar slutligt resultat för EU-valet 2024 (och 2019 ur 2024 års jämförelsefält)
från Valmyndigheten och dumpar till data/eu_results.json.

Källa: ./s/e/EU-val_2024_slutlig_00_E.zip i resultat.val.se/resultatfiler/euval2024/
(mandatfordelning_00_E.json). Filen innehåller även föregående val (2019) per parti.
EU-valet 2014 saknar feed (bara xlsx hos historik.val.se) och ingår inte än.

Zip-filerna är kodade i Windows-1252.

Användning:
    python fetch_eu_results.py
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import mandatorn_model.val_feed as vf

BASE = f"{vf.RESULT_BASE}/euval2024"
OUT = Path(__file__).parent / "data" / "eu_results.json"
MAIN = {"M", "L", "C", "KD", "S", "V", "MP", "SD"}


def _mandat_json(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = next(n for n in zf.namelist() if "mandatfordelning" in n and n.endswith(".json"))
        return json.loads(zf.read(name).decode("cp1252"))


def parse_national(data: dict) -> dict:
    """Riksnivå för 2024 och (ur jämförelsefälten) 2019."""
    v = data["valomrade"]
    pr = v["rostfordelning"]["rosterPaverkaMandat"]
    seats = {p["partiforkortning"]: p for p in v["mandatfordelning"]["partiLista"]}
    cur, prev = [], []
    for p in pr["partiRoster"]:
        ab = p.get("partiforkortning") or f"#{p['partikod']}"
        s = seats.get(p.get("partiforkortning"), {})
        cur.append({"party": ab, "code": p["partikod"], "name": p["partibeteckning"],
                    "votes": p["antalRoster"], "seats": s.get("antalMandat", 0)})
        if p.get("antalRosterForegaendeVal") is not None:
            prev.append({"party": ab, "code": p["partikod"], "name": p["partibeteckning"],
                         "votes": p["antalRosterForegaendeVal"], "seats": s.get("antalMandatForegaendeVal", 0)})
    return {
        "2024": {"valid_votes": pr["antalRoster"], "seats_total": v["totaltAntalMandat"],
                 "turnout": v["valdeltagande"], "eligible": v["antalRostberattigade"], "parties": cur},
        "2019": {"valid_votes": pr["antalRosterForegaendeVal"], "seats_total": v["totaltAntalMandatForegaendeVal"],
                 "turnout": v["valdeltagandeForegaendeVal"], "eligible": v["antalRostberattigadeForegaendeVal"],
                 "parties": prev},
    }


def main() -> None:
    index = vf.parse_index(vf._http_get(f"{BASE}/index.md5").decode("utf-8"))
    relpath = next(p for p in index if p.startswith("./s/e/") and p.endswith("_00_E.zip"))
    raw = vf._http_get(f"{BASE}/{relpath.lstrip('./')}", timeout=300)
    import hashlib
    assert hashlib.md5(raw).hexdigest() == index[relpath], "md5-mismatch"
    out = {
        "source": f"{BASE}/{relpath.lstrip('./')}",
        "note": "2019: antal mandat avser fördelningen med 21 mandat som gäller från 2020-02-01 (Storbritannien lämnade EU).",
        "elections": parse_national(_mandat_json(raw)),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Skrev {OUT} ({OUT.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
