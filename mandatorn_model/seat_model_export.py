"""Exporterar det klienten behöver för att köra seats.allocate_all_mandates i webbläsaren.

Värdena exporteras orörda (inga avrundningar, inga ifyllda standardvärden) så att
TypeScript-porten (web/src/lib/seatModel.ts) kan reproducera Python bitidentiskt:
saknade partiandelar och valid_votes lämnas utelämnade/None precis som i källan.
"""
from __future__ import annotations

from mandatorn_model.constants import BASELINE, CONSTITUENCIES, PARTIES, TOTAL_SEATS
from mandatorn_model.seats import BASELINE_OTHERS

SEAT_MODEL_VERSION = 1


def export_seat_model() -> dict:
    return {
        "version": SEAT_MODEL_VERSION,
        "parties": list(PARTIES),
        "baseline": {p: BASELINE[p] for p in PARTIES if p in BASELINE},
        "baseline_others": BASELINE_OTHERS,
        "total_seats": TOTAL_SEATS,
        "constituencies": [
            {
                "name": name,
                "seats": c["seats"],
                "valid_votes": c.get("valid_votes"),
                "shares": {p: c[p] for p in PARTIES if p in c},
            }
            for name, c in CONSTITUENCIES.items()
        ],
    }
