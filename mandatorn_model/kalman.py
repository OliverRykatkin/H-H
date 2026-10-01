"""mandatorn_model.kalman — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import numpy as np
import pandas as pd
from mandatorn_model.constants import (
    ANCHOR_COMPANY,
    ANCHOR_SIGMA,
    BASELINE,
    BASELINE_ELECTION_DATE,
    PARTIES,
    PARTIES_WITH_OTHER,
    PARTY_NAMES,
)

def aggregate_polls(
    df: pd.DataFrame,
    window_days: int = 90,
    decay_halflife_days: int = 30,
    use_house_weights: bool = True,
    house_weights: pd.DataFrame = None,
    reference_date: datetime = None,
) -> dict:
    """
    Viktat medelvärde med tre viktkällor:
      1. Tidsvikt  – exponentiellt avtagande (nyare mätning = tyngre)
      2. Urvalsvikt – sqrt(n) per mätning
      3. Institutsvikt – baserad på träffsäkerhet mot 2022 års val (valbar)

    reference_date: om angiven används detta datum som "idag" (för backtesting).
    """
    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=window_days)
    recent = df[(df["PublDate"] >= cutoff) & (df["PublDate"] < now)].copy()
    if recent.empty:
        return BASELINE.copy()

    recent["days_ago"] = (now - recent["PublDate"]).dt.days
    decay = np.log(2) / decay_halflife_days
    recent["time_weight"] = np.exp(-decay * recent["days_ago"])
    n_col = pd.to_numeric(recent["n"], errors="coerce").fillna(1000)
    recent["n_weight"] = np.sqrt(n_col)

    if use_house_weights and house_weights is not None and not house_weights.empty:
        weight_map = dict(zip(house_weights["Institut"], house_weights["Vikt"]))
        recent["house_weight"] = recent["Company"].map(weight_map).fillna(1.0)
    else:
        recent["house_weight"] = 1.0

    recent["weight"] = recent["time_weight"] * recent["n_weight"] * recent["house_weight"]

    result = {}
    for p in PARTIES:
        valid = recent[recent[p].notna()].copy()
        result[p] = float(np.average(valid[p], weights=valid["weight"])) if not valid.empty else BASELINE[p]
    return result


def _anchor_to_baseline(recent: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Efter baslinjevalet: släng mätningar t.o.m. valdagen och lägg valresultatet
    som första observation, så att filtret startar i utfallet och bara
    mätningar efter valet flyttar det. Valdagens vallokalsundersökningar
    (PublDate == valdagen) räknas som före valet."""
    election = pd.Timestamp(BASELINE_ELECTION_DATE)
    if pd.Timestamp(now) <= election:
        return recent
    after = recent[recent["PublDate"] > election]
    anchor = {p: BASELINE.get(p, np.nan) for p in PARTIES}
    anchor["O"] = max(0.0, 100.0 - sum(BASELINE.get(p, 0.0) for p in PARTIES))
    anchor.update({"PublDate": election, "Company": ANCHOR_COMPANY, "n": np.nan})
    return pd.concat([pd.DataFrame([anchor]), after], ignore_index=True)


def _obs_sigma(y: float, n: float, company: str, hw_map: dict) -> float:
    if company == ANCHOR_COMPANY:
        return ANCHOR_SIGMA
    p_frac = np.clip(y / 100.0, 0.01, 0.99)
    # Stickprovsvarians i pp²
    var_samp = p_frac * (1.0 - p_frac) * 10_000.0 / max(float(n), 100.0)
    # Institutsbrus: sämre institut → mer osäkerhet (skalas med 1/vikt²)
    hw = max(hw_map.get(company, 1.0), 0.2)
    return float(np.sqrt(max(var_samp / hw**2, 0.09)))  # min 0.3 pp


def aggregate_polls_kalman(
    df: pd.DataFrame,
    house_weights: pd.DataFrame = None,
    reference_date: datetime = None,
    sigma_process_per_day: float = 0.10,
    window_days: int = 365,
) -> dict:
    # df/house_weights hashas medvetet (inget understreck) så cachen
    # invalideras när nya opinionsmätningar tillkommer.

    # Referensdatum: idag om inget annat anges.
    # Det gör att estimatet uppdateras varje dag fönstret rullar
    # och gamla mätningar faller ur — även utan ny opinionsmätning.
    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=window_days)
    recent = df[(df["PublDate"] >= cutoff) & (df["PublDate"] <= now)].copy()
    recent = _anchor_to_baseline(recent, now)

    if recent.empty:
        return BASELINE.copy()

    recent = recent.sort_values("PublDate", kind="stable").reset_index(drop=True)

    # Institutsvikter: lägre vikt → mer mätningsmässigt brus
    hw_map = {}
    if house_weights is not None and not house_weights.empty:
        hw_map = dict(zip(house_weights["Institut"], house_weights["Vikt"]))

    t0 = recent["PublDate"].min()
    t_now = float((now - t0).days)

    results = {}

    for party in PARTIES:
        y_col  = pd.to_numeric(recent[party], errors="coerce")
        n_col  = pd.to_numeric(recent["n"],   errors="coerce").fillna(1000.0)
        valid  = y_col.notna()

        if valid.sum() == 0:
            results[party] = BASELINE.get(party, 0.0)
            continue

        t_obs = (recent.loc[valid, "PublDate"] - t0).dt.days.astype(float).values
        y_obs = y_col[valid].values
        n_obs = n_col[valid].values
        co_obs = recent.loc[valid, "Company"].fillna("").values

        sigma_obs = np.array([
            _obs_sigma(y, n, c, hw_map) for y, n, c in zip(y_obs, n_obs, co_obs)
        ])

        # ── Kalman-filter (framåtpass) ──
        n_pts = len(t_obs)
        xf = np.zeros(n_pts)
        Pf = np.zeros(n_pts)
        xf[0] = y_obs[0]
        Pf[0] = sigma_obs[0] ** 2

        for i in range(1, n_pts):
            dt   = max(float(t_obs[i] - t_obs[i - 1]), 1.0)
            Q    = sigma_process_per_day ** 2 * dt
            xp   = xf[i - 1]
            Pp   = Pf[i - 1] + Q
            R    = sigma_obs[i] ** 2
            K    = Pp / (Pp + R)
            xf[i] = xp + K * (y_obs[i] - xp)
            Pf[i] = (1.0 - K) * Pp

        # ── RTS-smoother (bakåtpass) ──
        xs = xf.copy()
        Ps = Pf.copy()
        for i in range(n_pts - 2, -1, -1):
            dt        = max(float(t_obs[i + 1] - t_obs[i]), 1.0)
            Q         = sigma_process_per_day ** 2 * dt
            P_pred    = Pf[i] + Q
            G         = Pf[i] / P_pred
            xs[i]     = xf[i] + G * (xs[i + 1] - xf[i])
            Ps[i]     = Pf[i] + G ** 2 * (Ps[i + 1] - P_pred)

        # ── Prediktion framåt till reference_date ──
        dt_ahead   = max(t_now - t_obs[-1], 0.0)
        x_now      = float(xs[-1])   # RTS-smoothat slutvärde
        # (vid prediktion bortom data faller vi tillbaka på filterets slutvärde)
        if dt_ahead > 0:
            x_now = float(xf[-1])   # filtervärde är bättre att extrapolera från

        results[party] = float(np.clip(x_now, 0.0, 100.0))

    # Normalisera till 100 %
    total = sum(results.values())
    if total > 0:
        results = {p: v / total * 100.0 for p, v in results.items()}

    return results


def aggregate_polls_kalman_timeseries(
    df: pd.DataFrame,
    house_weights: pd.DataFrame = None,
    reference_date: datetime = None,
    sigma_process_per_day: float = 0.10,
    window_days: int = 365,
) -> dict:
    """
    Samma Kalman-filter som aggregate_polls_kalman men returnerar hela
    tidsserien (300 interpolerade punkter t.o.m. idag) per parti.
    Används av make_trend_chart så att trenden överensstämmer med estimaten.

    df/house_weights hashas medvetet (inget understreck) så cachen
    invalideras när nya opinionsmätningar tillkommer.

    Returns: {parti: {"eval_dates": [...], "smooth_y": [...], "smooth_std": [...]}}
    """
    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=window_days)
    recent = df[(df["PublDate"] >= cutoff) & (df["PublDate"] <= now)].copy()
    recent = _anchor_to_baseline(recent, now)

    if recent.empty:
        return {}

    recent = recent.sort_values("PublDate", kind="stable").reset_index(drop=True)

    hw_map = {}
    if house_weights is not None and not house_weights.empty:
        hw_map = dict(zip(house_weights["Institut"], house_weights["Vikt"]))

    t0 = recent["PublDate"].min()
    t_now = float((now - t0).days)

    timeseries = {}

    for party in PARTIES_WITH_OTHER:
        y_col = pd.to_numeric(recent[party], errors="coerce")
        n_col = pd.to_numeric(recent["n"], errors="coerce").fillna(1000.0)
        valid = y_col.notna()

        if valid.sum() == 0:
            continue

        t_obs = (recent.loc[valid, "PublDate"] - t0).dt.days.astype(float).values
        y_obs = y_col[valid].values
        n_obs = n_col[valid].values
        co_obs = recent.loc[valid, "Company"].fillna("").values

        sigma_obs_arr = np.array([
            _obs_sigma(y, n, c, hw_map) for y, n, c in zip(y_obs, n_obs, co_obs)
        ])

        n_pts = len(t_obs)
        xf = np.zeros(n_pts)
        Pf = np.zeros(n_pts)
        xf[0] = y_obs[0]
        Pf[0] = sigma_obs_arr[0] ** 2

        for i in range(1, n_pts):
            dt = max(float(t_obs[i] - t_obs[i - 1]), 1.0)
            Q = sigma_process_per_day ** 2 * dt
            xp = xf[i - 1]
            Pp = Pf[i - 1] + Q
            R = sigma_obs_arr[i] ** 2
            K = Pp / (Pp + R)
            xf[i] = xp + K * (y_obs[i] - xp)
            Pf[i] = (1.0 - K) * Pp

        xs = xf.copy()
        Ps = Pf.copy()
        for i in range(n_pts - 2, -1, -1):
            dt = max(float(t_obs[i + 1] - t_obs[i]), 1.0)
            Q = sigma_process_per_day ** 2 * dt
            P_pred = Pf[i] + Q
            G = Pf[i] / P_pred
            xs[i] = xf[i] + G * (xs[i + 1] - xf[i])
            Ps[i] = Pf[i] + G ** 2 * (Ps[i + 1] - P_pred)

        # Interpolera + extrapolera till idag (300 punkter)
        t_end = max(t_obs.max(), t_now)
        eval_days = np.linspace(t_obs.min(), t_end, 300)
        smooth_y = np.interp(eval_days, t_obs, xs)
        smooth_std_interp = np.interp(eval_days, t_obs, Ps)
        dt_beyond = np.maximum(eval_days - t_obs.max(), 0.0)
        smooth_std_total = smooth_std_interp + sigma_process_per_day ** 2 * dt_beyond
        smooth_std = np.sqrt(np.maximum(smooth_std_total, 0.0))

        eval_dates = [t0 + timedelta(days=float(d)) for d in eval_days]

        timeseries[party] = {
            "eval_dates": eval_dates,
            "smooth_y": smooth_y.tolist(),
            "smooth_std": smooth_std.tolist(),
        }

    return timeseries


def kalman_smooth(
    dates_num: np.ndarray,
    y_vals: np.ndarray,
    sigma_obs: float = 1.8,
    sigma_process_per_day: float = 0.10,
    extend_to_day: float = None,
) -> tuple:
    """
    Kalman filter (forward pass) + RTS-smoother (bakåtpass) för opinionstrender.

    Modell (diskret, oregelbundna tidssteg):
      Tillstånd:    x[t] = x[t-1] + w[t],   w[t] ~ N(0, σ_process² · Δt)
      Observation:  y[t] = x[t]  + v[t],   v[t] ~ N(0, σ_obs²)

    Returnerar tre numpy-arrayer:
      smooth_y   – smoothad trend (posterior medelvärde) vid 300 jämna utvärderingspunkter
      smooth_std – posterior standardavvikelse (→ 95 % CI = ±1.96 × smooth_std)
      eval_days  – tidsaxel (dagar från min) för de 300 punkterna
    """
    n = len(dates_num)
    if n == 0:
        return np.array([]), np.array([]), np.array([])

    sort_idx = np.argsort(dates_num)
    t = dates_num[sort_idx].astype(float)
    y = y_vals[sort_idx].astype(float)

    # ── Framåtgående Kalman-filter ──
    xf = np.zeros(n)
    Pf = np.zeros(n)

    xf[0] = y[0]
    Pf[0] = sigma_obs ** 2

    for i in range(1, n):
        dt = max(float(t[i] - t[i - 1]), 1.0)
        Q = sigma_process_per_day ** 2 * dt
        # Prediktion
        xp = xf[i - 1]
        Pp = Pf[i - 1] + Q
        # Uppdatering
        K = Pp / (Pp + sigma_obs ** 2)
        xf[i] = xp + K * (y[i] - xp)
        Pf[i] = (1.0 - K) * Pp

    # ── RTS-smoother (bakåtpass) ──
    xs = xf.copy()
    Ps = Pf.copy()

    for i in range(n - 2, -1, -1):
        dt = max(float(t[i + 1] - t[i]), 1.0)
        Q = sigma_process_per_day ** 2 * dt
        G = Pf[i] / (Pf[i] + Q)
        xs[i] = xf[i] + G * (xs[i + 1] - xf[i])
        Ps[i] = Pf[i] + G ** 2 * (Ps[i + 1] - (Pf[i] + Q))

    # ── Interpolera + extrapolera till extend_to_day (t.o.m. idag) ──
    # För dagar bortom sista observation håller vi filtrets slutvärde
    # (xs[-1]) konstant och låter osäkerheten växa med processbruset.
    t_end = max(t.max(), extend_to_day) if extend_to_day is not None else t.max()
    eval_days = np.linspace(t.min(), t_end, 300)

    # Interpolera inom observationsperioden; clip ger sista värdet för extrapolation
    smooth_y = np.interp(eval_days, t, xs)

    # Osäkerhet: interpolera inom perioden, öka kvadratiskt utanför (random walk)
    smooth_std_interp = np.interp(eval_days, t, Ps)
    dt_beyond = np.maximum(eval_days - t.max(), 0.0)
    smooth_std_total = smooth_std_interp + sigma_process_per_day ** 2 * dt_beyond
    smooth_std = np.sqrt(np.maximum(smooth_std_total, 0.0))

    return smooth_y, smooth_std, eval_days


def build_trend_data(timeseries: dict) -> pd.DataFrame:
    """
    Returnerar en DataFrame med Kalman-smoothade dagliga estimat per parti,
    samma data som visas i trendgrafen. Används för nedladdning.
    Kolumner: Datum, M (%), L (%), C (%), KD (%), S (%), V (%), MP (%), SD (%)

    timeseries: output från aggregate_polls_kalman_timeseries()
    """
    series: dict = {}

    for p in PARTIES:
        ts = timeseries.get(p)
        if ts is None:
            continue
        eval_dates = pd.to_datetime(ts["eval_dates"]).round("D")
        smooth_y = np.array(ts["smooth_y"])
        s = pd.Series(smooth_y, index=eval_dates).rename(PARTY_NAMES.get(p, p))
        s = s[~s.index.duplicated(keep="last")]
        series[p] = s

    if not series:
        return pd.DataFrame()

    result = pd.DataFrame(series)
    result.index.name = "Datum"
    result.index = pd.to_datetime(result.index).strftime("%Y-%m-%d")
    result.columns = [PARTY_NAMES.get(c, c) + " (%)" for c in result.columns]
    result = result.round(2)
    return result.reset_index()
