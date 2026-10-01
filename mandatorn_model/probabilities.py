"""Sannolikheter ur simuleringen: deklarativa frågor (questions.toml) och koalitioner."""
from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np

from mandatorn_model.constants import COALITIONS, PARTIES, THRESHOLD

QUESTIONS_PATH = Path(__file__).with_name("questions.toml")


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    with open(path, "rb") as f:
        return tomllib.load(f)["question"]


def _votes(draws: dict, parties: list[str], n: int) -> np.ndarray:
    return sum(draws.get(p, np.zeros(n)) for p in parties)


def evaluate_question(q: dict, sim: dict) -> float:
    draws, n = sim["draws"], sim["n_sims"]
    kind = q["type"]
    if kind == "votes_greater":
        return float((_votes(draws, q["left"], n) > _votes(draws, q["right"], n)).mean())
    if kind == "votes_above":
        return float((_votes(draws, q["parties"], n) > q["value"]).mean())
    if kind == "above_threshold":
        return sim["above_threshold"].get(q["party"], 0)
    if kind == "all_above_threshold":
        return float(np.mean(np.all(
            np.stack([draws.get(p, np.zeros(n)) >= THRESHOLD for p in PARTIES]), axis=0
        )))
    if kind == "seats_at_least":
        pm = sim["party_mandates"]
        return float((sum(pm.get(p, np.zeros(n)) for p in q["parties"]) >= q["value"]).mean())
    raise ValueError(f"Okänd frågetyp: {kind}")


def evaluate_questions(sim: dict, questions: list[dict] | None = None) -> list[dict]:
    """[{id, text, p}] i konfigurationsordning."""
    return [{"id": q["id"], "text": q["text"], "p": evaluate_question(q, sim)}
            for q in (questions if questions is not None else load_questions())]


def coalition_summary(sim: dict, coalitions: dict = COALITIONS) -> list[dict]:
    """P(≥175 mandat), medel och percentiler per koalition, i konfigurationsordning."""
    n, pm = sim["n_sims"], sim["party_mandates"]
    rows = []
    for name, parties in coalitions.items():
        arr = sum(pm.get(p, np.zeros(n)) for p in parties)
        rows.append({
            "name": name,
            "parties": list(parties),
            "prob": float((arr >= 175).mean()),
            "mean": float(arr.mean()),
            "p5": int(np.percentile(arr, 5)),
            "p25": int(np.percentile(arr, 25)),
            "med": int(np.median(arr)),
            "p75": int(np.percentile(arr, 75)),
            "p95": int(np.percentile(arr, 95)),
        })
    return rows
