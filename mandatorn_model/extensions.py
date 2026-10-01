"""Beräkningar ovanpå befintlig modell som den publika sajten kräver (DECISIONS D11).

Inget här ändrar metoden: samma dragningar (simulation.run_simulation) körs genom
samma mandatmotor (seats.allocate_all_mandates) respektive samma uniform swing
(regional.apply_uniform_swing) per dragning.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from mandatorn_model.constants import BASELINE, CONSTITUENCIES, PARTIES
from mandatorn_model.regional import compute_national_swing
from mandatorn_model.seats import allocate_all_mandates


def simulate_constituency_seats(sim: dict) -> dict:
    """Fasta mandat per dragning, valkrets och parti (N1).

    Returnerar {"constituencies": [namn…], "parties": PARTIES,
    "fixed": int8-array [n_sims, n_valkretsar, n_partier],
    "total": int16-array [n_sims, n_partier]} — total = fasta + utjämning enligt
    allocate_all_mandates (kan skilja ett mandat från run_simulations nationella
    snabbfördelning, se docs/PARITY.md A3).
    """
    names = list(CONSTITUENCIES)
    n = sim["n_sims"]
    fixed = np.zeros((n, len(names), len(PARTIES)), dtype=np.int8)
    total = np.zeros((n, len(PARTIES)), dtype=np.int16)
    draws = sim["draws"]
    for i in range(n):
        alloc = allocate_all_mandates({p: float(draws[p][i]) for p in PARTIES})
        for c, name in enumerate(names):
            row = alloc["fixed"][name]
            fixed[i, c] = [row.get(p, 0) for p in PARTIES]
        total[i] = [alloc["total"].get(p, 0) for p in PARTIES]
    return {"constituencies": names, "parties": list(PARTIES), "fixed": fixed, "total": total}


def seat_distribution(counts: np.ndarray) -> dict[str, float]:
    """P(k mandat) för k = 0..max som {"k": sannolikhet}."""
    vals, freq = np.unique(counts, return_counts=True)
    return {str(int(v)): float(f / counts.size) for v, f in zip(vals, freq)}


def area_intervals(base_df: pd.DataFrame, sim: dict, ovriga_per_area: dict | None = None,
                   q: tuple[float, float] = (5, 95)) -> pd.DataFrame:
    """Uniform swing per dragning (N5) → p5/p50/p95 per område och parti.

    Samma formel som regional.apply_uniform_swing (nollsummerad sving mot
    BASELINE, omnormalisering per område till 100 − övriga), applicerad på
    varje dragning. Returnerar DataFrame[region_code, party, p5, p50, p95].
    """
    ovriga = ovriga_per_area or {}
    draws = np.stack([sim["draws"][p] for p in PARTIES], axis=1)          # [n, P]
    base_norm = np.array([BASELINE[p] for p in PARTIES], dtype=float)
    base_norm = base_norm / base_norm.sum() * 100.0
    cur_norm = draws / draws.sum(axis=1, keepdims=True) * 100.0
    swing = cur_norm - base_norm                                            # [n, P]

    wide = base_df.pivot_table(index="region_code", columns="party", values="pct_base", aggfunc="first")
    wide = wide.reindex(columns=PARTIES).fillna(0.0)
    rows = []
    for code, local in wide.iterrows():
        raw = np.clip(local.values[None, :] + swing, 0.0, None)            # [n, P]
        tot = raw.sum(axis=1, keepdims=True)
        target = 100.0 - ovriga.get(code, 0.0)
        pred = np.where(tot > 0, raw / np.where(tot > 0, tot, 1.0) * target, 0.0)
        lo, mid, hi = np.percentile(pred, [q[0], 50, q[1]], axis=0)
        for j, p in enumerate(PARTIES):
            rows.append({"region_code": code, "party": p,
                         "p5": float(lo[j]), "p50": float(mid[j]), "p95": float(hi[j])})
    return pd.DataFrame(rows)


def institute_bias(polls_df: pd.DataFrame, trend_timeseries: dict,
                   start: datetime, end: datetime) -> pd.DataFrame:
    """Husbias per institut och parti (N4) mot Kalman-trenden samma dag.

    Avvikelse = mätningens andel − trendens värde på publiceringsdagen
    (trenden inkluderar mätningen själv; se docs/ASSUMPTIONS.md A-4).
    Returnerar DataFrame med en rad per (institut, parti).
    """
    period = polls_df[(polls_df["PublDate"] >= start) & (polls_df["PublDate"] <= end)]
    rows = []
    for p in PARTIES:
        ts = trend_timeseries.get(p)
        if not ts:
            continue
        t_dates = pd.to_datetime(pd.Series(ts["eval_dates"])).values.astype("datetime64[ns]").astype("int64")
        t_vals = np.asarray(ts["smooth_y"], dtype=float)
        order = np.argsort(t_dates, kind="stable")
        t_dates, t_vals = t_dates[order], t_vals[order]
        sub = period[["Company", "PublDate", p]].dropna(subset=[p])
        if sub.empty:
            continue
        x = sub["PublDate"].values.astype("datetime64[ns]").astype("int64")
        trend_at = np.interp(x, t_dates, t_vals)
        dev = pd.to_numeric(sub[p], errors="coerce").values - trend_at
        df = pd.DataFrame({"institute": sub["Company"].fillna("Okänt").values, "dev": dev,
                           "trend": trend_at})
        for inst, g in df.groupby("institute", sort=True):
            rel = g["dev"] / g["trend"].where(g["trend"] > 0)
            rows.append({
                "institute": inst, "party": p, "n": int(len(g)),
                "share_over": float((g["dev"] > 0).mean()),
                "share_under": float((g["dev"] < 0).mean()),
                "mean_dev_pp": float(g["dev"].mean()),
                "median_dev_pp": float(g["dev"].median()),
                "mean_dev_rel": float(rel.mean()),
                "median_dev_rel": float(rel.median()),
            })
    return pd.DataFrame(rows)


def trend_table(trend_timeseries: dict, reference_date: datetime, keys: dict[str, list[str]],
                last_election: dict[str, float]) -> list[dict]:
    """Nuvärde och förändring mot en månad, ett år och senaste valet (N7).

    keys: {"M": ["M"], ..., "Högerblocket": ["M","L","KD","SD"]} — värdet summeras.
    """
    def value_at(parties: list[str], when: datetime) -> float | None:
        total = 0.0
        for p in parties:
            ts = trend_timeseries.get(p)
            if not ts:
                return None
            dates = pd.to_datetime(pd.Series(ts["eval_dates"]))
            if when < dates.min() or when > dates.max() + timedelta(days=1):
                return None
            idx = int(np.argmin(np.abs((dates - pd.Timestamp(when)).dt.total_seconds().values)))
            total += float(ts["smooth_y"][idx])
        return total

    out = []
    for key, parties in keys.items():
        now = value_at(parties, reference_date)
        out.append({
            "key": key,
            "now": now,
            "monthAgo": value_at(parties, reference_date - timedelta(days=30)),
            "yearAgo": value_at(parties, reference_date - timedelta(days=365)),
            "lastElection": sum(last_election.get(p, 0.0) for p in parties),
        })
    return out


def zero_sum_swing(raw_est: dict) -> dict:
    return compute_national_swing(raw_est, BASELINE)
