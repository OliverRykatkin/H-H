"""Slumpade korstestfall för mandatberäkningen: Pythons svar som facit för TS-porten.

    python tools/dump_seat_cases.py   → tests/golden/random_seat_cases.json

(a) allocate_riksdag-fall med heltalsröster (lika jämförelsetal, partier runt 4 % och
    12 %, överhäng), (b) nationella andelsvektorer genom seats.allocate_all_mandates med
    den riktiga seat-modellen (inbäddad). Fast seed.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from mandatorn_model.constants import PARTIES  # noqa: E402
from mandatorn_model.seat_model_export import export_seat_model  # noqa: E402
from mandatorn_model.seats import allocate_all_mandates  # noqa: E402
from mandatorn_model.vallag import allocate_riksdag  # noqa: E402

OUT = REPO / "tests" / "golden" / "random_seat_cases.json"
SEED = 20261001
LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]


def riksdag_case(rng: random.Random, i: int) -> dict:
    n_parties = rng.randint(2, 9)
    parties = LETTERS[:n_parties]
    n_vk = rng.randint(1, 6)
    kind = ["random", "tie", "threshold4", "threshold12", "overhang"][i % 5]
    consts = []
    for k in range(n_vk):
        fixed = rng.randint(1, 12)
        if kind == "tie":
            base = rng.randint(50, 500)
            votes = {p: base * rng.choice([1, 1, 2, 3]) for p in parties}
        elif kind == "overhang" and k < n_vk - 1:
            votes = {p: rng.randint(0, 60) for p in parties}
            votes[parties[0]] = rng.randint(300, 400)
            fixed = 1
        elif kind == "overhang":
            votes = {p: rng.randint(500, 4000) for p in parties}
            votes[parties[0]] = rng.randint(0, 40)
            fixed = rng.randint(6, 15)
        else:
            votes = {p: rng.randint(0, 5000) for p in parties}
        if kind == "threshold12" and k == 0:
            votes[parties[-1]] = int(sum(votes.values()) * rng.choice([0.12, 0.13, 0.119]) / 0.88) + rng.randint(0, 2)
        others = rng.randint(0, 400)
        consts.append({"name": f"V{k + 1}", "fixed_seats": fixed,
                       "valid_votes": sum(votes.values()) + others, "votes": votes})
    national = {p: sum(c["votes"][p] for c in consts) for p in parties}
    valid = sum(c["valid_votes"] for c in consts)
    if kind == "threshold4":
        p = parties[-1]
        rest = valid - national[p]
        national[p] = int(round(rest * rng.choice([0.04, 0.0399, 0.0401]) / (1 - 0.04)))
        valid = rest + national[p]
    total = sum(c["fixed_seats"] for c in consts) + rng.randint(0, 8)
    r = allocate_riksdag(consts, national, valid, total)
    return {
        "id": f"riksdag-{i}-{kind}", "total_seats": total, "national_valid": valid,
        "national_votes": national, "constituencies": consts,
        "expected": {"fixed": r.fixed, "adjustment": r.adjustment, "total": r.total,
                     "entitlement": r.entitlement, "eligible": r.eligible,
                     "returned": [list(x) for x in r.returned]},
    }


def shares_case(rng: random.Random, i: int) -> dict:
    base = {"M": 19, "L": 5, "C": 7, "KD": 6, "S": 28, "V": 8, "MP": 6, "SD": 18}
    shares = {p: max(0.0, base[p] + rng.gauss(0, 2.5)) for p in PARTIES}
    if i % 4 == 0:
        shares[rng.choice(["L", "KD", "MP", "C"])] = rng.choice([3.9, 3.95, 4.0, 4.05, 4.1, 3.97])
    mode = i % 3
    tot = sum(shares.values())
    if mode == 0:      # andel bland 8 partier (summa 100)
        shares = {p: v / tot * 100 for p, v in shares.items()}
    elif mode == 1:    # andel av alla röster (summa < 100, nowcast)
        shares = {p: v / tot * rng.uniform(96.0, 99.4) for p, v in shares.items()}
    m = allocate_all_mandates(shares)
    keys = ["fixed", "adjustment", "total", "fixed_total", "eligible_parties",
            "adjustment_by_constituency", "share_all", "others", "national_norm"]
    if i < 15:  # flyttalen per valkrets kontrolleras exakt i ett urval (filstorlek)
        keys.append("constituency_votes")
    return {
        "id": f"shares-{i}-{['norm100', 'all-votes', 'raw'][mode]}", "shares": shares,
        "expected": {k: m[k] for k in keys} | {"returned": [list(x) for x in m["returned"]]},
    }


def main() -> int:
    rng = random.Random(SEED)
    data = {
        "_doc": "Genererad av tools/dump_seat_cases.py — Pythons resultat är facit för web/tests/seats.test.ts.",
        "seed": SEED,
        "seat_model": export_seat_model(),
        "riksdag_cases": [riksdag_case(rng, i) for i in range(150)],
        "shares_cases": [shares_case(rng, i) for i in range(100)],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    kinds = {}
    for c in data["riksdag_cases"]:
        k = c["id"].split("-")[-1]
        kinds[k] = kinds.get(k, 0) + 1
    n_ret = sum(1 for c in data["riksdag_cases"] if c["expected"]["returned"])
    print(f"Skrev {OUT.relative_to(REPO)} ({OUT.stat().st_size // 1024} kB): {len(data['riksdag_cases'])} riksdagsfall "
          f"{kinds}, varav {n_ret} med återföring; {len(data['shares_cases'])} andelsfall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
