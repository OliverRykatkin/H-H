"""
Hämtar valnattens preliminära riksdagsräkning 2026 per valdistrikt och dumpar
till data/valnatt_2026.csv.gz — underlaget för Valnatt-flikens uppspelning.

Per ordinarie valdistrikt:
    district_id, reported_at (rapporteringsTid), comparable,
    total_valid_votes + votes_<P>             (preliminär räkning 2026)
    base_total_valid_votes + base_votes_<P>   (2022, enligt Valmyndighetens
                                                jämförelse mot föregående val)

Baslinjen tas direkt ur feedens `antalRosterForegaendeVal`, som Valmyndigheten
räknat om till 2026 års distriktsindelning ("Kan jämföras" / "Jämförs mot
summerat"). Distrikt med "Ej jämförbart" får comparable=False och kan inte
ingå i deltaberäkningen.

Användning:
    python fetch_valnatt_2026.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import val_feed as vf

PARTIES = vf.PARTIES
OUT_PATH = Path(__file__).parent / "data" / "valnatt_2026.csv.gz"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def build_rows(rostfordelning: dict) -> pd.DataFrame:
    rows = []
    for vd in rostfordelning["valdistrikt"]:
        if vd.get("valdistriktstyp") != "valdistrikt":
            continue
        rp = (vd.get("rostfordelning") or {}).get("rosterPaverkaMandat")
        if not rp or not vd.get("rapporteringsTid"):
            continue
        by_party = {pr.get("partiforkortning"): pr for pr in rp.get("partiRoster", [])}
        base_total = rp.get("antalRosterForegaendeVal")
        comparable = base_total is not None and all(
            by_party.get(p, {}).get("antalRosterForegaendeVal") is not None for p in PARTIES
        )
        row = {
            "district_id": int(vd["valdistriktskod"]),
            "reported_at": vd["rapporteringsTid"],
            "comparable": comparable,
            "total_valid_votes": int(rp["antalRoster"]),
            "base_total_valid_votes": int(base_total) if comparable else 0,
        }
        for p in PARTIES:
            pr = by_party.get(p, {})
            row[f"votes_{p}"] = int(pr.get("antalRoster") or 0)
            row[f"base_votes_{p}"] = int(pr.get("antalRosterForegaendeVal") or 0) if comparable else 0
        rows.append(row)
    return pd.DataFrame(rows).sort_values("reported_at").reset_index(drop=True)


def main() -> int:
    idx = vf.fetch_index(2026)
    relpath, md5 = vf.find_rd_file(idx, preliminary=True)
    print(f"Fil: {relpath}")
    data = vf.download_file(2026, relpath, expected_md5=md5)
    df = build_rows(vf.extract_rostfordelning(data))

    n_cmp = int(df["comparable"].sum())
    share_cmp = df.loc[df["comparable"], "total_valid_votes"].sum() / df["total_valid_votes"].sum()
    print(f"Distrikt: {len(df)} ordinarie, {n_cmp} jämförbara mot 2022 "
          f"({share_cmp:.1%} av rösterna)")
    print(f"Rapporterade {df['reported_at'].iloc[0]} → {df['reported_at'].iloc[-1]}")

    OUT_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(OUT_PATH, index=False, compression="gzip")
    print(f"Skrev: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
