"""
Hämtar 2022 valresultat från SCB PX-Web och dumpar till data/scb_2022.json.

Körs en gång (eller efter SCB-rättningar). app.py läser sedan filen istället för
att gå mot SCB live — sparar 6-12 sek per nytt Cloud Run-cold-start.

Användning:
    python fetch_scb_cache.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

SCB_RIKSDAG_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104C/ME0104T3"
SCB_REGIONVAL_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104B/ME0104T2"
SCB_KOMMUNVAL_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104A/ME0104T1"

SCB_PARTIES_RAW = ["M", "C", "FP", "KD", "MP", "S", "V", "SD"]
SCB_TO_APP_PARTY = {"FP": "L"}

SCB_REGIONVAL_TO_GEOJSON = {
    "01L":  "Stockholm",      "03L":  "Uppsala",
    "04L":  "Södermanland",   "05L":  "Östergötland",
    "06L":  "Jönköping",      "07L":  "Kronoberg",
    "08L":  "Kalmar",         "10L":  "Blekinge",
    "12L":  "Skåne",          "13L":  "Halland",
    "14L":  "Västra Götaland", "17L":  "Värmland",
    "18L":  "Örebro",         "19L":  "Västmanland",
    "20LG": "Dalarna",        "21L":  "Gävleborg",
    "22L":  "Västernorrland", "23L":  "Jämtland",
    "24L":  "Västerbotten",   "25L":  "Norrbotten",
}
SCB_REGIONVAL_CODES = list(SCB_REGIONVAL_TO_GEOJSON.keys())


def _get_region_codes(api_url: str) -> list:
    resp = requests.get(api_url, timeout=30)
    resp.raise_for_status()
    meta = resp.json()
    region_var = next(
        (v for v in meta.get("variables", []) if v["code"] == "Region"), None
    )
    return region_var["values"] if region_var else []


def fetch_one(
    api_url: str,
    contents_code: str,
    region_codes: list | None = None,
    party_codes: list | None = None,
) -> list[dict]:
    if region_codes is None:
        all_codes = _get_region_codes(api_url)
        region_codes = [c for c in all_codes if re.match(r"^\d{4}$", c)]

    if not region_codes:
        return []

    parties_to_fetch = party_codes if party_codes is not None else SCB_PARTIES_RAW
    query = {
        "query": [
            {"code": "Region",       "selection": {"filter": "item", "values": region_codes}},
            {"code": "Partimm",      "selection": {"filter": "item", "values": parties_to_fetch}},
            {"code": "ContentsCode", "selection": {"filter": "item", "values": [contents_code]}},
            {"code": "Tid",          "selection": {"filter": "item", "values": ["2022"]}},
        ],
        "response": {"format": "json"},
    }
    print(f"  -> POST {api_url} (contents={contents_code}, "
          f"regions={len(region_codes)}, parties={len(parties_to_fetch)})")
    resp = requests.post(api_url, json=query, timeout=120)
    resp.raise_for_status()
    raw = resp.json()

    rows = []
    for item in raw.get("data", []):
        keys = item.get("key", [])
        if len(keys) < 2:
            continue
        region_code = str(keys[0])
        party_scb = keys[1]
        vals = item.get("values", [])
        val_str = vals[0] if vals else None
        if not val_str or val_str in ("..", ""):
            continue
        party = SCB_TO_APP_PARTY.get(party_scb, party_scb)
        try:
            pct = float(val_str)
        except (ValueError, TypeError):
            continue
        rows.append({"region_code": region_code, "party": party, "pct_2022": pct})
    return rows


QUERIES = [
    {
        "label":         "Riksdag per kommun",
        "api_url":       SCB_RIKSDAG_URL,
        "contents_code": "ME0104B7",
        "region_codes":  None,
        "party_codes":   None,
    },
    {
        "label":         "Regionval per region (8 partier)",
        "api_url":       SCB_REGIONVAL_URL,
        "contents_code": "ME0104B5",
        "region_codes":  SCB_REGIONVAL_CODES,
        "party_codes":   None,
    },
    {
        "label":         "Regionval per region (ÖVRIGA)",
        "api_url":       SCB_REGIONVAL_URL,
        "contents_code": "ME0104B5",
        "region_codes":  SCB_REGIONVAL_CODES,
        "party_codes":   ["ÖVRIGA"],
    },
    {
        "label":         "Kommunalval per kommun (8 partier)",
        "api_url":       SCB_KOMMUNVAL_URL,
        "contents_code": "ME0104B2",
        "region_codes":  None,
        "party_codes":   None,
    },
    {
        "label":         "Kommunalval per kommun (ÖVRIGA)",
        "api_url":       SCB_KOMMUNVAL_URL,
        "contents_code": "ME0104B2",
        "region_codes":  None,
        "party_codes":   ["ÖVRIGA"],
    },
]


def main() -> int:
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "scb_2022.json"

    queries_out = []
    for q in QUERIES:
        print(f"Hämtar: {q['label']}")
        rows = fetch_one(
            q["api_url"], q["contents_code"],
            region_codes=q["region_codes"],
            party_codes=q["party_codes"],
        )
        print(f"  <- {len(rows)} rader")
        queries_out.append({
            "api_url":       q["api_url"],
            "contents_code": q["contents_code"],
            "region_codes":  q["region_codes"],
            "party_codes":   q["party_codes"],
            "rows":          rows,
        })

    payload = {"queries": queries_out}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"\nSparade {out_path} ({size_kb:.1f} kB, {sum(len(q['rows']) for q in queries_out)} rader totalt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
