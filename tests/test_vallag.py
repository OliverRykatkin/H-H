"""Golden tests: mandatberäkningen ska exakt återskapa Valmyndighetens officiella utfall."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mandatorn_model.vallag import allocate_riksdag, jamkade

GOLDEN = Path(__file__).parent / "golden"


def _load(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("year", [2022, 2026])
def test_officiellt_utfall_aterskapas_exakt(year):
    g = _load(f"riksdag_{year}.json")
    r = allocate_riksdag(g["constituencies"], g["national_votes"], g["valid_votes"], g["total_seats"])
    assert r.total == g["official_total"]
    assert sum(r.total.values()) == 349
    for c in g["constituencies"]:
        assert r.fixed[c["name"]] == c["official_fixed"], c["name"]
        assert r.adjustment[c["name"]] == c["official_adjustment"], c["name"]
    assert r.returned == []


def _case(cid):
    case = next(c for c in _load("synthetic.json")["cases"] if c["id"] == cid)
    r = allocate_riksdag(case["constituencies"], case["national_votes"], case["national_valid"], case["total_seats"])
    return case, r


def test_lika_jamforelsetal_avgors_deterministiskt():
    case, r = _case("lika-jamforelsetal")
    assert r.total == case["expected"]["total"]
    assert r.fixed == case["expected"]["fixed"]


def test_precis_pa_sparren_deltar():
    case, r = _case("precis-pa-sparren")
    assert r.eligible == case["expected_eligible"]
    assert "D" not in r.total
    assert sum(r.total.values()) == case["total_seats"]


def test_tolv_procent_i_valkrets_ger_bara_fasta_mandat_dar():
    case, r = _case("tolv-procent-i-valkrets")
    assert r.eligible == case["expected_eligible"]
    assert r.fixed["K2"].get("L", 0) == 1   # K2: A 300/1,2=250, L 200/1,2≈167, B 167/1,2≈139
    assert "L" not in r.entitlement
    assert sum(r.entitlement.values()) == case["total_seats"] - r.fixed["K2"]["L"]
    assert r.total["L"] == 1 and sum(r.total.values()) == case["total_seats"]


def test_aterforing_vid_overhang():
    case, r = _case("aterforing-vid-overhang")
    # R vinner K1–K3 (fasta) men har bara rätt till 1 mandat i landet (1100/10000 av 10 med jämkad metod).
    ent, _ = jamkade(case["national_votes"], case["total_seats"])
    assert r.entitlement == ent and ent["R"] == 1
    assert r.total["R"] == ent["R"] and sum(r.total.values()) == case["total_seats"]
    # De två mandaten med lägst jämförelsetal återförs: K3 (340/1,2) först, sedan en av K1/K2 (350/1,2).
    assert ("K3", "R") in r.returned and len(r.returned) == 2
    assert r.fixed["K3"].get("R", 0) == 0


def test_jamkade_forsta_divisor():
    seats, won = jamkade({"A": 120, "B": 100}, 1)
    assert seats == {"A": 1, "B": 0} and won["A"] == [100.0]
    seats, _ = jamkade({"A": 120, "B": 100}, 2)
    assert seats == {"A": 1, "B": 1}   # A: 120/3 = 40 < B: 100/1,2 = 83


def test_prognosmotorn_med_valresultatet_2026_ger_officiella_mandat():
    """Hela kedjan (andelar → röster per valkrets → vallagen) med 2026 års resultat som indata."""
    import fetch_election_2026 as fe
    from mandatorn_model.constants import BASELINE, CONSTITUENCIES, PARTIES
    from mandatorn_model.seats import allocate_all_mandates

    g = _load("riksdag_2026.json")
    official = {fe.VALKRETS_MAPPING[c["name"]]: c for c in g["constituencies"]}
    m = allocate_all_mandates(BASELINE)
    assert m["total"] == {p: g["official_total"].get(p, 0) for p in PARTIES}
    for name in CONSTITUENCIES:
        assert {p: v for p, v in m["fixed"][name].items() if v} == official[name]["official_fixed"], name
        assert m["adjustment_by_constituency"][name] == official[name]["official_adjustment"], name
