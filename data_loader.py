"""Ladda och normalisera Valmyndighetens valdistriktsdata för nowcasting.

Hämtar 2018 och 2022 riksdagsval på distriktsnivå, normaliserar till ett
gemensamt schema och cachar som parquet. Schema:
    district_id (int64), total_valid_votes (int), votes_<P> (int) för
    P in PARTIES, eligible_voters (int)

Uppsamlingsdistrikt (utlands-/brevröster räknade efter valnatten) exkluderas.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nowcast import PARTIES

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"

SOURCES = {
    "r_2018": (
        "https://historik.val.se/val/val2018/statistik/2018_R_per_valdistrikt.xlsx",
        RAW_DIR / "r-2018-per-valdistrikt.xlsx",
    ),
    "r_2022": (
        "https://val.se/download/18.162047b519a91d0533118f4b/1764336897948/"
        "Roster-per-distrikt-slutligt-antal-roster-inklusive-totalt-valdeltagande-"
        "riksdagsvalet-2022.xlsx",
        RAW_DIR / "r-2022-slutligt-per-valdistrikt.xlsx",
    ),
    "jamforelser_18_22": (
        "https://val.se/download/18.162047b519a91d0533119148/1666857349837/"
        "jamforelser-2018-och-2022-valdistrikt-och-uppsamlingsdistrikt-v2.xlsx",
        RAW_DIR / "jamforelser-2018-2022-valdistrikt.xlsx",
    ),
}

PARTY_NAME_TO_CODE = {
    "Moderaterna": "M",
    "Centerpartiet": "C",
    "Liberalerna (tidigare Folkpartiet)": "L",
    "Liberalerna": "L",
    "Kristdemokraterna": "KD",
    "Arbetarepartiet-Socialdemokraterna": "S",
    "Vänsterpartiet": "V",
    "Miljöpartiet de gröna": "MP",
    "Sverigedemokraterna": "SD",
}


def ensure_raw_files() -> None:
    """Ladda ner råfiler om de saknas lokalt."""
    import urllib.request

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for key, (url, path) in SOURCES.items():
        if not path.exists():
            print(f"Hämtar {key} → {path.name}...")
            urllib.request.urlretrieve(url, path)


def load_2022_districts() -> pd.DataFrame:
    """Läs 2022 års slutgiltiga resultat på distriktsnivå.

    Returns:
        DataFrame med kolumner: district_id, total_valid_votes, eligible_voters,
        votes_M, votes_S, ..., votes_SD.
    """
    cache = CACHE_DIR / "r_2022_districts.csv"
    if cache.exists():
        return pd.read_csv(cache)

    ensure_raw_files()
    df = pd.read_excel(SOURCES["r_2022"][1], sheet_name="roster_RD")
    df.columns = [c.strip() for c in df.columns]
    df["Parti"] = df["Parti"].astype(str).str.strip()
    df = df[df["Valdistriktnamn"] != "Uppsamlingsdistrikt"].copy()

    party_rows = df[df["Parti"].isin(PARTY_NAME_TO_CODE)].copy()
    party_rows["party_code"] = party_rows["Parti"].map(PARTY_NAME_TO_CODE)

    wide = party_rows.pivot_table(
        index="Valdistriktskod",
        columns="party_code",
        values="Röster",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={"Valdistriktskod": "district_id"})
    for p in PARTIES:
        if p not in wide.columns:
            wide[p] = 0
        wide = wide.rename(columns={p: f"votes_{p}"})

    summa = df[df["Parti"] == "Summa giltiga röster"][
        ["Valdistriktskod", "Röster", "Röstberättigade"]
    ].rename(
        columns={
            "Valdistriktskod": "district_id",
            "Röster": "total_valid_votes",
            "Röstberättigade": "eligible_voters",
        }
    )

    out = wide.merge(summa, on="district_id", how="left")
    out["district_id"] = out["district_id"].astype("int64")
    out["total_valid_votes"] = out["total_valid_votes"].astype("int64")
    out["eligible_voters"] = out["eligible_voters"].astype("int64")
    for p in PARTIES:
        out[f"votes_{p}"] = out[f"votes_{p}"].astype("int64")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


def load_2018_districts() -> pd.DataFrame:
    """Läs 2018 års slutgiltiga resultat på distriktsnivå.

    Returns:
        DataFrame med kolumner: district_id, total_valid_votes, eligible_voters,
        votes_M, votes_S, ..., votes_SD.

    district_id är konstruerat som: LÄNSKOD * 1e6 + KOMMUNKOD * 1e4 + VALDISTRIKTSKOD,
    vilket matchar 2022 års Valdistriktskod.
    """
    cache = CACHE_DIR / "r_2018_districts.csv"
    if cache.exists():
        return pd.read_csv(cache)

    ensure_raw_files()
    df = pd.read_excel(SOURCES["r_2018"][1], sheet_name="R antal")
    df.columns = [c.strip() for c in df.columns]

    df = df[df["VALDISTRIKTSKOD"] != 0].copy()
    df["district_id"] = (
        df["LÄNSKOD"] * 1_000_000
        + df["KOMMUNKOD"] * 10_000
        + df["VALDISTRIKTSKOD"]
    ).astype("int64")

    out = pd.DataFrame({"district_id": df["district_id"]})
    for p in PARTIES:
        out[f"votes_{p}"] = df[p].fillna(0).astype("int64").values
    out["total_valid_votes"] = df["RÖSTER GILTIGA"].astype("int64").values
    out["eligible_voters"] = df["RÖSTBERÄTTIGADE"].astype("int64").values

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


def load_aligned_pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returnera (baseline_2018, actual_2022) inner-joined på district_id.

    Boundary-changed distrikt (~60 st, <1 %) hoppas över för att hålla
    matematiken ren — den ena sidan saknar motsvarande distrikt i andra året.
    """
    df18 = load_2018_districts()
    df22 = load_2022_districts()
    common = set(df18["district_id"]) & set(df22["district_id"])
    baseline = df18[df18["district_id"].isin(common)].reset_index(drop=True)
    actual = df22[df22["district_id"].isin(common)].reset_index(drop=True)
    return baseline, actual


if __name__ == "__main__":
    b, a = load_aligned_pair()
    print(f"Baseline (2018): {len(b)} distrikt, {b['total_valid_votes'].sum():,} röster")
    print(f"Actual  (2022): {len(a)} distrikt, {a['total_valid_votes'].sum():,} röster")
    print()
    print("Nationella andelar (sanity check):")
    for p in PARTIES:
        s18 = b[f"votes_{p}"].sum() / b["total_valid_votes"].sum() * 100
        s22 = a[f"votes_{p}"].sum() / a["total_valid_votes"].sum() * 100
        print(f"  {p:<3}: 2018={s18:5.2f}%   2022={s22:5.2f}%   delta={s22-s18:+5.2f}pe")
