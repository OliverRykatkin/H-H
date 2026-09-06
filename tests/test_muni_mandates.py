"""Enhetstester för muni_mandates (opinionsbaserad kommunal mandatmodell)."""
from __future__ import annotations

from pathlib import Path

import pytest

from muni_mandates import (
    PARTIES,
    STRUCTURE_PATH,
    allocate_area_mandates,
    list_areas,
    load_structure,
)

ZERO = {p: 0.0 for p in PARTIES}


def _area(valkretsar, total_seats, n_utjamning=0, threshold=3.0, namn="Test",
          kod="0001", party_meta=None, seats_2022=None):
    if party_meta is None:
        party_meta = {}
        for vk in valkretsar:
            for p in vk["votes_2022"]:
                party_meta.setdefault(
                    p, {"namn": p, "farg": "#111111", "national": p in PARTIES}
                )
    return {
        "namn": namn, "kod": kod, "valtyp": "KF",
        "threshold_pct": threshold, "total_seats": total_seats,
        "n_utjamning": n_utjamning, "valkretsar": valkretsar,
        "party_meta": party_meta, "seats_2022": seats_2022 or {},
    }


def _vk(kod, fasta, votes, total=None):
    v = {p: 0 for p in PARTIES}
    v.update(votes)
    return {"kod": kod, "fasta": fasta, "total_2022": total or sum(v.values()),
            "votes_2022": v}


# --------------------------------------------------------------------------- #

def test_single_valkrets_proportional():
    """En valkrets, två partier 60/40, 10 mandat → 6/4 (Sainte-Laguë)."""
    area = _area([_vk("01", 10, {"M": 600, "S": 400})], total_seats=10)
    res = allocate_area_mandates(area, ZERO)
    assert res["total"]["M"] == 6
    assert res["total"]["S"] == 4
    assert sum(res["total"].values()) == 10


def test_threshold_excludes_small_party():
    """Parti under spärren (3 %) får inga mandat."""
    area = _area(
        [_vk("01", 20, {"M": 500, "S": 480, "V": 20})],  # V = 2 % < 3 %
        total_seats=20, threshold=3.0,
    )
    res = allocate_area_mandates(area, ZERO)
    assert res["total"]["V"] == 0
    assert "V" not in res["qualified"]
    assert {"M", "S"} <= set(res["qualified"])
    assert sum(res["total"].values()) == 20


def test_total_sums_to_total_seats():
    """Flera valkretsar: totalen summerar alltid till total_seats."""
    area = _area(
        [
            _vk("01", 8, {"M": 300, "S": 400, "SD": 300}),
            _vk("02", 7, {"M": 350, "S": 350, "SD": 300}),
        ],
        total_seats=17, n_utjamning=2,
    )
    res = allocate_area_mandates(area, ZERO)
    assert sum(res["total"].values()) == 17
    assert sum(res["fixed"].values()) == 15   # 8 + 7 fasta
    # utjämning = total − fasta, aldrig negativt
    assert all(res["adjustment"][p] >= 0 for p in PARTIES)


def test_swing_shifts_seats():
    """Positiv sving till SD ska flytta mandat till SD."""
    area = _area([_vk("01", 20, {"M": 500, "S": 450, "SD": 50})], total_seats=20,
                 threshold=0.0)
    base = allocate_area_mandates(area, ZERO)
    swung = allocate_area_mandates(area, {**ZERO, "SD": 20.0, "M": -20.0})
    assert swung["total"]["SD"] > base["total"]["SD"]
    assert swung["total"]["M"] < base["total"]["M"]


def test_local_party_held_at_2022_and_wins_seat():
    """Lokalt parti (icke-nationellt) hålls vid 2022 och konkurrerar om mandat."""
    votes = {"M": 400, "S": 400, "LOK": 200}
    area = _area(
        [_vk("01", 20, votes)], total_seats=20, threshold=3.0,
        party_meta={
            "M": {"namn": "M", "farg": "#1", "national": True},
            "S": {"namn": "S", "farg": "#2", "national": True},
            "LOK": {"namn": "Lokalpartiet", "farg": "#3", "national": False},
        },
    )
    res = allocate_area_mandates(area, ZERO)
    assert res["total"]["LOK"] > 0                 # lokalpartiet vinner mandat
    assert "LOK" in res["parties"]

    # Stor sving till riksdagspartier ska INTE ändra lokalpartiets röstbas
    swung = allocate_area_mandates(area, {**ZERO, "M": 30.0})
    # lokalpartiets projicerade röster = 2022 (hålls), oberoende av svingen
    assert swung["total"]["LOK"] >= 1


def test_seats_2022_passthrough():
    area = _area([_vk("01", 10, {"M": 600, "S": 400})], total_seats=10,
                 seats_2022={"M": 6, "S": 4})
    res = allocate_area_mandates(area, ZERO)
    assert res["seats_2022"]["M"] == 6
    assert res["seats_2022"]["S"] == 4


def test_empty_area_returns_zeros():
    area = _area([_vk("01", 0, {})], total_seats=0)
    res = allocate_area_mandates(area, ZERO)
    assert sum(res["total"].values()) == 0
    assert res["qualified"] == []


def test_zero_votes_returns_zeros():
    area = _area([_vk("01", 10, {"M": 0, "S": 0})], total_seats=10)
    res = allocate_area_mandates(area, ZERO)
    assert sum(res["total"].values()) == 0


# --------------------------------------------------------------------------- #
# Mot committad struktur (om filen finns)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    not Path(STRUCTURE_PATH).exists(),
    reason="data/muni_structure_2022.json saknas (kör fetch_muni_cache.py)",
)
def test_real_structure_stockholm_zero_swing():
    """Nollsving mot Stockholm KF ska ge exakt 101 mandat fördelat."""
    struct = load_structure()
    res = allocate_area_mandates(struct["KF"]["0180"], ZERO)
    assert sum(res["total"].values()) == struct["KF"]["0180"]["total_seats"] == 101


@pytest.mark.skipif(
    not Path(STRUCTURE_PATH).exists(),
    reason="data/muni_structure_2022.json saknas",
)
def test_list_areas_counts():
    struct = load_structure()
    assert len(list_areas(struct, "KF")) == 290
    assert len(list_areas(struct, "RF")) == 20
    # sorterat på namn, (kod, namn)-tupler
    kod, namn = list_areas(struct, "KF")[0]
    assert isinstance(kod, str) and isinstance(namn, str)
