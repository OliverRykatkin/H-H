"""mandatorn_model.regional — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

import pandas as pd
from mandatorn_model.constants import (
    LAN_TO_REGION_NAME,
    PARTIES,
    _ELECTION_2026,
)
from mandatorn_model.muni_mandates import load_structure_cached

def load_area_results(val_type: str) -> tuple[pd.DataFrame, dict]:
    """Senaste valets resultat per kommun/region för Regional-fliken.

    val_type: "RD" (riksdag per kommun), "KF" (kommunval) eller "RF" (regionval).
    Returnerar (DataFrame[region_code, party, pct_base], övriga_per_area) där
    region_code är 4-siffrig kommunkod (RD/KF) eller GeoJSON-regionnamn (RF) och
    övriga_per_area = andel för partier utanför de åtta (lokala partier m.fl.).
    Källa: Valmyndighetens slutliga resultat (data/election_2026.json och
    data/muni_structure_2026.json).
    """
    rows, ovriga = [], {}
    if val_type == "RD":
        for kod, shares in _ELECTION_2026.get("kommuner", {}).items():
            rows += [{"region_code": kod, "party": p, "pct_base": shares.get(p, 0.0)} for p in PARTIES]
    else:
        struct = load_structure_cached() or {}
        for kod, area in struct.get(val_type, {}).items():
            code = kod if val_type == "KF" else LAN_TO_REGION_NAME.get(kod)
            if code is None:
                continue
            total = sum(vk.get("total_2022", 0) for vk in area["valkretsar"])
            if total <= 0:
                continue
            votes = {p: sum(vk.get("votes_2022", {}).get(p, 0) for vk in area["valkretsar"]) for p in PARTIES}
            pct = {p: v / total * 100.0 for p, v in votes.items()}
            rows += [{"region_code": code, "party": p, "pct_base": pct[p]} for p in PARTIES]
            ovriga[code] = max(0.0, 100.0 - sum(pct.values()))
    return pd.DataFrame(rows, columns=["region_code", "party", "pct_base"]), ovriga


def compute_national_swing(
    current: dict, baseline: dict, parties: list | None = None
) -> dict:
    """Nollsummerad nationell sving (procentenheter).

    Normaliserar både nuläget (polls) och 2022 till samma bas — summa 100 över de
    8 riksdagspartierna — innan differensen tas. Polls saknar "övriga" medan 2022
    reserverar ~1,5 pp för övriga, så en rå differens (current − 2022) summerar
    till ~+1,5 pp. Den per-område-normaliseringen i uniform swing-modellen fördelar
    då det överskottet proportionellt mot partistorlek, vilket felaktigt förstärker
    stora partiers sving i områden där de är starka. Nollsummering tar bort det:
    svingen blir enhetlig över alla områden och mäter andelsförändring bland de 8
    riksdagspartierna (exkl. övriga).
    """
    parties = parties or PARTIES

    def _norm(d: dict) -> dict:
        s = sum(float(d.get(p, 0)) for p in parties)
        if s <= 0:
            return {p: 0.0 for p in parties}
        return {p: float(d.get(p, 0)) / s * 100.0 for p in parties}

    cur, base = _norm(current), _norm(baseline)
    return {p: cur[p] - base[p] for p in parties}


def apply_uniform_swing(
    df: pd.DataFrame,
    national_current: dict,
    national_base: dict,
    ovriga_per_area: dict | None = None,
) -> pd.DataFrame:
    """
    Uniform swing-modell:
      predicted[p][area] = baslinje_lokalt[p][area] + total_swing[p]
      total_swing[p] = nollsummerad nationell sving (se compute_national_swing)

    Normaliseras per geografisk enhet.
    Om ovriga_per_area anges (kommunalval/regionval) summeras de 8 partierna
    till (100 − ÖVRIGA%) per område, så att ÖVRIGA antas hålla sin baslinjenivå.
    Svingen är nollsummerad så att den inte förstärks proportionellt mot
    partistorlek vid omnormaliseringen.
    """
    if df.empty:
        return df

    swings = compute_national_swing(national_current, national_base)

    result = df.copy()
    result["swing"] = result["party"].map(swings).fillna(0.0)
    result["pct_raw"] = (result["pct_base"] + result["swing"]).clip(lower=0.0)

    region_totals = result.groupby("region_code")["pct_raw"].sum()
    result["_rtot"] = result["region_code"].map(region_totals)

    _ovriga = ovriga_per_area or {}
    result["pct_predicted"] = result.apply(
        lambda r: (
            r["pct_raw"] / r["_rtot"] * (100.0 - _ovriga.get(r["region_code"], 0.0))
            if r["_rtot"] > 0 else 0.0
        ),
        axis=1,
    )
    return result.drop(columns=["swing", "pct_raw", "_rtot"])
