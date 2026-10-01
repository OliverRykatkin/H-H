"""mandatorn_model.margins — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from mandatorn_model.constants import (
    CONSTITUENCIES,
    PARTIES,
    THRESHOLD,
)
from mandatorn_model.seats import allocate_all_mandates, modified_sainte_lague

def _perturb_shares(shares: dict, party: str, delta: float) -> dict:
    """
    Lägg till `delta` procentenheter på `party` och ta bort dem proportionellt
    från övriga partier så att totalsumman bevaras. `delta` kan vara negativ.
    Returnerar en ny dict (muterar inte indata).
    """
    total = sum(shares.values())
    x = shares.get(party, 0.0)
    # Clampa till [0, total] så scale aldrig blir negativ (negativa andelar)
    # även om en framtida cap råkar tillåta delta som skjuter över totalen.
    new_x = min(total, max(0.0, x + delta))
    others_sum = total - x
    if others_sum > 1e-9:
        scale = (total - new_x) / others_sum
        out = {p: (new_x if p == party else v * scale) for p, v in shares.items()}
    else:
        out = dict(shares)
        out[party] = new_x
    return out


def _first_crossing(eval_fn, base: int, sign: int,
                    cap: float = 12.0, coarse: float = 0.1, tol: float = 0.01):
    """
    Hitta minsta |delta| (procentenheter) i riktning `sign` där mandatantalet
    (eval_fn(signed_delta)) ändras bort från `base`. sign=+1 söker eval > base
    (vinna mandat), sign=−1 söker eval < base (förlora mandat).

    Grov linjär svepning hittar FÖRSTA övergången (robust mot icke-monotonicitet
    från spärr/utjämning), följt av bisektion för precision. Returnerar
    (delta_pp, nytt_mandatantal) eller (None, None) om ingen ändring inom `cap`.
    """
    want_more = sign > 0

    def changed(d):
        s = eval_fn(sign * d)
        return s > base if want_more else s < base

    prev, hit = 0.0, None
    steps = int(round(cap / coarse))
    for i in range(1, steps + 1):
        d = round(i * coarse, 6)
        if changed(d):
            hit = d
            break
        prev = d
    if hit is None:
        return None, None

    lo, hi = prev, hit
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if changed(mid):
            hi = mid
        else:
            lo = mid
    return hi, eval_fn(sign * hi)


def compute_national_margins(national_est_raw: dict, cap: float = 12.0) -> dict:
    """
    För varje parti: minsta förändring i nationell röstandel (procentenheter) för
    att TOTALA mandatantalet (fasta + utjämning) ska öka respektive minska med
    minst ett. Kör den fullständiga mandatmotorn (allocate_all_mandates), så
    4 %-spärren och utjämningsdynamiken fångas exakt. Skillnaden omfördelas
    proportionellt på övriga partier.
    """
    base_total = allocate_all_mandates(national_est_raw)["total"]
    out = {}
    for party in PARTIES:
        base = base_total.get(party, 0)

        def eval_fn(d, _party=party):
            return allocate_all_mandates(
                _perturb_shares(national_est_raw, _party, d)
            )["total"].get(_party, 0)

        gain_pp, gain_to = _first_crossing(eval_fn, base, +1, cap=cap)
        lose_pp, lose_to = _first_crossing(eval_fn, base, -1, cap=cap)
        cur = national_est_raw.get(party, 0.0)
        out[party] = {
            "seats": base,
            "gain_pp": gain_pp,
            "gain_to": gain_to if gain_to is not None else base,
            "gain_threshold": gain_pp is not None and cur < THRESHOLD,
            "lose_pp": lose_pp,
            "lose_to": lose_to if lose_to is not None else base,
            "lose_threshold": (
                lose_pp is not None and base > 0
                and (cur - lose_pp) < THRESHOLD <= cur
            ),
            "cap": cap,
        }
    return out


def compute_constituency_margins(national_est_raw: dict, const_name: str,
                                 cap: float = 20.0) -> dict:
    """
    För en vald valkrets: minsta förändring i partiets LOKALA röstandel
    (procentenheter) för att vinna respektive förlora ett FAST valkretsmandat.
    Endast nationellt spärrkvalificerade partier deltar; skillnaden omfördelas
    proportionellt bland övriga lokalt deltagande partier.
    """
    mandates = allocate_all_mandates(national_est_raw)
    eligible = mandates["eligible_parties"]
    cdata = CONSTITUENCIES[const_name]
    seats = cdata["seats"]

    c_elig = {p: mandates["constituency_votes"][const_name][p] for p in eligible}
    tot = sum(c_elig.values())
    if tot <= 0:
        return {}
    c_elig = {p: v / tot * 100 for p, v in c_elig.items()}
    base_alloc = modified_sainte_lague(c_elig, seats)

    out = {}
    for party in eligible:
        base = base_alloc.get(party, 0)

        def eval_fn(d, _party=party):
            return modified_sainte_lague(
                _perturb_shares(c_elig, _party, d), seats
            ).get(_party, 0)

        gain_pp, gain_to = _first_crossing(eval_fn, base, +1, cap=cap)
        lose_pp, lose_to = _first_crossing(eval_fn, base, -1, cap=cap)
        out[party] = {
            "local_share": c_elig[party],
            "seats": base,
            "gain_pp": gain_pp,
            "lose_pp": lose_pp,
            "cap": cap,
        }
    return out


def compute_closest_fixed_seats(national_est_raw: dict, top_n: int = 15,
                                cap: float = 8.0) -> list:
    """
    Rangordnar landets fasta valkretsmandat efter hur liten lokal röstförändring
    (procentenheter) som krävs för att mandatet ska byta parti. Per valkrets hittas
    den utmanare som är närmast att vinna ett mandat och vilket parti som då tappar
    det. Returnerar en lista sorterad stigande på 'margin_pp'.
    """
    mandates = allocate_all_mandates(national_est_raw)
    eligible = mandates["eligible_parties"]
    rows = []
    for name, cdata in CONSTITUENCIES.items():
        seats = cdata["seats"]
        c_elig = {p: mandates["constituency_votes"][name][p] for p in eligible}
        tot = sum(c_elig.values())
        if tot <= 0:
            continue
        c_elig = {p: v / tot * 100 for p, v in c_elig.items()}
        base_alloc = modified_sainte_lague(c_elig, seats)

        best = None
        for challenger in eligible:
            base = base_alloc.get(challenger, 0)
            if base >= seats:
                continue

            def eval_fn(d, _p=challenger):
                return modified_sainte_lague(
                    _perturb_shares(c_elig, _p, d), seats
                ).get(_p, 0)

            gain_pp, _ = _first_crossing(eval_fn, base, +1, cap=cap)
            if gain_pp is None:
                continue
            if best is None or gain_pp < best[0]:
                new_alloc = modified_sainte_lague(
                    _perturb_shares(c_elig, challenger, gain_pp + 1e-3), seats
                )
                loser = next(
                    (p for p in eligible
                     if new_alloc.get(p, 0) < base_alloc.get(p, 0)), None
                )
                best = (gain_pp, challenger, loser)

        if best is not None:
            rows.append({
                "Valkrets": name,
                "seats": seats,
                "challenger": best[1],
                "loser": best[2],
                "margin_pp": best[0],
            })
    rows.sort(key=lambda r: r["margin_pp"])
    return rows[:top_n]
