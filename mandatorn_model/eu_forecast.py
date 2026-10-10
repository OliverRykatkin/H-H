"""EU-valsprognos (fas 2): riksdagsmätningar som proxy plus historisk EU-avvikelse (D-EU2).

Det finns inga EU-mätningar. Modellen tar därför Kalman-estimatet för riksdagsopinionen
och lägger på partiets genomsnittliga avvikelse mellan EU-valet och närmast föregående
riksdagsval (2019 mot 2018, 2024 mot 2022), krympt mot noll (`SHRINK`). Osäkerheten
består av mätspridning, strukturell osäkerhet, horisont och avvikelsernas egen
spridning mellan de två valen. Metoden är mer osäker än riksdagsprognosen och
redovisas så i utdata (`EuNational.method`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from mandatorn_model.constants import (
    ELECTION_2026, HORIZON_K, NATIONAL_2018, NATIONAL_2022, PARTIES, TERM_DAYS,
)
from mandatorn_model.election import EU2029, ElectionProfile
from mandatorn_model.eu_seats import allocate_eu
from mandatorn_model.kalman import aggregate_polls_kalman
from mandatorn_model.polls import compute_house_weights, parse_polls
from mandatorn_model.seats import BASELINE_OTHERS

EU_RESULTS = Path(__file__).resolve().parents[1] / "data" / "eu_results.json"
RD_BEFORE = {"2019": NATIONAL_2018, "2024": NATIONAL_2022}   # närmast föregående riksdagsval
EU_ELECTION_DATES = {"2019": datetime(2019, 5, 26), "2024": datetime(2024, 6, 9)}

SHRINK = 0.5            # andel av den historiska avvikelsen som tas med
DEV_SD_FLOOR = 1.0      # pp: golv för avvikelsens spridning (två val räcker inte för mer)
FUNDAMENTAL = 1.0       # pp, som i riksdagssimuleringen
WINDOW_DAYS = 365
VOTE_SCALE = 1000.0     # andel (%) → "röster" i simuleringen; spärrbas = 100 * VOTE_SCALE


def load_eu_results(path: Path = EU_RESULTS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["elections"]


def eu_shares(election: dict) -> dict[str, float]:
    """Andel av alla giltiga röster (%) för de åtta partierna; O = resten."""
    v = election["valid_votes"]
    out = {p["party"]: 100.0 * p["votes"] / v for p in election["parties"] if p["party"] in PARTIES}
    out["O"] = 100.0 - sum(out.get(p, 0.0) for p in PARTIES)
    return out


def deviations(results: dict, years: list[str] | None = None) -> dict[str, dict[str, float]]:
    """EU-resultat minus föregående riksdagsval (pp av alla giltiga röster), per år och parti."""
    out = {}
    for y in years or sorted(results):
        eu = eu_shares(results[y])
        out[y] = {p: eu[p] - RD_BEFORE[y][p] for p in PARTIES}
    return out


@dataclass
class Proxy:
    """Avvikelsemodellen: medel (krympt) och spridning per parti, samt övrigas andel."""
    shift: dict[str, float]
    dev_sd: dict[str, float]
    others: float
    years: list[str]
    shrink: float

    @classmethod
    def from_history(cls, results: dict, years: list[str], shrink: float = SHRINK,
                     others_fallback: float | None = None) -> "Proxy":
        if not years:
            return cls({p: 0.0 for p in PARTIES}, {p: DEV_SD_FLOOR for p in PARTIES},
                       others_fallback if others_fallback is not None else 100 - sum(NATIONAL_2022.values()),
                       [], shrink)
        dev = deviations(results, years)
        mean = {p: float(np.mean([dev[y][p] for y in years])) for p in PARTIES}
        if len(years) > 1:
            sd = {p: max(DEV_SD_FLOOR, float(np.std([dev[y][p] for y in years], ddof=1))) for p in PARTIES}
        else:
            sd = {p: DEV_SD_FLOOR for p in PARTIES}
        others = float(np.mean([eu_shares(results[y])["O"] for y in years]))
        return cls({p: shrink * mean[p] for p in PARTIES}, sd, others, list(years), shrink)


def proxy_shares(raw_est: dict, proxy: Proxy, rd_others: float) -> dict[str, float]:
    """Riksdagsestimat (8 partier, summa 100) → förväntade EU-andelar av alla giltiga röster."""
    scale = (100.0 - rd_others) / 100.0
    adj = {p: max(0.1, raw_est[p] * scale + proxy.shift[p]) for p in PARTIES}
    k = (100.0 - proxy.others) / sum(adj.values())
    return {**{p: adj[p] * k for p in PARTIES}, "O": proxy.others}


def party_spread(polls: pd.DataFrame, reference_date: datetime, window_days: int = WINDOW_DAYS) -> dict[str, float]:
    """σ per parti ur spridningen i senaste mätningarna (samma regel som run_simulation)."""
    recent = polls[polls["PublDate"] >= reference_date - timedelta(days=window_days)]
    out = {}
    for p in PARTIES:
        vals = pd.to_numeric(recent[p], errors="coerce").dropna().values
        out[p] = max(float(np.std(vals)), 0.5) if len(vals) >= 3 else 1.5
    return out


def total_sd(shares: dict, spread: dict, proxy: Proxy, horizon_days: int) -> dict[str, dict[str, float]]:
    frac = max(horizon_days, 0) / TERM_DAYS
    parts = {}
    for p in PARTIES:
        hz = HORIZON_K * np.sqrt(max(shares[p], 1.0)) * np.sqrt(frac)
        total = float(np.sqrt(spread[p] ** 2 + FUNDAMENTAL ** 2 + hz ** 2 + proxy.dev_sd[p] ** 2))
        parts[p] = {"polls": spread[p], "horizon": float(hz), "deviation": proxy.dev_sd[p], "total": total}
    return parts


def point_seats(shares: dict, profile: ElectionProfile = EU2029) -> dict[str, int]:
    seats = allocate_eu({p: shares[p] * VOTE_SCALE for p in PARTIES}, 100.0 * VOTE_SCALE, profile)
    return {p: seats.get(p, 0) for p in PARTIES}


def simulate(shares: dict, sd: dict, n_sims: int, seed: int, profile: ElectionProfile = EU2029) -> dict:
    """Monte Carlo: normalfördelade andelar per parti, övriga fasta, riksspärr och EU-mandatregel."""
    rng = np.random.default_rng(seed)
    pool = 100.0 - shares["O"]
    draws = {p: np.maximum(0.0, rng.normal(shares[p], sd[p]["total"], n_sims)) for p in PARTIES}
    tot = sum(draws[p] for p in PARTIES)
    draws = {p: draws[p] / tot * pool for p in PARTIES}
    seats = {p: np.zeros(n_sims, dtype=int) for p in PARTIES}
    above = {p: 0 for p in PARTIES}
    largest = {p: 0 for p in PARTIES}
    for i in range(n_sims):
        sim = {p: float(draws[p][i]) for p in PARTIES}
        alloc = allocate_eu({p: v * VOTE_SCALE for p, v in sim.items()}, 100.0 * VOTE_SCALE, profile)
        for p in PARTIES:
            seats[p][i] = alloc.get(p, 0)
            above[p] += sim[p] >= profile.threshold * 100
        largest[max(sim, key=sim.get)] += 1
    return {"draws": draws, "seats": seats, "n_sims": n_sims,
            "above_threshold": {p: above[p] / n_sims for p in PARTIES},
            "p_largest": {p: largest[p] / n_sims for p in PARTIES}}


@dataclass
class EuForecast:
    reference_date: datetime
    seed: int
    profile: ElectionProfile
    raw_est: dict
    shares: dict
    proxy: Proxy
    sd: dict
    seats: dict
    sim: dict
    days_left: int
    latest_poll_date: str
    rd_others: float


def build_eu_forecast(polls: pd.DataFrame, reference_date: datetime, seed: int = 42, n_sims: int = 10_000,
                      profile: ElectionProfile = EU2029, results: dict | None = None) -> EuForecast:
    results = results or load_eu_results()
    hw = compute_house_weights(polls)
    raw_est = aggregate_polls_kalman(polls, house_weights=hw, reference_date=reference_date,
                                     window_days=max(WINDOW_DAYS, (reference_date - ELECTION_2026).days + 1))
    proxy = Proxy.from_history(results, sorted(results))
    rd_others = BASELINE_OTHERS            # riksdagsestimatet är normaliserat mot 2026 års övriga
    shares = proxy_shares(raw_est, proxy, rd_others)
    days_left = max(0, (profile.election_date - reference_date).days)
    sd = total_sd(shares, party_spread(polls, reference_date), proxy, days_left)
    return EuForecast(
        reference_date=reference_date, seed=seed, profile=profile, raw_est=raw_est, shares=shares,
        proxy=proxy, sd=sd, seats=point_seats(shares, profile), sim=simulate(shares, sd, n_sims, seed, profile),
        days_left=days_left, latest_poll_date=polls["PublDate"].max().strftime("%Y-%m-%d"), rd_others=rd_others,
    )


def backtest(polls: pd.DataFrame, results: dict | None = None, lead_days: int = 1) -> list[dict]:
    """Prognos dagen före varje EU-val med bara dåvarande mätningar. Utan avvikelse (naiv proxy)
    mot med avvikelse enbart ur tidigare EU-val (2019 har inget tidigare val, så där är de lika)."""
    results = results or load_eu_results()
    rows = []
    for year in sorted(results):
        ref = EU_ELECTION_DATES[year] - timedelta(days=lead_days)
        known = polls[polls["PublDate"] <= ref + timedelta(days=1)]
        raw = aggregate_polls_kalman(known, house_weights=compute_house_weights(known), reference_date=ref,
                                     window_days=WINDOW_DAYS)
        prior = [y for y in sorted(results) if y < year]
        rd_others = 100.0 - sum(RD_BEFORE[year][p] for p in PARTIES)
        official = eu_shares(results[year])
        naive = proxy_shares(raw, Proxy.from_history(results, [], others_fallback=rd_others), rd_others)
        adjusted = proxy_shares(raw, Proxy.from_history(results, prior), rd_others)
        seats_of = {p["party"]: p["seats"] for p in results[year]["parties"] if p["party"] in PARTIES}
        mae = lambda s: float(np.mean([abs(s[p] - official[p]) for p in PARTIES]))
        sn, sa = point_seats(naive), point_seats(adjusted)
        rows.append({
            "year": int(year), "referenceDate": ref.date().isoformat(),
            "official": {p: official[p] for p in PARTIES}, "naive": {p: naive[p] for p in PARTIES},
            "adjusted": {p: adjusted[p] for p in PARTIES},
            "maeNaive": mae(naive), "maeAdjusted": mae(adjusted),
            "seatsOfficial": {p: seats_of.get(p, 0) for p in PARTIES},
            "seatsNaive": sn, "seatsAdjusted": sa,
            "seatErrorNaive": sum(abs(sn[p] - seats_of.get(p, 0)) for p in PARTIES) // 2,
            "seatErrorAdjusted": sum(abs(sa[p] - seats_of.get(p, 0)) for p in PARTIES) // 2,
            "adjustedFrom": prior,
        })
    return rows
