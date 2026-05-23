"""Validera nowcast-algoritmen mot verklig 2022-data.

Spelar upp riksdagsvalet 2022 i räkningsordning och jämför MAE för
råräkning vs delta-korrigerad nowcast vid olika täckningsgrader.

Två scenarier testas:
    1. Ren storlekssortering: små distrikt först (worst-case bias)
    2. Brusig storlekssortering: storlek förklarar ~20 % av räkningsordningen,
       resten är logistiskt slumpvarians (artikelns observation)

Förväntade artikel-siffror (RD 2022, MAE i procentenheter):
    Täckning  Råräkning  Nowcast
    5 %       1.03       0.52
    10 %      0.77       0.37
    20 %      0.48       0.17
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import load_aligned_pair
from nowcast import PARTIES, simulate_election_night

ARTIKEL_MAE = {
    0.01: (2.10, 1.15),
    0.05: (1.03, 0.52),
    0.10: (0.77, 0.37),
    0.20: (0.48, 0.17),
    0.50: (0.13, 0.06),
    1.00: (0.05, 0.05),
}


def order_by_size(actual: pd.DataFrame) -> list[int]:
    """Ren storlekssortering, små distrikt först."""
    return actual.sort_values("total_valid_votes")["district_id"].tolist()


def order_by_size_with_noise(
    actual: pd.DataFrame, noise_ratio: float = 4.0, seed: int = 42
) -> list[int]:
    """Storlek + logistiskt brus (artikelns observation: storlek förklarar
    ~20 % av räkningsordningen)."""
    rng = np.random.default_rng(seed)
    sizes = actual["total_valid_votes"].values.astype(float)
    size_z = (sizes - sizes.mean()) / sizes.std()
    noise = rng.standard_normal(len(sizes)) * noise_ratio
    score = size_z + noise
    return actual.iloc[np.argsort(score)]["district_id"].tolist()


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("coverage")
        .agg(
            raw_mae_pe=("raw_error", lambda s: round(s.mean() * 100, 2)),
            nowcast_mae_pe=("nowcast_error", lambda s: round(s.mean() * 100, 2)),
        )
    )


def main() -> None:
    baseline, actual = load_aligned_pair()
    print(f"Laddade {len(actual)} distrikt (inner join 2018 och 2022)")
    print()

    coverage_levels = [0.01, 0.05, 0.10, 0.20, 0.50, 1.00]

    scenarios = {
        "Ren storlekssortering": order_by_size(actual),
        "Storlek + brus (~80% noise)": order_by_size_with_noise(actual),
    }

    rows = []
    for name, order in scenarios.items():
        df = simulate_election_night(
            actual, baseline, counting_order=order,
            coverage_levels=coverage_levels, parties=PARTIES,
        )
        for cov, (raw, now) in summarize(df).iterrows():
            artikel_raw, artikel_now = ARTIKEL_MAE.get(cov, (None, None))
            rows.append({
                "Scenario": name,
                "Tackning": f"{cov:.0%}",
                "Mitt RAW (pe)": raw,
                "Artikel RAW": artikel_raw,
                "Mitt NOWCAST": now,
                "Artikel NOWCAST": artikel_now,
            })

    report = pd.DataFrame(rows)
    print("Validering mot artikelns siffror:")
    print(report.to_string(index=False))
    print()
    print("Tolkning: 'Storlek + brus' bor matcha artikeln eftersom artikelns")
    print("verkliga tidsstamplar har ~80 % slumpvarians enligt deras OLS-regression.")
    print("'Ren storlekssortering' ar worst-case (maximal bias).")


if __name__ == "__main__":
    main()
