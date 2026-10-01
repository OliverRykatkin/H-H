"""Kvalitetsgrind före publicering. Flaggade körningar publiceras inte automatiskt.

Varje flagga har ett stabilt id. Godkända flaggor läggs i data/polls/quality_ack.txt
(ett id per rad, '#' för kommentar) och blockerar då inte längre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from mandatorn_model.constants import PARTIES, TOTAL_SEATS

ACK_PATH = Path(__file__).resolve().parents[1] / "data" / "polls" / "quality_ack.txt"


@dataclass
class QualityReport:
    flags: list[tuple[str, str]] = field(default_factory=list)
    acknowledged: list[tuple[str, str]] = field(default_factory=list)
    checked_polls: int = 0

    def add(self, flag_id: str, message: str) -> None:
        self.flags.append((flag_id, message))

    def apply_acks(self, acked: set[str]) -> "QualityReport":
        self.acknowledged += [f for f in self.flags if f[0] in acked]
        self.flags = [f for f in self.flags if f[0] not in acked]
        return self

    @property
    def ok(self) -> bool:
        return not self.flags

    def to_markdown(self) -> str:
        if self.ok:
            return (f"Kvalitetsgrind OK ({self.checked_polls} mätningar granskade, "
                    f"{len(self.acknowledged)} kvitterade flaggor).")
        lines = ["Kvalitetsgrinden flaggade körningen. Godkänn genom att lägga till id:na i "
                 "`data/polls/quality_ack.txt` (eller kör om med `--force`):", ""]
        lines += [f"- `{i}` — {m}" for i, m in self.flags]
        return "\n".join(lines)


def load_acks(path: Path = ACK_PATH) -> set[str]:
    if not path.exists():
        return set()
    ids = {ln.split("#", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()}
    return ids - {""}


def check_polls(polls: pd.DataFrame, reference_date: datetime, cfg: dict,
                aggregate: dict | None = None) -> QualityReport:
    rep = QualityReport()
    since = reference_date - timedelta(days=cfg["recent_days"])
    recent = polls[polls["PublDate"] >= since]
    rep.checked_polls = len(recent)
    for _, row in recent.iterrows():
        tag = f"{row.get('Company')}:{row['PublDate']:%Y-%m-%d}"
        label = f"{row.get('Company')} {row['PublDate']:%Y-%m-%d}"
        shares = pd.to_numeric(pd.Series({p: row.get(p) for p in PARTIES}), errors="coerce")
        if shares.notna().sum() == len(PARTIES):
            total = float(shares.sum())
            if not (cfg["share_sum_min"] <= total <= cfg["share_sum_max"]):
                rep.add(f"sum:{tag}", f"{label}: partiandelarna summerar till {total:.1f} %")
        field_to = pd.to_datetime(row.get("collectPeriodTo"), errors="coerce")
        if pd.notna(field_to) and field_to > reference_date + timedelta(days=1):
            rep.add(f"future:{tag}", f"{label}: fältperioden slutar i framtiden ({field_to:%Y-%m-%d})")
        field_from = pd.to_datetime(row.get("collectPeriodFrom"), errors="coerce")
        if pd.notna(field_from) and pd.notna(field_to) and field_from > field_to:
            rep.add(f"period:{tag}", f"{label}: fältperioden börjar efter att den slutar")
        if aggregate:
            for p in PARTIES:
                v = shares.get(p)
                if pd.notna(v) and abs(v - aggregate.get(p, v)) > cfg["max_dev_from_aggregate_pp"]:
                    rep.add(f"aggregate:{tag}:{p}",
                            f"{label}: {p} {v:.1f} % avviker {v - aggregate[p]:+.1f} pp från aggregatet")

    # Mot samma instituts förra mätning
    for company, g in polls.sort_values("PublDate", kind="stable").groupby("Company"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            row, prev = g.iloc[i], g.iloc[i - 1]
            if row["PublDate"] < since:
                continue
            for p in PARTIES:
                a = pd.to_numeric(row.get(p), errors="coerce")
                b = pd.to_numeric(prev.get(p), errors="coerce")
                if pd.isna(a) or pd.isna(b):
                    continue
                limit = cfg["max_jump_large_pp"] if max(a, b) >= cfg["large_party_pct"] else cfg["max_jump_small_pp"]
                if abs(a - b) > limit:
                    rep.add(f"jump:{company}:{row['PublDate']:%Y-%m-%d}:{p}",
                            f"{company} {row['PublDate']:%Y-%m-%d}: {p} ändrades {a - b:+.1f} pp "
                            f"mot institutets förra mätning (gräns {limit} pp)")

    # Dubbletter
    key = [c for c in ["Company", "PublDate"] + PARTIES if c in polls.columns]
    dup = polls[polls.duplicated(subset=key, keep=False) & (polls["PublDate"] >= since)]
    for (company, date), _ in dup.groupby(["Company", "PublDate"]):
        rep.add(f"duplicate:{company}:{date:%Y-%m-%d}", f"{company} {date:%Y-%m-%d}: dubblettmätning")
    return rep


def check_outputs(forecast, rep: QualityReport | None = None) -> QualityReport:
    rep = rep or QualityReport()
    total = sum(forecast.mandates["total"].values())
    if total != TOTAL_SEATS:
        rep.add("output:seats", f"Punktprognosen ger {total} mandat (ska vara {TOTAL_SEATS})")
    share_sum = sum(forecast.raw_est.values())
    if abs(share_sum - 100) > 1e-6:
        rep.add("output:share-sum", f"Estimaten summerar till {share_sum:.4f} % (ska vara 100)")
    pm = forecast.sim["party_mandates"]
    sums = sum(pm[p] for p in PARTIES)
    if not np.all(sums == TOTAL_SEATS):
        rep.add("output:draw-seats", f"{int(np.sum(sums != TOTAL_SEATS))} dragningar summerar inte till {TOTAL_SEATS} mandat")
    for p, v in forecast.sim["above_threshold"].items():
        if not 0.0 <= v <= 1.0:
            rep.add(f"output:p-threshold:{p}", f"P(spärr) för {p} = {v} utanför [0, 1]")
    return rep
