"""
Nowcasting för riksdagsvalnatten.

Implementerar metoden från valprognos.se: prognosen baseras på *förändringar*
(deltas) i röstandel jämfört med ett baslinjeval bland hittills räknade
distrikt, snarare än absoluta nivåer. Detta motverkar systematisk snedvridning
från räkningsordningen (små landsbygdsdistrikt rapporterar tidigt).

Algoritm (artikel sektion 2):
    1. För varje parti p: delta_p = current_share_in_counted − baseline_share_in_counted
    2. För oräknade distrikt: prognosticerad andel = baseline_share_in_uncounted + delta_p
    3. Slutlig prognos = viktat genomsnitt av faktiska röster (räknade) och
       prognosticerade röster (oräknade), viktat efter distriktsstorlek.

Källa: 'Nowcasting på valnatten – metod och utvärdering från valprognos.se'.
"""
from __future__ import annotations

import pandas as pd

PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"]
RIKSDAG_THRESHOLD = 0.04
RIKSDAG_TOTAL_SEATS = 349


def compute_nowcast(
    counted: pd.DataFrame,
    baseline: pd.DataFrame,
    parties: list[str] = PARTIES,
) -> dict:
    """Beräkna delta-korrigerad nationell prognos.

    Args:
        counted: Räknade distrikt i pågående val. Kolumner: district_id,
            total_valid_votes, votes_<P> för varje parti P.
        baseline: ALLA distrikt från baslinjevalet (t ex 2022). Samma schema.
            Måste innehålla samtliga district_id som finns i counted plus
            alla återstående oräknade.
        parties: Lista med partikoder.

    Returns:
        Dict med:
          - {party: projected_national_share} för varje parti
          - 'coverage': andel av total röstmängd som faktiskt räknats
          - 'deltas': {party: observed_delta_among_counted}
    """
    parties = list(parties)
    vote_cols = [f"votes_{p}" for p in parties]
    _validate_schema(counted, vote_cols, name="counted")
    _validate_schema(baseline, vote_cols, name="baseline")

    if counted.empty:
        total_baseline = float(baseline["total_valid_votes"].sum())
        result = {
            p: float(baseline[f"votes_{p}"].sum()) / total_baseline for p in parties
        }
        result["coverage"] = 0.0
        result["deltas"] = {p: 0.0 for p in parties}
        return result

    counted_ids = set(counted["district_id"])
    missing = counted_ids - set(baseline["district_id"])
    if missing:
        raise ValueError(
            f"{len(missing)} räknade distrikt-ID saknas i baslinjen "
            f"(t ex {sorted(missing)[:3]})"
        )

    in_counted = baseline["district_id"].isin(counted_ids)
    baseline_counted = baseline[in_counted]
    baseline_uncounted = baseline[~in_counted]

    current_total = float(counted["total_valid_votes"].sum())
    baseline_counted_total = float(baseline_counted["total_valid_votes"].sum())
    baseline_uncounted_total = float(baseline_uncounted["total_valid_votes"].sum())

    if baseline_uncounted.empty:
        result = {
            p: float(counted[f"votes_{p}"].sum()) / current_total for p in parties
        }
        result["coverage"] = 1.0
        result["deltas"] = {
            p: float(counted[f"votes_{p}"].sum()) / current_total
            - float(baseline_counted[f"votes_{p}"].sum()) / baseline_counted_total
            for p in parties
        }
        return result

    deltas: dict[str, float] = {}
    final_shares: dict[str, float] = {}
    projected_total = current_total + baseline_uncounted_total

    for p in parties:
        actual_votes_p = float(counted[f"votes_{p}"].sum())
        current_share_p = actual_votes_p / current_total
        baseline_share_p_counted = (
            float(baseline_counted[f"votes_{p}"].sum()) / baseline_counted_total
        )
        delta_p = current_share_p - baseline_share_p_counted

        baseline_share_p_uncounted = (
            float(baseline_uncounted[f"votes_{p}"].sum()) / baseline_uncounted_total
        )
        projected_share_p_uncounted = baseline_share_p_uncounted + delta_p
        projected_votes_p_uncounted = (
            projected_share_p_uncounted * baseline_uncounted_total
        )

        deltas[p] = delta_p
        final_shares[p] = (
            actual_votes_p + projected_votes_p_uncounted
        ) / projected_total

    final_shares["coverage"] = current_total / projected_total
    final_shares["deltas"] = deltas
    return final_shares


def modified_sainte_lague(
    votes: dict, n_seats: int = RIKSDAG_TOTAL_SEATS, first_divisor: float = 1.4
) -> dict:
    """Modifierad Sainte-Laguë (jämkade uddatalsmetoden).

    Args:
        votes: {party: vote_share_or_count} för partier som klarat spärren.
        n_seats: Antal mandat att fördela.
        first_divisor: 1.4 nationellt (riksdagens spärrnivå), 1.2 i valkretsar.

    Returns:
        {party: seat_count}.
    """
    seats = {p: 0 for p in votes}
    for _ in range(n_seats):
        quotients = {
            p: votes[p] / (first_divisor if seats[p] == 0 else (2 * seats[p] + 1))
            for p in votes
        }
        winner = max(quotients, key=quotients.get)
        seats[winner] += 1
    return seats


def project_mandates(
    nowcast: dict,
    parties: list[str] = PARTIES,
    threshold: float = RIKSDAG_THRESHOLD,
    n_seats: int = RIKSDAG_TOTAL_SEATS,
) -> dict:
    """Tillämpa 4%-spärr och fördela mandat nationellt."""
    qualifying = {p: nowcast[p] for p in parties if nowcast[p] >= threshold}
    if not qualifying:
        return {p: 0 for p in parties}
    seats = modified_sainte_lague(qualifying, n_seats=n_seats)
    return {p: seats.get(p, 0) for p in parties}


def simulate_election_night(
    actual: pd.DataFrame,
    baseline: pd.DataFrame,
    counting_order: list | pd.Series,
    coverage_levels: list[float] | None = None,
    parties: list[str] = PARTIES,
) -> pd.DataFrame:
    """Spela upp en valnatt och utvärdera nowcast mot råräkning.

    Args:
        actual: Faktiska resultat för det aktuella valet, alla distrikt.
        baseline: Baslinjevalets resultat, alla distrikt.
        counting_order: district_id i räkningsordning (tidigast först).
        coverage_levels: Täckningsgrader att utvärdera.
        parties: Lista med partikoder.

    Returns:
        DataFrame med en rad per (coverage, party): raw_share, nowcast_share,
        true_share, raw_error, nowcast_error.
    """
    if coverage_levels is None:
        coverage_levels = [0.01, 0.05, 0.10, 0.20, 0.50, 1.00]

    counting_order = pd.Series(list(counting_order))
    true_total = float(actual["total_valid_votes"].sum())
    true_shares = {
        p: float(actual[f"votes_{p}"].sum()) / true_total for p in parties
    }

    n_total = len(counting_order)
    rows = []
    for cov in coverage_levels:
        n_counted = max(1, int(round(cov * n_total)))
        counted_ids = set(counting_order.iloc[:n_counted])
        counted = actual[actual["district_id"].isin(counted_ids)]
        counted_total = float(counted["total_valid_votes"].sum())

        nowcast = compute_nowcast(counted, baseline, parties)

        for p in parties:
            raw_share = (
                float(counted[f"votes_{p}"].sum()) / counted_total
                if counted_total > 0
                else 0.0
            )
            rows.append(
                {
                    "coverage": cov,
                    "party": p,
                    "raw_share": raw_share,
                    "nowcast_share": nowcast[p],
                    "true_share": true_shares[p],
                    "raw_error": abs(raw_share - true_shares[p]),
                    "nowcast_error": abs(nowcast[p] - true_shares[p]),
                }
            )

    return pd.DataFrame(rows)


def _validate_schema(df: pd.DataFrame, vote_cols: list[str], name: str) -> None:
    required = {"district_id", "total_valid_votes", *vote_cols}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} saknar kolumner: {sorted(missing)}")
