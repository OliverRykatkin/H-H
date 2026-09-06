"""Opinionsbaserad mandatuppskattning för kommun- och regionfullmäktige.

Full kommunal/regional modell:
  1. Uniform swing (nationell riksdagssving sedan 2022) appliceras additivt på
     varje valkrets 2022-andelar per parti.
  2. Fasta mandat fördelas per valkrets med modifierad Sainte-Laguë (första
     divisor 1,2) bland partier som klarat områdesspärren (2 % odelade kommuner,
     3 % delade kommuner och regioner).
  3. Utjämningsmandat: den proportionella totalen för hela området (Sainte-Laguë,
     första divisor 1,0, över samtliga mandat) utgör slutfördelningen; skillnaden
     mot de fasta mandaten är utjämningsmandaten.

Strukturen (mandat per valkrets, utjämning, spärr, 2022-röster per parti och
2022 års mandatfördelning) läses från `data/muni_structure_2022.json`, genererad
av `fetch_muni_cache.py`.

Riksdagspartierna får den nationella opinionssvingen; lokala partier antas få
samma resultat som 2022 (ingen opinionsdata finns för dem) och modelleras
tillsammans med riksdagspartierna. Den anonyma "Övriga"-svansen (småpartier under
tröskeln för att listas) räknas in i nämnaren men konkurrerar inte om mandat.
"""
from __future__ import annotations

import json
from pathlib import Path

from nowcast import modified_sainte_lague

PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"]

DATA_DIR = Path(__file__).parent / "data"
STRUCTURE_PATH = DATA_DIR / "muni_structure_2022.json"


def load_structure(path: Path | str = STRUCTURE_PATH) -> dict:
    """Läs den committade 2022-strukturen (KF + RF)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_areas(structure: dict, valtyp: str) -> list[tuple[str, str]]:
    """Returnera [(kod, namn), ...] sorterat på namn för en valtyp (KF/RF)."""
    areas = structure.get(valtyp, {})
    return sorted(((kod, a["namn"]) for kod, a in areas.items()), key=lambda x: x[1])


def _is_national(area: dict, party: str) -> bool:
    """Är partiet ett av de 8 riksdagspartierna (får opinionssving)?"""
    meta = area.get("party_meta", {})
    if party in meta:
        return bool(meta[party].get("national"))
    return party in PARTIES


def _area_parties(area: dict) -> list[str]:
    """Alla namngivna partier i området (riksdagspartier + lokala)."""
    seen: dict[str, None] = {}
    for vk in area.get("valkretsar", []):
        for p in vk.get("votes_2022", {}):
            seen.setdefault(p, None)
    return list(seen)


def _projected_votes_per_valkrets(area: dict, swing: dict) -> list[dict]:
    """Projicera röster per valkrets.

    Riksdagspartier: additiv sving på 2022-andelen (andel_2022 + swing[p]).
    Lokala partier: hålls vid sitt 2022-röstetal (samma resultat som förra valet).
    "Övriga"-svansen (total_2022 − summa namngivna) hålls också och räknas in i
    nämnaren men konkurrerar inte om mandat.
    """
    out = []
    for vk in area.get("valkretsar", []):
        total = vk.get("total_2022", 0) or 0
        named = vk.get("votes_2022", {})
        votes: dict[str, float] = {}
        for p, v2022 in named.items():
            if _is_national(area, p) and total > 0:
                share_2022 = v2022 / total * 100.0
                proj_pct = max(0.0, share_2022 + swing.get(p, 0.0))
                votes[p] = proj_pct / 100.0 * total
            else:
                votes[p] = float(v2022)   # lokalt parti: hålls vid 2022
        ovriga = max(0.0, total - sum(named.values()))
        out.append({"kod": vk.get("kod", ""), "fasta": int(vk.get("fasta", 0)),
                    "votes": votes, "ovriga": ovriga})
    return out


def allocate_area_mandates(area: dict, swing: dict) -> dict:
    """Fördela mandat för ett valområde utifrån opinionssving.

    Riksdagspartier får den nationella svingen; lokala partier antas få samma
    resultat som 2022. Alla namngivna partier konkurrerar i den fulla modellen
    (Sainte-Laguë per valkrets + utjämningsmandat + områdesspärr).

    Args:
        area: ett områdesobjekt från strukturen (KF/RF).
        swing: {parti: procentenheter} nationell riksdagssving sedan 2022.

    Returns:
        {total, fixed, adjustment, seats_2022: {parti: mandat},
         per_valkrets: {kod: {parti: fasta}}, qualified: [...],
         projected_share: {parti: %}, parties: [...], party_meta,
         total_seats, n_utjamning, threshold_pct}
    """
    parties = _area_parties(area)
    total_seats = int(area.get("total_seats", 0))
    n_utjamning = int(area.get("n_utjamning", 0))
    threshold = float(area.get("threshold_pct", 0.0))
    seats_2022 = {p: int(area.get("seats_2022", {}).get(p, 0)) for p in parties}

    vk_votes = _projected_votes_per_valkrets(area, swing)

    area_votes = {p: sum(vk["votes"].get(p, 0.0) for vk in vk_votes) for p in parties}
    ovriga_total = sum(vk["ovriga"] for vk in vk_votes)
    grand_total = sum(area_votes.values()) + ovriga_total

    empty = {p: 0 for p in parties}
    if grand_total <= 0 or total_seats <= 0:
        return {
            "total": dict(empty), "fixed": dict(empty), "adjustment": dict(empty),
            "seats_2022": seats_2022, "per_valkrets": {}, "qualified": [],
            "projected_share": dict(empty), "parties": parties,
            "party_meta": area.get("party_meta", {}),
            "total_seats": total_seats, "n_utjamning": n_utjamning,
            "threshold_pct": threshold,
        }

    projected_share = {p: area_votes[p] / grand_total * 100.0 for p in parties}
    qualified = [p for p in parties if projected_share[p] >= threshold]
    q_area_votes = {p: area_votes[p] for p in qualified}

    # Fasta mandat per valkrets (Sainte-Laguë, första divisor 1,2)
    fixed = {p: 0 for p in parties}
    per_valkrets: dict[str, dict] = {}
    for vk in vk_votes:
        seats_here = vk["fasta"]
        q_votes = {p: vk["votes"][p] for p in qualified if vk["votes"].get(p, 0) > 0}
        if seats_here <= 0 or not q_votes:
            per_valkrets[vk["kod"]] = {}
            continue
        alloc = modified_sainte_lague(q_votes, n_seats=seats_here, first_divisor=1.2)
        per_valkrets[vk["kod"]] = {p: s for p, s in alloc.items() if s}
        for p, s in alloc.items():
            fixed[p] += s

    # Slutfördelning: utan utjämningsmandat är de fasta mandaten (divisor 1,2)
    # slutgiltiga. Med utjämningsmandat proportionaliseras hela områdets total
    # (Sainte-Laguë, divisor 1,0) och skillnaden mot de fasta = utjämning.
    if n_utjamning > 0 and q_area_votes:
        total = dict(empty)
        for p, s in modified_sainte_lague(
            q_area_votes, n_seats=total_seats, first_divisor=1.0
        ).items():
            total[p] = s
    else:
        total = dict(fixed)
    adjustment = {p: max(0, total[p] - fixed[p]) for p in parties}

    return {
        "total": total,
        "fixed": fixed,
        "adjustment": adjustment,
        "seats_2022": seats_2022,
        "per_valkrets": per_valkrets,
        "qualified": qualified,
        "projected_share": projected_share,
        "parties": parties,
        "party_meta": area.get("party_meta", {}),
        "total_seats": total_seats,
        "n_utjamning": n_utjamning,
        "threshold_pct": threshold,
    }


if __name__ == "__main__":
    # Röktest: Stockholm KF med noll sving ska ge ~2022 års mandatfördelning.
    struct = load_structure()
    sthlm = struct["KF"]["0180"]
    res = allocate_area_mandates(sthlm, {p: 0.0 for p in PARTIES})
    print(f"Stockholm KF ({sthlm['total_seats']} mandat, "
          f"{sthlm['n_utjamning']} utjämning, spärr {sthlm['threshold_pct']}%)")
    print("Nollsving-total:", {p: s for p, s in res["total"].items() if s})
    print("Officiell 2022:", {p: s for p, s in res["seats_2022"].items() if s})
    print("Summa:", sum(res["total"].values()))
