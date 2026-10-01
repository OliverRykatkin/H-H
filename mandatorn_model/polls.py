"""mandatorn_model.polls — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from io import StringIO
import numpy as np
import pandas as pd
import requests
from mandatorn_model.constants import (
    BASELINE,
    BASELINE_ELECTION_DATE,
    PARTIES,
    POLLS_URL,
)

def fetch_polls_text(url: str = POLLS_URL) -> str:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_polls(text: str) -> pd.DataFrame:
    """SwedishPolls-CSV → DataFrame med korrigerat PublDate, sorterad på datum."""
    df = pd.read_csv(StringIO(text))

    df["PublDate"] = pd.to_datetime(df["PublDate"], errors="coerce")

    # SwedishPolls bulkimporterar ibland äldre mätningar (t.ex. hela
    # Infostats månadsserie 2025–2026) och sätter samma PublDate på alla
    # rader — då klumpas hela historiken ihop på ett datum i Kalman-filtret.
    # När insamlingsperioden är känd och PublDate ligger minst 14 dagar
    # efter collectPeriodTo (eller approxPeriod=TRUE), använd istället
    # mittpunkten av insamlingsperioden som effektivt mätningsdatum.
    collect_from = pd.to_datetime(df.get("collectPeriodFrom"), errors="coerce")
    collect_to = pd.to_datetime(df.get("collectPeriodTo"), errors="coerce")
    midpoint = collect_from + (collect_to - collect_from) / 2
    gap_days = (df["PublDate"] - collect_to).dt.days
    approx = df.get("approxPeriod", pd.Series(index=df.index)).astype(str).str.upper().eq("TRUE")
    needs_fix = midpoint.notna() & (approx | (gap_days >= 14))
    df.loc[needs_fix, "PublDate"] = midpoint[needs_fix]

    df = df.dropna(subset=["PublDate"])
    for p in PARTIES:
        df[p] = pd.to_numeric(df[p], errors="coerce")
    df = df[df["house"] != "Election"].copy()
    df = df.dropna(subset=PARTIES, how="all")
    # Beräkna Övriga som residual (100 − summan av de 8 partierna)
    party_sum = df[PARTIES].sum(axis=1, min_count=1)
    df["O"] = (100 - party_sum).clip(lower=0)
    return df.sort_values("PublDate")


def compute_house_weights(
    df: pd.DataFrame,
    election_date: pd.Timestamp | None = None,
    actual: dict | None = None,
    label: str = "2026",
) -> pd.DataFrame:
    """
    Beräknar träffsäkerhetsvikter per opinionsinsitut baserat på ett tidigare val.

    Standardläge: mäter mot 2026 års riksdagsval (aktuellt facit).
    Kan köras mot valfritt val genom att skicka `election_date` + `actual`.

    Metod:
      1. Hämta alla mätningar de 90 dagarna *före* valdagen
      2. Beräkna medelabsolut fel (MAE) mot faktiskt valresultat per parti
      3. Vikt = 1 / MAE, normaliserad så att genomsnittet = 1
         (okända institut får standardvikt 1,0)
    """
    if election_date is None:
        election_date = pd.Timestamp(BASELINE_ELECTION_DATE)
    if actual is None:
        actual = BASELINE

    window = df[
        (df["PublDate"] >= election_date - pd.Timedelta(days=90))
        & (df["PublDate"] < election_date)
        & (df["house"] != "Election")
    ].copy()

    n_col = f"Antal mätningar ({label})"
    rows = []
    for house, grp in window.groupby("Company"):
        maes = []
        for p in PARTIES:
            vals = grp[p].dropna()
            if len(vals) > 0:
                maes.append(abs(vals.mean() - actual[p]))
        if maes:
            rows.append({
                "Institut": house,
                "MAE (pp)": round(float(np.mean(maes)), 3),
                n_col: len(grp),
            })

    if not rows:
        return pd.DataFrame(columns=["Institut", "MAE (pp)", n_col, "Vikt"])

    house_df = pd.DataFrame(rows).sort_values("MAE (pp)")
    inv_mae = 1.0 / house_df["MAE (pp)"].values
    house_df["Vikt"] = inv_mae / inv_mae.mean()
    house_df["Vikt"] = house_df["Vikt"].round(3)
    return house_df.reset_index(drop=True)
