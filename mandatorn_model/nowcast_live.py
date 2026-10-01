"""Live-nowcast på valnatten (fas 3): hämta Valmyndighetens preliminära räkning,
räkna nowcast och mandat, publicera en release med mode "nowcast".

    python -m mandatorn_model.nowcast_live --out s3://<data-bucket> --year 2030
    python -m mandatorn_model.nowcast_live --out dist-data --replay 2026 --step-minutes 10   # simulator

Varje nowcast-release bygger vidare på senaste prognosreleasen (samma filer + nowcast.json),
så att sajtens övriga sidor fungerar hela natten. Ingen fördröjning för publiken (D4).
Om Valmyndigheten inte svarar ligger senaste giltiga release kvar och status.json visar felet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from mandatorn_model import contracts as C
from mandatorn_model.constants import BLOC_PARTIES, PARTIES
from mandatorn_model.nowcast import compute_nowcast
from mandatorn_model.seats import allocate_all_mandates
from mandatorn_model.storage import Storage, storage_from_uri

REPO = Path(__file__).resolve().parents[1]
STOCKHOLM = ZoneInfo("Europe/Stockholm")
VOTE_COLS = [f"votes_{p}" for p in PARTIES]
COLS = ["district_id", "total_valid_votes"] + VOTE_COLS


@dataclass
class Snapshot:
    """Läget i räkningen vid ett tillfälle, i compute_nowcast-schemat."""
    counted: pd.DataFrame            # alla räknade ordinarie distrikt (för råräkningen)
    baseline: pd.DataFrame           # baslinjevalet, alignat till nuvarande district_id (jämförbara)
    n_total: int                     # antal ordinarie distrikt som ska räknas
    updated_at: str | None           # Valmyndighetens senasteUppdateringstid
    fingerprint: str                 # ändras när datan ändras (md5 eller simulerad tid)
    final: dict[str, float] | None = None   # slutresultat (bara simulatorn)
    meta: dict = field(default_factory=dict)


class Source(Protocol):
    def fetch(self) -> Snapshot | None: ...


# ── Baslinje: förra valets distrikt mappade till nuvarande indelning ─────────

def align_baseline(districts: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """districts: nuvarande distrikt med prev_codes ("|"-separerade koder i förra valet).
    baseline: förra valets slutresultat per distrikt (district_code, total_valid_votes, votes_P).

    Ett nytt distrikt får summan av sina föregångare. Har ett gammalt distrikt delats på
    flera nya fördelas dess röster lika mellan dem. Distrikt utan (kända) föregångare saknas
    i resultatet och ingår därför inte i deltaberäkningen.
    """
    base = baseline.assign(district_code=baseline["district_code"].astype(str).str.zfill(8)).set_index("district_code")
    refs: dict[str, int] = {}
    links = []
    for row in districts.itertuples():
        codes = [c.zfill(8) for c in str(getattr(row, "prev_codes", "") or "").split("|") if c]
        if codes and all(c in base.index for c in codes):
            links.append((row.district_id, codes))
            for c in codes:
                refs[c] = refs.get(c, 0) + 1
    rows = []
    for did, codes in links:
        vals = sum(base.loc[c, ["total_valid_votes"] + VOTE_COLS].astype(float) / refs[c] for c in codes)
        rows.append({"district_id": int(did), **{k: float(v) for k, v in vals.items()}})
    return pd.DataFrame(rows, columns=COLS)


# ── Källor ──────────────────────────────────────────────────────────────────

class ValmyndighetenSource:
    """Hämtar den preliminära RD-filen när index.md5 visar en ny version."""

    def __init__(self, year: int, baseline_path: Path):
        self.year = year
        self.baseline = pd.read_csv(baseline_path, dtype={"district_code": str})
        self._aligned_for: str | None = None
        self._aligned: pd.DataFrame | None = None

    def fetch(self) -> Snapshot | None:
        from mandatorn_model import val_feed as vf

        idx = vf.fetch_index(self.year)
        try:
            rel, md5 = vf.find_rd_file(idx, preliminary=True)
        except LookupError:
            return None  # inga resultat publicerade ännu
        res = vf.parse_rd_zip(vf.download_file(self.year, rel, expected_md5=md5))
        if res.districts.empty:
            return None
        key = hashlib.sha256(res.districts["prev_codes"].str.cat(sep=";").encode()).hexdigest()
        if key != self._aligned_for:  # distriktsindelningen ändras inte under natten
            self._aligned = align_baseline(res.districts, self.baseline)
            self._aligned_for = key
        return Snapshot(counted=res.counted()[COLS], baseline=self._aligned, n_total=int((res.districts.shape[0])),
                        updated_at=res.updated_at, fingerprint=md5, meta={"stage": res.stage, "file": rel})


class ReplaySource:
    """Simulator: spelar upp en sparad valnatt i verklig rapporteringsordning.

    year=2026: data/valnatt_2026.csv.gz (baslinje 2022 ur Valmyndighetens jämförelse).
    year=2022: data/valnatt_2022.csv.gz + 2018 års distrikt (data_loader; laddas ner vid behov).
    """

    def __init__(self, year: int, start: datetime, step: timedelta, end: datetime | None = None):
        df = pd.read_csv(REPO / "data" / f"valnatt_{year}.csv.gz")
        df["reported_at"] = pd.to_datetime(df["reported_at"])
        self.df = df
        if year == 2026:
            cmp = df[df["comparable"]]
            self.baseline = cmp[["district_id", "base_total_valid_votes"] + [f"base_{c}" for c in VOTE_COLS]].copy()
            self.baseline.columns = COLS
            from mandatorn_model.constants import BASELINE
            self.final = {p: BASELINE[p] / 100 for p in PARTIES}
        elif year == 2022:
            from mandatorn_model.constants import NATIONAL_2022
            from mandatorn_model.data_loader import load_2018_districts
            b = load_2018_districts()
            self.baseline = b[b["district_id"].isin(set(df["district_id"]))][COLS].copy()
            self.final = {p: NATIONAL_2022[p] / 100 for p in PARTIES}
        else:
            raise ValueError(f"Ingen sparad valnatt för {year}")
        self.year, self.t, self.step = year, start, step
        self.end = end or df["reported_at"].max().to_pydatetime()

    @property
    def done(self) -> bool:
        return self.t > self.end

    def fetch(self) -> Snapshot | None:
        t = self.t
        self.t = t + self.step
        counted = self.df[self.df["reported_at"] <= t]
        if counted.empty:
            return None
        return Snapshot(counted=counted[COLS], baseline=self.baseline, n_total=len(self.df),
                        updated_at=t.isoformat(), fingerprint=t.isoformat(), final=self.final,
                        meta={"replay": self.year})


# ── Beräkning ───────────────────────────────────────────────────────────────

def compute_state(snap: Snapshot, election: str, baseline_year: int) -> C.NowcastLive:
    base_ids = set(snap.baseline["district_id"])
    comparable = snap.counted[snap.counted["district_id"].isin(base_ids)]
    nc = compute_nowcast(comparable[COLS], snap.baseline[COLS], PARTIES)
    total = float(snap.counted["total_valid_votes"].sum())
    raw = {p: float(snap.counted[f"votes_{p}"].sum()) / total for p in PARTIES} if total else {p: nc[p] for p in PARTIES}
    alloc = allocate_all_mandates({p: nc[p] * 100 for p in PARTIES})
    seats = alloc["total"]
    return C.NowcastLive(
        election=election, baselineYear=baseline_year, feedUpdatedAt=snap.updated_at,
        publishedAt=snap.updated_at or "",  # flödets tid, inte klockan → samma läge ger samma release
        nCounted=int(len(snap.counted)), nTotal=int(snap.n_total), nComparable=int(len(comparable)),
        voteShareCounted=float(nc["coverage"]),
        raw=raw, nowcast={p: float(nc[p]) for p in PARTIES}, seats=seats, fixedSeats=alloc["fixed"],
        blocs=[C.NowcastBloc(name=b, parties=ps, seats=sum(seats[p] for p in ps), share=sum(nc[p] for p in ps) * 100)
               for b, ps in BLOC_PARTIES.items()],
        final=snap.final,
    )


# ── Publicering ─────────────────────────────────────────────────────────────

def publish_state(storage: Storage, state: C.NowcastLive, fingerprint: str) -> str:
    """Ny release = senaste prognosreleasens filer + nowcast.json, mode "nowcast"."""
    from mandatorn_model import publish as P

    current_raw = storage.get("manifest.json")
    if current_raw is None:
        raise SystemExit("Ingen release att bygga vidare på — kör mandatorn_model.publish först")
    current = C.Manifest.model_validate_json(current_raw)
    data = P.canonical_json(state)
    digest = P.sha256(data)
    entry = C.FileEntry(path="nowcast.json", object=f"files/{digest}.json", size=len(data), sha256=digest)
    files = sorted([f for f in current.files if f.path != "nowcast.json"] + [entry], key=lambda f: f.path)
    index = json.dumps([[f.path, f.sha256] for f in files], separators=(",", ":")).encode()
    release_id = P.sha256(index)
    manifest = current.model_copy(update={
        "release": release_id, "mode": "nowcast", "files": files, "supersededBy": None,
        "generatedAt": datetime.now(STOCKHOLM).replace(tzinfo=None).isoformat(timespec="seconds"),
        "inputHash": P.sha256(f"{current.inputHash}|{fingerprint}".encode()),
    })
    # Bara nowcast.json är ny; övriga filer finns redan och latest/-alias rörs inte under natten.
    objects = {entry.object: (data, "application/json", entry.path)}
    P.write(storage, manifest, objects, P.load_config())
    return release_id


def write_feed_status(storage: Storage, ok: bool, error: str | None = None, updated_at: str | None = None) -> None:
    raw = storage.get("status.json")
    status = json.loads(raw) if raw else {}
    status.update({"feedOk": ok, "feedCheckedAt": datetime.now(STOCKHOLM).isoformat(timespec="seconds")})
    if ok:
        status.update({"feedUpdatedAt": updated_at, "feedError": None})
    else:
        status["feedError"] = error
    storage.put_pointer("status.json", json.dumps(status, ensure_ascii=False, sort_keys=True).encode(), "application/json")


def run(source: Source, storage: Storage, election: str, baseline_year: int, interval: float = 60.0,
        max_iterations: int | None = None, sleep=time.sleep, log=print) -> list[str]:
    """Pollingloop. Publicerar bara när datan ändrats. Returnerar publicerade release-id."""
    published, last_fp, i = [], None, 0
    while max_iterations is None or i < max_iterations:
        i += 1
        try:
            snap = source.fetch()
            if snap is not None and snap.fingerprint != last_fp:
                state = compute_state(snap, election, baseline_year)
                rid = publish_state(storage, state, snap.fingerprint)
                published.append(rid)
                last_fp = snap.fingerprint
                log(f"{state.feedUpdatedAt}: {state.nCounted}/{state.nTotal} distrikt, "
                    f"{state.voteShareCounted:.0%} av rösterna → release {rid[:12]}")
            write_feed_status(storage, True, updated_at=snap.updated_at if snap else None)
        except Exception as e:  # noqa: BLE001 — senaste giltiga release ligger kvar
            log(f"Fel vid hämtning/publicering: {type(e).__name__}: {e}")
            write_feed_status(storage, False, error=f"{type(e).__name__}: {e}")
        if getattr(source, "done", False):
            break
        if max_iterations is None or i < max_iterations:
            sleep(interval)
    return published


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="Katalog eller s3://bucket (måste ha en prognosrelease)")
    ap.add_argument("--year", type=int, default=2030, help="Valår för live-flödet")
    ap.add_argument("--election", default="2030-09-08")
    ap.add_argument("--baseline", default=str(REPO / "data" / "baseline_districts_2026.csv.gz"))
    ap.add_argument("--interval", type=float, default=60.0, help="Sekunder mellan hämtningar (Valmyndigheten: ≥ 60)")
    ap.add_argument("--replay", type=int, choices=[2022, 2026], help="Simulator: spela upp en sparad valnatt")
    ap.add_argument("--step-minutes", type=float, default=10.0, help="Simulator: simulerad tid per steg")
    ap.add_argument("--distribution-id")
    a = ap.parse_args(argv)
    storage = storage_from_uri(a.out, a.distribution_id)
    if a.replay:
        start = datetime(a.replay, 9, 11 if a.replay == 2022 else 13, 20, 30)
        src = ReplaySource(a.replay, start, timedelta(minutes=a.step_minutes),
                           end=start + timedelta(hours=8))
        run(src, storage, election=start.date().isoformat(), baseline_year=a.replay - 4,
            interval=a.interval if a.interval < 60 else 0.0)
    else:
        src = ValmyndighetenSource(a.year, Path(a.baseline))
        run(src, storage, election=a.election, baseline_year=a.year - 4, interval=max(a.interval, 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
