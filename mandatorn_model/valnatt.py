"""mandatorn_model.valnatt — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from mandatorn_model.nowcast import PARTIES as NOWCAST_PARTIES
from mandatorn_model.nowcast import compute_nowcast
import numpy as np
import pandas as pd
from mandatorn_model.constants import (
    BASELINE,
    VALNATT_END,
    VALNATT_START,
    VALNATT_STEP_MIN,
)

def _load_valnatt_2026() -> pd.DataFrame | None:
    """Valnattens preliminära räkning 2026 per distrikt (data/valnatt_2026.csv.gz,
    genererad av fetch_valnatt.py) inkl. rapporteringstid och 2022-baslinje."""
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "valnatt_2026.csv.gz")
    if not _os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["reported_at"] = pd.to_datetime(df["reported_at"])
    return df


def _valnatt_times() -> list:
    n = int((VALNATT_END - VALNATT_START).total_seconds() // 60 // VALNATT_STEP_MIN)
    return [VALNATT_START + timedelta(minutes=VALNATT_STEP_MIN * i) for i in range(n + 1)]


def _valnatt_state(df: pd.DataFrame, t: datetime) -> dict:
    """Råräkning + nowcast när klockan är t på valnatten."""
    vote_cols = [f"votes_{p}" for p in NOWCAST_PARTIES]
    cmp = df[df["comparable"]]
    baseline = cmp[["district_id", "base_total_valid_votes"] + [f"base_{c}" for c in vote_cols]]
    baseline.columns = ["district_id", "total_valid_votes"] + vote_cols
    counted = df[df["reported_at"] <= t]
    counted_cmp = counted[counted["comparable"]][["district_id", "total_valid_votes"] + vote_cols]
    nowcast = compute_nowcast(counted_cmp, baseline, NOWCAST_PARTIES)
    total = counted["total_valid_votes"].sum()
    raw = (
        {p: counted[f"votes_{p}"].sum() / total for p in NOWCAST_PARTIES}
        if total > 0 else {p: nowcast[p] for p in NOWCAST_PARTIES}
    )
    final = {p: BASELINE[p] / 100.0 for p in NOWCAST_PARTIES}
    mae = lambda est: float(np.mean([abs(est[p] - final[p]) for p in NOWCAST_PARTIES]) * 100)
    return {
        "nowcast": nowcast, "raw": raw, "final": final,
        "n_counted": int(len(counted)), "n_total": int(len(df)),
        "vote_share_counted": float(total / df["total_valid_votes"].sum()),
        "mae_raw": mae(raw) if total > 0 else float("nan"),
        "mae_nowcast": mae(nowcast),
    }


def _valnatt_error_curve(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in _valnatt_times():
        stt = _valnatt_state(df, t)
        rows.append({"t": t, "Råräkning": stt["mae_raw"], "Nowcast": stt["mae_nowcast"]})
    return pd.DataFrame(rows)
