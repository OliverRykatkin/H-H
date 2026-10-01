"""Mandatfördelning i riksdagsval enligt vallagen (2022:1600) 14 kap. (DECISIONS D6).

Regler (verifierade mot Valmyndighetens officiella utfall 2022 och 2026, tests/golden/):
  1. Jämkade uddatalsmetoden: jämförelsetal = röster / 1,2 före första mandatet,
     därefter röster / (2k + 1) där k = redan tilldelade mandat.
  2. Fasta valkretsmandat fördelas i varje valkrets mellan partier som fått minst
     4 % av rösterna i landet eller minst 12 % av rösterna i valkretsen.
  3. Hela landets 349 mandat fördelas med samma metod mellan partier med minst 4 %
     i landet. Mandat som tagits av parti som bara klarat 12 %-spärren dras först av.
  4. Har ett parti fått fler fasta mandat än det ska ha i landet återförs de fasta
     mandat som har lägst jämförelsetal ("återföring").
  5. Övriga partier får utjämningsmandat för mellanskillnaden. De placeras ett i taget
     i den valkrets där partiet har högst jämförelsetal enligt den *ojämkade*
     uddatalsmetoden: röster / (2k + 1), k = partiets samtliga mandat i valkretsen
     (första divisor 1, inte 1,2). Empiriskt fastställt: ger exakt Valmyndighetens
     placering i alla 29 valkretsar 2022 och 2026; den jämkade varianten ger 9 resp.
     11 fel.

Lika jämförelsetal: lagen föreskriver lottning. Här avgörs det deterministiskt —
högre röstetal vinner, därefter partiförkortning i alfabetisk ordning (samma regel i
TypeScript-porten), så att resultaten är reproducerbara.
"""
from __future__ import annotations

from dataclasses import dataclass

NATIONAL_THRESHOLD = 0.04
CONSTITUENCY_THRESHOLD = 0.12
FIRST_DIVISOR = 1.2


def divisor(k: int) -> float:
    return FIRST_DIVISOR if k == 0 else 2 * k + 1


def placement_divisor(k: int) -> float:
    return 2 * k + 1


def _pick(cands: list[tuple[float, float, str]]) -> str:
    """Högst jämförelsetal; lika → högst röstetal; lika → partikod i bokstavsordning."""
    return min(cands, key=lambda c: (-c[0], -c[1], c[2]))[2]


def jamkade(votes: dict[str, float], n_seats: int, start: dict[str, int] | None = None) -> tuple[dict, dict]:
    """Fördela n_seats mandat. Returnerar (mandat per parti, jämförelsetal per tilldelat mandat)."""
    seats = {p: (start or {}).get(p, 0) for p in votes}
    won: dict[str, list[float]] = {p: [] for p in votes}
    for _ in range(n_seats):
        cands = [(v / divisor(seats[p]), v, p) for p, v in votes.items() if v > 0]
        if not cands:
            break
        p = _pick(cands)
        won[p].append(votes[p] / divisor(seats[p]))
        seats[p] += 1
    return seats, won


@dataclass
class RiksdagResult:
    fixed: dict[str, dict[str, int]]          # valkrets → parti → fasta mandat (efter återföring)
    adjustment: dict[str, dict[str, int]]     # valkrets → parti → utjämningsmandat
    total: dict[str, int]                     # parti → totalt
    entitlement: dict[str, int]               # parti → mandat enligt fördelningen i hela landet
    eligible: list[str]                       # partier med ≥ 4 % i landet
    returned: list[tuple[str, str]]           # (valkrets, parti) för återförda fasta mandat

    def fixed_total(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in self.fixed.values():
            for p, n in row.items():
                out[p] = out.get(p, 0) + n
        return out

    def adjustment_total(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in self.adjustment.values():
            for p, n in row.items():
                out[p] = out.get(p, 0) + n
        return out


def allocate_riksdag(constituencies: list[dict], national_votes: dict[str, float],
                     national_valid: float, total_seats: int = 349) -> RiksdagResult:
    """constituencies: [{name, fixed_seats, valid_votes, votes: {parti: röster}}].

    national_valid = samtliga giltiga röster i landet (spärrbasen, inkl. övriga partier).
    """
    eligible = sorted(p for p, v in national_votes.items() if v / national_valid >= NATIONAL_THRESHOLD)

    # 1. Fasta valkretsmandat
    fixed: dict[str, dict[str, int]] = {}
    quotients: list[tuple[float, float, str, str]] = []   # (jämförelsetal, röster, valkrets, parti)
    for c in constituencies:
        part = {p: v for p, v in c["votes"].items()
                if p in eligible or v / c["valid_votes"] >= CONSTITUENCY_THRESHOLD}
        seats, won = jamkade(part, c["fixed_seats"])
        fixed[c["name"]] = {p: n for p, n in seats.items() if n}
        quotients += [(q, part[p], c["name"], p) for p, qs in won.items() for q in qs]

    # 2. Hela landets fördelning (partier med lokal 12 %-spärr behåller sina fasta mandat)
    local_only = sum(n for row in fixed.values() for p, n in row.items() if p not in eligible)
    entitlement, _ = jamkade({p: national_votes[p] for p in eligible}, total_seats - local_only)

    # 3. Återföring vid överhäng: lägst jämförelsetal först
    returned: list[tuple[str, str]] = []
    fixed_tot = {p: sum(row.get(p, 0) for row in fixed.values()) for p in eligible}
    for p in eligible:
        excess = fixed_tot[p] - entitlement[p]
        if excess > 0:
            own = sorted((q, -v, vk) for q, v, vk, pp in quotients if pp == p)
            for q, _, vk in own[:excess]:
                fixed[vk][p] -= 1
                if fixed[vk][p] == 0:
                    del fixed[vk][p]
                returned.append((vk, p))
            fixed_tot[p] -= excess

    # 4. Utjämningsmandat och placering i valkretsar
    by_name = {c["name"]: c for c in constituencies}
    adjustment: dict[str, dict[str, int]] = {c["name"]: {} for c in constituencies}
    for p in eligible:
        need = entitlement[p] - fixed_tot[p]
        for _ in range(max(0, need)):
            cands = []
            for vk, c in by_name.items():
                v = c["votes"].get(p, 0)
                if v <= 0:
                    continue
                k = fixed[vk].get(p, 0) + adjustment[vk].get(p, 0)
                cands.append((v / placement_divisor(k), v, vk))
            vk = _pick(cands)
            adjustment[vk][p] = adjustment[vk].get(p, 0) + 1

    total: dict[str, int] = {}
    for row in list(fixed.values()) + list(adjustment.values()):
        for p, n in row.items():
            total[p] = total.get(p, 0) + n
    return RiksdagResult(fixed=fixed, adjustment=adjustment, total=total, entitlement=entitlement,
                         eligible=eligible, returned=returned)
