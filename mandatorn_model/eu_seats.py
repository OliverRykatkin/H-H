"""Mandatfördelning i EU-val: en riksvalkrets, 4 %-spärr, jämkade uddatalsmetoden.

Verifierad mot Valmyndighetens officiella utfall 2019 och 2024 (data/eu_results.json,
tests/test_eu_seats.py). Ingen utjämning eller valkretsspärr, till skillnad från riksdagsvalet.
"""
from __future__ import annotations

from mandatorn_model.election import EU2029, ElectionProfile
from mandatorn_model.vallag import _pick  # noqa: F401  (samma tiebreak som riksdagen)


def allocate_eu(votes: dict[str, float], valid_votes: float,
                profile: ElectionProfile = EU2029) -> dict[str, int]:
    """Röster per parti → mandat. `valid_votes` är alla giltiga röster (spärrbasen, inkl. övriga)."""
    eligible = {p: v for p, v in votes.items() if v > 0 and v / valid_votes >= profile.threshold}
    seats = {p: 0 for p in eligible}
    for _ in range(profile.seats):
        if not eligible:
            break
        cands = [(v / (profile.first_divisor if seats[p] == 0 else 2 * seats[p] + 1), v, p)
                 for p, v in eligible.items()]
        seats[_pick(cands)] += 1
    return {p: n for p, n in seats.items() if n}
