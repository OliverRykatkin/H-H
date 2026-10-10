"""Publicerar EU-valsprognosen som en egen release-kedja under prefixet `eu2029/`.

    python -m mandatorn_model.eu_publish --out dist-data

Samma manifestformat, innehållsadresserade filer och atomära pekarbyte som riksdagens
release (publish.py), men helt separata nycklar: riksdagens manifest.json rörs inte.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from mandatorn_model import contracts as C
from mandatorn_model import eu_forecast as F
from mandatorn_model.constants import PARTIES, PARTY_NAMES
from mandatorn_model.election import EU2029
from mandatorn_model.forecast import reference_day
from mandatorn_model.polls import parse_polls
from mandatorn_model.publish import (
    REPO, STOCKHOLM, Release, _normalized, assemble, load_config, model_version, write,
)
from mandatorn_model.quality import check_polls, load_acks
from mandatorn_model.storage import PrefixedStorage, storage_from_uri

INPUT_FILES = ["data/eu_results.json", "data/election_2026.json", "mandatorn_model/publish.toml"]
CAVEAT = ("Det finns inga EU-mätningar. Prognosen är därför mer osäker än riksdagsprognosen: "
          "EU-valet har lägre valdeltagande och andra väljarmönster (särskilt MP, V och småpartier).")
BACKTEST_NOTE = ("Prognos dagen före valet med dåvarande riksdagsmätningar. 2019 har inget tidigare EU-val att "
                 "hämta avvikelse ur, så där är de två varianterna lika. Två val räcker inte för att utvärdera "
                 "avvikelsemodellen statistiskt.")


def _dist(arr: np.ndarray) -> dict:
    vals, counts = np.unique(arr, return_counts=True)
    return {str(int(v)): int(c) for v, c in zip(vals, counts)}


def build_release(fc: F.EuForecast, backtest: list[dict]) -> Release:
    R = Release()
    last = F.load_eu_results()["2024"]
    last_share = F.eu_shares(last)
    last_seats = {p["party"]: p["seats"] for p in last["parties"]}
    scale = (100.0 - fc.rd_others) / 100.0
    estimates = []
    for p in PARTIES + ["O"]:
        is_party = p != "O"
        estimates.append(C.EuPartyEstimate(
            party=p, name=PARTY_NAMES[p], share=fc.shares[p], lastElection=last_share[p],
            change=fc.shares[p] - last_share[p],
            rdEquivalent=fc.raw_est[p] * scale if is_party else None,
            deviation=fc.proxy.shift[p] if is_party else None,
            sd=fc.sd[p]["total"] if is_party else None,
            pAboveThreshold=fc.sim["above_threshold"][p] if is_party else None,
            pLargest=fc.sim["p_largest"][p] if is_party else None,
            seats=fc.seats[p] if is_party else 0, seatsLast=last_seats.get(p, 0) if is_party else None,
        ))
    R.json("national.json", C.EuNational(
        election=fc.profile.key, electionDate=fc.profile.election_date.date().isoformat(),
        electionDateProvisional=True, seatsTotal=fc.profile.seats, threshold=fc.profile.threshold,
        referenceDate=fc.reference_date.date().isoformat(), daysLeft=fc.days_left,
        latestPoll=fc.latest_poll_date, estimates=estimates, seats=fc.seats,
        belowThreshold=[p for p in PARTIES if fc.shares[p] < fc.profile.threshold * 100],
        largestParty=max(PARTIES, key=lambda p: fc.shares[p]),
        method=C.EuMethod(
            proxy=("Riksdagsmätningarna aggregeras med Kalman-filter (som i riksdagsprognosen) och omräknas "
                   "till andel av alla giltiga röster. Partiets genomsnittliga avvikelse mellan EU-valet och "
                   "närmast föregående riksdagsval (2019 mot 2018, 2024 mot 2022) läggs på, krympt till "
                   f"{fc.proxy.shrink:.0%}. Avvikelsernas spridning mellan valen ingår i osäkerheten."),
            shrink=fc.proxy.shrink, deviationYears=[int(y) for y in fc.proxy.years], caveat=CAVEAT),
    ))
    parties = []
    for p in PARTIES:
        a = fc.sim["seats"][p]
        q = np.percentile(a, [5, 25, 50, 75, 95])
        parties.append(C.EuSeatDistribution(party=p, mean=float(a.mean()), p5=int(q[0]), p25=int(q[1]),
                                            median=int(q[2]), p75=int(q[3]), p95=int(q[4]), histogram=_dist(a)))
    R.json("simulation.json", C.EuSimulation(
        nSims=fc.sim["n_sims"], seed=fc.seed, horizonDays=fc.days_left, parties=parties))
    R.json("backtest.json", C.EuBacktest(
        note=BACKTEST_NOTE, years=[C.EuBacktestYear(**{**r, "adjustedFrom": [int(y) for y in r["adjustedFrom"]]})
                                   for r in backtest]))
    return R


def input_hash(polls_bytes: bytes, reference_date: datetime, seed: int, n_sims: int) -> str:
    h = hashlib.sha256()
    h.update(b"polls\0" + _normalized(polls_bytes, "polls.csv"))
    for rel in INPUT_FILES:
        p = REPO / rel
        h.update(rel.encode() + b"\0" + (_normalized(p.read_bytes(), rel) if p.exists() else b""))
    h.update(f"eu2029|{reference_date.isoformat()}|{seed}|{n_sims}".encode())
    return h.hexdigest()


def run(out: str, reference_date: datetime | None = None, seed: int | None = None, n_sims: int | None = None,
        force: bool = False, distribution_id: str | None = None, polls_path: str | None = None) -> dict:
    cfg = load_config()
    seed = cfg["model"]["seed"] if seed is None else seed
    n_sims = cfg["model"]["n_sims"] if n_sims is None else n_sims
    ref = reference_day(reference_date or datetime.now(STOCKHOLM).replace(tzinfo=None))
    polls_bytes = (REPO / (polls_path or cfg["inputs"]["polls"])).read_bytes()
    polls = parse_polls(polls_bytes.decode("utf-8"))
    polls = polls[polls["PublDate"] <= ref + timedelta(days=1)]

    fc = F.build_eu_forecast(polls, ref, seed=seed, n_sims=n_sims)
    report = check_polls(polls, ref, cfg["quality"], aggregate=fc.raw_est).apply_acks(load_acks())
    if sum(fc.seats.values()) != EU2029.seats:
        report.add("output:seats", f"Punktprognosen ger {sum(fc.seats.values())} mandat (ska vara {EU2029.seats})")
    if not report.ok and not force:
        print(report.to_markdown(), file=sys.stderr)
        return {"published": False, "report": report}

    release = build_release(fc, F.backtest(polls))
    field_end = pd.to_datetime(polls["collectPeriodTo"], errors="coerce").max()
    meta = dict(
        generatedAt=ref.isoformat(), modelVersion=model_version(), seed=seed,
        inputHash=input_hash(polls_bytes, ref, seed, n_sims), mode="forecast",
        pollsIncluded=C.PollsIncluded(count=int(len(polls)),
                                      latestFieldEnd=None if pd.isna(field_end) else field_end.date().isoformat(),
                                      latestPublished=fc.latest_poll_date),
    )
    manifest, objects = assemble(release, meta)
    storage = PrefixedStorage(storage_from_uri(out, distribution_id), EU2029.release_prefix)
    return {"published": True, "report": report, **write(storage, manifest, objects, cfg)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="dist-data", help="Katalog eller s3://bucket")
    ap.add_argument("--reference-date", help="YYYY-MM-DD (standard: i dag, Europe/Stockholm)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n-sims", type=int)
    ap.add_argument("--polls")
    ap.add_argument("--distribution-id")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    ref = datetime.fromisoformat(a.reference_date) if a.reference_date else None
    res = run(a.out, ref, a.seed, a.n_sims, a.force, a.distribution_id, a.polls)
    if not res["published"]:
        print("Ej publicerat: kvalitetsgrinden flaggade körningen.", file=sys.stderr)
        return 2
    print(f"EU-release {res['release']}  ({res['objects']} filer, {res['written']} nya)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
