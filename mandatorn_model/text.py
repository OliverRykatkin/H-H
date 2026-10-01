"""Verbal sannolikhetsskala och procentformat. Definieras i contracts/verbal_scale.json (D3)."""
from __future__ import annotations

import json
from pathlib import Path

_SCALE = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "verbal_scale.json").read_text(encoding="utf-8"))


def verbal(p: float) -> str:
    for step in _SCALE["steps"]:
        if "below" in step and p < step["below"]:
            return step["label"]
        if "atMost" in step and p <= step["atMost"]:
            return step["label"]
        if "below" not in step and "atMost" not in step:
            return step["label"]
    raise ValueError(p)


def display_pct(p: float) -> str:
    """Visar aldrig 0 % eller 100 % från simuleringar."""
    d = _SCALE["display"]
    if p < d["min"]:
        return d["belowMin"]
    if p > d["max"]:
        return d["aboveMax"]
    return f"{round(p * 100):.0f} %"
