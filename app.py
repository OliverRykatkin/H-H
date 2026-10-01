"""
Riksdagsprediction – Opinionsundersökningsaggregator
=====================================================
En interaktiv webbapp som aggregerar svenska opinionsmätningar och
beräknar mandatfördelning per riksdagsvalkrets.

Datakällor:
  - Opinionsundersökningar: MansMeg/SwedishPolls (GitHub)
  - Valresultat 2022 per valkrets: Valmyndigheten (hårdkodade)
  - Karta: okfse/sweden-geojson (GitHub)

Modell:
  - Aggregering: viktat medelvärde (tid + stickprovsstorlek)
  - Valkretsar: naiv offset-modell baserad på 2022 års avvikelse
  - Mandatfördelning: modifierad Sainte-Laguë + utjämningsmandat
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

from mandatorn_model.constants import (
    GEOJSON_URL,
    PARTIES,
    PARTIES_WITH_OTHER,
    PARTY_NAMES,
    PARTY_COLORS,
    BLOC_PARTIES,
    COALITIONS,
    NATIONAL_2022,
    ELECTION_2022,
    BASELINE,
    BASELINE_YEAR,
    BASELINE_ELECTION_DATE,
    NEXT_ELECTION,
    NEXT_ELECTION_YEAR,
    TREND_START,
    TREND_ELECTIONS,
    MUNI_GEOJSON_URL,
    REGION_GEOJSON_URL,
    REGION_NAME_TO_LAN,
    CONSTITUENCIES_2022,
    CONSTITUENCIES,
    COUNTY_TO_CONSTITUENCIES,
    THRESHOLD,
)
from mandatorn_model import polls as _m_polls
from mandatorn_model import candidates as _m_candidates
from mandatorn_model.kalman import (
    kalman_smooth,
    build_trend_data,
)
from mandatorn_model.seats import (
    estimate_constituency_votes,
    compute_baseline_mandates,
    allocate_all_mandates,
)
from mandatorn_model.margins import (
    compute_national_margins,
    compute_constituency_margins,
    compute_closest_fixed_seats,
)
from mandatorn_model.candidates import (
    predict_elected_candidates,
    predict_adjustment_constituencies,
    predict_adjustment_candidates,
)
from mandatorn_model.regional import (
    load_area_results,
    compute_national_swing,
    apply_uniform_swing,
)
from mandatorn_model.backtest import (
    backtest_house_weights,
    compute_backtesting,
)
from mandatorn_model.valnatt import (
    _load_valnatt_2026,
    _valnatt_times,
    _valnatt_state,
    _valnatt_error_curve,
)

from mandatorn_model.forecast import WINDOW_DAYS, build_forecast, reference_day
from mandatorn_model.probabilities import coalition_summary, evaluate_questions
from mandatorn_model.text import display_pct, verbal

# Streamlit-cache runt modellfunktionerna (paketet är fritt från streamlit)
build_forecast_cached = st.cache_data(show_spinner=False)(build_forecast)


@st.cache_data(ttl=3600)
def load_polls() -> pd.DataFrame:
    try:
        text = _m_polls.fetch_polls_text()
    except Exception as e:
        st.warning(f"Kunde inte hämta data från GitHub: {e}")
        return pd.DataFrame()
    return _m_polls.parse_polls(text)


load_area_results = st.cache_data(show_spinner=False)(load_area_results)


@st.cache_data(ttl=3600)
def load_candidates() -> pd.DataFrame:
    try:
        text = _m_candidates.fetch_candidates_text()
    except Exception as e:
        st.warning(f"Kunde inte hämta kandidatdata: {e}")
        return pd.DataFrame()
    return _m_candidates.parse_candidates(text)


compute_baseline_mandates = st.cache_data(compute_baseline_mandates)
compute_national_margins = st.cache_data(show_spinner=False)(compute_national_margins)
compute_constituency_margins = st.cache_data(show_spinner=False)(compute_constituency_margins)
compute_closest_fixed_seats = st.cache_data(show_spinner=False)(compute_closest_fixed_seats)
compute_backtesting = st.cache_data(ttl=86400)(compute_backtesting)
_load_valnatt_2026 = st.cache_data(show_spinner=False)(_load_valnatt_2026)
_valnatt_error_curve = st.cache_data(show_spinner=False)(_valnatt_error_curve)

from mandatorn_model.nowcast import (
    PARTIES as NOWCAST_PARTIES,
)

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────







# ─────────────────────────────────────────────
# ECONOMIST-INSPIRERAD LAYOUT
# ─────────────────────────────────────────────

def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Konverterar hex-färg till rgba-sträng med given transparens."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# BasLayout utan axlar (säkert att använda med **-unpacking i update_layout)
ECONOMIST_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Arial, Helvetica, sans-serif", size=12, color="#111213"),
    xaxis=dict(
        showgrid=False,
        showline=True,
        linecolor="#cccccc",
        linewidth=1,
        tickcolor="#cccccc",
        tickfont=dict(size=11, color="#555555"),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#ebebeb",
        gridwidth=1,
        showline=False,
        zeroline=False,
        tickcolor="#cccccc",
        tickfont=dict(size=11, color="#555555"),
    ),
)

# Variant utan axelnycklar – används när man definierar xaxis/yaxis separat i update_layout
ECONOMIST_BASE = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Arial, Helvetica, sans-serif", size=12, color="#111213"),
)





















# ─────────────────────────────────────────────
# DATAINHÄMTNING
# ─────────────────────────────────────────────



@st.cache_data(ttl=86400)
def load_geojson() -> dict:
    try:
        resp = requests.get(GEOJSON_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


@st.cache_data(ttl=86400, show_spinner=False)
def load_geojson_url(url: str) -> dict:
    """Hämtar och cachar valfri GeoJSON-fil (kommuner eller regioner)."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}








def make_regional_map(
    predicted_df: pd.DataFrame,
    geojson: dict,
    featureidkey: str,
    id_col: str,
    view_mode: str,
    title: str,
    name_map: dict | None = None,
) -> go.Figure:
    """
    Skapar interaktiv choropleth-karta.
    view_mode: "leading"  → färgar efter ledande parti
               party_code → visar det partiets stöd (kontinuerlig skala)
    name_map:  dict {region_code → visningsnamn} för tydligare hover-rubriker
    """
    if predicted_df.empty or not geojson:
        return go.Figure()

    # Pivot till bredt format: en rad per area, en kolumn per parti
    wide = predicted_df.pivot_table(
        index=id_col, columns="party", values="pct_predicted", aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    for p in PARTIES:
        if p not in wide.columns:
            wide[p] = 0.0
    wide[id_col] = wide[id_col].astype(str)

    # Visningsnamn per area (kommunnamn / regionnamn)
    if name_map:
        wide["_name"] = wide[id_col].map(name_map).fillna(wide[id_col])
    else:
        wide["_name"] = wide[id_col]

    party_cols = [p for p in PARTIES if p in wide.columns]

    def _hover_detail(row):
        lines = [f"<b>📍 {row['_name']}</b>", "─────────────────"]
        lines += [
            f"{PARTY_NAMES.get(p, p)}: <b>{row.get(p, 0.0):.1f}%</b>"
            for p in party_cols
        ]
        return "<br>".join(lines)

    wide["_detail"] = wide.apply(_hover_detail, axis=1)

    if view_mode == "leading":
        wide["_leader"] = wide[party_cols].idxmax(axis=1)
        wide["_lead_pct"] = wide[party_cols].max(axis=1)
        wide["_hover"] = wide.apply(
            lambda r: (
                f"<b>📍 {r['_name']}</b><br>"
                f"Ledande: <b>{PARTY_NAMES.get(r['_leader'], r['_leader'])}"
                f" {r['_lead_pct']:.1f}%</b><br>─────────────────<br>"
                + "<br>".join(
                    f"{PARTY_NAMES.get(p, p)}: {r.get(p, 0.0):.1f}%"
                    for p in party_cols
                )
            ),
            axis=1,
        )
        fig = px.choropleth_mapbox(
            wide,
            geojson=geojson,
            locations=id_col,
            featureidkey=featureidkey,
            color="_leader",
            color_discrete_map=PARTY_COLORS,
            custom_data=["_hover"],
            mapbox_style="carto-positron",
            center={"lat": 63.0, "lon": 16.5},
            zoom=3.5,
            opacity=0.75,
            labels={"_leader": "Ledande parti"},
        )
        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")

    else:
        party = view_mode
        if party not in wide.columns:
            return go.Figure()
        wide["_hover"] = wide.apply(
            lambda r: (
                f"<b>📍 {r['_name']}</b><br>"
                f"{PARTY_NAMES.get(party, party)}: <b>{r.get(party, 0.0):.1f}%</b>"
                f"<br>─────────────────<br>"
                + "<br>".join(
                    f"{PARTY_NAMES.get(p, p)}: {r.get(p, 0.0):.1f}%"
                    for p in party_cols
                )
            ),
            axis=1,
        )
        base_color = PARTY_COLORS.get(party, "#888888")
        fig = px.choropleth_mapbox(
            wide,
            geojson=geojson,
            locations=id_col,
            featureidkey=featureidkey,
            color=party,
            color_continuous_scale=["#f0f0f0", base_color],
            range_color=[0, 45],
            custom_data=["_hover"],
            labels={party: f"{PARTY_NAMES.get(party, party)} (%)"},
            mapbox_style="carto-positron",
            center={"lat": 63.0, "lon": 16.5},
            zoom=3.5,
            opacity=0.75,
        )
        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")

    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#111213")),
        paper_bgcolor="white",
        font=dict(family="Arial, Helvetica, sans-serif", size=12),
        margin=dict(t=50, b=0, l=0, r=0),
        height=620,
        legend_title_text="Ledande parti",
    )
    return fig










# ─────────────────────────────────────────────
# AGGREGERINGSMODELL
# ─────────────────────────────────────────────

















# ─────────────────────────────────────────────
# MANDATBERÄKNING
# ─────────────────────────────────────────────









# Bakåtkompatibelt alias — call sites har inte migrerats än.
compute_2022_mandates = compute_baseline_mandates




# ─────────────────────────────────────────────
# MANDATMARGINAL — känslighetsanalys
# ─────────────────────────────────────────────











# ─────────────────────────────────────────────
# VISUALISERING
# ─────────────────────────────────────────────

def make_support_bar(
    votes: dict,
    reference_2022: dict | None = None,
    reference_year: int = BASELINE_YEAR,
) -> go.Figure:
    parties = list(votes.keys())
    values = [votes[p] for p in parties]
    colors = [PARTY_COLORS.get(p, "#888") for p in parties]
    names = [PARTY_NAMES.get(p, p) for p in parties]

    fig = go.Figure()
    ref_label = f"Valresultat {reference_year}"

    if reference_2022:
        ref_values = [reference_2022.get(p, 0) for p in parties]
        fig.add_trace(go.Bar(
            name=ref_label,
            x=names, y=ref_values,
            marker_color=colors,
            opacity=0.35,
            marker_pattern_shape="/",
            marker_line_width=0,
            showlegend=True,
            hovertemplate=f"%{{x}}<br>{ref_label}: <b>%{{y:.1f}}%</b><extra></extra>",
        ))

    fig.add_trace(go.Bar(
        name="Aktuell opinion",
        x=names, y=values,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in values],
        textposition="outside",
        marker_line_width=0,
        showlegend=bool(reference_2022),
        hovertemplate="%{x}<br>Aktuell opinion: <b>%{y:.1f}%</b><extra></extra>",
    ))

    fig.add_hline(y=4.0, line_dash="dot", line_color="#999999", line_width=1.5,
                  annotation_text="4%-spärren", annotation_position="top right",
                  annotation_font=dict(size=10, color="#666666"))
    fig.update_layout(
        **ECONOMIST_LAYOUT,
        barmode="group",
        title=dict(text=f"Aktuellt stöd vs valresultat {reference_year}", font=dict(size=13, color="#111213")),
        yaxis_title="Röstandel (%)",
        yaxis_range=[0, max(values) * 1.25 + 3],
        height=460,
        margin=dict(t=80, b=20, l=50, r=10),
        legend=dict(orientation="h", yanchor="top", y=1.12, x=0, font=dict(size=10)),
    )
    fig.update_xaxes(tickangle=-35, tickfont=dict(size=10, color="#555555"))
    return fig


def make_mandate_bar(total_mandates: dict) -> go.Figure:
    parties = [p for p in PARTIES if total_mandates.get(p, 0) > 0]
    values = [total_mandates[p] for p in parties]
    colors = [PARTY_COLORS.get(p, "#888") for p in parties]
    names = [PARTY_NAMES.get(p, p) for p in parties]

    fig = go.Figure(go.Bar(
        x=names, y=values,
        marker_color=colors,
        marker_line_width=0,
        text=values,
        textposition="outside",
        hovertemplate="%{x}: <b>%{y} mandat</b><extra></extra>",
    ))
    fig.add_hline(y=175, line_dash="dot", line_color="#EF718C", line_width=1.5,
                  annotation_text="Majoritet (175)", annotation_position="top right",
                  annotation_font=dict(size=10, color="#EF718C"))
    fig.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text="Beräknad mandatfördelning — 349 mandat totalt", font=dict(size=13, color="#111213")),
        yaxis_title="Mandat",
        yaxis_range=[0, max(values) * 1.3 + 15],
        height=460,
        margin=dict(t=70, b=20, l=50, r=10),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=-35, tickfont=dict(size=10, color="#555555"))
    return fig






def make_trend_chart(df: pd.DataFrame, window_days: int, timeseries: dict = None) -> go.Figure:
    """
    Trendgraf med Kalman-smoother och 95 % konfidensband.
    Visar institut och stickprovsstorlek i tooltip.

    timeseries: output från aggregate_polls_kalman_timeseries() — om angivet
    används samma Kalman-körning som estimaten (med husvikter), annars
    faller funktionen tillbaka på en förenklad kalman_smooth utan vikter.
    """
    recent = df[df["PublDate"] >= TREND_START].copy()

    fig = go.Figure()

    for p in PARTIES_WITH_OTHER:
        col = recent[["PublDate", p, "Company", "n"]].dropna(subset=[p]).copy()
        if col.empty and not (timeseries and p in timeseries):
            continue
        col = col.sort_values("PublDate")

        party_color = PARTY_COLORS.get(p, "#888")
        fill_color = hex_to_rgba(party_color, alpha=0.12)

        # Använd timeseries från aggregate_polls_kalman_timeseries om tillgängligt,
        # annars faller vi tillbaka på förenklad kalman_smooth (utan husvikter).
        if timeseries and p in timeseries:
            ts = timeseries[p]
            eval_dates_list = list(pd.to_datetime(ts["eval_dates"]))
            smooth_y = ts["smooth_y"]
            smooth_std_arr = np.array(ts["smooth_std"])
            upper_ci = (np.array(smooth_y) + 1.96 * smooth_std_arr).tolist()
            lower_ci = (np.array(smooth_y) - 1.96 * smooth_std_arr).tolist()
        else:
            dates_num = (col["PublDate"] - col["PublDate"].min()).dt.days.values.astype(float)
            y_vals = col[p].values.astype(float)
            today_day = float((datetime.now() - col["PublDate"].min()).days)
            smooth_y_arr, smooth_std_arr, eval_days = kalman_smooth(
                dates_num, y_vals, extend_to_day=today_day
            )
            smooth_y = smooth_y_arr.tolist()
            upper_ci = (smooth_y_arr + 1.96 * smooth_std_arr).tolist()
            lower_ci = (smooth_y_arr - 1.96 * smooth_std_arr).tolist()
            eval_dates = col["PublDate"].min() + pd.to_timedelta(eval_days, unit="D")
            eval_dates_list = list(eval_dates)

        # Skuggat 95 % konfidensband (lägg till innan linjen för rätt z-ordning)
        fig.add_trace(go.Scatter(
            x=eval_dates_list + eval_dates_list[::-1],
            y=upper_ci + lower_ci[::-1],
            fill="toself",
            fillcolor=fill_color,
            line=dict(width=0),
            showlegend=False,
            legendgroup=p,
            hoverinfo="skip",
        ))

        # Smoothad trendlinje
        fig.add_trace(go.Scatter(
            x=eval_dates_list,
            y=smooth_y,
            mode="lines",
            line=dict(color=party_color, width=2.0),
            name=PARTY_NAMES.get(p, p),
            legendgroup=p,
            hovertemplate=(
                f"<b>{PARTY_NAMES.get(p, p)}</b><br>"
                "Datum: %{x|%Y-%m-%d}<br>"
                "Trend: <b>%{y:.1f}%</b>"
                "<extra></extra>"
            ),
        ))

        # Individuella mätningar (diskreta punkter, lättare)
        company_labels = col["Company"].fillna("Okänt").tolist()
        n_labels = pd.to_numeric(col["n"], errors="coerce").fillna(0).astype(int).tolist()

        fig.add_trace(go.Scatter(
            x=col["PublDate"],
            y=col[p],
            mode="markers",
            marker=dict(
                color=party_color, size=5, opacity=0.40,
                line=dict(width=0),
            ),
            name=PARTY_NAMES.get(p, p),
            legendgroup=p,
            showlegend=False,
            customdata=list(zip(company_labels, n_labels)),
            hovertemplate=(
                f"<b>{PARTY_NAMES.get(p, p)}</b><br>"
                "Datum: %{x|%Y-%m-%d}<br>"
                "Stöd: <b>%{y:.1f}%</b><br>"
                "Institut: %{customdata[0]}<br>"
                "Urval: %{customdata[1]:,}"
                "<extra></extra>"
            ),
        ))

    fig.add_hline(y=4.0, line_dash="dot", line_color="#999999", line_width=1.5,
                  annotation_text="4%-spärren",
                  annotation_font=dict(size=10, color="#666666"),
                  annotation_position="bottom right")

    for _edate, _elabel in TREND_ELECTIONS:
        fig.add_vline(
            x=_edate.timestamp() * 1000,
            line_dash="dash",
            line_color="#555555",
            line_width=1.2,
            annotation_text=_elabel,
            annotation_font=dict(size=10, color="#555555"),
            annotation_position="top right",
        )

    fig.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text="Opinionstrender", font=dict(size=14, color="#111213")),
        yaxis_title="Röstandel (%)",
        xaxis_title="",
        height=470,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=11), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=60, b=20, l=55, r=20),
        hovermode="closest",
    )
    return fig


def make_block_trend_chart(timeseries: dict, polls_df: pd.DataFrame = None) -> go.Figure:
    """
    Trendgraf för Höger- och Vänsterblocket över tid.
    Summerar Kalman-tidsserierna per block; konfidensbandet är approximativt
    (variansadditiv, samma stil som per-partitrenden). Om polls_df anges
    ritas även de enskilda mätningarnas blocksummor som diskreta punkter.
    """
    fig = go.Figure()

    block_colors = {
        "Högerblocket": "#29BFA2",
        "Vänsterblocket": "#EF718C",
    }

    recent_polls = None
    if polls_df is not None and not polls_df.empty:
        recent_polls = polls_df[polls_df["PublDate"] >= TREND_START].copy()

    for block_name, party_list in BLOC_PARTIES.items():
        eval_dates = None
        smooth_sum = None
        var_sum = None
        for p in party_list:
            ts = timeseries.get(p)
            if not ts or not ts.get("smooth_y"):
                continue
            sy = np.array(ts["smooth_y"], dtype=float)
            ss = np.array(ts["smooth_std"], dtype=float)
            if eval_dates is None:
                eval_dates = list(pd.to_datetime(ts["eval_dates"]))
                smooth_sum = sy.copy()
                var_sum = ss ** 2
            else:
                smooth_sum = smooth_sum + sy
                var_sum = var_sum + ss ** 2
        if eval_dates is None:
            continue

        std = np.sqrt(var_sum)
        upper = (smooth_sum + 1.96 * std).tolist()
        lower = (smooth_sum - 1.96 * std).tolist()

        color = block_colors.get(block_name, "#888")
        fill_color = hex_to_rgba(color, alpha=0.12)
        party_label = " + ".join(party_list)

        fig.add_trace(go.Scatter(
            x=eval_dates + eval_dates[::-1],
            y=upper + lower[::-1],
            fill="toself",
            fillcolor=fill_color,
            line=dict(width=0),
            showlegend=False,
            legendgroup=block_name,
            hoverinfo="skip",
        ))

        fig.add_trace(go.Scatter(
            x=eval_dates,
            y=smooth_sum.tolist(),
            mode="lines",
            line=dict(color=color, width=2.4),
            name=f"{block_name} ({party_label})",
            legendgroup=block_name,
            hovertemplate=(
                f"<b>{block_name}</b><br>"
                "Datum: %{x|%Y-%m-%d}<br>"
                "Stöd: <b>%{y:.1f}%</b>"
                "<extra></extra>"
            ),
        ))

        if recent_polls is not None:
            block_poll = recent_polls[["PublDate", "Company", "n"] + party_list].dropna(subset=party_list).copy()
            if not block_poll.empty:
                block_poll["BlockSum"] = block_poll[party_list].sum(axis=1)
                company_labels = block_poll["Company"].fillna("Okänt").tolist()
                n_labels = pd.to_numeric(block_poll["n"], errors="coerce").fillna(0).astype(int).tolist()
                fig.add_trace(go.Scatter(
                    x=block_poll["PublDate"],
                    y=block_poll["BlockSum"],
                    mode="markers",
                    marker=dict(color=color, size=5, opacity=0.40, line=dict(width=0)),
                    name=block_name,
                    legendgroup=block_name,
                    showlegend=False,
                    customdata=list(zip(company_labels, n_labels)),
                    hovertemplate=(
                        f"<b>{block_name}</b><br>"
                        "Datum: %{x|%Y-%m-%d}<br>"
                        "Stöd: <b>%{y:.1f}%</b><br>"
                        "Institut: %{customdata[0]}<br>"
                        "Urval: %{customdata[1]:,}"
                        "<extra></extra>"
                    ),
                ))

    fig.add_hline(y=50.0, line_dash="dot", line_color="#999999", line_width=1.5,
                  annotation_text="50 %",
                  annotation_font=dict(size=10, color="#666666"),
                  annotation_position="bottom right")

    for _edate, _elabel in TREND_ELECTIONS:
        fig.add_vline(
            x=_edate.timestamp() * 1000,
            line_dash="dash",
            line_color="#555555",
            line_width=1.2,
            annotation_text=_elabel,
            annotation_font=dict(size=10, color="#555555"),
            annotation_position="top right",
        )

    fig.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text="Blockstöd över tid", font=dict(size=14, color="#111213")),
        yaxis_title="Röstandel (%)",
        xaxis_title="",
        height=320,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=11), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=60, b=20, l=55, r=20),
        hovermode="closest",
    )
    return fig


def make_sweden_map(fixed_seats: dict, geojson: dict, selected_party: str = None) -> go.Figure:
    """
    Interaktiv karta över Sverige med Mapbox-underlag.
    Använder px.choropleth_mapbox för korrekt zoomning mot Sverige.
    """
    if not geojson:
        fig = go.Figure()
        fig.update_layout(title="Karta ej tillgänglig – kontrollera internetanslutningen")
        return fig

    # Aggregera mandat per länsnivå (21 regioner → en eller flera valkretsar)
    rows = []
    for county, constituencies in COUNTY_TO_CONSTITUENCIES.items():
        party_mandates = {p: 0 for p in PARTIES}
        for cname in constituencies:
            if cname in fixed_seats:
                for p in PARTIES:
                    party_mandates[p] += fixed_seats[cname].get(p, 0)

        total = sum(party_mandates.values())
        dominant = max(party_mandates, key=party_mandates.get) if total > 0 else PARTIES[0]

        # Hover-text med fullständig mandatuppdelning
        valkrets_note = (
            f"<br><i>({len(constituencies)} valkretsar: {', '.join(constituencies)})</i>"
            if len(constituencies) > 1 else ""
        )
        breakdown_lines = "".join(
            f"<br>  {PARTY_NAMES.get(p, p)}: <b>{party_mandates[p]}</b>"
            for p in sorted(PARTIES, key=lambda x: -party_mandates[x])
            if party_mandates[p] > 0
        )
        hover_text = f"<b>{county}</b>{valkrets_note}{breakdown_lines}"

        rows.append({
            "county": county,
            "dominant": dominant,
            "dominant_name": PARTY_NAMES.get(dominant, dominant),
            "total": total,
            "hover_text": hover_text,
            **{f"mandat_{p}": party_mandates[p] for p in PARTIES},
        })

    df_map = pd.DataFrame(rows)
    sweden_center = {"lat": 62.5, "lon": 16.5}

    if selected_party:
        color_col = f"mandat_{selected_party}"
        party_color = PARTY_COLORS.get(selected_party, "#888")
        fig = px.choropleth_mapbox(
            df_map,
            geojson=geojson,
            locations="county",
            featureidkey="properties.name",
            color=color_col,
            color_continuous_scale=[[0, "#eeeeee"], [1, party_color]],
            range_color=[0, max(df_map[color_col].max(), 1)],
            mapbox_style="carto-positron",
            zoom=3.6,
            center=sweden_center,
            opacity=0.85,
            custom_data=["hover_text"],
        )
        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
        )
        fig.update_coloraxes(
            colorbar_title_text=f"{PARTY_NAMES.get(selected_party, selected_party)}<br>mandat"
        )
    else:
        # Färgsätt varje region med det dominerande partiets färg
        color_map = {p: PARTY_COLORS[p] for p in PARTIES}
        fig = px.choropleth_mapbox(
            df_map,
            geojson=geojson,
            locations="county",
            featureidkey="properties.name",
            color="dominant",
            color_discrete_map=color_map,
            mapbox_style="carto-positron",
            zoom=3.6,
            center=sweden_center,
            opacity=0.85,
            custom_data=["hover_text"],
        )
        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
        )

    fig.update_layout(
        height=620,
        margin=dict(t=0, b=0, l=0, r=0),
        showlegend=False,
    )
    return fig


def make_constituency_bar(fixed_seats: dict, seats_2022: dict, party: str) -> go.Figure:
    """Grupperat stapeldiagram: baslinjevalets faktiska mandat vs prognos per valkrets."""
    consts = list(fixed_seats.keys())
    vals_pred = [fixed_seats[c].get(party, 0) for c in consts]
    vals_2022 = [seats_2022[c].get(party, 0) for c in consts]

    color = PARTY_COLORS.get(party, "#888")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=f"{BASELINE_YEAR} (faktiskt)", x=consts, y=vals_2022,
        marker_color=color, marker_line_width=0, opacity=0.35,
        text=vals_2022, textposition="outside",
        hovertemplate="<b>%{x}</b><br>" + str(BASELINE_YEAR) + ": <b>%{y}</b> mandat<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Prognos", x=consts, y=vals_pred,
        marker_color=color, marker_line_width=0, opacity=1.0,
        text=vals_pred, textposition="outside",
        hovertemplate="<b>%{x}</b><br>Prognos: <b>%{y}</b> mandat<extra></extra>",
    ))
    fig.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text=f"Mandat per valkrets — {PARTY_NAMES.get(party, party)}", font=dict(size=14, color="#111213")),
        yaxis_title="Mandat",
        xaxis_tickangle=-45,
        barmode="group",
        height=440,
        margin=dict(t=50, b=130, l=50, r=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def make_economist_mandate_chart(
    raw_est: dict,
    sim: dict,
    seats_2022_total: dict,
) -> go.Figure:
    """
    Horisontellt konfidensintervalldiagram i Economist-stil.
    Visar per parti:
      – Tunn horisontell linje:  5:e–95:e percentil (90 % CI)
      – Tjock linje / stapel:    25:e–75:e percentil (IQR)
      – Cirkel:                  Median
      – Diamant (grå):           Faktiska mandat i baslinjevalet
    Vertikal streckad linje vid 175 mandat (majoritet).
    """
    # Sortera partier efter median (störst överst)
    parties_sorted = sorted(
        [p for p in PARTIES if np.mean(sim["party_mandates"][p]) >= 0.5],
        key=lambda p: np.median(sim["party_mandates"][p]),
    )

    fig = go.Figure()

    # Majoritetsmarkering (vertikal linje)
    fig.add_vline(
        x=175, line_dash="dot", line_color="#EF718C", line_width=1.5,
    )
    fig.add_annotation(
        x=175, y=len(parties_sorted) - 0.1,
        text="Majoritet (175)", showarrow=False,
        font=dict(size=10, color="#EF718C"),
        xanchor="left", yanchor="top",
        xshift=5,
    )

    for i, p in enumerate(parties_sorted):
        arr = sim["party_mandates"][p]
        p5  = int(np.percentile(arr, 5))
        p25 = int(np.percentile(arr, 25))
        med = int(np.median(arr))
        p75 = int(np.percentile(arr, 75))
        p95 = int(np.percentile(arr, 95))

        party_color = PARTY_COLORS.get(p, "#888")
        ci_color    = hex_to_rgba(party_color, alpha=0.20)
        iqr_color   = hex_to_rgba(party_color, alpha=0.50)
        actual_2022 = seats_2022_total.get(p, 0)
        party_label = PARTY_NAMES.get(p, p)

        # 90 % CI – tunn rektangel
        fig.add_shape(
            type="rect",
            x0=p5, x1=p95,
            y0=i - 0.18, y1=i + 0.18,
            fillcolor=ci_color,
            line_width=0,
        )

        # IQR – tjock rektangel
        fig.add_shape(
            type="rect",
            x0=p25, x1=p75,
            y0=i - 0.32, y1=i + 0.32,
            fillcolor=iqr_color,
            line_width=0,
        )

        # Median – cirkel
        fig.add_trace(go.Scatter(
            x=[med], y=[i],
            mode="markers",
            marker=dict(color=party_color, size=10, symbol="circle",
                        line=dict(color="white", width=1.5)),
            name=party_label,
            legendgroup=p,
            hovertemplate=(
                f"<b>{party_label}</b><br>"
                f"Median: <b>{med}</b> mandat<br>"
                f"IQR (25–75): {p25}–{p75}<br>"
                f"90% CI: {p5}–{p95}<br>"
                f"{BASELINE_YEAR} faktiskt: {actual_2022}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

        # Baslinjevalet faktiskt – grå ruta
        if actual_2022 > 0:
            fig.add_trace(go.Scatter(
                x=[actual_2022], y=[i],
                mode="markers",
                marker=dict(color="#999999", size=8, symbol="diamond",
                            line=dict(color="white", width=1)),
                showlegend=(i == 0),
                name=f"{BASELINE_YEAR} (faktiskt)",
                legendgroup="actual",
                hovertemplate=(
                    f"<b>{party_label}</b> — {BASELINE_YEAR} faktiskt: <b>{actual_2022}</b> mandat<extra></extra>"
                ),
            ))

    # Lägg till phantom-trace för legendpost "Median"
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="#555555", size=10, symbol="circle"),
        name="Median (prognos)", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(color="#999999", size=8, symbol="diamond"),
        name=f"{BASELINE_YEAR} (faktiskt)", showlegend=True, legendgroup="actual2",
    ))

    fig.update_layout(
        **ECONOMIST_BASE,
        title=dict(text="Mandatprognos per parti — 90 % konfidensintervall", font=dict(size=14, color="#111213")),
        xaxis=dict(
            title="Mandat",
            showgrid=True,
            gridcolor="#ebebeb",
            gridwidth=1,
            showline=True,
            linecolor="#cccccc",
            zeroline=False,
            range=[0, 180],
            tickfont=dict(size=11, color="#555555"),
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(parties_sorted))),
            ticktext=[PARTY_NAMES.get(p, p) for p in parties_sorted],
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=12, color="#111213"),
        ),
        height=max(320, len(parties_sorted) * 52 + 80),
        margin=dict(t=60, b=40, l=130, r=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=11), bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="closest",
    )
    return fig


def make_coalition_chart(sim: dict) -> go.Figure:
    """
    Horisontellt sannolikhetsdiagram per koalition.
    Visar P(≥175 mandat), mandatmedelvärde och 90 % CI.
    """
    rows = coalition_summary(sim)
    rows.sort(key=lambda r: r["prob"])
    fig = go.Figure()

    for r in rows:
        color = "#29BFA2" if r["prob"] >= 0.5 else "#EF718C" if r["prob"] < 0.25 else "#a8a8a8"
        fig.add_trace(go.Bar(
            x=[r["prob"] * 100],
            y=[r["name"]],
            orientation="h",
            marker_color=color,
            marker_line_width=0,
            text=[f"  {r['prob']*100:.1f}%"],
            textposition="outside",
            hovertemplate=(
                f"<b>{r['name']}</b><br>"
                f"P(majoritet): <b>{r['prob']*100:.1f}%</b><br>"
                f"Snitt: {r['mean']:.0f} mandat<br>"
                f"IQR: {r['p25']}–{r['p75']}<br>"
                f"90% CI: {r['p5']}–{r['p95']}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.add_vline(x=50, line_dash="dot", line_color="#555555", line_width=1.2,
                  annotation_text="50%", annotation_font=dict(size=10, color="#555555"),
                  annotation_position="top right")

    fig.update_layout(
        **ECONOMIST_BASE,
        title=dict(text="Sannolikhet för riksdagsmajoritet per koalition", font=dict(size=14, color="#111213")),
        xaxis=dict(
            title="Sannolikhet för ≥ 175 mandat (%)",
            range=[0, 115],
            showgrid=True, gridcolor="#ebebeb", showline=True, linecolor="#cccccc",
            tickfont=dict(size=11, color="#555555"),
        ),
        yaxis=dict(showgrid=False, showline=False, tickfont=dict(size=11, color="#111213")),
        height=max(320, len(rows) * 58 + 80),
        margin=dict(t=60, b=40, l=300, r=90),
    )
    return fig


def make_coalition_mandate_dist(sim: dict) -> go.Figure:
    """Mandatfördelning per koalition – boxplot."""
    n_sims = sim["n_sims"]
    pm = sim["party_mandates"]

    fig = go.Figure()
    sorted_names = sorted(
        COALITIONS.keys(),
        key=lambda k: float(sum(pm.get(p, np.zeros(n_sims)) for p in COALITIONS[k]).mean()),
        reverse=True,
    )

    for name in sorted_names:
        arr = sum(pm.get(p, np.zeros(n_sims)) for p in COALITIONS[name])
        fig.add_trace(go.Box(
            x=arr,
            name=name,
            orientation="h",
            marker_color="#29BFA2",
            fillcolor=hex_to_rgba("#29BFA2", 0.20),
            line=dict(color="#29BFA2", width=1.2),
            boxmean=True,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Median: %{median}<br>"
                "Q1–Q3: %{q1}–%{q3}<br>"
                "Min–Max: %{lowerfence}–%{upperfence}"
                "<extra></extra>"
            ),
        ))

    fig.add_vline(x=175, line_dash="dot", line_color="#EF718C", line_width=1.5,
                  annotation_text="Majoritet (175)",
                  annotation_font=dict(size=10, color="#EF718C"),
                  annotation_position="top right")

    fig.update_layout(
        **ECONOMIST_BASE,
        title=dict(text="Mandatfördelning per koalition — 10 000 simuleringar", font=dict(size=14, color="#111213")),
        xaxis=dict(
            title="Mandat",
            showgrid=True, gridcolor="#ebebeb", showline=True, linecolor="#cccccc",
            tickfont=dict(size=11, color="#555555"),
        ),
        yaxis=dict(showgrid=False, showline=False, tickfont=dict(size=10, color="#111213")),
        height=max(360, len(sorted_names) * 60 + 80),
        margin=dict(t=60, b=40, l=300, r=20),
        showlegend=False,
    )
    return fig


def make_party_comparison(df: pd.DataFrame, party_x: str, party_y: str, window_days: int) -> go.Figure:
    """
    Scatter-plot av två partiers stöd mot varandra.
    Färgskalan visar tid (mörkare = nyare).
    """
    cutoff = datetime.now() - timedelta(days=window_days * 4)
    col = df[df["PublDate"] >= cutoff][["PublDate", party_x, party_y, "Company"]].dropna().copy()
    if col.empty:
        return go.Figure()

    days_from_start = (col["PublDate"] - col["PublDate"].min()).dt.days.values
    px_name = PARTY_NAMES.get(party_x, party_x)
    py_name = PARTY_NAMES.get(party_y, party_y)

    fig = go.Figure(go.Scatter(
        x=col[party_x],
        y=col[party_y],
        mode="markers",
        marker=dict(
            color=days_from_start,
            colorscale=[[0, "#d0e4f5"], [1, "#08519c"]],
            size=8,
            opacity=0.80,
            line=dict(width=0),
            colorbar=dict(
                title="Dagar sedan start",
                thickness=12,
                len=0.6,
                tickfont=dict(size=10),
            ),
        ),
        customdata=np.column_stack([
            col["PublDate"].dt.strftime("%Y-%m-%d").values,
            col["Company"].fillna("Okänt").values,
        ]),
        hovertemplate=(
            f"<b>{px_name}</b>: %{{x:.1f}}%<br>"
            f"<b>{py_name}</b>: %{{y:.1f}}%<br>"
            "Datum: %{customdata[0]}<br>"
            "Institut: %{customdata[1]}"
            "<extra></extra>"
        ),
        showlegend=False,
    ))

    # Diagonallinje (equality line) för visuell referens
    all_vals = list(col[party_x]) + list(col[party_y])
    lo, hi = min(all_vals) * 0.9, max(all_vals) * 1.1
    fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi,
                  line=dict(color="#cccccc", dash="dot", width=1))

    fig.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text=f"{px_name} vs {py_name} — stöd per mätning", font=dict(size=14, color="#111213")),
        xaxis_title=f"{px_name} (%)",
        yaxis_title=f"{py_name} (%)",
        height=420,
        margin=dict(t=60, b=50, l=60, r=80),
    )
    return fig




# ─────────────────────────────────────────────
# VALNATT (nowcasting)
# ─────────────────────────────────────────────











def _render_valnatt_replay() -> dict | None:
    """Spela upp valnatten 2026 i verklig räkningsordning. Returnerar nowcast-dict."""
    df = _load_valnatt_2026()
    if df is None or df.empty:
        st.warning("Valnattsdata saknas — kör `python fetch_valnatt_2026.py`.")
        return None

    times = _valnatt_times()
    t = st.select_slider(
        "Klockan på valnatten (13–14 september 2026)",
        options=times,
        value=datetime(2026, 9, 13, 22, 0),
        format_func=lambda x: x.strftime("%H:%M"),
        key="valnatt_time",
    )
    stt = _valnatt_state(df, t)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Räknade distrikt", f"{stt['n_counted']:,} av {stt['n_total']:,}".replace(",", " "))
    with c2:
        st.metric("Andel av rösterna", f"{stt['vote_share_counted'] * 100:.0f} %")
    with c3:
        st.metric("Fel råräkning", "–" if np.isnan(stt["mae_raw"]) else f"{stt['mae_raw']:.2f} pe")
    with c4:
        _d = None if np.isnan(stt["mae_raw"]) else f"{stt['mae_nowcast'] - stt['mae_raw']:+.2f} pe"
        st.metric("Fel nowcast", f"{stt['mae_nowcast']:.2f} pe", delta=_d, delta_color="inverse")

    party_codes = list(NOWCAST_PARTIES)
    party_labels = [PARTY_NAMES.get(p, p) for p in party_codes]
    fig = go.Figure()
    if stt["n_counted"]:
        fig.add_bar(name="Råräkning", x=party_labels,
                    y=[stt["raw"][p] * 100 for p in party_codes], marker_color="#cccccc")
    fig.add_bar(name="Nowcast", x=party_labels,
                y=[stt["nowcast"][p] * 100 for p in party_codes], marker_color="#29BFA2")
    fig.add_trace(go.Scatter(
        name=f"Slutresultat {BASELINE_YEAR}", x=party_labels,
        y=[stt["final"][p] * 100 for p in party_codes],
        mode="markers", marker=dict(symbol="diamond", size=12, color="black"),
    ))
    fig.update_layout(
        barmode="group", yaxis_title="Röstandel (%)", height=400,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    st.plotly_chart(fig, use_container_width=True, key="valnatt_replay_bar")

    rows = [{
        "Parti": PARTY_NAMES.get(p, p),
        "Råräkning (%)": round(stt["raw"][p] * 100, 2) if stt["n_counted"] else None,
        "Nowcast (%)": round(stt["nowcast"][p] * 100, 2),
        f"Slutresultat {BASELINE_YEAR} (%)": round(stt["final"][p] * 100, 2),
        "Nowcast-fel (pe)": round((stt["nowcast"][p] - stt["final"][p]) * 100, 2),
    } for p in party_codes]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    curve = _valnatt_error_curve(df)
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=curve["t"], y=curve["Råräkning"], name="Råräkning",
                               mode="lines", line=dict(color="#999999", width=2)))
    fig_c.add_trace(go.Scatter(x=curve["t"], y=curve["Nowcast"], name="Nowcast",
                               mode="lines", line=dict(color="#29BFA2", width=2.4)))
    fig_c.add_vline(x=t.timestamp() * 1000, line_dash="dot", line_color="#555555")
    fig_c.update_layout(
        **ECONOMIST_LAYOUT,
        title=dict(text="Genomsnittligt fel per parti under natten", font=dict(size=13, color="#111213")),
        yaxis_title="Fel mot slutresultatet (pe)", height=320,
        margin=dict(t=50, b=20, l=55, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig_c.update_xaxes(tickformat="%H:%M")
    st.plotly_chart(fig_c, use_container_width=True, key="valnatt_error_curve")
    st.caption(
        "Distrikten läggs till i den ordning de faktiskt rapporterades in till "
        "Valmyndigheten. Felet mäts mot det slutliga resultatet, som även innehåller "
        "röster som räknades först dagarna efter valet — därför planar båda kurvorna "
        "ut en bit över noll. Sent på natten blir råräkningen något bättre än nowcasten, "
        "eftersom var femte distrikt inte kan jämföras med 2022 och då inte ingår i "
        "deltaberäkningen."
    )
    return stt["nowcast"]


@st.cache_data(show_spinner=False)
def _load_muni_structure_cached():
    """Läs committad 2022-struktur (KF/RF) för opinions-mandat + selectbox-namn."""
    try:
        from mandatorn_model.muni_mandates import load_structure
        return load_structure()
    except Exception:
        return None


def _render_area_seats_baseline(area_struct: dict, area_label: str, stage: str = "") -> None:
    """Senaste valets mandatfördelning för ett KF/RF-område."""
    seats = area_struct.get("seats_2022", {})
    meta = area_struct.get("party_meta", {})
    total = sum(seats.values())
    if total == 0:
        st.info(f"Ingen {BASELINE_YEAR}-mandatfördelning tillgänglig för området.")
        return

    def _is_local(p):
        return not bool(meta.get(p, {}).get("national")) and p not in PARTIES

    def _label(p):
        return meta.get(p, {}).get("namn", p) if _is_local(p) else p

    def _color(p):
        if p in PARTY_COLORS:
            return PARTY_COLORS[p]
        return meta.get(p, {}).get("farg") or "#888888"

    def _fullname(p):
        return PARTY_NAMES.get(p, meta.get(p, {}).get("namn", p))

    seated = sorted([p for p in seats if seats[p] > 0], key=lambda p: -seats[p])
    fig = go.Figure()
    fig.add_bar(
        x=[_label(p) for p in seated],
        y=[seats[p] for p in seated],
        marker_color=[_color(p) for p in seated],
    )
    fig.update_layout(
        yaxis_title="Mandat", height=360,
        margin=dict(l=10, r=10, t=30, b=60), showlegend=False,
    )
    st.plotly_chart(
        fig, use_container_width=True,
        key=f"seats_base_{area_struct.get('valtyp', '')}_{area_struct.get('kod', '')}",
    )
    st.dataframe(
        pd.DataFrame([{"Parti": _fullname(p), f"Mandat {BASELINE_YEAR}": seats[p]} for p in seated]),
        hide_index=True, use_container_width=True,
    )
    _kind = "preliminär" if "preliminar" in stage else "slutlig"
    st.caption(f"{_kind.capitalize()} mandatfördelning {area_label} {BASELINE_YEAR} ({total} mandat).")


def _render_valnatt_local_mandates() -> None:
    """Mandatfördelning i KF/RF för vald kommun/region efter valet."""
    from mandatorn_model.muni_mandates import list_areas

    st.divider()
    st.subheader(f"Kommun & region — mandatfördelning {BASELINE_YEAR}")
    st.caption(
        f"Valmyndighetens mandatfördelning efter valet {BASELINE_YEAR}, inklusive lokala partier."
    )
    struct = _load_muni_structure_cached()
    if struct is None:
        st.info("Referensdata för kommuner/regioner saknas.")
        return
    stage = struct.get("stage", {})

    kf_areas = list_areas(struct, "KF")
    rf_areas = list_areas(struct, "RF")
    col1, col2 = st.columns(2)
    with col1:
        kf_name = st.selectbox("Kommun", [n for _, n in kf_areas], key="valnatt_kf_sel")
    with col2:
        rf_name = st.selectbox("Region", [n for _, n in rf_areas], key="valnatt_rf_sel")
    kf_kod = {n: k for k, n in kf_areas}[kf_name]
    rf_kod = {n: k for k, n in rf_areas}[rf_name]

    st.markdown(f"**{kf_name} — kommunfullmäktige**")
    _render_area_seats_baseline(struct["KF"][kf_kod], "kommunfullmäktige", stage.get(f"KF_{kf_kod}", ""))
    st.markdown(f"**{rf_name} — regionfullmäktige**")
    _render_area_seats_baseline(struct["RF"][rf_kod], "regionfullmäktige", stage.get(f"RF_{rf_kod}", ""))


def _render_opinion_area_mandat(area: dict, swing: dict, area_label: str) -> None:
    """Opinionsbaserad mandatuppskattning för ett valområde (Regional-fliken)."""
    from mandatorn_model.muni_mandates import allocate_area_mandates

    res = allocate_area_mandates(area, swing)
    total = res["total"]
    seats_2022 = res["seats_2022"]
    meta = res["party_meta"]
    parties = res["parties"]
    if sum(total.values()) == 0:
        st.info("Kunde inte beräkna en mandatfördelning för detta område.")
        return

    def _is_local(p: str) -> bool:
        return not bool(meta.get(p, {}).get("national")) and p not in PARTIES

    def _label(p: str) -> str:
        # Riksdagsparti → förkortning; lokalt parti → (förkortat) partinamn
        return p if not _is_local(p) else meta.get(p, {}).get("namn", p)

    def _fullname(p: str) -> str:
        return PARTY_NAMES.get(p, meta.get(p, {}).get("namn", p))

    def _color(p: str) -> str:
        if p in PARTY_COLORS:
            return PARTY_COLORS[p]
        return meta.get(p, {}).get("farg") or "#888888"

    st.subheader(f"Mandatuppskattning — {area['namn']} ({area_label})")
    st.caption(
        f"{res['total_seats']} mandat · spärr {res['threshold_pct']:.0f} % · "
        f"{res['n_utjamning']} utjämningsmandat. Riksdagspartier får den nationella "
        f"opinionssvingen sedan {BASELINE_YEAR}; **lokala partier antas få samma resultat "
        f"som {BASELINE_YEAR}**. Full modell: Sainte-Laguë per valkrets + utjämning."
    )

    seated = sorted([p for p in parties if total.get(p, 0) > 0],
                    key=lambda p: -total[p])
    fig = go.Figure()
    fig.add_bar(
        x=[_label(p) for p in seated],
        y=[total[p] for p in seated],
        marker_color=[_color(p) for p in seated],
    )
    fig.update_layout(
        yaxis_title="Mandat", height=360,
        margin=dict(l=10, r=10, t=30, b=60), showlegend=False,
    )
    st.plotly_chart(
        fig, use_container_width=True,
        key=f"opinion_mandat_{area['valtyp']}_{area['kod']}",
    )

    rows = []
    for p in parties:
        m, o = total.get(p, 0), seats_2022.get(p, 0)
        if m == 0 and o == 0 and res["projected_share"].get(p, 0) < 1.0:
            continue
        rows.append({
            "Parti": _fullname(p),
            "Röstandel (%)": round(res["projected_share"].get(p, 0), 1),
            "Mandat nu (est.)": m,
            f"Mandat {BASELINE_YEAR}": o,
            "Δ": f"{m - o:+d}",
        })
    st.dataframe(
        pd.DataFrame(rows).sort_values("Mandat nu (est.)", ascending=False),
        hide_index=True, use_container_width=True,
    )
    st.caption(
        f"Δ = förändring mot {BASELINE_YEAR}. Lokala partier visas med sitt fullständiga namn."
    )


def _render_valnatt_tab() -> None:
    """Valnatt-fliken: uppspelning av valnatten 2026 med nowcast."""
    st.subheader(f"🌙 Valnatten {BASELINE_YEAR} — uppspelning")
    st.markdown(
        "Under valnatten är råräkningen systematiskt missvisande eftersom små "
        "distrikt rapporterar först. **Nowcast-metoden** korrigerar för detta "
        "genom att jämföra *förändringen* (delta) i partistöd mellan räknade "
        "distrikt och förra valet (2022), snarare än att titta på absoluta nivåer. "
        "Dra i reglaget för att se hur prognosen utvecklades under natten."
    )
    st.caption(
        "Metod: [Nowcasting på valnatten – valprognos.se](https://www.nationalekonomi.se/artikel/nowcasting-pa-valnatten-metod-och-utvardering-fran-valprognos-se/)"
    )
    nowcast = _render_valnatt_replay()
    if nowcast is not None:
        _render_rd_downstream(nowcast)
    _render_valnatt_local_mandates()


def _render_rd_downstream(nowcast: dict) -> None:
    """Riksdagsmandat, per valkrets och förväntade invalda drivet av nowcasten."""
    # ─────────────────────────────────────────────────────────────────────
    # Mandatprojektion: kör nowcast-rösterna genom samma allokeringsmotor
    # som opinionsfliken så vi får fasta valkretsmandat, utjämningsmandat
    # och blockanalys driven av räkningen istället för opinionsmätningarna.
    # ─────────────────────────────────────────────────────────────────────
    nowcast_pct = {p: nowcast[p] * 100 for p in NOWCAST_PARTIES}
    mandates_nc = allocate_all_mandates(nowcast_pct)

    st.divider()
    st.subheader("Riksdagen — mandatfördelning enligt nowcast")
    st.caption(
        "Räkneresultaten projiceras till valkretsnivå via uniform swing "
        "(samma metod som opinionsfliken), och Sainte-Laguë körs på riktigt "
        "per valkrets + utjämningsmandat. 4 %-spärren tillämpas."
    )
    st.plotly_chart(
        make_mandate_bar(mandates_nc["total"]),
        use_container_width=True,
        key="mandate_bar_valnatt",
    )

    mand_col1, mand_col2 = st.columns(2)
    with mand_col1:
        mandate_df_nc = pd.DataFrame([
            {
                "Parti": PARTY_NAMES.get(p, p),
                "Fasta": mandates_nc["fixed_total"].get(p, 0),
                "Utjämning": mandates_nc["adjustment"].get(p, 0),
                "Totalt": mandates_nc["total"].get(p, 0),
            }
            for p in PARTIES if mandates_nc["total"].get(p, 0) > 0
        ]).sort_values("Totalt", ascending=False)
        st.dataframe(mandate_df_nc, hide_index=True, use_container_width=True)
    with mand_col2:
        for bloc_name, bloc_parties in BLOC_PARTIES.items():
            total_bloc = sum(mandates_nc["total"].get(p, 0) for p in bloc_parties)
            majoritet_delta = total_bloc - 175
            st.metric(
                bloc_name,
                f"{total_bloc} mandat",
                delta=f"{majoritet_delta:+d} mot majoritet",
            )
            for p in bloc_parties:
                m = mandates_nc["total"].get(p, 0)
                if m > 0:
                    st.write(f"  {PARTY_NAMES.get(p, p)}: {m}")
            st.markdown("---")

    # ── Per valkrets ──
    st.divider()
    st.subheader("Per valkrets")
    const_names_nc = sorted(mandates_nc["fixed"].keys())
    sel_const_nc = st.selectbox(
        "Välj valkrets",
        const_names_nc,
        key="valnatt_const_sel",
    )
    fixed_for_const = mandates_nc["fixed"].get(sel_const_nc, {})
    votes_for_const = mandates_nc["constituency_votes"].get(sel_const_nc, {})
    const_rows = []
    for p in PARTIES:
        v = votes_for_const.get(p, 0.0)
        m = fixed_for_const.get(p, 0)
        if m == 0 and v < 0.5:
            continue
        const_rows.append({
            "Parti": PARTY_NAMES.get(p, p),
            "Röstandel (%)": round(v, 1),
            "Fasta mandat": m,
        })
    const_df_nc = pd.DataFrame(const_rows).sort_values("Röstandel (%)", ascending=False)
    st.dataframe(const_df_nc, hide_index=True, use_container_width=True)

    # ── Förväntade invalda ──
    st.divider()
    st.subheader("Förväntade invalda enligt nowcast")
    with st.spinner("Hämtar kandidatdata från Valmyndigheten..."):
        cand_df_nc = load_candidates()
    if cand_df_nc.empty:
        st.info(
            "Kandidatregistreringen från Valmyndigheten är inte tillgänglig ännu. "
            "Sektionen aktiveras när kandidatlistorna publicerats."
        )
    else:
        elected_nc = predict_elected_candidates(mandates_nc["fixed"], cand_df_nc)
        adj_consts_nc = predict_adjustment_constituencies(
            mandates_nc["adjustment"],
            mandates_nc["fixed"],
            mandates_nc["constituency_votes"],
            placement=mandates_nc["adjustment_by_constituency"],
        )
        elected_adj_nc = predict_adjustment_candidates(
            adj_consts_nc, cand_df_nc, elected_nc
        )

        cand_const_options = ["Alla valkretsar"] + const_names_nc
        sel_const_cand = st.selectbox(
            "Välj valkrets",
            cand_const_options,
            key="valnatt_cand_sel",
        )

        chosen_consts = const_names_nc if sel_const_cand == "Alla valkretsar" else [sel_const_cand]
        cand_rows = []
        for c_name in chosen_consts:
            seats_in_c = mandates_nc["fixed"].get(c_name, {})
            elected_in_c = elected_nc.get(c_name, {})
            for p in PARTIES:
                n_seats = seats_in_c.get(p, 0)
                if n_seats == 0:
                    continue
                cands = elected_in_c.get(p, [])
                if cands:
                    for c in cands:
                        cand_rows.append({
                            "Valkrets": c_name,
                            "Parti": PARTY_NAMES.get(p, p),
                            "Listplats": int(c["ordning"]) if pd.notna(c["ordning"]) else "–",
                            "Namn": c["namn"],
                            "Mandattyp": "Fast",
                        })
                else:
                    for rank in range(1, n_seats + 1):
                        cand_rows.append({
                            "Valkrets": c_name,
                            "Parti": PARTY_NAMES.get(p, p),
                            "Listplats": rank,
                            "Namn": "Ej registrerad ännu",
                            "Mandattyp": "Fast",
                        })

        for p, cands_adj in elected_adj_nc.items():
            for c in cands_adj:
                c_name = c.get("adj_valkrets", "–")
                if sel_const_cand != "Alla valkretsar" and c_name != sel_const_cand:
                    continue
                cand_rows.append({
                    "Valkrets": c_name,
                    "Parti": PARTY_NAMES.get(p, p),
                    "Listplats": int(c["ordning"]) if pd.notna(c.get("ordning")) else "–",
                    "Namn": c.get("namn", "–"),
                    "Mandattyp": "Utjämning",
                })

        if cand_rows:
            cand_df_show = pd.DataFrame(cand_rows)
            n_total_seats = sum(mandates_nc["total"].get(p, 0) for p in PARTIES)
            n_registered = (cand_df_show["Namn"] != "Ej registrerad ännu").sum()
            st.caption(
                f"{n_registered} av {len(cand_df_show)} förväntade mandat har "
                f"registrerade kandidater. Totalt {n_total_seats} mandat i riksdagen."
            )
            st.dataframe(cand_df_show, hide_index=True, use_container_width=True)
        else:
            st.info("Inga mandat att visa för vald valkrets.")

    with st.expander("Om metoden"):
        st.markdown("""
        **Algoritm:**
        1. För varje parti p: beräkna delta_p = (current_share − baseline_share) bland räknade distrikt
        2. För oräknade distrikt: prognosticerad andel = baseline_share + delta_p
        3. Slutlig prognos = viktat genomsnitt av faktiska + prognosticerade röster

        **Data:**
        - Räkningsordning = distriktens faktiska rapporteringstid på valnatten 2026.
        - Baslinje = Valmyndighetens jämförelsesiffror för 2022, omräknade till 2026
          års distriktsindelning. 5 059 av 6 312 distrikt (≈ 80 % av rösterna) är
          jämförbara; övriga ingår i råräkningen men inte i deltaberäkningen.
        - Facit = slutligt valresultat 2026 (inkl. röster räknade efter valnatten).
        """)


# ─────────────────────────────────────────────
# STREAMLIT-APP
# ─────────────────────────────────────────────

def main():
    from PIL import Image as _PILImage
    import os as _os
    _favicon_path = _os.path.join(_os.path.dirname(__file__), "favicon.png")
    _favicon = _PILImage.open(_favicon_path) if _os.path.exists(_favicon_path) else "🏛️"
    st.set_page_config(
        page_title="Mandatorn",
        page_icon=_favicon,
        layout="wide",
        initial_sidebar_state="collapsed",  # Sidopanelen används inte
    )

    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

        /* DM Sans – täcker hela Streamlit-appen */
        html, body, * {
            font-family: "DM Sans", sans-serif !important;
        }
        /* Streamlit-specifika selektorer */
        .stApp, .stApp *, section[data-testid="stSidebar"] *,
        [data-testid="stMarkdownContainer"] *,
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"], [data-testid="column"] *,
        .stTabs [data-baseweb="tab"], .stDataFrame *,
        div[data-testid="stCaptionContainer"],
        .stButton button, .stSelectbox *, .stRadio *,
        .stSlider *, .stExpander *, p, h1, h2, h3, h4, h5, h6,
        span, div, li, td, th, label, input, textarea, select {
            font-family: "DM Sans", sans-serif !important;
        }
        h1 { font-size: 1.9rem !important; font-weight: 700; color: #111213; letter-spacing: -0.5px; }
        h2 { font-size: 1.3rem !important; font-weight: 600; color: #111213; }
        h3 { font-size: 1.1rem !important; font-weight: 600; color: #333333; }
        /* Topplinje i brandteal */
        .main > div:first-child { border-top: 4px solid #29BFA2; padding-top: 1rem; }
        /* Renare dataframe-tabeller */
        .stDataFrame { border: none !important; }
        /* Ljusare metriker */
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 600; }

        /* ── Fliknavigering: förhindra överlapp med innehåll ── */
        .stTabs [data-baseweb="tab-list"] {
            position: sticky !important;
            top: 0 !important;
            z-index: 999 !important;
            background: white !important;
            padding-bottom: 4px !important;
            border-bottom: 1px solid #ebebeb !important;
        }
        /* Expanders ska aldrig rendera under flikraden */
        .stExpander {
            position: relative !important;
            z-index: 1 !important;
            overflow: visible !important;
        }
        details[data-testid="stExpander"] {
            overflow: visible !important;
        }
        details[data-testid="stExpander"] summary {
            z-index: 1 !important;
            position: relative !important;
        }

        /* ── Mobilanpassning ── */
        @media (max-width: 768px) {
            /* Stapla alla kolumner vertikalt */
            [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
            }
            /* Mindre rubrik på mobil */
            h1 { font-size: 1.4rem !important; }
            h2 { font-size: 1.1rem !important; }
            /* Mindre metriker på mobil */
            [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
            [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
            /* Mindre padding i main-containern */
            .main .block-container { padding: 1rem 0.75rem !important; }
            /* Fliklablar – tillåt radbrytning */
            .stTabs [data-baseweb="tab"] { padding: 0.4rem 0.5rem !important; font-size: 0.8rem !important; }
        }
    </style>
    """, unsafe_allow_html=True)

    # Fasta inställningar (ej justerbara av användaren)
    window_days = WINDOW_DAYS

    with st.spinner("Hämtar data..."):
        polls_df = load_polls()
        geojson = load_geojson()

    if polls_df.empty:
        st.error(
            "⚠️ **Kunde inte ladda opinionsdata.**\n\n"
            "Appen hämtar mätningar från SwedishPolls på GitHub. "
            "Kontrollera din internetanslutning och ladda om sidan. "
            "Om problemet kvarstår kan källan vara tillfälligt otillgänglig."
        )
        st.stop()

    with st.spinner("Kör prognosen (Kalman + 10 000 simuleringar)..."):
        fc = build_forecast_cached(polls_df, reference_day(datetime.now()))
    _days_left = fc.days_left
    house_weights_df = fc.house_weights
    latest_date = fc.latest_poll_date
    raw_est = fc.raw_est
    raw_est_with_other = fc.raw_est_with_other
    raw_est_other = raw_est_with_other["O"]
    shares_all = fc.shares_all  # visningsandelar: andel av alla röster (D21)
    trend_timeseries = fc.trend_timeseries
    mandates = fc.mandates

    # ── Topprad med logo ──
    import os as _os2, base64 as _b64
    _logo_path = _os2.path.join(_os2.path.dirname(__file__), "logo.svg")
    if _os2.path.exists(_logo_path):
        with open(_logo_path, "r") as _lf:
            _logo_svg = _lf.read()
        _logo_b64 = _b64.b64encode(_logo_svg.encode()).decode()
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{_logo_b64}" style="height:72px;margin-bottom:0.2rem;" alt="Mandatorn logo"/>',
            unsafe_allow_html=True,
        )
    else:
        st.title("Mandatorn")
    st.caption("*Nils Silverström — ett svenskt försök till FiveThirtyEight*")
    st.caption(f"Senaste undersökning: **{latest_date}** · {len(polls_df)} mätningar totalt")
    st.caption(
        f"Mandatprognosen visar läget **om det vore val idag**. "
        f"Nästa riksdagsval: **{NEXT_ELECTION:%Y-%m-%d}** ({_days_left} dagar kvar) — "
        f"simuleringarnas osäkerhet inkluderar opinionsrörelser fram till dess."
    )

    st.info(
        "⚠️ **Disclaimer:** Detta är en oberoende statistisk modell baserad på publicerade "
        "opinionsmätningar och utgör inte ett officiellt valresultat eller en politisk rekommendation. "
        "Alla prognoser är förenade med osäkerhet. Modellbeskrivning finns i fliken **Metod**. "
        "Datakälla: [MansMeg/SwedishPolls](https://github.com/MansMeg/SwedishPolls) · "
        "Valresultat: [Valmyndigheten](https://www.val.se).",
        icon=None,
    )

    bloc_h = sum(mandates["total"].get(p, 0) for p in BLOC_PARTIES["Högerblocket"])
    bloc_v = sum(mandates["total"].get(p, 0) for p in BLOC_PARTIES["Vänsterblocket"])
    biggest = max(raw_est, key=raw_est.get)
    below = [p for p in PARTIES if raw_est.get(p, 0) < THRESHOLD]

    row1_c1, row1_c2 = st.columns(2)
    with row1_c1:
        st.metric("Högerblocket", f"{bloc_h} mandat", delta=f"{bloc_h - 175:+d} mot majoritet")
    with row1_c2:
        st.metric("Vänsterblocket", f"{bloc_v} mandat", delta=f"{bloc_v - 175:+d} mot majoritet")
    row2_c1, row2_c2 = st.columns(2)
    with row2_c1:
        st.metric("Största parti", PARTY_NAMES[biggest], delta=f"{raw_est[biggest]:.1f}%")
    with row2_c2:
        st.metric("Under 4%-spärren", ", ".join(below) if below else "Inga")

    st.divider()

    # Bygg mandattabell här så den är tillgänglig i alla flikar
    fixed_df = pd.DataFrame(mandates["fixed"]).T.fillna(0).astype(int)
    fixed_df["Totalt"] = fixed_df[PARTIES].sum(axis=1)
    fixed_df.index.name = "Valkrets"
    fixed_df = fixed_df[[p for p in PARTIES if p in fixed_df.columns] + ["Totalt"]]
    fixed_df.columns = [PARTY_NAMES.get(c, c) if c != "Totalt" else c for c in fixed_df.columns]

    # Kör simulering en gång – används i både Tab 2 och Tab 4
    sim = fc.sim
    # Baslinjevalets fasta mandat per parti (summerat nationellt) för referens i CI-diagrammet
    seats_2022_total = fc.baseline_seats_total

    _tab_labels = [
        "📊 Opinion", "🏛️ Mandat", "🗺️ Valkretsar",
        "🎲 Simulering", "👤 Kandidater",
        "📍 Regional", "📋 Data", "ℹ️ Metod", "🙋 Om mig",
    ]
    # Valnatt-fliken: uppspelning av valnatten 2026.
    _tab_labels.insert(8, "🌙 Valnatt")  # före "Om mig"

    _tabs = st.tabs(_tab_labels)
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab_valnatt, tab9 = _tabs

    # ── Tab 1: Nationell opinion ──
    with tab1:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.plotly_chart(make_trend_chart(polls_df, window_days, timeseries=trend_timeseries), use_container_width=True, key="trend_chart_tab1")
            st.caption(
                "**Övriga** (grå linje) = partier utanför de åtta riksdagspartierna summerade. "
                "Övriga ingår inte i mandatberäkningen."
            )
            trend_csv = build_trend_data(trend_timeseries)
            if not trend_csv.empty:
                st.download_button(
                    "⬇️ Ladda ner trenddata (CSV)",
                    data=trend_csv.to_csv(index=False).encode("utf-8"),
                    file_name="mandatorn_opinionstrender.csv",
                    mime="text/csv",
                    key="dl_trend",
                )
            st.plotly_chart(make_block_trend_chart(trend_timeseries, polls_df=polls_df), use_container_width=True, key="block_trend_chart_tab1")
            st.caption(
                "Blockstödet är summan av partiernas Kalman-smoothade trender. "
                "Konfidensbandet antar oberoende partifel och är en approximation."
            )
        with col2:
            st.plotly_chart(make_support_bar(raw_est, reference_2022=BASELINE), use_container_width=True, key="support_bar_tab1")
            st.subheader("Estimat per parti")
            _baseline_label = f"{BASELINE_YEAR} (%)"
            _delta_label = "Δ (pp)"
            _est_rows = [
                {
                    "Parti": PARTY_NAMES.get(p, p),
                    _baseline_label: f"{BASELINE.get(p, 0):.1f}",
                    "Nu (%)": f"{shares_all.get(p, 0):.1f}",
                    _delta_label: f"{shares_all.get(p, 0) - BASELINE.get(p, 0):+.1f}",
                    "Över spärren": "Ja" if shares_all.get(p, 0) >= THRESHOLD else "Nej",
                }
                for p in PARTIES
            ]
            # Lägg till Övriga (ingen spärr-kolumn relevant)
            _est_rows.append({
                "Parti": "Övriga",
                _baseline_label: f"{max(0, 100 - sum(BASELINE.values())):.1f}",
                "Nu (%)": f"{raw_est_other:.1f}",
                _delta_label: f"{raw_est_other - max(0, 100 - sum(BASELINE.values())):+.1f}",
                "Över spärren": "–",
            })
            est_df = pd.DataFrame(_est_rows)
            st.dataframe(est_df, hide_index=True, use_container_width=True)

        # ── Mandatfördelning (kompakt) ──
        st.divider()
        st.subheader("Aktuell mandatprognos")
        st.plotly_chart(make_mandate_bar(mandates["total"]), use_container_width=True, key="mandate_bar_tab1")
        mand_col1, mand_col2 = st.columns(2)
        with mand_col1:
            mandate_df_t1 = pd.DataFrame([
                {
                    "Parti": PARTY_NAMES.get(p, p),
                    "Fasta": mandates["fixed_total"].get(p, 0),
                    "Utjämning": mandates["adjustment"].get(p, 0),
                    "Totalt": mandates["total"].get(p, 0),
                }
                for p in PARTIES if mandates["total"].get(p, 0) > 0
            ]).sort_values("Totalt", ascending=False)
            st.dataframe(mandate_df_t1, hide_index=True, use_container_width=True)
        with mand_col2:
            for bloc_name, bloc_parties in BLOC_PARTIES.items():
                total_bloc = sum(mandates["total"].get(p, 0) for p in bloc_parties)
                st.metric(bloc_name, f"{total_bloc} mandat")
                for p in bloc_parties:
                    m = mandates["total"].get(p, 0)
                    if m > 0:
                        st.write(f"  {PARTY_NAMES.get(p, p)}: {m}")
                st.markdown("---")

        # ── Partistöd per valkrets ──
        st.divider()
        st.subheader("Partistöd per valkrets")
        const_names_t1 = sorted(CONSTITUENCIES.keys())
        sel_const_t1 = st.selectbox("Välj valkrets", const_names_t1, key="tab1_const_sel")

        # Använder raw_est – samma estimat som mandatfördelningen
        _c22_t1 = CONSTITUENCIES[sel_const_t1]
        _pred_t1 = estimate_constituency_votes(raw_est, _c22_t1)

        _baseline_col_t1 = f"{BASELINE_YEAR} (%)"
        _now_col_t1 = "Opinion nu (%)"
        const_detail_rows_t1 = []
        for p in PARTIES:
            v22 = _c22_t1.get(p, 0.0)
            v26 = _pred_t1.get(p, 0.0)
            const_detail_rows_t1.append({
                "parti_kod": p,
                "Parti": PARTY_NAMES.get(p, p),
                _baseline_col_t1: round(v22, 1),
                _now_col_t1: round(v26, 1),
                "Förändring (pp)": round(v26 - v22, 1),
            })
        const_detail_df_t1 = pd.DataFrame(const_detail_rows_t1)

        _chart_colors_t1 = [PARTY_COLORS.get(p, "#888") for p in PARTIES]
        _baseline_label_t1 = f"Valresultat {BASELINE_YEAR}"
        fig_const_t1 = go.Figure()
        fig_const_t1.add_trace(go.Bar(
            name=_baseline_label_t1,
            x=const_detail_df_t1["Parti"],
            y=const_detail_df_t1[_baseline_col_t1],
            marker_color=_chart_colors_t1,
            opacity=0.4,
            marker_pattern_shape="/",
            hovertemplate=f"<b>%{{x}}</b><br>{_baseline_label_t1}: <b>%{{y:.1f}}%</b><extra></extra>",
        ))
        fig_const_t1.add_trace(go.Bar(
            name="Opinion nu",
            x=const_detail_df_t1["Parti"],
            y=const_detail_df_t1[_now_col_t1],
            marker_color=_chart_colors_t1,
            opacity=0.95,
            # Ingen text-attribut – etiketter läggs som annotations för att
            # helt undvika att Plotly duplicerar värdet i hover-tooltip.
            hovertemplate="<b>%{x}</b><br>Opinion nu: <b>%{y:.1f}%</b><extra></extra>",
        ))

        # Lägg till stapeletiketter som annotations (helt frikopplade från hover)
        _y_max_t1 = max(
            const_detail_df_t1[_now_col_t1].max(),
            const_detail_df_t1[_baseline_col_t1].max()
        )
        _annotations_t1 = [
            dict(
                x=parti,
                y=val,
                text=f"{val:.1f}%",
                xanchor="center",
                yanchor="bottom",
                yshift=4,
                showarrow=False,
                font=dict(size=11, color="#111213"),
            )
            for parti, val in zip(
                const_detail_df_t1["Parti"],
                const_detail_df_t1[_now_col_t1],
            )
        ]

        fig_const_t1.update_layout(
            **ECONOMIST_BASE,
            barmode="group",
            hovermode="closest",
            title=dict(
                text=f"{sel_const_t1} — partistöd {BASELINE_YEAR} vs opinionen nu",
                font=dict(size=13, color="#111213"),
            ),
            xaxis=dict(showgrid=False, showline=True, linecolor="#cccccc", tickfont=dict(size=11)),
            yaxis=dict(
                showgrid=True, gridcolor="#ebebeb", zeroline=False, ticksuffix="%",
                range=[0, _y_max_t1 * 1.2],
            ),
            annotations=_annotations_t1,
            height=360,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            margin=dict(t=60, b=20, l=50, r=10),
        )
        st.plotly_chart(fig_const_t1, use_container_width=True, key="const_bar_tab1")

        def _color_const_chg_t1(val):
            try:
                v = float(val)
                if v > 0.5:  return "color:#2ca02c; font-weight:600"
                if v < -0.5: return "color:#d62728; font-weight:600"
            except Exception:
                pass
            return ""

        st.dataframe(
            const_detail_df_t1.drop(columns=["parti_kod"])
            .style
            .format({_baseline_col_t1: "{:.1f}", _now_col_t1: "{:.1f}", "Förändring (pp)": "{:+.1f}"})
            .map(_color_const_chg_t1, subset=["Förändring (pp)"]),
            hide_index=True, use_container_width=True,
        )

    # ── Tab 2: Mandatfördelning ──
    with tab2:
        st.plotly_chart(make_mandate_bar(mandates["total"]), use_container_width=True, key="mandate_bar_tab2")

        st.divider()
        st.subheader("Mandatprognos med osäkerhetsintervall")
        st.caption(
            f"Diamant = faktiskt {BASELINE_YEAR}-resultat. Skuggat område = 90 % konfidensintervall "
            "(baserat på 10 000 simuleringar). Tjock del = IQR (25:e–75:e percentil)."
        )
        st.plotly_chart(
            make_economist_mandate_chart(raw_est, sim, seats_2022_total),
            use_container_width=True,
            key="economist_mandate_tab2",
        )

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Mandatöversikt")
            mandate_df = pd.DataFrame([
                {
                    "Parti": PARTY_NAMES.get(p, p),
                    "Fasta": mandates["fixed_total"].get(p, 0),
                    "Utjämning": mandates["adjustment"].get(p, 0),
                    "Totalt": mandates["total"].get(p, 0),
                }
                for p in PARTIES if mandates["total"].get(p, 0) > 0
            ]).sort_values("Totalt", ascending=False)
            st.dataframe(mandate_df, hide_index=True, use_container_width=True)

        with col2:
            st.subheader("Blocköversikt")
            for bloc_name, bloc_parties in BLOC_PARTIES.items():
                total_bloc = sum(mandates["total"].get(p, 0) for p in bloc_parties)
                st.metric(bloc_name, f"{total_bloc} mandat")
                for p in bloc_parties:
                    m = mandates["total"].get(p, 0)
                    if m > 0:
                        st.write(f"  {PARTY_NAMES.get(p, p)}: {m}")
                st.markdown("---")

        # ── Mandatmarginal ──
        st.divider()
        st.subheader("Mandatmarginal – hur nära nästa mandat?")
        st.caption(
            "Minsta förändring i röstandel (procentenheter) som krävs för att ett "
            "parti ska vinna ett mandat till respektive förlora ett mandat. "
            "Skillnaden fördelas proportionellt på övriga partier (totalen hålls "
            "konstant). Beräknat med den fullständiga mandatmotorn, så 4 %-spärren "
            "och utjämningsdynamiken är inräknade."
        )

        # Nationellt – totala mandat
        st.markdown("**Nationellt — totala mandat (349)**")
        _nat = compute_national_margins(raw_est)
        _nat_cap = next((m["cap"] for m in _nat.values()), 12.0)

        def _fmt_gain(m):
            if m["gain_pp"] is None:
                return "—"
            if m["gain_threshold"]:
                return f"+{m['gain_pp']:.2f} → når 4 %-spärren (+{m['gain_to'] - m['seats']})"
            jump = m["gain_to"] - m["seats"]
            return f"+{m['gain_pp']:.2f}" + (f"  (+{jump})" if jump > 1 else "")

        def _fmt_lose(m, cap):
            if m["seats"] == 0:
                return "—"
            if m["lose_pp"] is None:
                return f"> {cap:.0f}"
            if m["lose_threshold"]:
                return f"−{m['lose_pp']:.2f} → under 4 %-spärren (−{m['seats']})"
            jump = m["seats"] - m["lose_to"]
            return f"−{m['lose_pp']:.2f}" + (f"  (−{jump})" if jump > 1 else "")

        _nat_rows = [
            {
                "Parti": PARTY_NAMES.get(p, p),
                "Andel (%)": f"{raw_est.get(p, 0):.1f}",
                "Mandat": _nat[p]["seats"],
                "För +1 mandat (pp)": _fmt_gain(_nat[p]),
                "För −1 mandat (pp)": _fmt_lose(_nat[p], _nat_cap),
            }
            for p in PARTIES
        ]
        st.dataframe(pd.DataFrame(_nat_rows), hide_index=True, use_container_width=True)

        # Sammanfattning: närmast att vinna / tappa ett mandat
        _gain_cand = [(p, _nat[p]["gain_pp"]) for p in PARTIES if _nat[p]["gain_pp"] is not None]
        _lose_cand = [(p, _nat[p]["lose_pp"]) for p in PARTIES
                      if _nat[p]["lose_pp"] is not None and _nat[p]["seats"] > 0]
        if _gain_cand and _lose_cand:
            _g = min(_gain_cand, key=lambda t: t[1])
            _l = min(_lose_cand, key=lambda t: t[1])
            st.caption(
                f"Närmast ett nytt mandat: **{PARTY_NAMES.get(_g[0], _g[0])}** "
                f"(+{_g[1]:.2f} pp). Närmast att tappa ett mandat: "
                f"**{PARTY_NAMES.get(_l[0], _l[0])}** (−{_l[1]:.2f} pp)."
            )

        # Lokalt – fasta valkretsmandat
        st.markdown("**Lokalt — fasta valkretsmandat per valkrets**")
        _mc1, _ = st.columns([1, 2])
        with _mc1:
            _margin_const = st.selectbox(
                "Välj valkrets",
                sorted(CONSTITUENCIES.keys()),
                key="margin_const_sel",
            )
        _seats_here = CONSTITUENCIES[_margin_const]["seats"]
        st.caption(
            f"{_margin_const}: {_seats_here} fasta mandat. Marginalen avser partiets "
            "lokala röstandel i valkretsen."
        )
        _loc = compute_constituency_margins(raw_est, _margin_const)
        _loc_cap = next((m["cap"] for m in _loc.values()), 20.0)
        _loc_rows = []
        for p in PARTIES:
            if p not in _loc:
                continue
            m = _loc[p]
            _g = "—" if m["gain_pp"] is None else f"+{m['gain_pp']:.2f}"
            if m["seats"] == 0:
                _l = "—"
            elif m["lose_pp"] is None:
                _l = f"> {_loc_cap:.0f}"
            else:
                _l = f"−{m['lose_pp']:.2f}"
            _loc_rows.append({
                "Parti": PARTY_NAMES.get(p, p),
                "Lokal andel (%)": f"{m['local_share']:.1f}",
                "Fasta mandat": m["seats"],
                "För +1 fast mandat (pp)": _g,
                "För −1 fast mandat (pp)": _l,
            })
        if _loc_rows:
            st.dataframe(pd.DataFrame(_loc_rows), hide_index=True, use_container_width=True)
        else:
            st.info("Inga spärrkvalificerade partier att visa för vald valkrets.")

        # Landets jämnaste fasta mandat
        st.markdown("**Landets jämnaste fasta mandat**")
        st.caption(
            "De valkretsmandat där minst lokal röstförändring krävs för att mandatet "
            "ska byta parti — i praktiken där valet avgörs."
        )
        _closest = compute_closest_fixed_seats(raw_est, top_n=15)
        if _closest:
            _close_df = pd.DataFrame([
                {
                    "Valkrets": r["Valkrets"],
                    "Mandat i valkr.": r["seats"],
                    "Närmast vinner": PARTY_NAMES.get(r["challenger"], r["challenger"]),
                    "Tappar till": PARTY_NAMES.get(r["loser"], r["loser"]) if r["loser"] else "–",
                    "Marginal (pp)": f"+{r['margin_pp']:.2f}",
                }
                for r in _closest
            ])
            st.dataframe(_close_df, hide_index=True, use_container_width=True)

    # ── Tab 3: Valkretsar ──
    with tab3:
        st.subheader("Partistöd per valkrets")
        const_names = sorted(CONSTITUENCIES.keys())
        sel_const = st.selectbox("Välj valkrets", const_names, key="tab3_const_sel")

        # Beräkna predicted vote share per valkrets med uniform swing
        # Använder raw_est – samma estimat som mandatfördelningen
        _c22 = CONSTITUENCIES[sel_const]
        _pred = estimate_constituency_votes(raw_est, _c22)

        _baseline_col = f"{BASELINE_YEAR} (%)"
        _now_col = "Opinion nu (%)"
        const_detail_rows = []
        for p in PARTIES:
            v22 = _c22.get(p, 0.0)
            v26 = _pred.get(p, 0.0)
            const_detail_rows.append({
                "parti_kod": p,
                "Parti": PARTY_NAMES.get(p, p),
                _baseline_col: round(v22, 1),
                _now_col: round(v26, 1),
                "Förändring (pp)": round(v26 - v22, 1),
            })
        const_detail_df = pd.DataFrame(const_detail_rows)

        # Stapeldiagram
        _chart_colors = [PARTY_COLORS.get(p, "#888") for p in PARTIES]
        _baseline_label = f"Valresultat {BASELINE_YEAR}"
        fig_const = go.Figure()
        fig_const.add_trace(go.Bar(
            name=_baseline_label,
            x=const_detail_df["Parti"],
            y=const_detail_df[_baseline_col],
            marker_color=_chart_colors,
            opacity=0.4,
            marker_pattern_shape="/",
            hovertemplate=f"%{{x}}<br>{_baseline_label}: <b>%{{y:.1f}}%</b><extra></extra>",
        ))
        fig_const.add_trace(go.Bar(
            name="Opinion nu",
            x=const_detail_df["Parti"],
            y=const_detail_df[_now_col],
            marker_color=_chart_colors,
            opacity=0.95,
            text=const_detail_df[_now_col].round(1).astype(str) + "%",
            textposition="outside",
            hovertemplate="%{x}<br>Opinion nu: <b>%{y:.1f}%</b><extra></extra>",
        ))
        fig_const.update_layout(
            **ECONOMIST_BASE,
            barmode="group",
            title=dict(
                text=f"{sel_const} — partistöd {BASELINE_YEAR} vs opinion nu",
                font=dict(size=13, color="#111213"),
            ),
            xaxis=dict(showgrid=False, showline=True, linecolor="#cccccc", tickfont=dict(size=11)),
            yaxis=dict(
                showgrid=True, gridcolor="#ebebeb", zeroline=False, ticksuffix="%",
                range=[0, max(const_detail_df[_now_col].max(),
                              const_detail_df[_baseline_col].max()) * 1.2],
            ),
            height=360,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            margin=dict(t=60, b=20, l=50, r=10),
        )
        st.plotly_chart(fig_const, use_container_width=True, key="const_bar_tab3")

        # Tabell
        def _color_const_chg(val):
            try:
                v = float(val)
                if v > 0.5:  return "color:#2ca02c; font-weight:600"
                if v < -0.5: return "color:#d62728; font-weight:600"
            except Exception:
                pass
            return ""

        st.dataframe(
            const_detail_df.drop(columns=["parti_kod"])
            .style
            .format({_baseline_col: "{:.1f}", _now_col: "{:.1f}", "Förändring (pp)": "{:+.1f}"})
            .map(_color_const_chg, subset=["Förändring (pp)"]),
            hide_index=True, use_container_width=True,
        )

        st.divider()
        st.subheader(f"Fasta mandat per valkrets – prognos vs {BASELINE_YEAR}")

        seats_2022 = compute_2022_mandates()

        # Bygg 2022-tabell i samma format som fixed_df
        df_2022 = pd.DataFrame(seats_2022).T.fillna(0).astype(int)
        df_2022["Totalt"] = df_2022[PARTIES].sum(axis=1)
        df_2022.index.name = "Valkrets"
        df_2022 = df_2022[[p for p in PARTIES if p in df_2022.columns] + ["Totalt"]]
        df_2022.columns = [PARTY_NAMES.get(c, c) if c != "Totalt" else c for c in df_2022.columns]

        # Differenstabell: prognos − 2022
        diff_df = fixed_df.copy()
        for col in diff_df.columns:
            if col in df_2022.columns:
                diff_df[col] = fixed_df[col] - df_2022[col]

        # Välj vy
        vy = st.radio(
            "Välj vy",
            ["Prognos", f"{BASELINE_YEAR} (faktiskt)", f"Förändring (prognos − {BASELINE_YEAR})"],
            horizontal=True,
            key="const_vy",
        )

        if vy == "Prognos":
            st.caption("Beräknade fasta valkretsmandat baserat på aktuell opinion.")
            st.dataframe(fixed_df, use_container_width=True)
        elif vy == f"{BASELINE_YEAR} (faktiskt)":
            st.caption(f"Faktiska fasta mandat från riksdagsvalet {BASELINE_ELECTION_DATE.day} september {BASELINE_YEAR}.")
            st.dataframe(df_2022, use_container_width=True)
        else:
            st.caption(f"Positivt tal = prognosen ger fler mandat än {BASELINE_YEAR}. Negativt = färre.")
            # Färgkoda med bakgrundsfärger
            def color_diff(val):
                if isinstance(val, (int, float)):
                    if val > 0:
                        return "background-color: #d4edda; color: #155724"
                    elif val < 0:
                        return "background-color: #f8d7da; color: #721c24"
                return ""
            st.dataframe(
                diff_df.style.map(color_diff),
                use_container_width=True,
            )

        st.divider()
        st.subheader("Partidetalj per valkrets")
        bar_party = st.selectbox(
            "Välj parti",
            options=PARTIES,
            format_func=lambda p: PARTY_NAMES.get(p, p),
            key="bar_party",
        )
        st.caption(f"Ljus stapel = {BASELINE_YEAR} faktiskt, mörk stapel = prognos.")
        st.plotly_chart(
            make_constituency_bar(mandates["fixed"], seats_2022, bar_party),
            use_container_width=True,
            key="const_bar_tab3_party",
        )

    # ── Tab 8: Metod & Källor ──
    with tab8:
        st.header("Metod & Källor")

        st.subheader("1. Opinionsaggregering – Kalman-filter med RTS-smoother")
        st.markdown(r"""
**Datakälla.** Appen hämtar samtliga tillgängliga opinionsmätningar från
[SwedishPolls](https://github.com/MansMeg/SwedishPolls) (Måns Magnusson, Uppsala
universitet), en öppen databas med svenska riksdagsundersökningar från 1980 och
framåt. Estimaten uppdateras dagligen eftersom fönstret rullar och äldre mätningar
faller ur.

**Tillståndsrymdsmodell.** Det latenta opinionsläget $x_t$ för varje parti modelleras
som en diskret random walk med oregelbundna tidssteg:

$$x_t = x_{t-1} + w_t, \quad w_t \sim \mathcal{N}\!\left(0,\; \sigma^2_{\mathrm{proc}} \cdot \Delta t\right)$$

Processbruset $\sigma_{\mathrm{proc}} = 0{,}10$ procentenheter per dag (≈ 0,7 pp per
vecka) kalibrerades empiriskt mot historiska opinionsvariationer.

**Observationsmodell.** Varje enskild mätning $y_i$ betraktas som ett brusigt utfall
av det latenta tillståndet:

$$y_i = x_{t_i} + v_i, \quad v_i \sim \mathcal{N}\!\left(0,\; \sigma^2_{\mathrm{obs},i}\right)$$

Observationsbruset modelleras utifrån binomialantagandet och institutsvikt $w_i$
(se avsnitt 2):

$$\sigma_{\mathrm{obs},i} = \frac{100\,\sqrt{\bar{p}_i\,(1-\bar{p}_i)\,/\,n_i}}{w_i}$$

Härledningen följer direkt av stickprovsvariansen för en andel $\bar{p}_i$
(uppmätt partistöd), skalad med institutsvikten. Formuleringen prioriterar stora,
träffsäkra undersökningar utan godtycklig halveringstid.

**Skattningsalgoritm.** Tillståndet skattas med en tvåpassalgoritm: framåtpasset
(standard Kalman-filter) bearbetas sekventiellt och följs av ett bakåtpass med
Rauch–Tung–Striebel (RTS) glatting, som korrigerar historiska estimat med
efterföljande observationsinformation. Bortom sista observation ökar posteriorvariansen
med $\sigma^2_{\mathrm{proc}} \cdot \Delta t$ per dag (random walk-antagande).
Trenddiagrammet visar 95 %-iga bayesianska konfidensband
($\pm 1{,}96 \times$ posterior standardavvikelse).

**Start i valresultatet.** Efter ett val nollställs filtret: senaste valresultatet
(riksdagsvalet """ + str(BASELINE_YEAR) + r""") läggs in som första observation med
$\sigma_{\mathrm{obs}} = 0{,}1$ pp, och endast mätningar publicerade *efter* valdagen
används (valdagens vallokalsundersökningar räknas bort). Direkt efter valet ligger
estimatet därför på utfallet och flyttas sedan bara av nya mätningar — gamla
mätningar från valrörelsen påverkar inte längre.

**Riksdagsspärren.** Partier med skattat stöd under 4,0 % exkluderas från
mandatberäkningen. **Övriga partier** beräknas som residualen
$100\% - \sum_p x_p$ per undersökning och smoothas med samma modell, men ingår
inte i mandatberäkningen.
""")

        st.subheader("2. Institutsviktning")
        st.markdown(r"""
Varje opinionsinstut tilldelas en vikt $w_k$ baserad på träffsäkerheten mot
riksdagsvalet """ + str(BASELINE_YEAR) + r""". För varje institut $k$ beräknas medelabsolut fel (MAE) i
procentenheter över de $P$ riksdagspartierna:

$$\mathrm{MAE}_k = \frac{1}{P} \sum_{p=1}^{P} \bigl| e_{k,p} - r_p \bigr|$$

där $e_{k,p}$ är institutets estimat och $r_p$ det faktiska valresultatet för
parti $p$. Vikten sätts proportionellt mot institutets relativa träffsäkerhet:

$$w_k = \frac{\bar{M}}{\mathrm{MAE}_k}, \qquad \bar{M} = \frac{1}{K}\sum_{k=1}^{K} \mathrm{MAE}_k$$

normaliserat så att det aritmetiska medelvärdet av vikterna är 1,0. Institut med
lägre MAE erhåller $w_k > 1$; institut som saknar historiska data tilldelas
standardvikten $w_k = 1{,}0$. Vikten inkorporeras i observationsbruset (avsnitt 1).
Inga systematiska biasjusteringar tillämpas — detta motiveras av transparensskäl
och för att undvika överanpassning till ett enda val.
""")

        st.subheader("3. Valkretsprognosmodell – uniform swing")
        st.markdown(r"""
Mandatberäkning per valkrets baseras på en **uniform swing**-modell (Curtice &
Steed, 1980). Låt $r_{p,c}$ beteckna valresultatet """ + str(BASELINE_YEAR) + r""" för parti $p$ i valkrets
$c$ och $\bar{r}_p$ rikssnittet samma år. Det geografiska bidraget definieras:

$$\delta_{p,c} = r_{p,c} - \bar{r}_p$$

Prognosen för parti $p$ i valkrets $c$ ges av:

$$e_{p,c} = \hat{x}_p + \delta_{p,c}$$

där $\hat{x}_p$ är det aktuella nationella Kalman-estimatet och $e_{p,c}$ är
prognosen för parti $p$ i valkrets $c$. Negativa värden
trunkeras till 0 och resultaten normaliseras till summan 100 %. Modellen antar
stabila regionala mönster — ett rimligt antagande på kort sikt men med ökande
fel vid starka geografiska rörelser.
""")

        st.subheader("4. Mandatfördelning – modifierad Sainte-Laguë")
        st.markdown(r"""
Mandat fördelas med **modifierad Sainte-Laguë-metoden**, identisk med
Valmyndighetens metod för riksdagsval (Vallagen 14 kap. 6 §).

**Fasta valkretsmandat (310 st).** Inom varje valkrets $c$ tilldelas parti $p$
mandat sekventiellt med kvoter $e_{p,c} / d_k$ där divisorserien är
$d = (1{,}2;\; 3;\; 5;\; 7;\; \ldots)$. Den sänkta första divisorn (1,2 sedan
2018; tidigare 1,4) ökar proportionaliteten för mindre partier marginellt.

**Utjämningsmandat (39 st).** Riksdagen görs nationellt proportionell: för varje
parti beräknas skillnaden mellan proportionell andel av 349 mandat och erhållna
fasta mandat, och utjämningsmandat fördelas tills skillnaden är noll. Modellen
garanterar att den totala mandatsumman exakt uppgår till 349.

Majoritetsgräns: 175 mandat (> 50 %).
""")

        st.subheader("5. Kandidatprediktion")
        st.markdown(r"""
Kandidatprediktionen baseras på Valmyndighetens officiella kandidatlistor för
riksdagsvalet 2026 (uppdateras löpande via val.se öppna data-API).

**Fasta valkretsmandat.** Varje kandidat tilldelas en *hemvalkrets* — den valkrets
där de uppnår lägst ordningsnummer — vilket approximerar personlig förankring och
historiska personkryssresultat. Valkretsar med störst antal mandat prioriteras
i allokeringsordningen, vilket förhindrar att toppkandidater "dubbelräknas" i
småvalkretsar. Inom varje valkrets väljs de $n$ högst rankade kandidaterna vars
hemvalkrets matchar, med fallback till samtliga kandidater om poolen underskrider $n$.

**Utjämningsmandat.** För varje parti med utjämningsmandat identifieras de kandidater
med bäst hemvalkrets-listplacering som inte redan invalts via fast mandat.
Utjämningsmandat är i modellen inte knutna till en specifik valkrets (formell
tilldelning kräver detaljerad mandatjämförelse per valkrets som faller utanför
modellens scope).

Personkryss simuleras inte. Avvikelse från faktiskt utfall förväntas i valresultat
med högt krysspådrag.
""")

        st.subheader("6. Datakällor")
        st.markdown("""
| Källa | Beskrivning | Länk |
|---|---|---|
| MansMeg/SwedishPolls | Opinionsundersökningar 1980– | [GitHub](https://github.com/MansMeg/SwedishPolls) |
| Valmyndigheten | Kandidatlistor 2026 & valresultat 2022 och 2026 (riksdag, kommun, region) | [val.se](https://www.val.se) |
| okfse/sweden-geojson | GeoJSON-karta över Sveriges 21 län | [GitHub](https://github.com/okfse/sweden-geojson) |
| Botten Ada (ada_code) | Inspiration för modellstruktur | [GitHub](https://github.com/MansMeg/ada_code) |
| Curtice & Steed (1980) | Uniform swing-modellen | *The British General Election of 1979* |

Valresultat per valkrets är hämtade från Valmyndighetens officiella slutresultat och
utgör referensdata för geografisk offset och institutsviktning.
""")

        st.subheader("7. Begränsningar & modellantaganden")
        st.markdown(r"""
**Uniform swing.** Modellen antar konstanta regionala mönster sedan senaste valet. Geografiska
rörelser — t.ex. differentierat tapp i storstäder kontra glesbygd — fångas inte upp,
vilket kan ge systematiska fel i enskilda valkretsar.

**Val idag vs valdagen.** Punktprognosen visar mandatfördelningen *om det vore val
idag*. Monte Carlo-simuleringen lägger dessutom till en horisontterm
$\sigma_{\mathrm{hor},p} = 0{,}566\,\sqrt{x_p}\,\sqrt{d / D}$, där $d$ är dagar kvar
till nästa val och $D$ mandatperiodens längd — ≈ 2 pp för ett 12 %-parti fyra år ut,
kalibrerat mot partiernas rörelse mellan valen 2018, 2022 och 2026. Termen går mot
noll när valdagen närmar sig.

**Övriga partier.** Övriga ingår inte i mandatberäkningen. Modellen kan inte fördela
Övrigas stöd på enskilda partier utan partispecifik polldata, vilket innebär att
ett genombrott nära 4 %-gränsen inte modelleras.

**Institutsvikter baserade på ett enda val.** Vikterna kalibreras mot """ + str(BASELINE_YEAR) + r""" och
riskerar att återspegla idiosynkratiska fel snarare än strukturell träffsäkerhet.
Med fler historiska val (t.ex. 2018, 2014) skulle skattningarna bli mer robusta.

**Personkryss.** Kandidatprediktionen baseras enbart på listordning. Historiskt
krysspådrag kan avsevärt förändra vem som väljs in, särskilt inom S och M.

**Karta.** Stockholm, Skåne och Västra Götaland innehåller flera valkretsar vars
mandat aggregeras till länet i kartvisningen.
""")

        st.subheader("8. Backtesting — träffsäkerhet inför senaste val")
        _bt_year = st.radio(
            "Backtesta mot",
            options=[BASELINE_YEAR, 2022],
            format_func=lambda y: f"Riksdagsvalet {y}",
            horizontal=True,
            key="bt_year_select",
        )
        _bt_date = BASELINE_ELECTION_DATE if _bt_year == BASELINE_YEAR else ELECTION_2022
        _bt_actual = BASELINE if _bt_year == BASELINE_YEAR else NATIONAL_2022
        st.markdown(rf"""
Out-of-sample-validering: modellen kördes retrospektivt för varje referensdatum
under det sista året före riksdagsvalet {_bt_year}. Felet mäts som
differensen $\hat{{e}}_p - r_p$ (procentenheter) per parti och datum. Aggregerade
mått: **MAE** (medelabsolut fel) och **RMSE** (root mean squared error).
""")
        with st.spinner("Beräknar backtesting..."):
            bt_df = compute_backtesting(
                polls_df, backtest_house_weights(polls_df, _bt_year),
                election_date=_bt_date, actual=_bt_actual,
            )

        # Sammanfattningsstatistik per referensdatum
        err_agg = bt_df.groupby(["Referensdatum", "Dagar till val"])["Fel (pp)"].agg(
            MAE=lambda x: float(np.mean(np.abs(x))),
            RMSE=lambda x: float(np.sqrt(np.mean(np.array(x)**2))),
        ).reset_index().sort_values("Dagar till val", ascending=False)

        # MAE + RMSE-diagram
        fig_bt = go.Figure()
        fig_bt.add_trace(go.Scatter(
            x=err_agg["Referensdatum"],
            y=err_agg["MAE"],
            mode="lines+markers",
            name="MAE",
            line=dict(color="#29BFA2", width=2.5),
            marker=dict(size=6, color="#29BFA2"),
            hovertemplate="Datum: %{x}<br>MAE: <b>%{y:.2f} pp</b><extra></extra>",
        ))
        fig_bt.add_trace(go.Scatter(
            x=err_agg["Referensdatum"],
            y=err_agg["RMSE"],
            mode="lines+markers",
            name="RMSE",
            line=dict(color="#E8112D", width=2.0, dash="dot"),
            marker=dict(size=6, color="#E8112D"),
            hovertemplate="Datum: %{x}<br>RMSE: <b>%{y:.2f} pp</b><extra></extra>",
        ))
        fig_bt.update_layout(
            **ECONOMIST_LAYOUT,
            title=dict(text=f"MAE och RMSE per referensdatum — inför valet {_bt_year}", font=dict(size=13, color="#111213")),
            xaxis_title="",
            yaxis_title="Fel (procentenheter)",
            height=340,
            margin=dict(t=50, b=20, l=60, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(fig_bt, use_container_width=True, key="backtesting_chart")
        st.caption(
            "Lägre MAE/RMSE = bättre träffsäkerhet. RMSE straffar stora enskilda fel hårdare än MAE. "
            "Felet sjunker typiskt ju närmre valet, eftersom fler färska mätningar finns tillgängliga."
        )

        # Per-parti-fellopp (felet vid 7 dagar kvar)
        st.markdown("**Fel per parti vid 7 dagar till valet**")
        final_errors = bt_df[bt_df["Dagar till val"] == 7][["Parti", "Estimat (%)", "Faktiskt (%)", "Fel (pp)"]].sort_values("Fel (pp)", key=abs, ascending=False)
        def color_error(val):
            try:
                v = float(val)
                if abs(v) <= 1.0:  return "background-color:#d4edda; color:#155724"
                elif abs(v) <= 2.0: return "background-color:#fff3cd; color:#856404"
                else:               return "background-color:#f8d7da; color:#721c24"
            except Exception:
                return ""
        st.dataframe(
            final_errors.style
                .format({"Estimat (%)": "{:.2f}", "Faktiskt (%)": "{:.2f}", "Fel (pp)": "{:+.2f}"})
                .map(color_error, subset=["Fel (pp)"]),
            hide_index=True, use_container_width=True,
        )

        # Övergripande summary metrics
        overall_mae  = float(np.mean(np.abs(bt_df["Fel (pp)"])))
        overall_rmse = float(np.sqrt(np.mean(bt_df["Fel (pp)"]**2)))
        final_mae    = float(np.mean(np.abs(bt_df[bt_df["Dagar till val"]==7]["Fel (pp)"])))
        m1, m2, m3 = st.columns(3)
        m1.metric("MAE (alla datum)", f"{overall_mae:.2f} pp")
        m2.metric("RMSE (alla datum)", f"{overall_rmse:.2f} pp")
        m3.metric("MAE (7 dagar till val)", f"{final_mae:.2f} pp")

    # ── Tab 4: Simulering ──
    with tab4:
        st.header("Monte Carlo-simulering")
        st.markdown(
            "Simulerar **10 000 möjliga utfall** baserat på osäkerheten i opinionsmätningarna. "
            "Varje simulation drar slumpmässiga röstandelar från en normalfördelning "
            "centrerad kring aggregeringen och med spridning baserad på variansen "
            "mellan de senaste mätningarna **plus hur mycket opinionen hinner röra sig "
            f"fram till valet {NEXT_ELECTION_YEAR}** ({_days_left} dagar kvar). "
            "Sannolikheterna avser alltså valdagen, inte ett val idag — osäkerheten "
            "krymper i takt med att valet närmar sig."
        )

        # ── Hur sannolikt är det att… ──
        st.divider()
        st.subheader("Hur sannolikt är det att…")

        # Verbal skala och procentformat definieras på ett ställe (mandatorn_model.text, D3).
        _fmt_pct, _verdict = display_pct, verbal

        _scenarios = [(q["text"], q["p"]) for q in evaluate_questions(sim)]

        for question, prob in _scenarios:
            verdict = _verdict(prob)
            pct_str = _fmt_pct(prob)
            bar_width = min(max(prob, 0.03), 1.0)
            bar_color = (
                "#29BFA2" if prob >= 0.70
                else "#a8a8a8" if prob >= 0.30
                else "#EF718C"
            )
            st.markdown(f"**{question}**")
            col_v, col_b = st.columns([1, 3])
            with col_v:
                st.markdown(f"*{verdict}*")
            with col_b:
                st.markdown(
                    f"""<div style="background:#e8e8e8; border-radius:4px; height:28px; width:100%; position:relative;">
                    <div style="background:{bar_color}; width:{bar_width*100:.1f}%; height:100%; border-radius:4px;
                         display:flex; align-items:center; justify-content:center;">
                    <span style="color:{'white' if prob > 0.15 else '#333'}; font-weight:600; font-size:0.9rem;">
                    {pct_str}</span></div></div>""",
                    unsafe_allow_html=True,
                )
            st.markdown("")
        st.divider()

        bh = sim["bloc_h"]
        bv = sim["bloc_v"]
        p_h_maj = float((bh >= 175).mean())
        p_v_maj = float((bv >= 175).mean())
        p_none   = max(0.0, 1.0 - p_h_maj - p_v_maj)

        # ── Sannolikheter för majoriteter ──
        st.subheader("Sannolikhet för riksdagsmajoritet")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Högerblocket ≥ 175", f"{p_h_maj*100:.1f} %")
            st.caption("M + L + KD + SD")
        with m2:
            st.metric("Vänsterblocket ≥ 175", f"{p_v_maj*100:.1f} %")
            st.caption("S + V + MP + C")
        with m3:
            st.metric("Inget block har majoritet", f"{p_none*100:.1f} %")
            st.caption("Hängt parlament")

        # Sannolikhetsstaplar
        fig_prob = go.Figure()
        for label, val, color in [
            ("Högerblocket", p_h_maj, "#29BFA2"),
            ("Vänsterblocket", p_v_maj, "#EF718C"),
            ("Inget block", p_none, "#999999"),
        ]:
            fig_prob.add_trace(go.Bar(
                x=[label], y=[val * 100],
                marker_color=color,
                text=[f"{val*100:.1f}%"],
                textposition="outside",
                width=0.4,
            ))
        fig_prob.update_layout(
            **ECONOMIST_LAYOUT,
            yaxis_title="Sannolikhet (%)",
            yaxis_range=[0, 105],
            height=300,
            showlegend=False, margin=dict(t=20, b=10, l=55, r=10),
        )
        st.plotly_chart(fig_prob, use_container_width=True, key="probability_bar_tab4")

        st.divider()

        # ── Mandatfördelning per block (histogram) ──
        st.subheader("Fördelning av riksdagsmandat per block")
        col1, col2 = st.columns(2)
        for col_obj, bloc_arr, bloc_name, color in [
            (col1, bh, "Högerblocket", "#29BFA2"),
            (col2, bv, "Vänsterblocket", "#EF718C"),
        ]:
            with col_obj:
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=bloc_arr, nbinsx=40,
                    marker_color=color, opacity=0.75,
                    name=bloc_name,
                    hovertemplate="Mandat: %{x}<br>Antal sim: %{y}<extra></extra>",
                ))
                fig_hist.add_vline(
                    x=175, line_dash="dash", line_color="black",
                    annotation_text="Majoritet (175)",
                    annotation_position="top right",
                )
                fig_hist.add_vline(
                    x=float(np.mean(bloc_arr)), line_color=color, line_width=2,
                    annotation_text=f"Snitt: {np.mean(bloc_arr):.0f}",
                    annotation_position="top left",
                )
                fig_hist.update_layout(
                    **ECONOMIST_LAYOUT,
                    title=dict(text=bloc_name, font=dict(size=13, color="#111213")),
                    xaxis_title="Mandat", yaxis_title="Antal simuleringar",
                    height=320,
                    showlegend=False, margin=dict(t=40, b=10, l=55, r=10),
                )
                st.plotly_chart(fig_hist, use_container_width=True, key=f"hist_{bloc_name}")

        st.divider()

        # ── Konfidensintervall per parti ──
        st.subheader("Konfidensintervall per parti (90 % CI)")
        ci_rows = []
        for p in PARTIES:
            arr = sim["party_mandates"][p]
            ci_rows.append({
                "Parti": PARTY_NAMES.get(p, p),
                "Estimat (%)": f"{raw_est.get(p, 0):.1f}",
                "σ polls": f"{sim['party_std'][p]:.1f}",
                "σ horisont": f"{sim['horizon_std'][p]:.1f}",
                "σ total": f"{sim['total_std'][p]:.1f}",
                "Mandat (snitt)": f"{np.mean(arr):.1f}",
                "5:e percentil": int(np.percentile(arr, 5)),
                "Median": int(np.median(arr)),
                "95:e percentil": int(np.percentile(arr, 95)),
                "P(över 4%)": f"{sim['above_threshold'][p]*100:.1f} %",
            })
        ci_df = pd.DataFrame(ci_rows)
        st.dataframe(ci_df, hide_index=True, use_container_width=True)

        st.divider()

        # ── Mandatfördelning per parti (box plot) ──
        st.subheader("Mandatspridning per parti")
        fig_box = go.Figure()
        for p in sorted(PARTIES, key=lambda x: -np.mean(sim["party_mandates"][x])):
            arr = sim["party_mandates"][p]
            if np.mean(arr) < 0.5:
                continue
            fig_box.add_trace(go.Box(
                y=arr,
                name=PARTY_NAMES.get(p, p),
                marker_color=PARTY_COLORS.get(p, "#888"),
                boxmean="sd",
                hovertemplate=(
                    f"<b>{PARTY_NAMES.get(p, p)}</b><br>"
                    "Median: %{median}<br>"
                    "Q1–Q3: %{q1}–%{q3}<br>"
                    "Min–Max: %{lowerfence}–%{upperfence}"
                    "<extra></extra>"
                ),
            ))
        fig_box.update_layout(
            **ECONOMIST_LAYOUT,
            yaxis_title="Mandat",
            height=420, showlegend=False,
            margin=dict(t=20, b=10, l=55, r=10),
        )
        st.plotly_chart(fig_box, use_container_width=True, key="box_mandates_tab4")

        st.caption(
            f"Baserat på {sim['n_sims']:,} simuleringar. "
            "σ polls = standardavvikelse bland senaste mätningarna. "
            f"σ horisont = förväntad opinionsrörelse fram till valet {NEXT_ELECTION_YEAR}. "
            "σ total inkluderar även 1,0 % strukturell osäkerhet."
        )

        # ── Koalitionsanalys ──
        st.divider()
        st.subheader("Koalitionsanalys")
        st.markdown(
            "Baserat på **10 000 simuleringar** — hur sannolikt är det att respektive "
            "koalitionskombination uppnår riksdagsmajoritet (≥ 175 mandat)?"
        )

        st.plotly_chart(make_coalition_chart(sim), use_container_width=True, key="coalition_bar_tab4")

        st.divider()
        st.subheader("Mandatfördelning per koalition")
        st.caption(
            "Lådagrammet visar median (linje), IQR (låda) och 90 % av simuleringarna (morrhår). "
            "Röd linje = majoritetsgräns (175 mandat)."
        )
        st.plotly_chart(make_coalition_mandate_dist(sim), use_container_width=True, key="coalition_dist_tab4")

        st.divider()
        st.subheader("Koalitionstabell")
        coal_rows = []
        n_sims_c = sim["n_sims"]
        pm_c = sim["party_mandates"]
        for name, parties in COALITIONS.items():
            arr = sum(pm_c.get(p, np.zeros(n_sims_c)) for p in parties)
            coal_rows.append({
                "Koalition": name,
                "Partier": " + ".join(parties),
                "P(majoritet)": f"{float((arr >= 175).mean())*100:.1f}%",
                "Snitt mandat": f"{float(arr.mean()):.0f}",
                "Median": int(np.median(arr)),
                "5:e percentil": int(np.percentile(arr, 5)),
                "95:e percentil": int(np.percentile(arr, 95)),
            })
        coal_rows.sort(key=lambda r: float(r["P(majoritet)"][:-1]), reverse=True)
        st.dataframe(pd.DataFrame(coal_rows), hide_index=True, use_container_width=True)

    # ── Tab 5: Kandidater ──
    with tab5:
        st.header("Förväntade riksdagsledamöter")
        st.markdown(
            "Baserat på mandatprognoserna och Valmyndighetens registrerade kandidatlistor "
            "för riksdagsvalet 2026. Kandidaterna visas i listordning — de överst på listan "
            "har störst chans att bli invalda."
        )

        with st.spinner("Hämtar kandidatdata från Valmyndigheten..."):
            cand_df = load_candidates()

        if cand_df.empty:
            st.error(
                "⚠️ **Kunde inte hämta kandidatdata från Valmyndigheten.**\n\n"
                "Kandidatregistreringen öppnar månader innan valet och kan vara otillgänglig "
                "tidigt. Kontrollera din internetanslutning och ladda om sidan."
            )
        else:
            # Registreringsstatus per parti
            reg_status = {}
            for p in PARTIES:
                n_const = cand_df[cand_df["parti"] == p]["valkrets"].nunique()
                n_cands = len(cand_df[cand_df["parti"] == p])
                reg_status[p] = {"valkretsar": n_const, "kandidater": n_cands}

            st.subheader("Registreringsstatus")
            st.caption(
                "Valmyndigheten öppnar kandidatregistreringen månader innan valet. "
                "Partier som ännu inte registrerat visas utan kandidater nedan."
            )
            status_rows = []
            for p in PARTIES:
                s = reg_status[p]
                status_rows.append({
                    "Parti": PARTY_NAMES.get(p, p),
                    "Registrerade kandidater": s["kandidater"],
                    "Valkretsar med kandidater": f"{s['valkretsar']} / 29",
                    "Status": "Registrerade" if s["kandidater"] > 0 else "Ej registrerade ännu",
                })
            status_df = pd.DataFrame(status_rows)

            def color_status(val):
                if val == "Registrerade":
                    return "background-color:#d4edda; color:#155724"
                elif val == "Ej registrerade ännu":
                    return "background-color:#fff3cd; color:#856404"
                return ""

            st.dataframe(
                status_df.style.map(color_status, subset=["Status"]),
                hide_index=True, use_container_width=True,
            )

            st.divider()

            # Prediktera invalda kandidater (fasta mandat + utjämningsmandat)
            elected = predict_elected_candidates(mandates["fixed"], cand_df)
            adj_constituencies = predict_adjustment_constituencies(
                mandates["adjustment"],
                mandates["fixed"],
                mandates["constituency_votes"],
                placement=mandates["adjustment_by_constituency"],
            )
            elected_adj = predict_adjustment_candidates(
                adj_constituencies, cand_df, elected
            )

            # Välj valkrets
            sel_valkrets = st.selectbox(
                "Välj valkrets",
                options=sorted(mandates["fixed"].keys()),
                key="cand_valkrets",
            )

            # Bygg tabell – visa ALLA partier med förutsedda mandat,
            # oavsett om de har registrerade kandidater eller ej
            rows = []
            valkrets_seats = mandates["fixed"].get(sel_valkrets, {})
            valkrets_cands = elected.get(sel_valkrets, {})

            for p in PARTIES:
                n_seats = valkrets_seats.get(p, 0)
                if n_seats == 0:
                    continue
                cands = valkrets_cands.get(p, [])
                if cands:
                    for c in cands:
                        rows.append({
                            "Parti": PARTY_NAMES.get(p, p),
                            "Förutsedda mandat": n_seats,
                            "Listplats": int(c["ordning"]) if pd.notna(c["ordning"]) else "–",
                            "Namn": c["namn"],
                            "Ålder": int(c["alder"]) if pd.notna(c["alder"]) else "–",
                            "Kön": "Kvinna" if str(c["kon"]).strip() == "K" else "Man",
                            "Hemkommun": c["hemkommun"] if pd.notna(c["hemkommun"]) else "–",
                            "Status": "Registrerad",
                        })
                else:
                    # Partiet har förutsedda mandat men inga registrerade kandidater
                    for rank in range(1, n_seats + 1):
                        rows.append({
                            "Parti": PARTY_NAMES.get(p, p),
                            "Förutsedda mandat": n_seats,
                            "Listplats": rank,
                            "Namn": "Ej registrerad ännu",
                            "Ålder": "–",
                            "Kön": "–",
                            "Hemkommun": "–",
                            "Status": "Ej registrerad",
                        })

            st.subheader(f"Förväntade invalda — {sel_valkrets}")
            if rows:
                cand_table = pd.DataFrame(rows)
                n_registered = (cand_table["Status"] == "Registrerad").sum()
                n_total = len(cand_table)
                st.caption(
                    f"{n_registered} av {n_total} förväntade mandat har registrerade kandidater. "
                    "Uppdateras automatiskt när fler partier registrerar sina listor."
                )

                def color_status_row(val):
                    if val == "Ej registrerad ännu":
                        return "background-color:#fff3cd; color:#856404"
                    return ""

                st.dataframe(
                    cand_table.drop(columns=["Status"]).style.map(
                        color_status_row,
                        subset=["Namn"],
                    ),
                    hide_index=True, use_container_width=True,
                )

                # Könsfördelning bland registrerade
                registered = cand_table[cand_table["Status"] == "Registrerad"]
                if len(registered) >= 2:
                    gender_counts = registered["Kön"].value_counts()
                    fig_gender = go.Figure(go.Bar(
                        x=gender_counts.index.tolist(),
                        y=gender_counts.values.tolist(),
                        marker_color=["#e07b8a", "#6baed6"],
                        marker_line_width=0,
                        text=gender_counts.values.tolist(),
                        textposition="outside",
                    ))
                    fig_gender.update_layout(
                        **ECONOMIST_LAYOUT,
                        title=dict(text=f"Könsfördelning (registrerade) — {sel_valkrets}", font=dict(size=13, color="#111213")),
                        height=280, showlegend=False,
                        margin=dict(t=40, b=20, l=50, r=10),
                        yaxis_title="Antal kandidater",
                    )
                    st.plotly_chart(fig_gender, use_container_width=True, key="gender_chart_tab5")

            st.divider()
            st.subheader("Alla förväntade invalda — riksdag totalt")
            all_rows = []
            for vk, party_dict in elected.items():
                for p, cands in party_dict.items():
                    for c in cands:
                        all_rows.append({
                            "Valkrets": vk,
                            "Parti": PARTY_NAMES.get(p, p),
                            "Listplats": int(c["ordning"]) if pd.notna(c["ordning"]) else None,
                            "Namn": c["namn"],
                            "Ålder": int(c["alder"]) if pd.notna(c["alder"]) else None,
                            "Kön": "Kvinna" if str(c["kon"]).strip() == "K" else "Man",
                            "Hemkommun": c["hemkommun"] if pd.notna(c["hemkommun"]) else "–",
                        })
            if all_rows:
                all_df = pd.DataFrame(all_rows)
                n_parties_reg = all_df["Parti"].nunique()
                # Dynamisk caption — lista partier som saknar kandidatdata
                _missing = [
                    PARTY_NAMES.get(p, p) for p in PARTIES
                    if p not in cand_df["parti"].unique() and mandates["total"].get(p, 0) > 0
                ]
                _missing_txt = (
                    f" {', '.join(_missing)} visas när de registrerar sina listor."
                    if _missing else ""
                )
                st.caption(
                    f"{len(all_df)} registrerade kandidater förutsedda att väljas in, "
                    f"från {n_parties_reg} partier.{_missing_txt}"
                )
                st.dataframe(all_df, hide_index=True, use_container_width=True)
                st.download_button(
                    "Ladda ner kandidatprediktion (CSV)",
                    data=all_df.to_csv(index=False),
                    file_name="riksdagsprediction_kandidater.csv",
                    mime="text/csv",
                )

            # ── Utjämningsmandat ──
            st.divider()
            st.subheader("Förutsedda utjämningsmandat")
            total_adj = sum(mandates["adjustment"].values())
            st.caption(
                f"Totalt {total_adj} utjämningsmandat fördelas nationellt för att "
                "göra riksdagen proportionell. Kandidaterna nedan är nästa i kön "
                "per parti — de som inte redan vunnit ett fast valkretsmandat."
            )
            st.info(
                "ℹ️ **Utjämningsvalkrets beräknad via Sainte-Laguë.** "
                "Kolumnen *Tilldelas valkrets* visar vilken valkrets mandatet "
                "går till enligt samma kvotlogik som Valmyndigheten använder — "
                "den valkrets där partiet har högst oanvänd Sainte-Laguë-kvot "
                "efter att fasta mandat är fördelade. Kandidaten är nästa person "
                "på den valkretsens lista. Personkryss modelleras inte och kan "
                "förändra ordningen.",
                icon=None,
            )

            adj_rows = []
            for p in PARTIES:
                n_adj = mandates["adjustment"].get(p, 0)
                if n_adj == 0:
                    continue
                cands = elected_adj.get(p, [])
                # Bygg lista av (adj_valkrets, kandidat) — en rad per mandat
                adj_consts = adj_constituencies.get(p, [])
                if cands:
                    for i, c in enumerate(cands):
                        vkr = c.get("adj_valkrets") or (adj_consts[i] if i < len(adj_consts) else "–")
                        adj_rows.append({
                            "Parti": PARTY_NAMES.get(p, p),
                            "Utjämn.": n_adj,
                            "Namn": c["namn"],
                            "Tilldelas valkrets": vkr or "–",
                            "Listplats": int(c["ordning"]) if pd.notna(c.get("ordning")) else "–",
                            "Ålder": int(c["alder"]) if pd.notna(c.get("alder")) else "–",
                            "Kön": "Kvinna" if str(c.get("kon", "")).strip() == "K" else "Man",
                            "Hemkommun": c["hemkommun"] if pd.notna(c.get("hemkommun")) else "–",
                            "Status": "Registrerad",
                        })
                else:
                    for i, vkr in enumerate(adj_consts[:n_adj]):
                        adj_rows.append({
                            "Parti": PARTY_NAMES.get(p, p),
                            "Utjämn.": n_adj,
                            "Namn": "Ej registrerad ännu",
                            "Tilldelas valkrets": vkr or "–",
                            "Listplats": "–",
                            "Ålder": "–",
                            "Kön": "–",
                            "Hemkommun": "–",
                            "Status": "Ej registrerad",
                        })

            if adj_rows:
                adj_df = pd.DataFrame(adj_rows)

                def color_adj_row(val):
                    if val == "Ej registrerad ännu":
                        return "background-color:#fff3cd; color:#856404"
                    return ""

                st.dataframe(
                    adj_df.drop(columns=["Status"]).style.map(
                        color_adj_row, subset=["Namn"]
                    ),
                    hide_index=True, use_container_width=True,
                )
                st.download_button(
                    "Ladda ner utjämningsmandat (CSV)",
                    data=adj_df.drop(columns=["Status"]).to_csv(index=False),
                    file_name="riksdagsprediction_utjamning.csv",
                    mime="text/csv",
                    key="dl_adj_cands",
                )

            st.divider()
            st.subheader("ℹ️ Så fungerar kandidatprediktionen")
            st.markdown("""
**Datakälla:** Valmyndighetens registrerade kandidatlistor för riksdagsvalet 2026.
Listan uppdateras löpande i takt med att partierna registrerar sina kandidater.

**Mandatunderlag:** Prognostiserat antal fasta valkretsmandat per parti och valkrets,
beräknat med modifierad Sainte-Laguë på Kalman-smoothade pollsiffror.

**En kandidat — en valkrets:**
Kandidater får lov att stå på listor i flera valkretsar samtidigt, men kan bara
bli invald från en. Modellen hanterar detta i två steg:

1. Varje kandidat tilldelas en *hemvalkrets* via sin hemkommun: den
   valkrets där kandidater från kommunen har bäst listplacering (vid lika
   placering: där flest kandidater från kommunen står).
2. Valkretsar med flest mandat tilldelas kandidater först. I första hand
   väljs kandidater vars hemvalkrets är denna valkrets, därefter kandidater
   utan känd hemkommun och sist övriga på listan, alltid i listordning.

**Utjämningsmandat:**
Utöver de fasta valkretsmandaten fördelas 39 utjämningsmandat för att
göra riksdagen proportionell. Varje partis utjämningsmandat placeras i den
valkrets där partiet har högst kvarvarande jämförelsetal (röstandel ×
valkretsens storlek som approximation, delat med 1,2 / 3 / 5 … efter antalet
mandat partiet redan fått där). Mandatet går sedan till nästa ej invalda
kandidat på partiets lista i den valkretsen.

**Begränsningar:**
Modellen förutsäger invalda enbart baserat på listplacering — personkryss
simuleras inte. Kandidater från partier som inte registrerat sina listor
ännu visas inte.
""")

    # ── Tab 7: Data ──
    with tab7:
        st.subheader("Senaste opinionsundersökningar")
        show_n = st.slider("Antal rader", 10, 200, 50)
        disp = polls_df[["PublDate", "Company", "n"] + PARTIES].tail(show_n).copy()
        disp["PublDate"] = disp["PublDate"].dt.strftime("%Y-%m-%d")
        disp = disp.sort_values("PublDate", ascending=False)
        fmt = {p: "{:.1f}" for p in PARTIES}
        fmt["n"] = "{:.0f}"
        st.dataframe(
            disp.style.format(fmt),
            hide_index=True, use_container_width=True,
        )

        st.subheader(f"Institutsvikter – träffsäkerhet mot {BASELINE_YEAR} års val")
        st.caption(
            "MAE = medelabsolut fel i procentenheter mot faktiskt valresultat. "
            f"Lägre MAE → högre vikt. Institut utan mätningar före valet {BASELINE_YEAR} får standardvikt 1,0."
        )

        # Färgkoda vikttabellen
        def color_weight(val):
            try:
                v = float(val)
                if v >= 1.3:   return "background-color:#d4edda; color:#155724"
                elif v >= 0.9: return "background-color:#fff3cd; color:#856404"
                else:          return "background-color:#f8d7da; color:#721c24"
            except Exception:
                return ""

        styled_hw = house_weights_df.style.map(
            color_weight, subset=["Vikt"]
        ).format({"MAE (pp)": "{:.3f}", "Vikt": "{:.3f}"})
        st.dataframe(styled_hw, hide_index=True, use_container_width=True)

        _indikator_row = house_weights_df[house_weights_df["Institut"] == "Indikator"]
        if not _indikator_row.empty:
            _ind_vikt = float(_indikator_row["Vikt"].iloc[0])
            _ind_mae  = float(_indikator_row["MAE (pp)"].iloc[0])
            st.caption(
                f"ℹ️ **Indikator** får vikten **{_ind_vikt:.3f}** "
                f"(MAE mot {BASELINE_YEAR} års val: {_ind_mae:.3f} pp)."
            )
        else:
            st.caption(f"ℹ️ Indikator saknas i {BASELINE_YEAR}-data och får standardvikt 1,0.")

        # Litet stapeldiagram för vikterna
        fig_hw = go.Figure(go.Bar(
            x=house_weights_df["Institut"],
            y=house_weights_df["Vikt"],
            text=house_weights_df["Vikt"].round(2),
            textposition="outside",
            marker_color=[
                "#2ca02c" if v >= 1.3 else "#ff7f0e" if v >= 0.9 else "#d62728"
                for v in house_weights_df["Vikt"]
            ],
        ))
        fig_hw.add_hline(y=1.0, line_dash="dash", line_color="gray",
                         annotation_text="Standardvikt (1,0)")
        fig_hw.update_layout(
            **ECONOMIST_LAYOUT,
            title=dict(text=f"Institutsvikter baserade på träffsäkerhet {BASELINE_YEAR}", font=dict(size=13, color="#111213")),
            yaxis_title="Vikt", yaxis_range=[0, house_weights_df["Vikt"].max() * 1.25],
            height=320, showlegend=False,
            margin=dict(t=50, b=10, l=55, r=10),
        )
        st.plotly_chart(fig_hw, use_container_width=True, key="house_weights_chart")

        st.subheader("Valresultat 2022 per valkrets (referensdata)")
        _c22 = pd.DataFrame(CONSTITUENCIES_2022).T
        _c22_fmt = {p: "{:.2f}" for p in PARTIES if p in _c22.columns}
        if "seats" in _c22.columns:
            _c22_fmt["seats"] = "{:.0f}"
        st.dataframe(
            _c22.style.format(_c22_fmt),
            use_container_width=True,
        )

        st.download_button(
            "Ladda ner mandatdata (CSV)",
            data=fixed_df.to_csv(),
            file_name="riksdagsprediction_mandat.csv",
            mime="text/csv",
        )


    # ── Tab 6: Regional & kommunal ──
    with tab6:
        st.header("Regional & kommunal valprediktion")
        st.markdown(
            f"Applicerar en **uniform swing-modell** på valresultaten {BASELINE_YEAR} per "
            "region och kommun. Modellen tar det aktuella nationella opinionsläget och "
            f"fördelar förändringen sedan valet {BASELINE_YEAR} lika i alla kommuner och "
            "regioner. Data från **Valmyndigheten** och **okfse/sweden-geojson**."
        )

        st.markdown(f"""
**Uniform swing** innebär att den nationella förändringen sedan valet {BASELINE_YEAR}
appliceras lika i alla kommuner. Om SD nationellt gått från 17,5 % → 19,0 % (+1,5 pp)
får varje kommun +1,5 pp på sin lokala {BASELINE_YEAR}-siffra — oavsett om kommunen
är SD-stark eller svag.

Det är en förenkling, men transparent och vanlig i valanalys.

`prediktion = {BASELINE_YEAR}-lokalt + nationell opinionssving (sedan {BASELINE_YEAR})`

Institutsviktning tillämpas på mandatprognosen och simuleringen.
Alla estimat bygger på Kalman-smoothade pollsiffror utan historisk korrigering.
**Lokalpartier** får ingen sving — de antas hålla sitt resultat från {BASELINE_YEAR}.
Källa: Valmyndigheten (slutligt resultat {BASELINE_YEAR}) · okfse/sweden-geojson · MansMeg/SwedishPolls.
""")

        # ── Kontroller ──
        val_type = st.radio(
            "Valtyp",
            ["Riksdag per kommun", "Regionval per region", "Kommunalval per kommun"],
            horizontal=False,
            key="map_val_type",
        )

        # ── Baslinje: senaste valets resultat per område ──
        if val_type == "Riksdag per kommun":
            base_df, _ = load_area_results("RD")
            ovriga_per_area = {}
            geo = load_geojson_url(MUNI_GEOJSON_URL)
            featureidkey = "properties.id"
        elif val_type == "Regionval per region":
            base_df, ovriga_per_area = load_area_results("RF")
            geo = load_geojson_url(REGION_GEOJSON_URL)
            featureidkey = "properties.name"
        else:  # Kommunalval
            base_df, ovriga_per_area = load_area_results("KF")
            geo = load_geojson_url(MUNI_GEOJSON_URL)
            featureidkey = "properties.id"
        id_col = "region_code"
        _base_col = f"{BASELINE_YEAR} (%)"
        _pred_col = "Opinion nu (%)"

        if base_df.empty:
            st.warning(
                f"Valresultat {BASELINE_YEAR} per område saknas — kör "
                "`python fetch_election_2026.py` och `python fetch_muni_cache.py`."
            )
        elif not geo:
            st.warning("Kunde inte hämta GeoJSON-karta från GitHub. Försök igen.")
        else:
            # ── Bygg name_map (kod → visningsnamn) ──
            if featureidkey == "properties.id":
                name_map_geo = {
                    f["properties"].get("id"): f["properties"].get("kom_namn", "")
                    for f in geo.get("features", [])
                }
            else:  # properties.name — för regioner är koden redan namnet
                name_map_geo = {
                    f["properties"].get("name"): f["properties"].get("name", "")
                    for f in geo.get("features", [])
                }

            predicted_df = apply_uniform_swing(
                base_df, raw_est, BASELINE,
                ovriga_per_area=ovriga_per_area,
            )

            # ── Detaljvy per vald kommun/region ──
            st.subheader("Detaljvy — välj en kommun eller region")

            # Bygg sorterad lista med visningsnamn
            area_codes = sorted(predicted_df[id_col].unique())
            area_display = {
                code: name_map_geo.get(code, code) for code in area_codes
            }
            # Sortera på namn
            sorted_areas = sorted(area_display.items(), key=lambda x: x[1])
            name_to_code = {name: code for code, name in sorted_areas}
            area_names_sorted = [name for _, name in sorted_areas]

            sel_area_name = st.selectbox(
                "Välj kommun / region",
                area_names_sorted,
                key="map_area_sel",
            )
            sel_area_code = name_to_code.get(sel_area_name, area_codes[0])

            # Hämta data för vald area
            area_pred = predicted_df[predicted_df[id_col] == sel_area_code]
            area_base = base_df[base_df["region_code"] == sel_area_code]

            pred_dict = dict(zip(area_pred["party"], area_pred["pct_predicted"]))
            hist_dict = dict(zip(area_base["party"], area_base["pct_base"]))

            detail_rows = []
            for p in PARTIES:
                pred_val = pred_dict.get(p, 0.0)
                hist_val = hist_dict.get(p, 0.0)
                detail_rows.append({
                    "parti_kod": p,
                    "Parti": PARTY_NAMES.get(p, p),
                    _base_col: round(hist_val, 1),
                    _pred_col: round(pred_val, 1),
                    "Förändring (pp)": round(pred_val - hist_val, 1),
                })
            # Lägg till ÖVRIGA för regionval och kommunalval — antas hålla sin baslinjenivå
            ov_pct = ovriga_per_area.get(sel_area_code, 0.0)
            if ov_pct > 0:
                detail_rows.append({
                    "parti_kod": "ÖVRIGA",
                    "Parti": "Lokala partier (ÖVRIGA)",
                    _base_col: round(ov_pct, 1),
                    _pred_col: round(ov_pct, 1),
                    "Förändring (pp)": 0.0,
                })
            detail_df = pd.DataFrame(detail_rows)

            # Stapeldiagram: bara riksdagspartierna (ej ÖVRIGA)
            chart_df = detail_df[detail_df["parti_kod"].isin(PARTIES)]
            chart_colors = [PARTY_COLORS.get(p, "#888") for p in chart_df["parti_kod"]]
            fig_detail = go.Figure()
            fig_detail.add_trace(go.Bar(
                name=f"Valresultat {BASELINE_YEAR}",
                x=chart_df["Parti"],
                y=chart_df[_base_col],
                marker_color=chart_colors,
                opacity=0.45,
                marker_pattern_shape="/",
            ))
            fig_detail.add_trace(go.Bar(
                name="Opinion nu",
                x=chart_df["Parti"],
                y=chart_df[_pred_col],
                marker_color=chart_colors,
                opacity=0.95,
                text=chart_df[_pred_col].round(1).astype(str) + "%",
                textposition="outside",
            ))
            fig_detail.update_layout(
                **ECONOMIST_BASE,
                barmode="group",
                title=dict(
                    text=f"{sel_area_name} — valet {BASELINE_YEAR} jämfört med opinionen nu",
                    font=dict(size=13, color="#111213"),
                ),
                xaxis=dict(
                    showgrid=False, showline=True,
                    linecolor="#cccccc", tickfont=dict(size=11),
                ),
                yaxis=dict(
                    showgrid=True, gridcolor="#ebebeb",
                    zeroline=False, ticksuffix="%",
                    range=[0, max(chart_df[_pred_col].max(),
                                  chart_df[_base_col].max()) * 1.2],
                ),
                height=360,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                margin=dict(t=60, b=20, l=50, r=10),
            )
            st.plotly_chart(fig_detail, use_container_width=True, key="regional_detail_tab6")

            # Detailtabell
            def _color_chg(val):
                try:
                    v = float(val)
                    if v > 0.5:   return "color:#2ca02c; font-weight:600"
                    if v < -0.5:  return "color:#d62728; font-weight:600"
                except Exception:
                    pass
                return ""

            display_detail = (
                detail_df.drop(columns=["parti_kod"])
                .style
                .format({_base_col: "{:.1f}", _pred_col: "{:.1f}", "Förändring (pp)": "{:+.1f}"})
                .map(_color_chg, subset=["Förändring (pp)"])
            )
            st.dataframe(display_detail, hide_index=True, use_container_width=True)

            # ── Nationell sving-tabell ──
            st.divider()
            st.subheader(f"Nationell svängning sedan valet {BASELINE_YEAR}")
            st.caption(
                f"Den nationella opinionsförändringen sedan valet {BASELINE_YEAR} som appliceras "
                "uniformt i alla kommuner och regioner. Svingen är **nollsummerad** "
                f"(polls och {BASELINE_YEAR} på samma bas, andel bland de 8 riksdagspartierna) "
                "så att den blir enhetlig över alla områden och inte förstärks för "
                f"stora partier. Därför kan den skilja sig något från polls minus {BASELINE_YEAR}."
            )
            _zero_swing = compute_national_swing(raw_est, BASELINE)
            swing_rows = []
            for p in PARTIES:
                cur = float(raw_est.get(p, 0))
                ref = float(BASELINE.get(p, 0))
                swing_rows.append({
                    "Parti": PARTY_NAMES.get(p, p),
                    f"Riksdag {BASELINE_YEAR} (%)": round(ref, 1),
                    "Nu i polls (%)": round(cur, 1),
                    "Opinionssving (pp)": f"{_zero_swing[p]:+.1f}",
                })
            swing_df = pd.DataFrame(swing_rows)

            def _color_total(val):
                try:
                    v = float(str(val).replace("+", ""))
                    if v > 0.3:   return "color:#2ca02c; font-weight:600"
                    if v < -0.3:  return "color:#d62728; font-weight:600"
                except Exception:
                    pass
                return ""

            st.dataframe(
                swing_df.style
                .format({f"Riksdag {BASELINE_YEAR} (%)": "{:.1f}", "Nu i polls (%)": "{:.1f}"})
                .map(_color_total, subset=["Opinionssving (pp)"]),
                hide_index=True, use_container_width=True,
            )

            # ── Fullständig tabell + nedladdning ──
            with st.expander("Visa tabell med alla kommuner/regioner"):
                wide_table = predicted_df.pivot_table(
                    index=id_col, columns="party", values="pct_predicted", aggfunc="first"
                ).reset_index()
                wide_table.columns.name = None
                party_cols_t = [p for p in PARTIES if p in wide_table.columns]
                wide_table.insert(
                    0, "Namn",
                    wide_table[id_col].map(name_map_geo).fillna(wide_table[id_col])
                )
                wide_table["Ledande"] = (
                    wide_table[party_cols_t]
                    .idxmax(axis=1)
                    .map(lambda x: PARTY_NAMES.get(x, x))
                )
                for p in party_cols_t:
                    wide_table[p] = wide_table[p].round(1)
                rename_cols = {p: f"{PARTY_NAMES.get(p, p)} (%)" for p in party_cols_t}
                rename_cols[id_col] = "Kod"
                wide_table = wide_table.rename(columns=rename_cols)
                pct_cols = [f"{PARTY_NAMES.get(p, p)} (%)" for p in party_cols_t]
                st.dataframe(
                    wide_table.style.format({c: "{:.1f}" for c in pct_cols}),
                    hide_index=True, use_container_width=True,
                )
                st.download_button(
                    "⬇️ Ladda ner prediktion (CSV)",
                    data=wide_table.to_csv(index=False).encode("utf-8"),
                    file_name="regional_prediktion.csv",
                    mime="text/csv",
                )

            # ── Opinionsbaserad mandatuppskattning (KF/RF) ──
            # Full kommunal/regional modell driven av uniform swing. Alltid
            # tillgänglig.
            if val_type in ("Kommunalval per kommun", "Regionval per region"):
                st.divider()
                _struct = _load_muni_structure_cached()
                if val_type == "Kommunalval per kommun":
                    _area = (_struct or {}).get("KF", {}).get(str(sel_area_code))
                    _area_label = "kommunfullmäktige"
                else:
                    _lan = REGION_NAME_TO_LAN.get(sel_area_name)
                    _area = (_struct or {}).get("RF", {}).get(_lan) if _lan else None
                    _area_label = "regionfullmäktige"

                if _area is None:
                    st.info(
                        f"{sel_area_name} saknar {_area_label}-struktur (t.ex. Gotland "
                        "som är en region-kommun utan regionval), eller så saknas "
                        "referensdata (kör `python fetch_muni_cache.py`)."
                    )
                else:
                    _swing = compute_national_swing(raw_est, BASELINE)
                    _render_opinion_area_mandat(_area, _swing, _area_label)


    # ── Tab Valnatt (uppspelning av valnatten 2026) ──
    with tab_valnatt:
        _render_valnatt_tab()

    # ── Tab 9: Om mig ──
    with tab9:
        st.header("Om mig")

        col_text, col_space = st.columns([2, 1])
        with col_text:
            st.markdown("""
### Oliver Rykatkin

Jag är **Senior Consultant inom insikter och Public Affairs** på
[Hallvarsson & Halvarsson](https://www.halvarsson.se) — ett av Sveriges ledande
kommunikationsbolag med fokus på finansiell kommunikation och samhällsfrågor.

Jag har en **kandidatexamen i Statistik från Uppsala Universitet**, vilket lagt grunden
för mitt intresse för kvantitativ analys och opinionsdata.

Vid sidan av arbetet har jag en **politisk bakgrund inom MUF och Moderaterna**
och sitter i nämnd i min hemkommun **Nacka**.

---

### Om Mandatorn

Mandatorn är ett personligt projekt som kombinerar mitt statistiska intresse med
mitt engagemang i svensk politik. Inspirerad av amerikanska valmodeller som
FiveThirtyEight ville jag se om liknande metodik går att tillämpa på svenska
riksdagsval — med opinionsmätningar, Kalman-smoother och Monte Carlo-simuleringar
som grund.

Modellen är öppen och transparent. Metodbeskrivningen finns i fliken **Metod**.
Alla synpunkter och förbättringsförslag tas tacksamt emot.
""")

        st.divider()
        st.caption(
            "Mandatorn är ett oberoende projekt och representerar inte Hallvarsson & Halvarsson "
            "eller Moderaterna. Alla prognoser är förenade med osäkerhet — se metodfliken för detaljer."
        )


if __name__ == "__main__":
    main()
