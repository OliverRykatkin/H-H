"""Enhetstester för nowcast-modulen.

Verifierar matematiken på syntetiska data där svaret kan handräknas.
"""
from __future__ import annotations

import pandas as pd
import pytest

from nowcast import (
    compute_nowcast,
    modified_sainte_lague,
    project_mandates,
    simulate_election_night,
)

TWO_PARTIES = ["A", "B"]


def make_districts(rows: list[tuple]) -> pd.DataFrame:
    """Hjälpfunktion: (district_id, votes_A, votes_B) → DataFrame."""
    df = pd.DataFrame(rows, columns=["district_id", "votes_A", "votes_B"])
    df["total_valid_votes"] = df["votes_A"] + df["votes_B"]
    return df


def test_zero_coverage_returns_baseline():
    """Vid 0% täckning ska prognosen vara identisk med baslinjen."""
    baseline = make_districts(
        [(i, 60, 40) if i < 3 else (i, 40, 60) for i in range(6)]
    )
    counted = baseline.iloc[0:0]

    result = compute_nowcast(counted, baseline, parties=TWO_PARTIES)

    assert result["coverage"] == 0.0
    assert result["A"] == pytest.approx(0.5)
    assert result["B"] == pytest.approx(0.5)
    assert result["deltas"] == {"A": 0.0, "B": 0.0}


def test_full_coverage_returns_actual():
    """Vid 100% täckning ska prognosen vara identisk med faktiskt resultat."""
    baseline = make_districts([(i, 60, 40) for i in range(4)])
    actual = make_districts([(i, 30, 70) for i in range(4)])

    result = compute_nowcast(actual, baseline, parties=TWO_PARTIES)

    assert result["coverage"] == 1.0
    assert result["A"] == pytest.approx(0.30)
    assert result["B"] == pytest.approx(0.70)


def test_uniform_delta_recovers_truth_exactly():
    """Om delta är uniformt över alla distrikt ska prognosen vara exakt sann
    redan vid mycket låg täckning. Det är hela poängen med metoden.

    Setup: 6 distrikt, 100 röster vardera.
      - Distrikt 0-2: baseline A=60% B=40%
      - Distrikt 3-5: baseline A=40% B=60%
      - I aktuellt val: A tappar 5pp uniformt över alla distrikt.
        → 0-2: A=55%, 3-5: A=35%
      - Distrikt 0,1 räknas tidigt (33% täckning) — råräkningen ger A=55%
        men sanningen är (55+55+55+35+35+35)/6 = 45%.

    Förväntat: nowcast ska ge exakt 45% trots biaserade räknade distrikt.
    """
    baseline = make_districts(
        [(0, 60, 40), (1, 60, 40), (2, 60, 40), (3, 40, 60), (4, 40, 60), (5, 40, 60)]
    )
    counted = make_districts([(0, 55, 45), (1, 55, 45)])

    result = compute_nowcast(counted, baseline, parties=TWO_PARTIES)

    assert result["A"] == pytest.approx(0.45)
    assert result["B"] == pytest.approx(0.55)
    assert result["deltas"]["A"] == pytest.approx(-0.05)
    assert result["coverage"] == pytest.approx(2 / 6)


def test_raw_count_is_biased_when_counting_order_correlates_with_demographics():
    """Råräkningen ska vara biaserad i samma setup som test ovan.
    Detta validerar att vi mäter rätt jämförelseproblem.
    """
    counted = make_districts([(0, 55, 45), (1, 55, 45)])
    total = counted["total_valid_votes"].sum()
    raw_share_a = counted["votes_A"].sum() / total

    assert raw_share_a == pytest.approx(0.55)
    assert abs(raw_share_a - 0.45) == pytest.approx(0.10)


def test_simulate_election_night_returns_expected_schema():
    """Simuleringen ska producera rader för alla (coverage, party)-par."""
    baseline = make_districts([(i, 60, 40) for i in range(10)])
    actual = make_districts([(i, 55, 45) for i in range(10)])

    df = simulate_election_night(
        actual,
        baseline,
        counting_order=list(range(10)),
        coverage_levels=[0.1, 0.5, 1.0],
        parties=TWO_PARTIES,
    )

    assert set(df.columns) == {
        "coverage",
        "party",
        "raw_share",
        "nowcast_share",
        "true_share",
        "raw_error",
        "nowcast_error",
    }
    assert len(df) == 3 * 2
    assert (df["nowcast_error"] <= df["raw_error"] + 1e-9).all()


def test_simulate_nowcast_beats_raw_with_biased_counting_order():
    """Om räkningsordningen korrelerar med distriktsegenskaper ska
    nowcast slå råräkningen vid låg täckning.
    """
    baseline_rows = [(i, 60, 40) for i in range(5)] + [
        (i, 40, 60) for i in range(5, 10)
    ]
    actual_rows = [(i, 55, 45) for i in range(5)] + [
        (i, 35, 65) for i in range(5, 10)
    ]
    baseline = make_districts(baseline_rows)
    actual = make_districts(actual_rows)
    counting_order = list(range(10))

    df = simulate_election_night(
        actual,
        baseline,
        counting_order=counting_order,
        coverage_levels=[0.1, 0.3, 0.5],
        parties=TWO_PARTIES,
    )

    a_rows = df[df["party"] == "A"]
    assert (a_rows["nowcast_error"] < a_rows["raw_error"]).all()


def test_missing_district_in_baseline_raises():
    """Om ett räknat distrikt-ID saknas i baslinjen ska vi få ett tydligt fel."""
    baseline = make_districts([(0, 60, 40), (1, 60, 40)])
    counted = make_districts([(99, 50, 50)])

    with pytest.raises(ValueError, match="saknas i baslinjen"):
        compute_nowcast(counted, baseline, parties=TWO_PARTIES)


def test_missing_schema_column_raises():
    bad = pd.DataFrame({"district_id": [1], "total_valid_votes": [100]})

    with pytest.raises(ValueError, match="saknar kolumner"):
        compute_nowcast(bad, bad, parties=TWO_PARTIES)


def test_sainte_lague_known_case():
    """Modifierad Sainte-Laguë: 100 mandat, 50/30/20 → 50/30/20 ungefär."""
    votes = {"A": 0.50, "B": 0.30, "C": 0.20}
    seats = modified_sainte_lague(votes, n_seats=100, first_divisor=1.0)
    assert sum(seats.values()) == 100
    assert seats["A"] > seats["B"] > seats["C"]


def test_project_mandates_applies_threshold():
    """Partier under 4% ska inte få mandat."""
    nowcast = {"M": 0.20, "S": 0.30, "V": 0.10, "SD": 0.20, "L": 0.03, "C": 0.05, "MP": 0.03, "KD": 0.09}
    mandates = project_mandates(nowcast)

    assert mandates["L"] == 0
    assert mandates["MP"] == 0
    assert sum(mandates.values()) == 349
    assert mandates["S"] > mandates["M"]
