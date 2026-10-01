"""Riksdagens mandat: valkretsprognos (uniform swing) + mandatfördelning enligt vallagen."""
from __future__ import annotations

from mandatorn_model.constants import (
    BASELINE,
    CONSTITUENCIES,
    PARTIES,
    TOTAL_SEATS,
)
from mandatorn_model.vallag import allocate_riksdag

# Övriga partiers andel i baslinjevalet (procent av giltiga röster); antas oförändrad.
BASELINE_OTHERS = max(0.0, 100.0 - sum(BASELINE.get(p, 0.0) for p in PARTIES))

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


def _norm8(d: dict) -> dict:
    tot = sum(float(d.get(p, 0.0)) for p in PARTIES)
    return {p: float(d.get(p, 0.0)) / tot * 100.0 if tot > 0 else 0.0 for p in PARTIES}


def estimate_constituency_votes(national_est: dict, constituency: dict) -> dict:
    """Uniform swing per valkrets: valkretsens baslinjeandel + nollsummerad nationell
    sving (samma formel som regional.compute_national_swing, D17). Normerad till 100."""
    nat, base = _norm8(national_est), _norm8(BASELINE)
    result = {p: max(0.0, constituency.get(p, BASELINE.get(p, 0)) + nat[p] - base[p]) for p in PARTIES}
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


def allocate_all_mandates(national_est_raw: dict, others: float | None = None) -> dict:
    """Riksdagens mandat för ett nationellt estimat, enligt vallagen (vallag.allocate_riksdag).

    national_est_raw: procent per riksdagsparti. Summerar indata till ~100 tolkas det som
    andel bland de åtta partierna och övriga antas ligga kvar på baslinjevalets nivå
    (BASELINE_OTHERS); summerar det till mindre (t.ex. nowcastens andel av alla röster)
    är resten övriga. Spärrarna prövas mot andel av samtliga giltiga röster (PARITY A4).
    Röster per valkrets = prognostiserad andel × valkretsens giltiga röster i baslinjevalet.
    """
    s8 = {p: max(0.0, float(national_est_raw.get(p, 0.0))) for p in PARTIES}
    tot8 = sum(s8.values())
    if others is None:
        others = max(0.0, 100.0 - tot8) if tot8 < 99.5 else BASELINE_OTHERS
    share_all = {p: (v / tot8 * (100.0 - others) if tot8 > 0 else 0.0) for p, v in s8.items()}

    const_list, const_votes = [], {}
    for name, cdata in CONSTITUENCIES.items():
        c_shares = estimate_constituency_votes(share_all, cdata)
        others_c = max(0.0, 100.0 - sum(cdata.get(p, 0.0) for p in PARTIES))
        valid = float(cdata.get("valid_votes") or cdata["seats"] * 25_000)
        const_votes[name] = c_shares
        const_list.append({
            "name": name, "fixed_seats": cdata["seats"], "valid_votes": valid,
            "votes": {p: c_shares[p] / 100.0 * (100.0 - others_c) / 100.0 * valid for p in PARTIES},
        })
    national_valid = sum(c["valid_votes"] for c in const_list)
    national_votes = {p: share_all[p] / 100.0 * national_valid for p in PARTIES}
    r = allocate_riksdag(const_list, national_votes, national_valid, TOTAL_SEATS)

    fixed_seats = {name: {p: r.fixed[name].get(p, 0) for p in PARTIES} for name in CONSTITUENCIES}
    party_fixed_total = {p: sum(fixed_seats[n][p] for n in fixed_seats) for p in PARTIES}
    adjustment = {p: n for p, n in r.adjustment_total().items() if n}
    elig_total = sum(share_all[p] for p in r.eligible)
    return {
        "fixed": fixed_seats,
        "adjustment": adjustment,
        "total": {p: r.total.get(p, 0) for p in PARTIES},
        "fixed_total": party_fixed_total,
        "constituency_votes": const_votes,
        "eligible_parties": r.eligible,
        "national_norm": {p: share_all[p] / elig_total * 100 for p in r.eligible} if elig_total else {},
        "adjustment_by_constituency": {name: dict(r.adjustment[name]) for name in CONSTITUENCIES},
        "returned": r.returned,
        "share_all": share_all,
        "others": others,
    }
