"""Seat-modellen som exporteras till klienten ska räcka för att återskapa allocate_all_mandates."""
from __future__ import annotations

import json

from mandatorn_model.constants import BASELINE, CONSTITUENCIES, PARTIES, TOTAL_SEATS
from mandatorn_model.seat_model_export import export_seat_model
from mandatorn_model.seats import BASELINE_OTHERS


def test_export_innehaller_allt_och_ar_json():
    m = json.loads(json.dumps(export_seat_model()))
    assert m["parties"] == PARTIES
    assert m["total_seats"] == TOTAL_SEATS
    assert m["baseline_others"] == BASELINE_OTHERS
    assert m["baseline"] == {p: BASELINE[p] for p in PARTIES}
    assert [c["name"] for c in m["constituencies"]] == list(CONSTITUENCIES)
    for c in m["constituencies"]:
        src = CONSTITUENCIES[c["name"]]
        assert c["seats"] == src["seats"] and c["valid_votes"] == src.get("valid_votes")
        assert c["shares"] == {p: src[p] for p in PARTIES if p in src}
    assert sum(c["seats"] for c in m["constituencies"]) == 310


def test_golden_filen_ar_aktuell():
    """random_seat_cases.json bäddar in seat-modellen; den ska matcha dagens export."""
    from pathlib import Path

    path = Path(__file__).parent / "golden" / "random_seat_cases.json"
    embedded = json.loads(path.read_text(encoding="utf-8"))["seat_model"]
    assert embedded == json.loads(json.dumps(export_seat_model())), \
        "Kör python tools/dump_seat_cases.py efter ändringar i baslinjen"
