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

Strukturen (mandat per valkrets, utjämning, spärr, 2022-röster) läses från
`data/muni_structure_2022.json`, genererad av `fetch_muni_cache.py`.

Begränsning: bara de 8 riksdagspartierna modelleras. Lokala partier (som vinner
verkliga mandat i kommunerna) prognosticeras inte — mandatsummorna är därför en
approximation som systematiskt gynnar riksdagspartierna.
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


def _projected_votes_per_valkrets(area: dict, swing: dict,
                                  parties: list[str]) -> list[dict]:
    """Applicera additiv sving på varje valkrets 2022-andelar → projicerade röster.

    För varje valkrets: andel_2022[p] = votes_2022[p] / total_2022 (i procent),
    projicerad andel = max(0, andel_2022 + swing[p]), projicerade röster =
    andel/100 * total_2022. total_2022 inkluderar lokala partier, så andelarna
    för de 8 partierna summerar till < 100 (resten är lokala/övriga).
    """
    out = []
    for vk in area.get("valkretsar", []):
        total = vk.get("total_2022", 0) or 0
        votes = {}
        if total > 0:
            for p in parties:
                share_2022 = vk["votes_2022"].get(p, 0) / total * 100.0
                proj_pct = max(0.0, share_2022 + swing.get(p, 0.0))
                votes[p] = proj_pct / 100.0 * total
        else:
            votes = {p: 0.0 for p in parties}
        out.append({"kod": vk.get("kod", ""), "fasta": int(vk.get("fasta", 0)),
                    "votes": votes})
    return out


def allocate_area_mandates(area: dict, swing: dict,
                           parties: list[str] = PARTIES) -> dict:
    """Fördela mandat för ett valområde utifrån opinionssving.

    Args:
        area: ett områdesobjekt från strukturen (KF/RF).
        swing: {parti: procentenheter} nationell sving sedan 2022.
        parties: partikoder att modellera (default 8 riksdagspartier).

    Returns:
        {total, fixed, adjustment: {parti: mandat}, per_valkrets: {kod: {parti: fasta}},
         qualified: [partier över spärren], projected_share: {parti: %},
         total_seats, n_utjamning, threshold_pct}
    """
    parties = list(parties)
    total_seats = int(area.get("total_seats", 0))
    n_utjamning = int(area.get("n_utjamning", 0))
    threshold = float(area.get("threshold_pct", 0.0))

    vk_votes = _projected_votes_per_valkrets(area, swing, parties)

    # Områdestotal → spärr + slutlig proportionell fördelning
    area_votes = {p: sum(vk["votes"].get(p, 0.0) for vk in vk_votes) for p in parties}
    grand_total = sum(area_votes.values())

    empty = {p: 0 for p in parties}
    if grand_total <= 0 or total_seats <= 0:
        return {
            "total": dict(empty), "fixed": dict(empty), "adjustment": dict(empty),
            "per_valkrets": {}, "qualified": [], "projected_share": dict(empty),
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
        per_valkrets[vk["kod"]] = {p: alloc.get(p, 0) for p in alloc if alloc.get(p, 0)}
        for p, s in alloc.items():
            fixed[p] += s

    # Slutlig proportionell total (Sainte-Laguë, första divisor 1,0) → utjämning
    total = dict(empty)
    if q_area_votes:
        prop = modified_sainte_lague(q_area_votes, n_seats=total_seats, first_divisor=1.0)
        for p, s in prop.items():
            total[p] = s
    adjustment = {p: max(0, total[p] - fixed[p]) for p in parties}

    return {
        "total": total,
        "fixed": fixed,
        "adjustment": adjustment,
        "per_valkrets": per_valkrets,
        "qualified": qualified,
        "projected_share": projected_share,
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
    print("Nollsving-total:", {p: res["total"][p] for p in PARTIES if res["total"][p]})
    print("Summa:", sum(res["total"].values()))
