"""mandatorn_model.simulation — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import numpy as np
import pandas as pd
from mandatorn_model.constants import (
    HORIZON_K,
    PARTIES,
    TERM_DAYS,
    THRESHOLD,
    TOTAL_SEATS,
)
from mandatorn_model.seats import modified_sainte_lague

def run_simulation(
    raw_est: dict,
    polls_df: pd.DataFrame,
    window_days: int,
    n_sims: int = 10_000,
    horizon_days: int = 0,
) -> dict:
    """
    Monte Carlo-simulering av mandatutfall.

    Osäkerhetsmodell per parti:
      σ_total = sqrt(σ_polls² + σ_fundamental² + σ_horisont²)

    σ_polls  = standardavvikelse bland senaste mätningarna (fångar houseeffects + slump)
    σ_fundamental = 1,0 % tillägg för strukturell osäkerhet
    σ_horisont = opinionsrörelse fram till valdagen:
                 HORIZON_K · sqrt(andel) · sqrt(horizon_days / TERM_DAYS)
                 (≈ 2 pp för ett 12,5 %-parti en hel mandatperiod ut; 0 på valdagen)
    horizon_days = dagar kvar till nästa val (0 = "om det vore val idag").

    Varje simulation:
      1. Dra stöd från N(μ, σ_total) per parti, trunkera vid 0
      2. Tillämpa 4 %-spärren
      3. Fördela 349 mandat med MSL nationellt (ej per valkrets – snabbt)
      4. Samla statistik
    """
    cutoff = datetime.now() - timedelta(days=window_days)
    recent = polls_df[polls_df["PublDate"] >= cutoff].copy()

    # Skatta σ per parti från spridningen i senaste mätningarna
    party_std = {}
    for p in PARTIES:
        vals = pd.to_numeric(recent[p], errors="coerce").dropna().values
        party_std[p] = max(float(np.std(vals)), 0.5) if len(vals) >= 3 else 1.5

    FUNDAMENTAL = 1.0
    horizon_frac = max(horizon_days, 0) / TERM_DAYS
    horizon_std = {
        p: HORIZON_K * np.sqrt(max(raw_est[p], 1.0)) * np.sqrt(horizon_frac)
        for p in PARTIES
    }
    total_std = {
        p: np.sqrt(party_std[p] ** 2 + FUNDAMENTAL ** 2 + horizon_std[p] ** 2)
        for p in PARTIES
    }

    # Simulera
    rng = np.random.default_rng(seed=42)
    draws = {
        p: np.maximum(0, rng.normal(raw_est[p], total_std[p], n_sims))
        for p in PARTIES
    }

    # Normalisera varje simulation till 100 %
    totals = sum(draws[p] for p in PARTIES)
    draws = {p: draws[p] / totals * 100 for p in PARTIES}

    # Mandatfördelning per simulation (snabb nationell MSL)
    party_mandates = {p: np.zeros(n_sims, dtype=int) for p in PARTIES}
    bloc_h = np.zeros(n_sims, dtype=int)
    bloc_v = np.zeros(n_sims, dtype=int)
    above_threshold = {p: 0 for p in PARTIES}

    for i in range(n_sims):
        sim = {p: draws[p][i] for p in PARTIES}
        eligible = {p: v for p, v in sim.items() if v >= THRESHOLD}
        if not eligible:
            continue
        tot = sum(eligible.values())
        norm = {p: v / tot * 100 for p, v in eligible.items()}
        alloc = modified_sainte_lague(norm, TOTAL_SEATS)
        for p in PARTIES:
            m = alloc.get(p, 0)
            party_mandates[p][i] = m
            if sim[p] >= THRESHOLD:
                above_threshold[p] += 1
        bloc_h[i] = sum(alloc.get(p, 0) for p in ["M", "L", "KD", "SD"])
        bloc_v[i] = sum(alloc.get(p, 0) for p in ["S", "V", "MP", "C"])

    return {
        "draws": draws,
        "party_mandates": party_mandates,
        "party_std": party_std,
        "horizon_std": horizon_std,
        "total_std": total_std,
        "bloc_h": bloc_h,
        "bloc_v": bloc_v,
        "above_threshold": {p: above_threshold[p] / n_sims for p in PARTIES},
        "n_sims": n_sims,
    }
