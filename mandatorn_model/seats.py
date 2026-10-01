"""mandatorn_model.seats — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from mandatorn_model.constants import (
    BASELINE,
    CONSTITUENCIES,
    PARTIES,
    THRESHOLD,
    TOTAL_SEATS,
)

def modified_sainte_lague(votes: dict, n_seats: int) -> dict:
    import heapq
    seats = {p: 0 for p in votes}
    heap = [(-v / 1.2, p) for p, v in votes.items()]
    heapq.heapify(heap)
    for _ in range(n_seats):
        if not heap:
            break
        neg_q, p = heapq.heappop(heap)
        seats[p] += 1
        heapq.heappush(heap, (-votes[p] / (2 * seats[p] + 1), p))
    return seats


def estimate_constituency_votes(national_est: dict, constituency: dict) -> dict:
    result = {}
    for p in PARTIES:
        offset = constituency.get(p, BASELINE.get(p, 0)) - BASELINE.get(p, 0)
        result[p] = max(0.0, national_est.get(p, 0) + offset)
    total = sum(result.values())
    return {p: v / total * 100 for p, v in result.items()} if total > 0 else result


def compute_baseline_mandates() -> dict:
    """Faktisk mandatfördelning per valkrets från senaste val (baslinjen).

    Använder ACTUAL mandatfördelning ur data/election_2026.json om den finns
    (Valmyndighetens officiella siffror). Annars faller vi tillbaka på att
    reproducera fördelningen genom att köra Sainte-Laguë på 2022 års röstandelar.
    """
    fixed_seats = {}
    has_real = all(
        isinstance(cdata.get("mandat"), dict) and cdata["mandat"]
        for cdata in CONSTITUENCIES.values()
    )
    if has_real:
        for name, cdata in CONSTITUENCIES.items():
            mandat = cdata.get("mandat") or {}
            fixed_seats[name] = {
                p: int(mandat.get(p, {}).get("fasta", 0)) for p in PARTIES
            }
        return fixed_seats

    for name, cdata in CONSTITUENCIES.items():
        votes = {p: cdata.get(p, 0) for p in PARTIES}
        total = sum(votes.values())
        if total > 0:
            votes = {p: v / total * 100 for p, v in votes.items()}
        alloc = modified_sainte_lague(votes, cdata["seats"])
        fixed_seats[name] = {p: alloc.get(p, 0) for p in PARTIES}
    return fixed_seats


def allocate_all_mandates(national_est_raw: dict) -> dict:
    eligible = [p for p in PARTIES if national_est_raw.get(p, 0) >= THRESHOLD]
    elig_votes = {p: national_est_raw[p] for p in eligible}
    total_elig = sum(elig_votes.values())
    national_norm = {p: v / total_elig * 100 for p, v in elig_votes.items()}

    fixed_seats = {}
    const_votes = {}
    party_fixed_total = {p: 0 for p in PARTIES}

    for name, cdata in CONSTITUENCIES.items():
        c_votes_all = estimate_constituency_votes(national_est_raw, cdata)
        c_votes_elig = {p: c_votes_all[p] for p in eligible}
        tot = sum(c_votes_elig.values())
        if tot > 0:
            c_votes_elig = {p: v / tot * 100 for p, v in c_votes_elig.items()}

        const_votes[name] = c_votes_all
        alloc = modified_sainte_lague(c_votes_elig, cdata["seats"])
        fixed_seats[name] = {p: alloc.get(p, 0) for p in PARTIES}
        for p in PARTIES:
            party_fixed_total[p] += fixed_seats[name].get(p, 0)

    national_prop = modified_sainte_lague(national_norm, TOTAL_SEATS)

    # Utjämningsmandat: fördela exakt (TOTAL_SEATS − fasta) mandat bland partier
    # som fortfarande behöver fler mandat för att nå proportionell andel.
    # Kör en ny Sainte-Laguë-fördelning för utjämningssätet med "återstående behov"
    # som röstandel — detta garanterar att summan alltid = TOTAL_SEATS (349).
    total_fixed_seats = sum(party_fixed_total.values())
    adj_seats_available = TOTAL_SEATS - total_fixed_seats  # normalt 39

    adj_need = {
        p: max(0.0, national_prop.get(p, 0) - party_fixed_total.get(p, 0))
        for p in eligible
    }
    adj_need_total = sum(adj_need.values())

    if adj_need_total > 0 and adj_seats_available > 0:
        adj_norm = {p: v / adj_need_total * 100 for p, v in adj_need.items() if v > 0}
        adjustment = modified_sainte_lague(adj_norm, adj_seats_available)
    else:
        adjustment = {}

    total = {p: party_fixed_total[p] + adjustment.get(p, 0) for p in PARTIES}

    return {
        "fixed": fixed_seats,
        "adjustment": adjustment,
        "total": total,
        "fixed_total": party_fixed_total,
        "constituency_votes": const_votes,
        "eligible_parties": eligible,
        "national_norm": national_norm,
    }
