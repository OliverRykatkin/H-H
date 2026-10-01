"""Kör modellen och publicerar en oföränderlig, kontrollsummerad release.

    python -m mandatorn_model.publish --out dist-data
    python -m mandatorn_model.publish --out s3://mandatorn-data --distribution-id E123
    python -m mandatorn_model.publish --out dist-data --supersedes <release-id>

Ordning: alla datafiler (innehållsadresserade, immutable) → releases/<id>/manifest.json
→ releases/index.json → latest/-alias → manifest.json (pekare, sist = atomärt byte).
Samma indata + referensdatum + seed + modellversion ger samma release-id.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
import tomllib
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from mandatorn_model import contracts as C
from mandatorn_model.backtest import backtest_house_weights, compute_backtesting
from mandatorn_model.constants import (
    BASELINE, BASELINE_ELECTION_DATE, BASELINE_YEAR, BLOC_PARTIES, CONSTITUENCIES, ELECTION_2022,
    LAN_TO_REGION_NAME, NATIONAL_2022, NEXT_ELECTION, PARTIES, PARTIES_WITH_OTHER, PARTY_NAMES,
    THRESHOLD, TREND_ELECTIONS, TREND_START,
)
from mandatorn_model.extensions import (
    area_intervals, institute_bias, seat_distribution, simulate_constituency_seats, trend_table,
)
from mandatorn_model.forecast import Forecast, build_forecast, reference_day
from mandatorn_model.margins import (
    compute_closest_fixed_seats, compute_constituency_margins, compute_national_margins,
)
from mandatorn_model.muni_mandates import allocate_area_mandates, load_structure_cached
from mandatorn_model.polls import parse_polls
from mandatorn_model.probabilities import coalition_summary, evaluate_questions
from mandatorn_model.regional import apply_uniform_swing, compute_national_swing, load_area_results
from mandatorn_model.seats import estimate_constituency_votes
from mandatorn_model.storage import ALIAS, Storage, storage_from_uri
from mandatorn_model.text import display_pct, verbal
from mandatorn_model.valnatt import _load_valnatt_2026, _valnatt_state, _valnatt_times
from mandatorn_model.seats import allocate_all_mandates
from mandatorn_model.quality import check_outputs, check_polls, load_acks

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).with_name("publish.toml")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
DECIMALS = 4
LICENSE = "CC BY-NC 4.0"
ATTRIBUTION = ("Källa: Mandatorn (mandatorn.se), CC BY-NC 4.0. Bygger på opinionsmätningar via "
               "SwedishPolls (CC0) och valresultat från Valmyndigheten.")
# Valdag och dagen före: dragningar sparas för alltid (D5).
ELECTION_DAYS = {d.isoformat() for e in (NEXT_ELECTION, BASELINE_ELECTION_DATE)
                 for d in (e.date(), (e - timedelta(days=1)).date())}
INPUT_FILES = [
    "data/election_2026.json", "data/muni_structure_2026.json", "data/muni_structure_2022.json",
    "data/valnatt_2026.csv.gz", "mandatorn_model/questions.toml", "mandatorn_model/publish.toml",
]


# ── Hjälpare ────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower().replace("ä", "a").replace("å", "a").replace("ö", "o"))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    out, dash = [], False
    for ch in t:
        if ch.isalnum():
            out.append(ch); dash = False
        elif not dash:
            out.append("-"); dash = True
    return "".join(out).strip("-")


def _round(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        r = round(obj, DECIMALS)
        return 0.0 if r == 0 else r
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def canonical_json(model: C.BaseModel) -> bytes:
    data = _round(model.model_dump(mode="json"))
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_csv(df: pd.DataFrame) -> bytes:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(DECIMALS)
    return df.to_csv(index=False, lineterminator="\n", float_format=f"%.{DECIMALS}g").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def model_version() -> str:
    import os

    if os.environ.get("MODEL_VERSION"):
        return os.environ["MODEL_VERSION"]
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "mandatorn_model", "data"],
                               cwd=REPO, capture_output=True, text=True).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except Exception:
        return "okänd"


def _f(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


# ── Artefakter ──────────────────────────────────────────────────────────────

class Release:
    def __init__(self):
        self.files: dict[str, tuple[bytes, str]] = {}  # logisk sökväg → (bytes, content-type)

    def json(self, path: str, model: C.BaseModel):
        self.files[path] = (canonical_json(model), "application/json")

    def csv(self, path: str, df: pd.DataFrame, columns: dict[str, str], title: str):
        self.files[path] = (canonical_csv(df[list(columns)]), "text/csv; charset=utf-8")
        schema = {
            "title": title, "license": LICENSE, "attribution": ATTRIBUTION,
            "columns": [{"name": k, "description": v, "type": str(df[k].dtype)} for k, v in columns.items()],
        }
        self.files[path.replace(".csv", ".schema.json")] = (
            json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), "application/json")

    def raw(self, path: str, data: bytes, content_type: str):
        self.files[path] = (data, content_type)


def _daily_band(ts: dict, days: list[pd.Timestamp], split: pd.Timestamp) -> tuple[list, list, list]:
    """Interpolera ett partis (sammanfogade) trend till dagliga p5/p50/p95.
    Före split används segmentet före valet, från split det efter."""
    d = pd.to_datetime(pd.Series(ts["eval_dates"])).values.astype("datetime64[ns]").astype("int64")
    y, s = np.asarray(ts["smooth_y"], float), np.asarray(ts["smooth_std"], float)
    brk = next((i for i in range(1, len(d)) if d[i] <= d[i - 1]), len(d))
    segs = [(d[:brk], y[:brk], s[:brk]), (d[brk:], y[brk:], s[brk:])]
    x = np.array([t.value for t in days])
    mid, sd = np.full(len(x), np.nan), np.full(len(x), np.nan)
    one_day = 86_400 * 10**9
    if brk == len(d):
        masks = [np.ones(len(x), bool)]
        segs = segs[:1]
    else:
        masks = [x < split.value, x >= split.value]
    for (dd, yy, ss), mask in zip(segs, masks):
        if len(dd) == 0:
            continue
        mask = mask & (x >= dd.min()) & (x <= dd.max() + one_day)
        mid[mask] = np.interp(x[mask], dd, yy)
        sd[mask] = np.interp(x[mask], dd, ss)
    return list(mid - 1.645 * sd), list(mid), list(mid + 1.645 * sd)


def build_release(polls: pd.DataFrame, fc: Forecast, cfg: dict) -> tuple[Release, dict]:
    R = Release()
    ref = fc.reference_date
    sim, raw_est, mandates = fc.sim, fc.raw_est, fc.mandates
    n = sim["n_sims"]
    od = cfg["open_data"]
    swing = compute_national_swing(raw_est, BASELINE)
    blocs_sim = {"Högerblocket": sim["bloc_h"], "Vänsterblocket": sim["bloc_v"]}
    stats: dict = {}

    # national.json
    baseline_o = max(0.0, 100.0 - sum(BASELINE[p] for p in PARTIES))
    estimates = [C.PartyEstimate(
        party=p, name=PARTY_NAMES.get(p, "Övriga"), share=fc.raw_est_with_other[p],
        baseline=BASELINE.get(p, baseline_o) if p != "O" else baseline_o,
        change=fc.raw_est_with_other[p] - (BASELINE.get(p) if p != "O" else baseline_o),
        sd=float(sim["total_std"][p]) if p in PARTIES else None,
        pAboveThreshold=float(sim["above_threshold"][p]) if p in PARTIES else None,
    ) for p in PARTIES_WITH_OTHER]
    blocs = [C.Bloc(name=b, parties=ps, seats=sum(mandates["total"].get(p, 0) for p in ps),
                    share=sum(raw_est[p] for p in ps), pMajority=float((blocs_sim[b] >= 175).mean()))
             for b, ps in BLOC_PARTIES.items()]
    trend_keys = {p: [p] for p in PARTIES} | dict(BLOC_PARTIES)
    trend = [C.TrendRow(name=PARTY_NAMES.get(r["key"], r["key"]), **r)
             for r in trend_table(fc.trend_timeseries, ref, trend_keys, BASELINE)
             if r["now"] is not None]
    R.json("national.json", C.National(
        referenceDate=ref.date().isoformat(), baselineYear=BASELINE_YEAR,
        nextElection=NEXT_ELECTION.date().isoformat(), daysLeft=fc.days_left,
        latestPoll=fc.latest_poll_date, estimates=estimates, seats=mandates["total"], blocs=blocs,
        largestParty=max(raw_est, key=raw_est.get),
        belowThreshold=[p for p in PARTIES if raw_est[p] < THRESHOLD], swing=swing, trend=trend,
    ))

    # timeseries.json + öppen CSV
    days = list(pd.date_range(TREND_START, ref, freq="D"))
    split = pd.Timestamp(BASELINE_ELECTION_DATE)
    series, ts_rows = {}, []
    for p in PARTIES_WITH_OTHER:
        if p in fc.trend_timeseries:
            lo, mid, hi = _daily_band(fc.trend_timeseries[p], days, split)
            series[p] = C.SeriesBand(p5=lo, p50=mid, p95=hi)
    for b, ps in BLOC_PARTIES.items():
        mids = np.array([series[p].p50 for p in ps], float)
        var = np.array([((np.array(series[p].p95) - np.array(series[p].p50)) / 1.645) ** 2 for p in ps])
        m, sd = mids.sum(axis=0), np.sqrt(var.sum(axis=0))
        series[b] = C.SeriesBand(p5=list(m - 1.645 * sd), p50=list(m), p95=list(m + 1.645 * sd))
    date_strs = [d.date().isoformat() for d in days]
    R.json("timeseries.json", C.Timeseries(
        dates=date_strs, series=series,
        elections=[{"date": d.date().isoformat(), "label": lbl} for d, lbl in TREND_ELECTIONS]))
    for key, band in series.items():
        for i, d in enumerate(date_strs):
            if not math.isnan(band.p50[i]):
                ts_rows.append({"datum": d, "parti": key, "p5": band.p5[i], "p50": band.p50[i], "p95": band.p95[i]})
    if od.get("timeseries"):
        R.csv("open/timeseries.csv", pd.DataFrame(ts_rows), {
            "datum": "Datum (YYYY-MM-DD)", "parti": "Partiförkortning (O = övriga) eller block",
            "p5": "5:e percentil av skattad röstandel (%), ±1,645·σ ur Kalman/RTS",
            "p50": "Skattad röstandel (%)", "p95": "95:e percentil av skattad röstandel (%)",
        }, "Mandatorn — opinionstrend per dag")

    # polls.json
    recent = polls.sort_values("PublDate", ascending=False, kind="stable").head(200)
    R.json("polls.json", C.Polls(polls=[C.Poll(
        published=r.PublDate.date().isoformat(),
        fieldFrom=None if pd.isna(r.collectPeriodFrom) else str(r.collectPeriodFrom)[:10],
        fieldTo=None if pd.isna(r.collectPeriodTo) else str(r.collectPeriodTo)[:10],
        institute=str(r.Company), n=None if pd.isna(r.n) else int(r.n),
        shares={p: _f(pd.to_numeric(getattr(r, p), errors="coerce")) for p in PARTIES},
    ) for r in recent.itertuples()]))

    # mandates.json
    R.json("mandates.json", C.Mandates(
        parties=[C.PartySeats(party=p, fixed=mandates["fixed_total"][p], adjustment=mandates["adjustment"].get(p, 0),
                              total=mandates["total"][p], baseline=fc.baseline_seats_total[p]) for p in PARTIES],
        constituencies=mandates["fixed"], baselineConstituencies=fc.baseline_seats))

    # simulation.json
    pm = sim["party_mandates"]
    hist = {b: {str(int(k)): int(v) for k, v in zip(*np.unique(a, return_counts=True))} for b, a in blocs_sim.items()}
    p_h, p_v = float((sim["bloc_h"] >= 175).mean()), float((sim["bloc_v"] >= 175).mean())
    R.json("simulation.json", C.Simulation(
        nSims=n, seed=fc.seed, horizonDays=fc.days_left,
        parties=[C.SeatDistribution(
            party=p, mean=float(pm[p].mean()), p5=int(np.percentile(pm[p], 5)), p25=int(np.percentile(pm[p], 25)),
            median=int(np.median(pm[p])), p75=int(np.percentile(pm[p], 75)), p95=int(np.percentile(pm[p], 95)),
            sdPolls=float(sim["party_std"][p]), sdHorizon=float(sim["horizon_std"][p]),
            sdTotal=float(sim["total_std"][p]), pAboveThreshold=float(sim["above_threshold"][p]),
        ) for p in PARTIES],
        blocs={"Högerblocket": {"pMajority": p_h}, "Vänsterblocket": {"pMajority": p_v},
               "Inget block": {"pMajority": max(0.0, 1.0 - p_h - p_v)}},
        blocHistogram=hist, coalitions=[C.Coalition(**c) for c in coalition_summary(sim)]))

    # probabilities.json
    R.json("probabilities.json", C.Probabilities(questions=[
        C.Probability(id=q["id"], text=q["text"], p=q["p"], label=verbal(q["p"]), display=display_pct(q["p"]))
        for q in evaluate_questions(sim)]))

    # Valkretsar (N1)
    cs = simulate_constituency_seats(sim)
    stats["constituency_sims"] = int(cs["fixed"].shape[0])
    vk_rows, mandat_rows = [], []
    for c, name in enumerate(cs["constituencies"]):
        cdata = CONSTITUENCIES[name]
        now = estimate_constituency_votes(raw_est, cdata)
        margins = compute_constituency_margins(raw_est, name)
        dist = {p: seat_distribution(cs["fixed"][:, c, j]) for j, p in enumerate(PARTIES)}
        R.json(f"valkrets/{slugify(name)}.json", C.Constituency(
            name=name, slug=slugify(name), seats=cdata["seats"], baseline={p: cdata.get(p, 0.0) for p in PARTIES},
            now=now, fixedNow=mandates["fixed"][name], fixedBaseline=fc.baseline_seats[name],
            seatDistribution=dist,
            margins=[C.SeatMargin(party=p, gainPp=_f(m.get("gain_pp")), losePp=_f(m.get("lose_pp")))
                     for p, m in margins.items()]))
        for j, p in enumerate(PARTIES):
            arr = cs["fixed"][:, c, j]
            vk_rows.append({"valkrets": name, "parti": p, "baslinje": cdata.get(p, 0.0), "prognos": now[p],
                            "fasta_mandat": mandates["fixed"][name][p], "fasta_mandat_baslinje": fc.baseline_seats[name][p],
                            "fasta_mandat_p5": int(np.percentile(arr, 5)), "fasta_mandat_p95": int(np.percentile(arr, 95))})
            for k, prob in dist[p].items():
                mandat_rows.append({"valkrets": name, "parti": p, "typ": "fasta", "mandat": int(k),
                                    "sannolikhet": prob, "forvantat": float(arr.mean())})
    for j, p in enumerate(PARTIES):
        arr = cs["total"][:, j]
        for k, prob in seat_distribution(arr).items():
            mandat_rows.append({"valkrets": "Riket", "parti": p, "typ": "totalt", "mandat": int(k),
                                "sannolikhet": prob, "forvantat": float(arr.mean())})
    if od.get("valkretsar"):
        R.csv("open/valkretsar.csv", pd.DataFrame(vk_rows), {
            "valkrets": "Riksdagsvalkrets", "parti": "Partiförkortning",
            "baslinje": f"Röstandel i valet {BASELINE_YEAR} (%)", "prognos": "Prognos om det vore val idag (%)",
            "fasta_mandat": "Fasta mandat, punktprognos", "fasta_mandat_baslinje": f"Fasta mandat {BASELINE_YEAR}",
            "fasta_mandat_p5": "5:e percentil fasta mandat (simulering)", "fasta_mandat_p95": "95:e percentil fasta mandat",
        }, "Mandatorn — prognos per riksdagsvalkrets")
    if od.get("mandat"):
        R.csv("open/mandat.csv", pd.DataFrame(mandat_rows), {
            "valkrets": "Valkrets, eller 'Riket' för totala mandat", "parti": "Partiförkortning",
            "typ": "'fasta' (valkretsmandat) eller 'totalt' (fasta + utjämning, riket)",
            "mandat": "Antal mandat", "sannolikhet": "Sannolikhet för exakt så många mandat",
            "forvantat": "Förväntat antal mandat (medel över simuleringarna)",
        }, "Mandatorn — sannolikhetsfördelning för mandat")

    # Kommuner och regioner (N5)
    struct = load_structure_cached() or {}
    area_cfg = {"RD": "riksdag", "KF": "kommunval", "RF": "regionval"}
    area_data = {}
    for vt in area_cfg:
        base_df, ovr = load_area_results(vt)
        pred = apply_uniform_swing(base_df, raw_est, BASELINE, ovriga_per_area=ovr)
        iv = area_intervals(base_df, sim, ovr)
        area_data[vt] = (base_df, pred, iv, ovr)

    def shares(vt, code) -> C.AreaShares | None:
        base_df, pred, iv, ovr = area_data[vt]
        b = base_df[base_df.region_code == code]
        if b.empty:
            return None
        pr = pred[pred.region_code == code].set_index("party")["pct_predicted"]
        ivc = iv[iv.region_code == code].set_index("party")
        return C.AreaShares(baseline=dict(zip(b.party, b.pct_base)), now=pr.to_dict(),
                            p5=ivc["p5"].to_dict(), p95=ivc["p95"].to_dict(), others=ovr.get(code, 0.0))

    def seats(vt, kod) -> C.AreaSeats | None:
        area = struct.get(vt, {}).get(kod)
        if area is None:
            return None
        res = allocate_area_mandates(area, swing)
        meta = res["party_meta"]
        return C.AreaSeats(totalSeats=res["total_seats"], threshold=res["threshold_pct"], nAdjustment=res["n_utjamning"],
                           now={p: int(v) for p, v in res["total"].items() if v},
                           baseline={p: int(v) for p, v in res["seats_2022"].items() if v},
                           names={p: meta.get(p, {}).get("namn", p) for p in res["parties"]},
                           stage=struct.get("stage", {}).get(f"{vt}_{kod}", ""))

    k_rows, r_rows = [], []
    for kod, area in sorted(struct.get("KF", {}).items()):
        name = area["namn"]
        rd, kf = shares("RD", kod), shares("KF", kod)
        R.json(f"kommun/{kod}.json", C.Area(kind="kommun", code=kod, name=name, slug=slugify(name),
                                            riksdag=rd, kommunval=kf, kommunSeats=seats("KF", kod)))
        for label, sh in (("riksdag", rd), ("kommunval", kf)):
            if sh:
                k_rows += [{"kommunkod": kod, "kommun": name, "val": label, "parti": p, "baslinje": sh.baseline.get(p),
                            "prognos": sh.now.get(p), "p5": sh.p5.get(p), "p95": sh.p95.get(p)} for p in PARTIES]
    for lan, region in sorted(LAN_TO_REGION_NAME.items()):
        sh = shares("RF", region)
        R.json(f"region/{lan}.json", C.Area(kind="region", code=lan, name=region, slug=slugify(region),
                                            regionval=sh, regionSeats=seats("RF", lan)))
        if sh:
            r_rows += [{"lankod": lan, "region": region, "val": "regionval", "parti": p, "baslinje": sh.baseline.get(p),
                        "prognos": sh.now.get(p), "p5": sh.p5.get(p), "p95": sh.p95.get(p)} for p in PARTIES]
    area_cols = {"val": "riksdag, kommunval eller regionval", "parti": "Partiförkortning",
                 "baslinje": f"Röstandel i valet {BASELINE_YEAR} (%)", "prognos": "Prognos, uniform swing (%)",
                 "p5": "5:e percentil (simulering)", "p95": "95:e percentil (simulering)"}
    if od.get("kommuner"):
        R.csv("open/kommuner.csv", pd.DataFrame(k_rows), {"kommunkod": "Kommunkod (SCB)", "kommun": "Kommun", **area_cols},
              "Mandatorn — prognos per kommun")
    if od.get("regioner"):
        R.csv("open/regioner.csv", pd.DataFrame(r_rows), {"lankod": "Länskod", "region": "Region", **area_cols},
              "Mandatorn — prognos per region")

    # margins.json
    nat = compute_national_margins(raw_est)
    R.json("margins.json", C.Margins(
        national={p: {"seats": m["seats"], "gainPp": _f(m["gain_pp"]), "losePp": _f(m["lose_pp"])} for p, m in nat.items()},
        closest=[{"constituency": r["Valkrets"], "seats": r["seats"], "challenger": r["challenger"],
                  "loser": r["loser"], "marginPp": _f(r["margin_pp"])} for r in compute_closest_fixed_seats(raw_est)]))

    # backtest/<år>.json
    for year, edate, actual in ((BASELINE_YEAR, BASELINE_ELECTION_DATE, BASELINE), (2022, ELECTION_2022, NATIONAL_2022)):
        bt = compute_backtesting(polls, backtest_house_weights(polls, year), election_date=edate, actual=actual)
        R.json(f"backtest/{year}.json", C.Backtest(year=year, rows=[
            {"date": r["Referensdatum"], "daysBefore": int(r["Dagar till val"]), "party": r["Parti"],
             "estimate": float(r["Estimat (%)"]), "actual": float(r["Faktiskt (%)"]), "error": float(r["Fel (pp)"])}
            for r in bt.to_dict("records")]))

    # institutes.json + institutsbias.csv (N4)
    bias = institute_bias(polls, fc.trend_timeseries, TREND_START, ref)
    weights = fc.house_weights.rename(columns=lambda c: {"Institut": "institute", "MAE (pp)": "mae", "Vikt": "weight"}.get(c, "n" if c.startswith("Antal mätningar") else c))
    R.json("institutes.json", C.Institutes(weights=weights.to_dict("records"), bias=bias.to_dict("records")))
    if od.get("institutsbias"):
        R.csv("open/institutsbias.csv", bias, {
            "institute": "Opinionsinstitut", "party": "Partiförkortning", "n": "Antal mätningar",
            "share_over": "Andel mätningar över trenden", "share_under": "Andel mätningar under trenden",
            "mean_dev_pp": "Medelavvikelse mot trenden (pp)", "median_dev_pp": "Medianavvikelse (pp)",
            "mean_dev_rel": "Medelavvikelse i andel av partiets storlek", "median_dev_rel": "Medianavvikelse, relativ",
        }, f"Mandatorn — husbias per institut och parti ({TREND_START:%Y-%m-%d}–{ref:%Y-%m-%d})")

    # valnatt/2026/*.json
    vdf = _load_valnatt_2026()
    if vdf is not None:
        times, curve = [], []
        for t in _valnatt_times():
            s = _valnatt_state(vdf, t)
            hhmm = t.strftime("%H%M")
            seats_t = allocate_all_mandates({p: s["nowcast"][p] * 100 for p in PARTIES})["total"]
            R.json(f"valnatt/2026/{hhmm}.json", C.ValnattState(
                year=2026, time=t.isoformat(), nCounted=s["n_counted"], nTotal=s["n_total"],
                voteShareCounted=s["vote_share_counted"], raw=s["raw"] if s["n_counted"] else None,
                nowcast={p: s["nowcast"][p] for p in PARTIES}, final=s["final"],
                maeRaw=_f(s["mae_raw"]), maeNowcast=s["mae_nowcast"], seats=seats_t))
            times.append(hhmm)
            curve.append({"time": t.isoformat(), "raw": _f(s["mae_raw"]), "nowcast": s["mae_nowcast"]})
        R.json("valnatt/2026/index.json", C.ValnattIndex(year=2026, times=times, curve=curve))

    # draws.parquet
    if cfg["draws"]["enabled"] and od.get("draws"):
        k = min(cfg["draws"]["sample"], n)
        cols = {"draw": np.arange(k, dtype=np.int32)}
        for p in PARTIES:
            cols[p] = np.round(sim["draws"][p][:k], 4).astype(np.float32)
        for j, p in enumerate(PARTIES):
            cols[f"seats_{p}"] = cs["total"][:k, j].astype(np.int16)
        R.raw("open/draws.parquet", _parquet(cols), "application/vnd.apache.parquet")

    R.raw("open/README.md", _open_readme(od).encode("utf-8"), "text/markdown; charset=utf-8")
    return R, stats


def _parquet(cols: dict) -> bytes:
    import polars as pl

    buf = io.BytesIO()
    pl.DataFrame(cols).write_parquet(buf, compression="zstd", statistics=False)
    return buf.getvalue()


def _open_readme(od: dict) -> str:
    files = [f"- `{k}.csv` (+ `.schema.json`)" for k in
             ("timeseries", "institutsbias", "kommuner", "regioner", "valkretsar", "mandat", "kandidater") if od.get(k)]
    if od.get("draws"):
        files.append("- `draws.parquet` — urval av simuleringsdragningar (andelar + mandat)")
    return (
        "# Mandatorn — öppen data\n\n"
        f"Licens: **{LICENSE}** (https://creativecommons.org/licenses/by-nc/4.0/deed.sv). "
        "Kommersiell licens för medier och företag: se https://mandatorn.se/licens.\n\n"
        f"Ange källa: *{ATTRIBUTION}*\n\n"
        "Filerna finns på stabila adresser under `latest/` och i varje release under "
        "`releases/<id>/` (se manifestet).\n\n" + "\n".join(files) + "\n"
    )


# ── Publicering ─────────────────────────────────────────────────────────────

def _normalized(data: bytes, rel: str) -> bytes:
    """Radslut normaliseras för textfiler, så att hashen är densamma på Windows och Linux."""
    return data if rel.endswith(".gz") else data.replace(b"\r\n", b"\n")


def input_hash(polls_bytes: bytes, reference_date: datetime, seed: int, n_sims: int) -> str:
    h = hashlib.sha256()
    h.update(b"polls\0" + _normalized(polls_bytes, "polls.csv"))
    for rel in INPUT_FILES:
        p = REPO / rel
        h.update(rel.encode() + b"\0" + (_normalized(p.read_bytes(), rel) if p.exists() else b""))
    h.update(f"{reference_date.isoformat()}|{seed}|{n_sims}".encode())
    return h.hexdigest()


def assemble(release: Release, meta: dict) -> tuple[C.Manifest, dict[str, tuple[bytes, str, str]]]:
    """→ (manifest, {objektnyckel: (bytes, content-type, logisk sökväg)})."""
    objects, entries = {}, []
    for path in sorted(release.files):
        data, ctype = release.files[path]
        digest = sha256(data)
        ext = Path(path).suffix or ".bin"
        key = f"files/{digest}{ext}"
        objects[key] = (data, ctype, path)
        entries.append(C.FileEntry(path=path, object=key, size=len(data), sha256=digest))
    index = json.dumps([[e.path, e.sha256] for e in entries], separators=(",", ":")).encode()
    release_id = sha256(index)
    manifest = C.Manifest(release=release_id, files=entries, **meta)
    return manifest, objects


def write(storage: Storage, manifest: C.Manifest, objects: dict, cfg: dict, supersedes: str | None = None,
          run_at: str | None = None) -> dict:
    written = 0
    for k, (d, ct, path) in objects.items():
        # Dragningar gallras av en livscykelregel på taggen (D5); dygnets första
        # och valdagens dragningar sparas dessutom under egna prefix utan tagg.
        tags = {"retention": "draws"} if path == "open/draws.parquet" else None
        written += storage.put_immutable(k, d, ct, tags=tags)
        if path == "open/draws.parquet":
            day = manifest.generatedAt[:10]
            storage.put_immutable(f"draws-daily/{day}/draws.parquet", d, ct)
            if day in ELECTION_DAYS:
                storage.put_immutable(f"draws-election/{day}/draws.parquet", d, ct)
    rid = manifest.release
    mbytes = canonical_json(manifest)
    storage.put_pointer(f"releases/{rid}/manifest.json", mbytes, "application/json")

    idx_raw = storage.get("releases/index.json")
    idx = C.ReleaseIndex.model_validate_json(idx_raw) if idx_raw else C.ReleaseIndex(releases=[])
    entries = {e.release: e for e in idx.releases}
    entries[rid] = C.ReleaseIndexEntry(release=rid, generatedAt=manifest.generatedAt, mode=manifest.mode,
                                       supersededBy=entries.get(rid).supersededBy if rid in entries else None)
    if supersedes and supersedes != rid:
        old_raw = storage.get(f"releases/{supersedes}/manifest.json")
        if old_raw is None:
            raise SystemExit(f"Releasen {supersedes} finns inte")
        old = C.Manifest.model_validate_json(old_raw)
        old.supersededBy = rid
        storage.put_pointer(f"releases/{supersedes}/manifest.json", canonical_json(old), "application/json")
        if supersedes in entries:
            entries[supersedes].supersededBy = rid
    idx.releases = sorted(entries.values(), key=lambda e: (e.generatedAt, e.release))
    storage.put_pointer("releases/index.json", canonical_json(idx), "application/json")

    for key, (data, ctype, path) in objects.items():
        if path.startswith("open/"):
            storage.put_pointer("latest/" + path[len("open/"):], data, ctype, cache_control=ALIAS)

    storage.put_pointer("manifest.json", mbytes, "application/json")  # sist: atomärt byte
    status = {"release": rid, "generatedAt": manifest.generatedAt, "mode": manifest.mode,
              "runAt": run_at or datetime.now(STOCKHOLM).isoformat(timespec="seconds"),
              "modelVersion": manifest.modelVersion}
    storage.put_pointer("status.json", json.dumps(status, ensure_ascii=False, sort_keys=True).encode(), "application/json")
    storage.invalidate(["manifest.json", "releases/index.json", "status.json", "latest/*"])
    return {"release": rid, "objects": len(objects), "written": int(written)}


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def run(out: str, reference_date: datetime | None = None, seed: int | None = None, n_sims: int | None = None,
        supersedes: str | None = None, force: bool = False, distribution_id: str | None = None,
        polls_path: str | None = None, report_path: str | None = None) -> dict:
    cfg = load_config()
    seed = cfg["model"]["seed"] if seed is None else seed
    n_sims = cfg["model"]["n_sims"] if n_sims is None else n_sims
    ref = reference_day(reference_date or datetime.now(STOCKHOLM).replace(tzinfo=None))
    polls_bytes = (REPO / (polls_path or cfg["inputs"]["polls"])).read_bytes()
    polls = parse_polls(polls_bytes.decode("utf-8"))
    polls = polls[polls["PublDate"] <= ref + timedelta(days=1)]

    fc = build_forecast(polls, ref, seed=seed, n_sims=n_sims)
    report = check_outputs(fc, check_polls(polls, ref, cfg["quality"], aggregate=fc.raw_est)).apply_acks(load_acks())
    if report_path:
        Path(report_path).write_text(report.to_markdown(), encoding="utf-8")
    if not report.ok and not force:
        print(report.to_markdown(), file=sys.stderr)
        return {"published": False, "report": report}

    release, stats = build_release(polls, fc, cfg)
    field_end = pd.to_datetime(polls["collectPeriodTo"], errors="coerce").max()
    meta = dict(
        generatedAt=ref.isoformat(), modelVersion=model_version(), seed=seed,
        inputHash=input_hash(polls_bytes, ref, seed, n_sims), mode=cfg["model"]["mode"],
        pollsIncluded=C.PollsIncluded(count=int(len(polls)),
                                      latestFieldEnd=None if pd.isna(field_end) else field_end.date().isoformat(),
                                      latestPublished=fc.latest_poll_date),
    )
    manifest, objects = assemble(release, meta)
    size = len(canonical_json(manifest))
    if size > 100_000:
        raise SystemExit(f"Manifestet är {size} byte (> 100 kB)")
    result = write(storage_from_uri(out, distribution_id), manifest, objects, cfg, supersedes=supersedes)
    return {"published": True, "report": report, "manifest_bytes": size, **stats, **result}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="dist-data", help="Katalog eller s3://bucket")
    ap.add_argument("--reference-date", help="YYYY-MM-DD (standard: i dag, Europe/Stockholm)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n-sims", type=int)
    ap.add_argument("--polls", help="Sökväg till Polls.csv (standard enligt publish.toml)")
    ap.add_argument("--supersedes", help="Release-id som den nya releasen rättar")
    ap.add_argument("--distribution-id", help="CloudFront-distribution att invalidera")
    ap.add_argument("--force", action="store_true", help="Publicera trots flaggor i kvalitetsgrinden")
    ap.add_argument("--report", help="Skriv kvalitetsrapport (markdown) hit")
    a = ap.parse_args(argv)
    ref = datetime.fromisoformat(a.reference_date) if a.reference_date else None
    res = run(a.out, ref, a.seed, a.n_sims, a.supersedes, a.force, a.distribution_id, a.polls, a.report)
    if not res["published"]:
        print("Ej publicerat: kvalitetsgrinden flaggade körningen.", file=sys.stderr)
        return 2
    print(f"Release {res['release']}  ({res['objects']} filer, {res['written']} nya, "
          f"manifest {res['manifest_bytes']} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
