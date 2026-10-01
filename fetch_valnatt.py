"""
Hämtar valnattens preliminära riksdagsräkning per valdistrikt för ett valår och dumpar
till data/valnatt_<år>.csv.gz — underlaget för uppspelning och simulatorn (fas 3).

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
    python fetch_valnatt.py            # 2026 (baslinje 2022)
    python fetch_valnatt.py 2022       # 2022 (baslinje 2018) — simulator/integrationstest
    python fetch_valnatt.py --baseline 2026   # slutligt resultat per distrikt → data/baseline_districts_2026.csv.gz
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import mandatorn_model.val_feed as vf

PARTIES = vf.PARTIES
DATA = Path(__file__).parent / "data"

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


def build_baseline(rostfordelning: dict) -> pd.DataFrame:
    """Slutligt resultat per ordinarie distrikt (baslinje för nästa vals nowcast)."""
    rows = []
    for vd in rostfordelning["valdistrikt"]:
        if vd.get("valdistriktstyp") != "valdistrikt":
            continue
        rp = (vd.get("rostfordelning") or {}).get("rosterPaverkaMandat")
        if not rp:
            continue
        by_party = {pr.get("partiforkortning"): pr for pr in rp.get("partiRoster", [])}
        row = {"district_code": vd["valdistriktskod"], "total_valid_votes": int(rp["antalRoster"])}
        row.update({f"votes_{p}": int(by_party.get(p, {}).get("antalRoster") or 0) for p in PARTIES})
        rows.append(row)
    return pd.DataFrame(rows).sort_values("district_code").reset_index(drop=True)


def main(argv: list[str]) -> int:
    baseline = "--baseline" in argv
    years = [a for a in argv if a.isdigit()]
    year = int(years[0]) if years else 2026
    idx = vf.fetch_index(year)
    relpath, md5 = vf.find_rd_file(idx, preliminary=not baseline)
    print(f"Fil: {relpath}")
    data = vf.download_file(year, relpath, expected_md5=md5)
    if baseline:
        df = build_baseline(vf.extract_rostfordelning(data))
        out = DATA / f"baseline_districts_{year}.csv.gz"
        df.to_csv(out, index=False, compression={"method": "gzip", "mtime": 0})  # deterministisk gzip
        print(f"{len(df)} distrikt, {df['total_valid_votes'].sum():,} röster → {out} ({out.stat().st_size // 1024} kB)")
        return 0
    df = build_rows(vf.extract_rostfordelning(data))
    n_cmp = int(df["comparable"].sum())
    share_cmp = df.loc[df["comparable"], "total_valid_votes"].sum() / df["total_valid_votes"].sum()
    print(f"Distrikt: {len(df)} ordinarie, {n_cmp} jämförbara mot förra valet ({share_cmp:.1%} av rösterna)")
    print(f"Rapporterade {df['reported_at'].iloc[0]} → {df['reported_at'].iloc[-1]}")
    out = DATA / f"valnatt_{year}.csv.gz"
    df.to_csv(out, index=False, compression={"method": "gzip", "mtime": 0})  # deterministisk gzip
    print(f"Skrev: {out} ({out.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
