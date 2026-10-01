"""Rekonstruera prognosens utveckling fram till ett val (DECISIONS D12) → data/archive_<år>.json.

    python tools/build_archive.py 2026

För varje dag det sista året före valet körs Kalman-aggregeringen och simuleringen med
dagens modellkod, men bara på mätningar publicerade t.o.m. den dagen och med horisonten
räknad mot valdagen. Mandat redovisas bara nationellt (landets fördelning): valkrets-
modellen utgår från valresultatet själv och skulle läcka facit in i en prognos före valet.
Filen märks som rekonstruerad med modellversion (git-commit).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from mandatorn_model.constants import (  # noqa: E402
    BASELINE, ELECTION_2026, PARTIES, SEATS_NATIONAL_2026, TOTAL_SEATS,
)
from mandatorn_model.kalman import aggregate_polls_kalman  # noqa: E402
from mandatorn_model.polls import parse_polls  # noqa: E402
from mandatorn_model.simulation import run_simulation  # noqa: E402

ELECTIONS = {2026: (ELECTION_2026, BASELINE, {p: v["total"] for p, v in SEATS_NATIONAL_2026.items()})}
N_SIMS = 10_000
SEED = 42


def main(year: int) -> int:
    election, result, seats_result = ELECTIONS[year]
    polls = parse_polls((REPO / "data" / "polls" / "Polls.csv").read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    days = []
    for back in range(365, 0, -1):
        ref = election - timedelta(days=back)
        avail = polls[polls["PublDate"] <= ref]
        # Vikterna kalibreras mot valet innan (som backtesten, D19) — aldrig mot facit.
        from mandatorn_model.backtest import backtest_house_weights

        hw = backtest_house_weights(avail, year)
        est = aggregate_polls_kalman(avail, house_weights=hw, reference_date=ref, window_days=365)
        sim = run_simulation(est, avail, 365, n_sims=N_SIMS, horizon_days=back, reference_date=ref, seed=SEED)
        pm = sim["party_mandates"]
        days.append({
            "date": ref.date().isoformat(),
            "daysLeft": back,
            "shares": {p: round(est[p], 3) for p in PARTIES},
            "seatsMedian": {p: int(np.median(pm[p])) for p in PARTIES},
            "pThreshold": {p: round(sim["above_threshold"][p], 4) for p in PARTIES},
            "pMajority": {"Högerblocket": round(float((sim["bloc_h"] >= 175).mean()), 4),
                          "Vänsterblocket": round(float((sim["bloc_v"] >= 175).mean()), 4)},
        })
        if back % 30 == 0:
            print(ref.date(), {p: round(est[p], 1) for p in PARTIES}, flush=True)
    out = {
        "year": year, "electionDate": election.date().isoformat(), "reconstructed": True,
        "modelVersion": commit, "nSims": N_SIMS, "seed": SEED, "totalSeats": TOTAL_SEATS,
        "note": ("Rekonstruerad i efterhand med dagens modellkod och mätningar publicerade fram till respektive "
                 "dag. Mandat i landet (ingen valkretsmodell, för att inte läcka valresultatet)."),
        "result": {"shares": {p: result[p] for p in PARTIES}, "seats": seats_result},
        "days": days,
    }
    path = REPO / "data" / f"archive_{year}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(days)} dagar → {path.relative_to(REPO)} ({path.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2026))
