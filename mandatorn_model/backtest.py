"""mandatorn_model.backtest — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import pandas as pd
from mandatorn_model.constants import (
    BASELINE,
    BASELINE_ELECTION_DATE,
    PARTIES,
    PARTY_NAMES,
)
from mandatorn_model.kalman import aggregate_polls_kalman

def compute_backtesting(
    polls_df: pd.DataFrame,
    house_weights_df: pd.DataFrame,
    election_date: datetime | None = None,
    actual: dict | None = None,
) -> pd.DataFrame:
    """
    Backtesting: kör aggregatorn månadsvis från 365 dagar före valet t.o.m.
    7 dagar före. Returnerar DataFrame med estimat, faktiskt resultat och fel (pp)
    per parti och referensdatum. Default: baslinjeåret (2026).
    """
    if election_date is None:
        election_date = BASELINE_ELECTION_DATE
    if actual is None:
        actual = BASELINE

    # Månadsvis + täta punkter nära valet för hög upplösning
    monthly = list(range(365, 29, -30))          # 365, 335, 305, …, 35
    fine    = [28, 21, 14, 10, 7]                # finare upplösning sista månaden
    test_offsets = sorted(set(monthly + fine), reverse=True)

    rows = []
    for days_before in test_offsets:
        ref = election_date - timedelta(days=days_before)
        est = aggregate_polls_kalman(
            polls_df,
            house_weights=house_weights_df,
            reference_date=ref,
            window_days=365,
        )
        for p in PARTIES:
            rows.append({
                "Referensdatum": ref.strftime("%Y-%m-%d"),
                "Dagar till val": days_before,
                "Parti": PARTY_NAMES.get(p, p),
                "Estimat (%)": round(est.get(p, 0), 2),
                "Faktiskt (%)": actual[p],
                "Fel (pp)": round(est.get(p, 0) - actual[p], 2),
            })
    return pd.DataFrame(rows)


def backtest_house_weights(polls_df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Institutsvikter för backtest av valet `year`, kalibrerade mot valet innan (D19).

    Tidigare användes vikter kalibrerade mot facit för samma (eller ett senare) val,
    vilket gjorde backtesten för optimistisk (PARITY A8).
    """
    from mandatorn_model.constants import ELECTION_2018, ELECTION_2022, NATIONAL_2018, NATIONAL_2022
    from mandatorn_model.polls import compute_house_weights

    prior = {2026: (ELECTION_2022, NATIONAL_2022, "2022"), 2022: (ELECTION_2018, NATIONAL_2018, "2018")}
    date, actual, label = prior[year]
    return compute_house_weights(polls_df, election_date=date, actual=actual, label=label)
