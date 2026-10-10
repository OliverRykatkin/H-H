"""EU-valet: mandatreglerna ska återskapa Valmyndighetens officiella utfall 2019 och 2024."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mandatorn_model.election import EU2029, PROFILES, RD2026
from mandatorn_model.eu_seats import allocate_eu

DATA = json.loads((Path(__file__).parent.parent / "data" / "eu_results.json").read_text(encoding="utf-8"))["elections"]


@pytest.mark.parametrize("year", ["2019", "2024"])
def test_officiellt_utfall_aterskapas(year):
    e = DATA[year]
    votes = {p["party"]: p["votes"] for p in e["parties"]}
    official = {p["party"]: p["seats"] for p in e["parties"] if p["seats"]}
    got = allocate_eu(votes, e["valid_votes"])
    assert got == official
    assert sum(got.values()) == 21


def test_sparr_pa_fyra_procent_av_giltiga_roster():
    votes = {"A": 400, "B": 39, "C": 561}
    assert "B" not in allocate_eu(votes, 1000)
    assert "B" in allocate_eu({"A": 400, "B": 40, "C": 560}, 1000)


def test_profiler():
    assert PROFILES == {"rd2026": RD2026, "eu2029": EU2029}
    assert EU2029.seats == 21 and EU2029.constituencies == 0 and RD2026.seats == 349
