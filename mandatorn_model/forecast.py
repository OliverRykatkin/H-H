"""Hela prognoskörningen för ett referensdatum: allt app.main() räknade före flikarna."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from mandatorn_model.constants import (
    BASELINE_ELECTION_DATE,
    NEXT_ELECTION,
    PARTIES,
    PARTIES_WITH_OTHER,
    TREND_START,
)
from mandatorn_model.kalman import aggregate_polls_kalman, aggregate_polls_kalman_timeseries
from mandatorn_model.polls import compute_house_weights
from mandatorn_model.seats import allocate_all_mandates, compute_baseline_mandates
from mandatorn_model.simulation import run_simulation

WINDOW_DAYS = 365
DEFAULT_SEED = 42
DEFAULT_N_SIMS = 10_000


@dataclass
class Forecast:
    reference_date: datetime
    seed: int
    house_weights: pd.DataFrame
    raw_est: dict
    raw_est_with_other: dict
    trend_timeseries: dict
    mandates: dict
    sim: dict
    days_left: int
    latest_poll_date: str
    baseline_seats: dict
    baseline_seats_total: dict


def reference_day(now: datetime) -> datetime:
    """Referensdatum avrundat till dygnets början: samma dag ger samma prognos."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def build_trend_timeseries(polls_df: pd.DataFrame, house_weights: pd.DataFrame,
                           reference_date: datetime, raw_est_with_other: dict) -> dict:
    """Trendserie i två segment: TREND_START → valdagen (oankrat) och valdagen →
    reference_date (ankrat i valresultatet, skalat så att slutpunkten = estimatet)."""
    trend_days = (reference_date - BASELINE_ELECTION_DATE).days + 1
    raw_ts = aggregate_polls_kalman_timeseries(
        polls_df, house_weights=house_weights, reference_date=reference_date,
        window_days=trend_days,
    )
    trend = {}
    for p in PARTIES_WITH_OTHER:
        if p not in raw_ts:
            continue
        ts = raw_ts[p]
        endpoint = ts["smooth_y"][-1] if ts["smooth_y"] else 0.0
        target = raw_est_with_other.get(p, endpoint)
        scale = target / endpoint if abs(endpoint) > 0.01 else 1.0
        trend[p] = {
            "eval_dates": ts["eval_dates"],
            "smooth_y": [v * scale for v in ts["smooth_y"]],
            "smooth_std": [v * scale for v in ts["smooth_std"]],
        }
    pre_ts = aggregate_polls_kalman_timeseries(
        polls_df, house_weights=house_weights, reference_date=BASELINE_ELECTION_DATE,
        window_days=(BASELINE_ELECTION_DATE - TREND_START).days,
    )
    for p, pre in pre_ts.items():
        post = trend.get(p)
        if post is None:
            trend[p] = pre
            continue
        trend[p] = {k: list(pre[k]) + list(post[k]) for k in ("eval_dates", "smooth_y", "smooth_std")}
    return trend


def build_forecast(polls_df: pd.DataFrame, reference_date: datetime,
                   seed: int = DEFAULT_SEED, n_sims: int = DEFAULT_N_SIMS) -> Forecast:
    house_weights = compute_house_weights(polls_df)
    trend_days = (reference_date - BASELINE_ELECTION_DATE).days + 1
    # Kalman-fönstret täcker alltid hela tiden sedan baslinjevalet, så att
    # filtret startar i valresultatet utan lucka mot första mätningen.
    raw_est = aggregate_polls_kalman(
        polls_df, house_weights=house_weights, reference_date=reference_date,
        window_days=max(WINDOW_DAYS, trend_days),
    )
    # Övriga: slutpunkten i Kalman-tidsserien efter valet (raw_est summerar till 100 %).
    post_ts = aggregate_polls_kalman_timeseries(
        polls_df, house_weights=house_weights, reference_date=reference_date,
        window_days=trend_days,
    )
    o_ts = post_ts.get("O", {})
    raw_est_other = max(0.0, float(o_ts["smooth_y"][-1]) if o_ts.get("smooth_y") else 0.0)
    raw_est_with_other = {**raw_est, "O": raw_est_other}

    days_left = max(0, (NEXT_ELECTION - reference_date).days)
    baseline_seats = compute_baseline_mandates()
    return Forecast(
        reference_date=reference_date,
        seed=seed,
        house_weights=house_weights,
        raw_est=raw_est,
        raw_est_with_other=raw_est_with_other,
        trend_timeseries=build_trend_timeseries(polls_df, house_weights, reference_date, raw_est_with_other),
        mandates=allocate_all_mandates(raw_est),
        sim=run_simulation(raw_est, polls_df, WINDOW_DAYS, n_sims=n_sims, horizon_days=days_left,
                           reference_date=reference_date, seed=seed),
        days_left=days_left,
        latest_poll_date=polls_df["PublDate"].max().strftime("%Y-%m-%d"),
        baseline_seats=baseline_seats,
        baseline_seats_total={p: sum(baseline_seats[c].get(p, 0) for c in baseline_seats) for p in PARTIES},
    )
