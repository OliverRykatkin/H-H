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
import json
from datetime import datetime, timedelta
from io import StringIO
import plotly.express as px
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────

POLLS_URL = (
    "https://raw.githubusercontent.com/MansMeg/SwedishPolls/master/Data/Polls.csv"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_regions.geojson"
)
CANDIDATES_URL = (
    "https://data.val.se/filer/val2026/parti/kandidaturer.csv"
)

# Valmyndighetens valkretsnamn → appens interna namn
VALKRETS_MAPPING = {
    "Stockholms kommun":            "Stockholms stad",
    "Stockholms län":               "Stockholms län",
    "Uppsala län":                  "Uppsala",
    "Södermanlands län":            "Södermanland",
    "Östergötlands län":            "Östergötland",
    "Jönköpings län":               "Jönköping",
    "Kronobergs län":               "Kronoberg",
    "Kalmar län":                   "Kalmar",
    "Gotlands län":                 "Gotland",
    "Blekinge län":                 "Blekinge",
    "Skåne läns norra och östra":   "Skåne N/Ö",
    "Skåne läns södra":             "Skåne S",
    "Skåne läns västra":            "Skåne V",
    "Malmö kommun":                 "Malmö",
    "Hallands län":                 "Halland",
    "Göteborgs kommun":             "Göteborg",
    "Västra Götalands läns norra":  "VG Norra",
    "Västra Götalands läns södra":  "VG Södra",
    "Västra Götalands läns västra": "VG Västra",
    "Västra Götalands läns östra":  "VG Östra",
    "Värmlands län":                "Värmland",
    "Örebro län":                   "Örebro",
    "Västmanlands län":             "Västmanland",
    "Dalarnas län":                 "Dalarna",
    "Gävleborgs län":               "Gävleborg",
    "Västernorrlands län":          "Västernorrland",
    "Jämtlands län":                "Jämtland",
    "Västerbottens län":            "Västerbotten",
    "Norrbottens län":              "Norrbotten",
}

PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"]

# PARTIES_WITH_OTHER inkluderar Övriga för trendgraf och estimattabell,
# men INTE för mandatberäkning (Övriga tar aldrig sig över spärren).
PARTIES_WITH_OTHER = PARTIES + ["O"]

PARTY_NAMES = {
    "M": "Moderaterna",
    "L": "Liberalerna",
    "C": "Centerpartiet",
    "KD": "Kristdemokraterna",
    "S": "Socialdemokraterna",
    "V": "Vänsterpartiet",
    "MP": "Miljöpartiet",
    "SD": "Sverigedemokraterna",
    "O": "Övriga",
}

PARTY_COLORS = {
    "M": "#52BDEC",
    "L": "#006AB3",
    "C": "#009933",
    "KD": "#000077",
    "S": "#E8112D",
    "V": "#AF0000",
    "MP": "#83CF39",
    "SD": "#DDDD00",
    "O": "#AAAAAA",
}

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

# Blocktillhörighet
BLOC_PARTIES = {
    "Högerblocket": ["M", "L", "KD", "SD"],
    "Vänsterblocket": ["S", "V", "MP", "C"],
}

# Koalitionskombinationer för sannolikhetsanalys
COALITIONS = {
    "Nuv. regering (M + L + KD + SD)": ["M", "L", "KD", "SD"],
    "Opposition (S + V + MP + C)": ["S", "V", "MP", "C"],
    "Rödgröna (S + V + MP)": ["S", "V", "MP"],
    "M + KD + SD (utan L)": ["M", "KD", "SD"],
    "Mittenblock (S + C + L)": ["S", "C", "L"],
    "Storkoalition (S + M)": ["S", "M"],
    "S + MP + C + L": ["S", "MP", "C", "L"],
}

# Riksdagsvalet 2022 – nationellt slutresultat
NATIONAL_2022 = {
    "M": 19.10, "L": 4.61, "C": 6.71, "KD": 5.34,
    "S": 30.33, "V": 6.75, "MP": 5.08, "SD": 20.54,
}

# Valens datum
ELECTION_2026 = datetime(2026, 9, 13)   # Preliminärt: andra söndagen i september 2026
ELECTION_2022 = datetime(2022, 9, 11)

# Nationella valresultat 2022 — används som referens i valkrets- och swing-modellen
# compute_polling_bias_2022() och compute_model_correction_2022()
# baserat på aggregatorns faktiska prestanda dagen innan valet 2022.

# ── Kart-URLs ──
MUNI_GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_municipalities.geojson"
)
REGION_GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_regions.geojson"
)

# ── SCB PX-Web API-endpoints för 2022 valresultat ──
SCB_RIKSDAG_URL = (
    "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104C/ME0104T3"
)
SCB_REGIONVAL_URL = (
    "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104B/ME0104T2"
)
SCB_KOMMUNVAL_URL = (
    "https://api.scb.se/OV0104/v1/doris/sv/ssd/ME/ME0104/ME0104A/ME0104T1"
)

# SCB använder "FP" för Liberalerna (heter "L" i appen)
SCB_TO_APP_PARTY = {"FP": "L"}
SCB_PARTIES_RAW = ["M", "C", "FP", "KD", "MP", "S", "V", "SD"]

# SCB regionval-koder (XXL / XXLG) → GeoJSON-namn för de 20 regionerna
# (Gotland saknas i SCB:s regionval-tabell – Region Gotland är en region-kommun)
SCB_REGIONVAL_TO_GEOJSON = {
    "01L":  "Stockholm",      "03L":  "Uppsala",
    "04L":  "Södermanland",   "05L":  "Östergötland",
    "06L":  "Jönköping",      "07L":  "Kronoberg",
    "08L":  "Kalmar",         "10L":  "Blekinge",
    "12L":  "Skåne",          "13L":  "Halland",
    "14L":  "Västra Götaland","17L":  "Värmland",
    "18L":  "Örebro",         "19L":  "Västmanland",
    "20LG": "Dalarna",        "21L":  "Gävleborg",
    "22L":  "Västernorrland", "23L":  "Jämtland",
    "24L":  "Västerbotten",   "25L":  "Norrbotten",
}
# Exakta regionval-koder att begära från SCB (20 st, Gotland exkluderas)
SCB_REGIONVAL_CODES = list(SCB_REGIONVAL_TO_GEOJSON.keys())

# Riksdagsvalet 2022 – per valkrets
CONSTITUENCIES_2022 = {
    "Blekinge":         {"seats": 5,  "M": 17.86, "L": 3.51, "C": 4.84,  "KD": 5.54,  "S": 31.14, "V": 4.44,  "MP": 2.91,  "SD": 28.53},
    "Dalarna":          {"seats": 9,  "M": 16.43, "L": 3.10, "C": 6.50,  "KD": 6.02,  "S": 31.66, "V": 5.33,  "MP": 3.80,  "SD": 25.69},
    "Gotland":          {"seats": 2,  "M": 16.81, "L": 2.82, "C": 11.72, "KD": 3.97,  "S": 34.64, "V": 6.37,  "MP": 6.47,  "SD": 15.69},
    "Gävleborg":        {"seats": 9,  "M": 16.24, "L": 2.99, "C": 6.25,  "KD": 5.10,  "S": 34.73, "V": 5.91,  "MP": 3.45,  "SD": 24.09},
    "Göteborg":         {"seats": 17, "M": 18.48, "L": 5.85, "C": 5.86,  "KD": 4.37,  "S": 27.65, "V": 12.85, "MP": 7.92,  "SD": 14.66},
    "Halland":          {"seats": 10, "M": 22.47, "L": 4.84, "C": 7.03,  "KD": 6.01,  "S": 28.27, "V": 4.04,  "MP": 3.59,  "SD": 22.58},
    "Jämtland":         {"seats": 4,  "M": 14.79, "L": 2.64, "C": 9.14,  "KD": 5.38,  "S": 36.07, "V": 5.59,  "MP": 5.02,  "SD": 20.11},
    "Jönköping":        {"seats": 11, "M": 18.73, "L": 3.70, "C": 7.45,  "KD": 9.31,  "S": 29.05, "V": 3.96,  "MP": 3.22,  "SD": 23.28},
    "Kalmar":           {"seats": 8,  "M": 17.78, "L": 3.18, "C": 6.53,  "KD": 6.96,  "S": 31.74, "V": 4.64,  "MP": 3.37,  "SD": 24.50},
    "Kronoberg":        {"seats": 6,  "M": 19.51, "L": 3.12, "C": 6.05,  "KD": 6.76,  "S": 30.97, "V": 5.03,  "MP": 3.47,  "SD": 23.61},
    "Malmö":            {"seats": 10, "M": 17.87, "L": 4.53, "C": 5.49,  "KD": 3.00,  "S": 29.57, "V": 12.49, "MP": 7.49,  "SD": 16.37},
    "Norrbotten":       {"seats": 8,  "M": 13.57, "L": 2.54, "C": 5.29,  "KD": 5.12,  "S": 41.64, "V": 6.98,  "MP": 3.44,  "SD": 20.30},
    "Skåne N/Ö":        {"seats": 10, "M": 19.52, "L": 3.76, "C": 4.95,  "KD": 6.15,  "S": 25.21, "V": 3.94,  "MP": 2.96,  "SD": 32.21},
    "Skåne S":          {"seats": 12, "M": 22.06, "L": 6.15, "C": 6.62,  "KD": 4.76,  "S": 25.35, "V": 4.96,  "MP": 5.55,  "SD": 23.36},
    "Skåne V":          {"seats": 9,  "M": 19.82, "L": 4.48, "C": 4.97,  "KD": 4.72,  "S": 27.34, "V": 4.61,  "MP": 3.54,  "SD": 28.75},
    "Stockholms stad":  {"seats": 29, "M": 19.07, "L": 6.87, "C": 8.48,  "KD": 3.17,  "S": 28.07, "V": 11.73, "MP": 10.02, "SD": 10.67},
    "Stockholms län":   {"seats": 40, "M": 24.01, "L": 5.95, "C": 7.39,  "KD": 4.89,  "S": 27.12, "V": 6.28,  "MP": 5.14,  "SD": 17.55},
    "Södermanland":     {"seats": 9,  "M": 19.21, "L": 3.59, "C": 5.94,  "KD": 4.74,  "S": 32.94, "V": 5.20,  "MP": 4.01,  "SD": 23.01},
    "Uppsala":          {"seats": 12, "M": 18.26, "L": 5.01, "C": 7.25,  "KD": 5.93,  "S": 29.13, "V": 7.85,  "MP": 6.73,  "SD": 18.18},
    "Värmland":         {"seats": 9,  "M": 17.05, "L": 3.71, "C": 6.34,  "KD": 5.81,  "S": 34.59, "V": 5.01,  "MP": 3.64,  "SD": 22.80},
    "Västerbotten":     {"seats": 8,  "M": 14.15, "L": 3.12, "C": 7.79,  "KD": 4.71,  "S": 40.73, "V": 8.50,  "MP": 5.44,  "SD": 14.46},
    "Västernorrland":   {"seats": 8,  "M": 13.97, "L": 2.74, "C": 7.45,  "KD": 5.41,  "S": 39.42, "V": 5.75,  "MP": 3.43,  "SD": 20.68},
    "Västmanland":      {"seats": 8,  "M": 19.13, "L": 4.16, "C": 5.40,  "KD": 5.01,  "S": 32.00, "V": 6.13,  "MP": 3.20,  "SD": 23.67},
    "VG Norra":         {"seats": 8,  "M": 17.53, "L": 3.63, "C": 5.72,  "KD": 6.17,  "S": 31.28, "V": 5.16,  "MP": 3.64,  "SD": 25.43},
    "VG Södra":         {"seats": 7,  "M": 18.92, "L": 3.84, "C": 7.09,  "KD": 6.96,  "S": 29.14, "V": 5.34,  "MP": 3.56,  "SD": 23.59},
    "VG Västra":        {"seats": 11, "M": 20.46, "L": 5.43, "C": 6.41,  "KD": 6.28,  "S": 28.03, "V": 5.68,  "MP": 5.18,  "SD": 21.20},
    "VG Östra":         {"seats": 8,  "M": 18.58, "L": 3.35, "C": 6.61,  "KD": 6.96,  "S": 31.40, "V": 4.45,  "MP": 3.26,  "SD": 24.12},
    "Örebro":           {"seats": 9,  "M": 16.74, "L": 4.55, "C": 6.26,  "KD": 5.34,  "S": 33.25, "V": 6.11,  "MP": 4.05,  "SD": 22.09},
    "Östergötland":     {"seats": 14, "M": 19.83, "L": 4.41, "C": 6.48,  "KD": 5.97,  "S": 30.55, "V": 5.62,  "MP": 4.63,  "SD": 21.20},
}

# Kartans 21 län → valkrets(er)
COUNTY_TO_CONSTITUENCIES = {
    "Stockholm":      ["Stockholms stad", "Stockholms län"],
    "Uppsala":        ["Uppsala"],
    "Södermanland":   ["Södermanland"],
    "Östergötland":   ["Östergötland"],
    "Jönköping":      ["Jönköping"],
    "Kronoberg":      ["Kronoberg"],
    "Kalmar":         ["Kalmar"],
    "Gotland":        ["Gotland"],
    "Blekinge":       ["Blekinge"],
    "Skåne":          ["Skåne N/Ö", "Skåne S", "Skåne V", "Malmö"],
    "Halland":        ["Halland"],
    "Västra Götaland":["Göteborg", "VG Norra", "VG Södra", "VG Västra", "VG Östra"],
    "Värmland":       ["Värmland"],
    "Örebro":         ["Örebro"],
    "Västmanland":    ["Västmanland"],
    "Dalarna":        ["Dalarna"],
    "Gävleborg":      ["Gävleborg"],
    "Västernorrland": ["Västernorrland"],
    "Jämtland":       ["Jämtland"],
    "Västerbotten":   ["Västerbotten"],
    "Norrbotten":     ["Norrbotten"],
}

TOTAL_SEATS = 349
FIXED_SEATS = 310
THRESHOLD = 4.0

# ─────────────────────────────────────────────
# DATAINHÄMTNING
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_polls() -> pd.DataFrame:
    try:
        resp = requests.get(POLLS_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
    except Exception as e:
        st.warning(f"Kunde inte hämta data från GitHub: {e}")
        return pd.DataFrame()

    df["PublDate"] = pd.to_datetime(df["PublDate"], errors="coerce")
    df = df.dropna(subset=["PublDate"])
    for p in PARTIES:
        df[p] = pd.to_numeric(df[p], errors="coerce")
    df = df[df["house"] != "Election"].copy()
    df = df.dropna(subset=PARTIES, how="all")
    # Beräkna Övriga som residual (100 − summan av de 8 partierna)
    party_sum = df[PARTIES].sum(axis=1, min_count=1)
    df["O"] = (100 - party_sum).clip(lower=0)
    return df.sort_values("PublDate")


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


@st.cache_data(ttl=86400, show_spinner=False)
def _scb_get_region_codes(api_url: str) -> list:
    """Hämtar alla giltiga Region-koder för en SCB PX-Web-tabell."""
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        meta = resp.json()
    except Exception:
        return []
    region_var = next(
        (v for v in meta.get("variables", []) if v["code"] == "Region"), None
    )
    return region_var["values"] if region_var else []


@st.cache_data(ttl=86400, show_spinner=False)
def load_scb_results(
    api_url: str,
    contents_code: str,
    region_codes: list | None = None,
    party_codes: list | None = None,
) -> pd.DataFrame:
    """
    Hämtar 2022 valresultat per geografisk enhet från SCB PX-Web API.
    SCB kräver att Region-koder anges explicit i frågan (utelämning ger rikssnitt).
    region_codes=None → hämtar alla 4-siffriga kommuner automatiskt.
    party_codes=None  → hämtar de 8 riksdagspartierna (SCB_PARTIES_RAW).
    Returnerar DataFrame med kolumner: region_code, party, pct_2022
    """
    import re as _re

    if region_codes is None:
        all_codes = _scb_get_region_codes(api_url)
        region_codes = [c for c in all_codes if _re.match(r"^\d{4}$", c)]

    if not region_codes:
        return pd.DataFrame(columns=["region_code", "party", "pct_2022"])

    parties_to_fetch = party_codes if party_codes is not None else SCB_PARTIES_RAW

    query = {
        "query": [
            {
                "code": "Region",
                "selection": {"filter": "item", "values": region_codes},
            },
            {
                "code": "Partimm",
                "selection": {"filter": "item", "values": parties_to_fetch},
            },
            {
                "code": "ContentsCode",
                "selection": {"filter": "item", "values": [contents_code]},
            },
            {
                "code": "Tid",
                "selection": {"filter": "item", "values": ["2022"]},
            },
        ],
        "response": {"format": "json"},
    }
    try:
        resp = requests.post(api_url, json=query, timeout=120)
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        return pd.DataFrame(columns=["region_code", "party", "pct_2022"])

    rows = []
    for item in raw.get("data", []):
        keys = item.get("key", [])
        if len(keys) < 2:
            continue
        region_code = str(keys[0])
        party_scb = keys[1]
        vals = item.get("values", [])
        val_str = vals[0] if vals else None
        if not val_str or val_str in ("..", ""):
            continue
        party = SCB_TO_APP_PARTY.get(party_scb, party_scb)
        try:
            pct = float(val_str)
        except (ValueError, TypeError):
            continue
        rows.append({"region_code": region_code, "party": party, "pct_2022": pct})

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["region_code", "party", "pct_2022"]
    )



def apply_uniform_swing(
    df: pd.DataFrame,
    national_current: dict,
    national_2022: dict,
    ovriga_per_area: dict | None = None,
) -> pd.DataFrame:
    """
    Uniform swing-modell:
      predicted[p][area] = 2022_local[p][area] + total_swing[p]
      total_swing[p] = national_current[p] − national_2022[p]

    Normaliseras per geografisk enhet.
    Om ovriga_per_area anges (kommunalval/regionval) summeras de 8 partierna
    till (100 − ÖVRIGA%) per område, så att ÖVRIGA antas hålla sin 2022-nivå.
    """
    if df.empty:
        return df

    effective_current = {
        p: float(national_current.get(p, 0))
        for p in PARTIES
    }

    swings = {
        p: effective_current[p] - float(national_2022.get(p, 0))
        for p in PARTIES
    }

    result = df.copy()
    result["swing"] = result["party"].map(swings).fillna(0.0)
    result["pct_raw"] = (result["pct_2022"] + result["swing"]).clip(lower=0.0)

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


@st.cache_data(ttl=3600)
def load_candidates() -> pd.DataFrame:
    """
    Hämtar kandidaturdata från Valmyndigheten för riksdagsvalet 2026.

    Filtrerar på VALTYP=RD, mappar valkretsnamn till appens interna format
    och returnerar en DataFrame med kolumnerna:
      parti, valkrets, namn, ordning, alder, kon, hemkommun
    """
    try:
        resp = requests.get(CANDIDATES_URL, timeout=20)
        resp.raise_for_status()
        # Dekoda med utf-8-sig för att ta bort BOM-tecknet i början av filen
        text = resp.content.decode("utf-8-sig")
        df = pd.read_csv(StringIO(text), sep=";", on_bad_lines="skip")
    except Exception as e:
        st.warning(f"Kunde inte hämta kandidatdata: {e}")
        return pd.DataFrame()

    rd = df[df["VALTYP"] == "RD"].copy()

    # Filtrera bort rikslistan ("HELA LANDET") — den innehåller nationellt
    # placerade kandidater som dyker upp under alla valkretsar i rådata och
    # skulle blanda ihop lokala listor med den nationella listan.
    rd = rd[rd["VALKRETSBETECKNING PÅ VALSEDELN"].str.strip() != "HELA LANDET"]

    rd["parti"] = rd["PARTIFÖRKORTNING"].str.strip()
    rd["valkrets"] = rd["VALKRETSNAMN"].map(VALKRETS_MAPPING)
    rd["ordning"] = pd.to_numeric(rd["ORDNING"], errors="coerce")

    rd = rd[["parti", "valkrets", "NAMN", "ordning", "ÅLDER_PÅ_VALDAGEN", "KÖN", "FOLKBOKFÖRINGSKOMMUN"]].copy()
    rd.columns = ["parti", "valkrets", "namn", "ordning", "alder", "kon", "hemkommun"]
    rd = rd.dropna(subset=["valkrets", "namn"])
    rd = rd[rd["parti"].isin(PARTIES)]
    return rd.reset_index(drop=True)


def predict_elected_candidates(fixed_seats: dict, candidates_df: pd.DataFrame) -> dict:
    """
    Matchar mandatprediktionen mot kandidatlistorna och returnerar
    de förväntade invalda riksdagsledamöterna per valkrets och parti.

    Strategi (tre pass):
      1. Bygg hemkommun→valkrets-mappning från data: varje kommuns "hemvalkrets"
         är den valkrets som listar flest kandidater från den kommunen.
      2. Per valkrets (störst först): välj i första hand kandidater vars hemkommun
         tillhör denna valkrets — de "reserveras" för sin hemmavalkrets.
      3. Fyll resterande platser med kandidater vars hemkommun är okänd.
      4. Sista utväg: ta vem som helst på den lokala listan.

    Logiken gör att rikspolitiker (Ulf Kristersson i Södermanland, Elisabeth
    Svantesson i Örebro) tilldelas rätt valkrets även om de finns på fler listor.

    Returns: {valkrets: {parti: [{'namn':…, 'ordning':…, 'alder':…, 'kon':…, 'hemkommun':…}]}}
    """
    if candidates_df.empty:
        return {valkrets: {} for valkrets in fixed_seats}

    # ── Hemkommun → naturlig valkrets (datadrivet) ──────────────────────────
    # För varje hemkommun: den valkrets där flest kandidater med den kommunen
    # är listade. Ger en proxy för geografi utan hårdkodad geodata.
    _hk = candidates_df[candidates_df["hemkommun"].notna() & candidates_df["ordning"].notna()]
    hemkommun_to_valkrets: dict[str, str] = {}
    if not _hk.empty:
        # Primär sortering: lägsta ordningsnummer (en kandidat på plats 2 i
        # Dalarna men plats 32 i Stockholm pekar tydligt på Dalarna).
        # Sekundär sortering: antal kandidater vid oavgjort (Stockholm stad
        # har många fler plats-1-kandidater med hemkommun Stockholm än vad
        # Östergötland har, trots att båda har min_ordning = 1).
        _stats = (
            _hk.groupby(["hemkommun", "valkrets"])["ordning"]
            .agg(min_ordning="min", count="size")
            .reset_index()
            .sort_values(["min_ordning", "count"], ascending=[True, False])
        )
        hemkommun_to_valkrets = (
            _stats
            .drop_duplicates(subset="hemkommun")
            .set_index("hemkommun")["valkrets"]
            .to_dict()
        )

    cdf = candidates_df.copy()
    cdf["natural_valkrets"] = cdf["hemkommun"].map(hemkommun_to_valkrets)

    # ── Lås kandidater till sin hemmavalkrets ────────────────────────────────
    # En kandidat låses till sin naturliga valkrets om tre villkor är uppfyllda:
    #   1. Hemkommun mappas till en känd valkrets (natural_valkrets finns)
    #   2. Kandidaten faktiskt finns på den valkretsens lista
    #   3. Partiet vinner minst ett fast mandat i den valkretsen
    # Låsta kandidater är INTE tillgängliga för andra valkretsar — de räknas
    # enbart för sin hemmavalkrets, oavsett hur högt de listas på andras listor.

    party_wins_in: dict[str, set[str]] = {}
    for c, pdict in fixed_seats.items():
        for p, n in pdict.items():
            if n > 0:
                party_wins_in.setdefault(p, set()).add(c)

    listed_in: set[tuple] = set(zip(cdf["parti"], cdf["namn"], cdf["valkrets"]))
    const_seats_dict = {k: v["seats"] for k, v in CONSTITUENCIES_2022.items()}

    locked_to: dict[str, str] = {}   # "{parti}|{namn}" → hemmavalkrets

    # Lås 1: hemkommun-baserad (primär)
    for _, row in cdf.drop_duplicates(["parti", "namn"]).iterrows():
        nv = row.get("natural_valkrets")
        if not nv:
            continue
        parti, namn = row["parti"], row["namn"]
        if (
            (parti, namn, nv) in listed_in
            and nv in party_wins_in.get(parti, set())
        ):
            locked_to[f"{parti}|{namn}"] = nv

    # Lås 2: för kandidater utan hemkommun som finns på flera listor
    # (t.ex. partiledare vars adress är skyddad) — tilldela minsta valkrets
    # där partiet vinner mandat och kandidaten är listad. Partiledare placeras
    # typiskt på sin hemmavalkrets listade oavsett storlek, och den minsta
    # listan de finns på är ofta den "riktiga" (de är mest unika/avgörande där).
    multi_no_hk = (
        cdf[cdf["natural_valkrets"].isna()]
        .groupby(["parti", "namn"])["valkrets"]
        .nunique()
    )
    for (parti, namn) in multi_no_hk[multi_no_hk > 1].index:
        key = f"{parti}|{namn}"
        if key in locked_to:
            continue   # redan låst via hemkommun
        appearances = cdf[
            (cdf["parti"] == parti) & (cdf["namn"] == namn)
        ]["valkrets"].tolist()
        eligible = [v for v in appearances if v in party_wins_in.get(parti, set())]
        if not eligible:
            continue
        home = min(eligible, key=lambda v: const_seats_dict.get(v, 999))
        locked_to[key] = home

    # ── Allokera mandat ──────────────────────────────────────────────────────
    # Processen behöver inte storleksordnas — låsningen hanterar konflikten.
    # Kandidater sorteras i ordningsföljd per valkretslista.
    # Pass 1: plocka kandidater som är tillgängliga (ej låsta till annan valkrets)
    # Pass 2: sista utväg — ta låsta-till-annan om lokala kandidater inte räcker

    elected: set[str] = set()
    result: dict = {}

    for valkrets, party_seats in fixed_seats.items():
        result[valkrets] = {}
        for parti, n_seats in party_seats.items():
            if n_seats == 0:
                continue

            local = cdf[
                (cdf["parti"] == parti) &
                (cdf["valkrets"] == valkrets)
            ].sort_values("ordning")

            chosen: list = []

            # Pass 1: ta kandidater som inte är låsta till annan valkrets
            for _, row in local.iterrows():
                key = f"{parti}|{row['namn']}"
                if key in elected:
                    continue
                lock = locked_to.get(key)
                if lock and lock != valkrets:
                    continue   # reserverad för sin hemmavalkrets
                chosen.append(row.to_dict())
                elected.add(key)
                if len(chosen) == n_seats:
                    break

            # Pass 2: sista utväg — ta låsta kandidater om listan är för kort
            if len(chosen) < n_seats:
                for _, row in local.iterrows():
                    key = f"{parti}|{row['namn']}"
                    if key in elected:
                        continue
                    chosen.append(row.to_dict())
                    elected.add(key)
                    if len(chosen) == n_seats:
                        break

            if chosen:
                result[valkrets][parti] = chosen

    return result


def predict_adjustment_constituencies(
    adjustment: dict,
    fixed_seats: dict,
    constituency_votes: dict,
) -> dict:
    """
    Beräknar vilka valkretsar som ger ett parti dess utjämningsmandat.

    Använder samma Sainte-Laguë-logik som Valmyndigheten: efter att fasta
    mandat är fördelade fortsätter kvotserien för varje (parti, valkrets)-par.
    Utjämningssätet går iterativt till den valkrets med högst nästa kvot.

    Divisorserien: 1,2 → 3 → 5 → 7 → … (modifierad Sainte-Laguë)

    Returns: {parti: [valkrets1, valkrets2, …]}  (längd = antal adj-mandat)
    """
    def _next_divisor(k: int) -> float:
        return 1.2 if k == 0 else float(2 * k + 1)

    # Skalningsfaktor per valkrets: antal fasta mandatplatser är proportionellt
    # mot antalet röstberättigade. Genom att multiplicera röstandel med
    # mandatantal approximerar vi faktiska röstetal — annars "vinner" alltid
    # Gotland (2 mandat, delar med 1,2) mot Stockholm (42 mandat, delar med 17).
    const_seats = {k: v["seats"] for k, v in CONSTITUENCIES_2022.items()}

    # Startläge: antal fasta mandat per (parti, valkrets)
    seat_tally: dict = {}
    for constituency, party_dict in fixed_seats.items():
        for party, seats in party_dict.items():
            seat_tally[(party, constituency)] = int(seats)

    result = {}
    for party, n_adj in adjustment.items():
        if n_adj == 0:
            continue
        local_tally = {c: seat_tally.get((party, c), 0) for c in constituency_votes}
        assigned = []
        for _ in range(n_adj):
            best_c, best_q = None, -1.0
            for constituency, votes in constituency_votes.items():
                pct = votes.get(party, 0.0)
                # Skala till pseudo-röster via valkretsens mandatantal
                scaled_votes = pct * const_seats.get(constituency, 1)
                k = local_tally.get(constituency, 0)
                q = scaled_votes / _next_divisor(k)
                if q > best_q:
                    best_q = q
                    best_c = constituency
            if best_c:
                assigned.append(best_c)
                local_tally[best_c] = local_tally.get(best_c, 0) + 1
        if assigned:
            result[party] = assigned
    return result


def predict_adjustment_candidates(
    adj_constituencies: dict,
    candidates_df: pd.DataFrame,
    elected_fixed: dict,
) -> dict:
    """
    Plockar rätt kandidat för varje utjämningsmandat baserat på vilken
    valkrets mandatet tilldelas (från predict_adjustment_constituencies).

    För varje (parti, valkrets)-utjämningssäte väljs nästa icke-invalda
    kandidat på den valkretsens lista i ordningsföljd.

    Args:
        adj_constituencies: {parti: [valkrets1, valkrets2, …]}
        candidates_df:      kandidatregistret
        elected_fixed:      redan invalda via fasta mandat

    Returns: {parti: [{'namn':…, 'ordning':…, 'alder':…, 'kon':…,
                        'hemkommun':…, 'adj_valkrets':…}]}
    """
    if candidates_df.empty:
        return {}

    # Samla alla som redan vunnit ett fast mandat
    already_elected: set[str] = set()
    for valkrets, party_dict in elected_fixed.items():
        for parti, cands in party_dict.items():
            for c in cands:
                already_elected.add(f"{parti}|{c['namn']}")

    result = {}
    for parti, constituencies in adj_constituencies.items():
        chosen = []
        picked_this_round: set[str] = set()

        for adj_valkrets in constituencies:
            pool = candidates_df[
                (candidates_df["parti"] == parti) &
                (candidates_df["valkrets"] == adj_valkrets)
            ].sort_values("ordning")

            for _, row in pool.iterrows():
                key = f"{parti}|{row['namn']}"
                if key in already_elected or key in picked_this_round:
                    continue
                rec = row.to_dict()
                rec["adj_valkrets"] = adj_valkrets
                chosen.append(rec)
                picked_this_round.add(key)
                break

        if chosen:
            result[parti] = chosen
    return result


# ─────────────────────────────────────────────
# AGGREGERINGSMODELL
# ─────────────────────────────────────────────

@st.cache_data
def compute_house_weights(df: pd.DataFrame) -> pd.DataFrame:
    """
    Beräknar träffsäkerhetsvikter per opinionsinsitut baserat på 2022 års val.

    Metod:
      1. Hämta alla mätningar de 90 dagarna *före* riksdagsvalet 11 sept 2022
      2. Beräkna medelabsolut fel (MAE) mot faktiskt valresultat per parti
      3. Vikt = 1 / MAE, normaliserad så att genomsnittet = 1
         (okända institut får standardvikt 1,0)
    """
    ELECTION_DATE = pd.Timestamp("2022-09-11")
    ACTUAL = NATIONAL_2022

    window = df[
        (df["PublDate"] >= ELECTION_DATE - pd.Timedelta(days=90))
        & (df["PublDate"] < ELECTION_DATE)
        & (df["house"] != "Election")
    ].copy()

    rows = []
    for house, grp in window.groupby("Company"):
        maes = []
        for p in PARTIES:
            vals = grp[p].dropna()
            if len(vals) > 0:
                maes.append(abs(vals.mean() - ACTUAL[p]))
        if maes:
            rows.append({
                "Institut": house,
                "MAE (pp)": round(float(np.mean(maes)), 3),
                "Antal mätningar (2022)": len(grp),
            })

    if not rows:
        return pd.DataFrame(columns=["Institut", "MAE (pp)", "Antal mätningar (2022)", "Vikt"])

    house_df = pd.DataFrame(rows).sort_values("MAE (pp)")
    inv_mae = 1.0 / house_df["MAE (pp)"].values
    house_df["Vikt"] = inv_mae / inv_mae.mean()
    house_df["Vikt"] = house_df["Vikt"].round(3)
    return house_df.reset_index(drop=True)


@st.cache_data(ttl=86400, show_spinner=False)
def compute_backtesting_correction(
    _polls_df: pd.DataFrame,
    _house_weights_df: pd.DataFrame,
) -> dict:
    """
    Backtesting-korrigering: kör aggregatorn med standardinställningar
    dagen innan riksdagsvalet 2022 och returnerar det totala felet.

    Korrigering[p] = NATIONAL_2022[p] − modellestimат[p]
                   = −(Fel pp från backtesting-tabellen vid valdagen)

    Täcker alla systematiska fel: pollingbias, modellspecifika fel
    och institutsviktningens effekt — allt i ett tal per parti.
    """
    ref = ELECTION_2022 - timedelta(days=1)
    est = aggregate_polls_kalman(
        _polls_df,
        _house_weights=_house_weights_df,
        reference_date=ref,
        window_days=365,
    )
    return {p: round(NATIONAL_2022.get(p, 0) - est.get(p, 0), 2) for p in PARTIES}


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
        return NATIONAL_2022.copy()

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
        result[p] = float(np.average(valid[p], weights=valid["weight"])) if not valid.empty else NATIONAL_2022[p]
    return result


@st.cache_data(show_spinner=False)
def aggregate_polls_kalman(
    _df: pd.DataFrame,
    _house_weights: pd.DataFrame = None,
    reference_date: datetime = None,
    sigma_process_per_day: float = 0.10,
    window_days: int = 365,
) -> dict:
    # Rename underscored params (required by @st.cache_data unhashable convention)
    df = _df
    house_weights = _house_weights

    # Referensdatum: idag om inget annat anges.
    # Det gör att estimatet uppdateras varje dag fönstret rullar
    # och gamla mätningar faller ur — även utan ny opinionsmätning.
    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=window_days)
    recent = df[(df["PublDate"] >= cutoff) & (df["PublDate"] <= now)].copy()

    if recent.empty:
        return NATIONAL_2022.copy()

    recent = recent.sort_values("PublDate").reset_index(drop=True)

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
            results[party] = NATIONAL_2022.get(party, 0.0)
            continue

        t_obs = (recent.loc[valid, "PublDate"] - t0).dt.days.astype(float).values
        y_obs = y_col[valid].values
        n_obs = n_col[valid].values
        co_obs = recent.loc[valid, "Company"].fillna("").values

        # ── Observationsbrus per mätning ──
        sigma_obs = np.zeros(len(y_obs))
        for i, (y, n, c) in enumerate(zip(y_obs, n_obs, co_obs)):
            p_frac = np.clip(y / 100.0, 0.01, 0.99)
            # Stickprovsvarians i pp²
            var_samp = p_frac * (1.0 - p_frac) * 10_000.0 / max(float(n), 100.0)
            # Institutsbrus: sämre institut → mer osäkerhet (skalas med 1/vikt²)
            hw = max(hw_map.get(c, 1.0), 0.2)
            sigma_obs[i] = float(np.sqrt(max(var_samp / hw**2, 0.09)))  # min 0.3 pp

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


@st.cache_data(show_spinner=False)
def aggregate_polls_kalman_timeseries(
    _df: pd.DataFrame,
    _house_weights: pd.DataFrame = None,
    reference_date: datetime = None,
    sigma_process_per_day: float = 0.10,
    window_days: int = 365,
) -> dict:
    """
    Samma Kalman-filter som aggregate_polls_kalman men returnerar hela
    tidsserien (300 interpolerade punkter t.o.m. idag) per parti.
    Används av make_trend_chart så att trenden överensstämmer med estimaten.

    Returns: {parti: {"eval_dates": [...], "smooth_y": [...], "smooth_std": [...]}}
    """
    df = _df
    house_weights = _house_weights

    now = reference_date or datetime.now()
    cutoff = now - timedelta(days=window_days)
    recent = df[(df["PublDate"] >= cutoff) & (df["PublDate"] <= now)].copy()

    if recent.empty:
        return {}

    recent = recent.sort_values("PublDate").reset_index(drop=True)

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

        sigma_obs_arr = np.zeros(len(y_obs))
        for i, (y, n, c) in enumerate(zip(y_obs, n_obs, co_obs)):
            p_frac = np.clip(y / 100.0, 0.01, 0.99)
            var_samp = p_frac * (1.0 - p_frac) * 10_000.0 / max(float(n), 100.0)
            hw = max(hw_map.get(c, 1.0), 0.2)
            sigma_obs_arr[i] = float(np.sqrt(max(var_samp / hw**2, 0.09)))

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


# ─────────────────────────────────────────────
# MANDATBERÄKNING
# ─────────────────────────────────────────────

def modified_sainte_lague(votes: dict, n_seats: int) -> dict:
    import heapq
    seats = {p: 0 for p in votes}
    heap = [(-v / 1.2, p) for p, v in votes.items()]
    heapq.heapify(heap)
    for _ in range(n_seats):
        if not heap:
            break
        neg_q, p = heapq.heappop(heap)
        seats[p] += 1
        heapq.heappush(heap, (-votes[p] / (2 * seats[p] + 1), p))
    return seats


def estimate_constituency_votes(national_est: dict, constituency: dict) -> dict:
    result = {}
    for p in PARTIES:
        offset = constituency.get(p, NATIONAL_2022.get(p, 0)) - NATIONAL_2022.get(p, 0)
        result[p] = max(0.0, national_est.get(p, 0) + offset)
    total = sum(result.values())
    return {p: v / total * 100 for p, v in result.items()} if total > 0 else result


@st.cache_data
def run_simulation(
    raw_est: dict,
    polls_df: pd.DataFrame,
    window_days: int,
    n_sims: int = 10_000,
) -> dict:
    """
    Monte Carlo-simulering av mandatutfall.

    Osäkerhetsmodell per parti:
      σ_total = sqrt(σ_polls² + σ_fundamental²)

    σ_polls  = standardavvikelse bland senaste mätningarna (fångar houseeffects + slump)
    σ_fundamental = 1,0 % tillägg för strukturell osäkerhet

    Varje simulation:
      1. Dra stöd från N(μ, σ_total) per parti, trunkera vid 0
      2. Tillämpa 4 %-spärren
      3. Fördela 349 mandat med MSL nationellt (ej per valkrets – snabbt)
      4. Samla statistik
    """
    cutoff = datetime.now() - timedelta(days=window_days)
    recent = polls_df[polls_df["PublDate"] >= cutoff].copy()

    # Skatta σ per parti från spridningen i senaste mätningarna
    party_std = {}
    for p in PARTIES:
        vals = pd.to_numeric(recent[p], errors="coerce").dropna().values
        party_std[p] = max(float(np.std(vals)), 0.5) if len(vals) >= 3 else 1.5

    FUNDAMENTAL = 1.0
    total_std = {p: np.sqrt(party_std[p] ** 2 + FUNDAMENTAL ** 2) for p in PARTIES}

    # Simulera
    rng = np.random.default_rng(seed=42)
    draws = {
        p: np.maximum(0, rng.normal(raw_est[p], total_std[p], n_sims))
        for p in PARTIES
    }

    # Normalisera varje simulation till 100 %
    totals = sum(draws[p] for p in PARTIES)
    draws = {p: draws[p] / totals * 100 for p in PARTIES}

    # Mandatfördelning per simulation (snabb nationell MSL)
    party_mandates = {p: np.zeros(n_sims, dtype=int) for p in PARTIES}
    bloc_h = np.zeros(n_sims, dtype=int)
    bloc_v = np.zeros(n_sims, dtype=int)
    above_threshold = {p: 0 for p in PARTIES}

    for i in range(n_sims):
        sim = {p: draws[p][i] for p in PARTIES}
        eligible = {p: v for p, v in sim.items() if v >= THRESHOLD}
        if not eligible:
            continue
        tot = sum(eligible.values())
        norm = {p: v / tot * 100 for p, v in eligible.items()}
        alloc = modified_sainte_lague(norm, TOTAL_SEATS)
        for p in PARTIES:
            m = alloc.get(p, 0)
            party_mandates[p][i] = m
            if sim[p] >= THRESHOLD:
                above_threshold[p] += 1
        bloc_h[i] = sum(alloc.get(p, 0) for p in ["M", "L", "KD", "SD"])
        bloc_v[i] = sum(alloc.get(p, 0) for p in ["S", "V", "MP", "C"])

    return {
        "draws": draws,
        "party_mandates": party_mandates,
        "party_std": party_std,
        "total_std": total_std,
        "bloc_h": bloc_h,
        "bloc_v": bloc_v,
        "above_threshold": {p: above_threshold[p] / n_sims for p in PARTIES},
        "n_sims": n_sims,
    }


@st.cache_data
def compute_2022_mandates() -> dict:
    """Beräknar faktisk mandatfördelning per valkrets från 2022 års valresultat."""
    fixed_seats = {}
    for name, cdata in CONSTITUENCIES_2022.items():
        votes = {p: cdata.get(p, 0) for p in PARTIES}
        total = sum(votes.values())
        if total > 0:
            votes = {p: v / total * 100 for p, v in votes.items()}
        alloc = modified_sainte_lague(votes, cdata["seats"])
        fixed_seats[name] = {p: alloc.get(p, 0) for p in PARTIES}
    return fixed_seats


def allocate_all_mandates(national_est_raw: dict) -> dict:
    eligible = [p for p in PARTIES if national_est_raw.get(p, 0) >= THRESHOLD]
    elig_votes = {p: national_est_raw[p] for p in eligible}
    total_elig = sum(elig_votes.values())
    national_norm = {p: v / total_elig * 100 for p, v in elig_votes.items()}

    fixed_seats = {}
    const_votes = {}
    party_fixed_total = {p: 0 for p in PARTIES}

    for name, cdata in CONSTITUENCIES_2022.items():
        c_votes_all = estimate_constituency_votes(national_est_raw, cdata)
        c_votes_elig = {p: c_votes_all[p] for p in eligible}
        tot = sum(c_votes_elig.values())
        if tot > 0:
            c_votes_elig = {p: v / tot * 100 for p, v in c_votes_elig.items()}

        const_votes[name] = c_votes_all
        alloc = modified_sainte_lague(c_votes_elig, cdata["seats"])
        fixed_seats[name] = {p: alloc.get(p, 0) for p in PARTIES}
        for p in PARTIES:
            party_fixed_total[p] += fixed_seats[name].get(p, 0)

    national_prop = modified_sainte_lague(national_norm, TOTAL_SEATS)

    # Utjämningsmandat: fördela exakt (TOTAL_SEATS − fasta) mandat bland partier
    # som fortfarande behöver fler mandat för att nå proportionell andel.
    # Kör en ny Sainte-Laguë-fördelning för utjämningssätet med "återstående behov"
    # som röstandel — detta garanterar att summan alltid = TOTAL_SEATS (349).
    total_fixed_seats = sum(party_fixed_total.values())
    adj_seats_available = TOTAL_SEATS - total_fixed_seats  # normalt 39

    adj_need = {
        p: max(0.0, national_prop.get(p, 0) - party_fixed_total.get(p, 0))
        for p in eligible
    }
    adj_need_total = sum(adj_need.values())

    if adj_need_total > 0 and adj_seats_available > 0:
        adj_norm = {p: v / adj_need_total * 100 for p, v in adj_need.items() if v > 0}
        adjustment = modified_sainte_lague(adj_norm, adj_seats_available)
    else:
        adjustment = {}

    total = {p: party_fixed_total[p] + adjustment.get(p, 0) for p in PARTIES}

    return {
        "fixed": fixed_seats,
        "adjustment": adjustment,
        "total": total,
        "fixed_total": party_fixed_total,
        "constituency_votes": const_votes,
        "eligible_parties": eligible,
        "national_norm": national_norm,
    }


# ─────────────────────────────────────────────
# VISUALISERING
# ─────────────────────────────────────────────

def make_support_bar(votes: dict, reference_2022: dict | None = None) -> go.Figure:
    parties = list(votes.keys())
    values = [votes[p] for p in parties]
    colors = [PARTY_COLORS.get(p, "#888") for p in parties]
    names = [PARTY_NAMES.get(p, p) for p in parties]

    fig = go.Figure()

    if reference_2022:
        ref_values = [reference_2022.get(p, 0) for p in parties]
        fig.add_trace(go.Bar(
            name="Valresultat 2022",
            x=names, y=ref_values,
            marker_color=colors,
            opacity=0.35,
            marker_pattern_shape="/",
            marker_line_width=0,
            showlegend=True,
            hovertemplate="%{x}<br>Valresultat 2022: <b>%{y:.1f}%</b><extra></extra>",
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
        title=dict(text="Aktuellt stöd vs valresultat 2022", font=dict(size=13, color="#111213")),
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
        series[p] = s

    if not series:
        return pd.DataFrame()

    result = pd.DataFrame(series)
    result.index.name = "Datum"
    result.index = pd.to_datetime(result.index).strftime("%Y-%m-%d")
    result.columns = [PARTY_NAMES.get(c, c) + " (%)" for c in result.columns]
    result = result.round(2)
    return result.reset_index()


def make_trend_chart(df: pd.DataFrame, window_days: int, timeseries: dict = None) -> go.Figure:
    """
    Trendgraf med Kalman-smoother och 95 % konfidensband.
    Visar institut och stickprovsstorlek i tooltip.

    timeseries: output från aggregate_polls_kalman_timeseries() — om angivet
    används samma Kalman-körning som estimaten (med husvikter), annars
    faller funktionen tillbaka på en förenklad kalman_smooth utan vikter.
    """
    # Visa mätningar från en månad före valet 2022 och framåt
    cutoff = ELECTION_2022 - timedelta(days=30)
    recent = df[df["PublDate"] >= cutoff].copy()

    fig = go.Figure()

    for p in PARTIES_WITH_OTHER:
        col = recent[["PublDate", p, "Company", "n"]].dropna(subset=[p]).copy()
        if col.empty:
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

    fig.add_vline(
        x=datetime(2022, 9, 11).timestamp() * 1000,
        line_dash="dash",
        line_color="#555555",
        line_width=1.2,
        annotation_text="Val 2022",
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
    """Grupperat stapeldiagram: 2022 faktiskt vs prognos per valkrets."""
    consts = list(fixed_seats.keys())
    vals_pred = [fixed_seats[c].get(party, 0) for c in consts]
    vals_2022 = [seats_2022[c].get(party, 0) for c in consts]

    color = PARTY_COLORS.get(party, "#888")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="2022 (faktiskt)", x=consts, y=vals_2022,
        marker_color=color, marker_line_width=0, opacity=0.35,
        text=vals_2022, textposition="outside",
        hovertemplate="<b>%{x}</b><br>2022: <b>%{y}</b> mandat<extra></extra>",
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
      – Diamant (grå):           Faktiskt 2022 mandat
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
                f"2022 faktiskt: {actual_2022}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

        # 2022 faktiskt – grå ruta
        if actual_2022 > 0:
            fig.add_trace(go.Scatter(
                x=[actual_2022], y=[i],
                mode="markers",
                marker=dict(color="#999999", size=8, symbol="diamond",
                            line=dict(color="white", width=1)),
                showlegend=(i == 0),
                name="2022 (faktiskt)",
                legendgroup="actual",
                hovertemplate=(
                    f"<b>{party_label}</b> — 2022 faktiskt: <b>{actual_2022}</b> mandat<extra></extra>"
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
        name="2022 (faktiskt)", showlegend=True, legendgroup="actual2",
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
    n_sims = sim["n_sims"]
    pm = sim["party_mandates"]

    rows = []
    for name, parties in COALITIONS.items():
        arr = sum(pm.get(p, np.zeros(n_sims)) for p in parties)
        prob = float((arr >= 175).mean())
        rows.append({
            "name": name,
            "prob": prob,
            "mean": float(arr.mean()),
            "p5":  int(np.percentile(arr, 5)),
            "p25": int(np.percentile(arr, 25)),
            "med": int(np.median(arr)),
            "p75": int(np.percentile(arr, 75)),
            "p95": int(np.percentile(arr, 95)),
        })

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


@st.cache_data(ttl=86400)
def compute_backtesting(polls_df: pd.DataFrame, house_weights_df: pd.DataFrame) -> pd.DataFrame:
    """
    Backtesting: kör aggregatorn månadsvis från 365 dagar före valet 2022-09-11 t.o.m.
    7 dagar före. Returnerar DataFrame med estimat, faktiskt resultat och fel (pp)
    per parti och referensdatum.
    """
    election_date = datetime(2022, 9, 11)

    # Månadsvis + täta punkter nära valet för hög upplösning
    monthly = list(range(365, 29, -30))          # 365, 335, 305, …, 35
    fine    = [28, 21, 14, 10, 7]                # finare upplösning sista månaden
    test_offsets = sorted(set(monthly + fine), reverse=True)

    rows = []
    for days_before in test_offsets:
        ref = election_date - timedelta(days=days_before)
        est = aggregate_polls_kalman(
            polls_df,
            _house_weights=house_weights_df,
            reference_date=ref,
            window_days=365,
        )
        for p in PARTIES:
            rows.append({
                "Referensdatum": ref.strftime("%Y-%m-%d"),
                "Dagar till val": days_before,
                "Parti": PARTY_NAMES.get(p, p),
                "Estimat (%)": round(est.get(p, 0), 2),
                "Faktiskt (%)": NATIONAL_2022[p],
                "Fel (pp)": round(est.get(p, 0) - NATIONAL_2022[p], 2),
            })
    return pd.DataFrame(rows)


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

    _days_left = max(0, (ELECTION_2026 - datetime.now()).days)

    # Fasta inställningar (ej justerbara av användaren)
    window_days = 365
    decay_half = 30

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

    house_weights_df = compute_house_weights(polls_df)

    latest_date = polls_df["PublDate"].max().strftime("%Y-%m-%d")
    raw_est = aggregate_polls_kalman(
        polls_df,
        _house_weights=house_weights_df,
        window_days=window_days,
    )

    # Tidsserie med samma Kalman-modell (husvikter) — används i trendgrafen.
    # Fönstret sträcker sig från en månad före valet 2022 t.o.m. idag;
    # slutpunkten skalas sedan till raw_est (365-dagars estimat) nedan.
    _trend_days = (datetime.now() - (ELECTION_2022 - timedelta(days=30))).days
    _raw_timeseries = aggregate_polls_kalman_timeseries(
        polls_df,
        _house_weights=house_weights_df,
        window_days=_trend_days,
    )

    # Övriga-estimat: hämtas direkt från Kalman-tidsseriens slutpunkt
    # (raw_est summerar till 100 % efter normalisering, så residualen är alltid 0)
    _o_ts = _raw_timeseries.get("O", {})
    raw_est_other = max(0.0, float(_o_ts["smooth_y"][-1]) if _o_ts.get("smooth_y") else 0.0)
    raw_est_with_other = {**raw_est, "O": raw_est_other}

    # Skala tidsserien så att slutpunkten (idag) matchar estimaten exakt.
    # aggregate_polls_kalman normaliserar slutvärdet till 100 %, men
    # aggregate_polls_kalman_timeseries returnerar onormaliserade värden —
    # därför skalas varje partis tidsserie med faktorn est[p] / endpoint.
    trend_timeseries = {}
    for p in PARTIES_WITH_OTHER:
        if p not in _raw_timeseries:
            continue
        ts = _raw_timeseries[p]
        endpoint = ts["smooth_y"][-1] if ts["smooth_y"] else 0.0
        target = raw_est_with_other.get(p, endpoint)
        scale = target / endpoint if abs(endpoint) > 0.01 else 1.0
        trend_timeseries[p] = {
            "eval_dates": ts["eval_dates"],
            "smooth_y":   [v * scale for v in ts["smooth_y"]],
            "smooth_std": [v * scale for v in ts["smooth_std"]],
        }

    mandates = allocate_all_mandates(raw_est)

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
    with st.spinner("Kör 10 000 simuleringar..."):
        sim = run_simulation(raw_est, polls_df, window_days)

    # Beräkna 2022-mandat per parti (summerat nationellt) för referens i CI-diagrammet
    seats_2022_const = compute_2022_mandates()
    seats_2022_total = {p: sum(seats_2022_const[c].get(p, 0) for c in seats_2022_const) for p in PARTIES}

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "📊 Opinion", "🏛️ Mandat", "🗺️ Valkretsar",
        "🎲 Simulering", "👤 Kandidater",
        "📍 Regional", "📋 Data", "ℹ️ Metod", "🙋 Om mig",
    ])

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
        with col2:
            st.plotly_chart(make_support_bar(raw_est, reference_2022=NATIONAL_2022), use_container_width=True, key="support_bar_tab1")
            st.subheader("Estimat per parti")
            _est_rows = [
                {
                    "Parti": PARTY_NAMES.get(p, p),
                    "2022 (%)": f"{NATIONAL_2022.get(p, 0):.1f}",
                    "Nu (%)": f"{raw_est_with_other.get(p, 0):.1f}",
                    "Δ (pp)": f"{raw_est_with_other.get(p, 0) - NATIONAL_2022.get(p, 0):+.1f}",
                    "Över spärren": "Ja" if raw_est_with_other.get(p, 0) >= THRESHOLD else "Nej",
                }
                for p in PARTIES
            ]
            # Lägg till Övriga (ingen spärr-kolumn relevant)
            _est_rows.append({
                "Parti": "Övriga",
                "2022 (%)": f"{max(0, 100 - sum(NATIONAL_2022.values())):.1f}",
                "Nu (%)": f"{raw_est_other:.1f}",
                "Δ (pp)": f"{raw_est_other - max(0, 100 - sum(NATIONAL_2022.values())):+.1f}",
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
        const_names_t1 = sorted(CONSTITUENCIES_2022.keys())
        sel_const_t1 = st.selectbox("Välj valkrets", const_names_t1, key="tab1_const_sel")

        # Använder raw_est – samma estimat som mandatfördelningen
        _swing_t1 = {p: raw_est.get(p, 0) - NATIONAL_2022.get(p, 0) for p in PARTIES}
        _c22_t1 = CONSTITUENCIES_2022[sel_const_t1]
        _raw_t1 = {p: max(0.0, _c22_t1.get(p, 0) + _swing_t1.get(p, 0)) for p in PARTIES}
        _tot_t1 = sum(_raw_t1.values())
        _pred_t1 = {p: _raw_t1[p] / _tot_t1 * 100 if _tot_t1 > 0 else 0.0 for p in PARTIES}

        const_detail_rows_t1 = []
        for p in PARTIES:
            v22 = _c22_t1.get(p, 0.0)
            v26 = _pred_t1.get(p, 0.0)
            const_detail_rows_t1.append({
                "parti_kod": p,
                "Parti": PARTY_NAMES.get(p, p),
                "2022 (%)": round(v22, 1),
                "Prediktion 2026 (%)": round(v26, 1),
                "Förändring (pp)": round(v26 - v22, 1),
            })
        const_detail_df_t1 = pd.DataFrame(const_detail_rows_t1)

        _chart_colors_t1 = [PARTY_COLORS.get(p, "#888") for p in PARTIES]
        fig_const_t1 = go.Figure()
        fig_const_t1.add_trace(go.Bar(
            name="Valresultat 2022",
            x=const_detail_df_t1["Parti"],
            y=const_detail_df_t1["2022 (%)"],
            marker_color=_chart_colors_t1,
            opacity=0.4,
            marker_pattern_shape="/",
            hovertemplate="<b>%{x}</b><br>Valresultat 2022: <b>%{y:.1f}%</b><extra></extra>",
        ))
        fig_const_t1.add_trace(go.Bar(
            name="Prediktion 2026",
            x=const_detail_df_t1["Parti"],
            y=const_detail_df_t1["Prediktion 2026 (%)"],
            marker_color=_chart_colors_t1,
            opacity=0.95,
            # Ingen text-attribut – etiketter läggs som annotations för att
            # helt undvika att Plotly duplicerar värdet i hover-tooltip.
            hovertemplate="<b>%{x}</b><br>Prediktion 2026: <b>%{y:.1f}%</b><extra></extra>",
        ))

        # Lägg till stapeletiketter som annotations (helt frikopplade från hover)
        _y_max_t1 = max(
            const_detail_df_t1["Prediktion 2026 (%)"].max(),
            const_detail_df_t1["2022 (%)"].max()
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
                const_detail_df_t1["Prediktion 2026 (%)"],
            )
        ]

        fig_const_t1.update_layout(
            **ECONOMIST_BASE,
            barmode="group",
            hovermode="closest",
            title=dict(
                text=f"{sel_const_t1} — partistöd 2022 vs prediktion 2026",
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
            .format({"2022 (%)": "{:.1f}", "Prediktion 2026 (%)": "{:.1f}", "Förändring (pp)": "{:+.1f}"})
            .map(_color_const_chg_t1, subset=["Förändring (pp)"]),
            hide_index=True, use_container_width=True,
        )

    # ── Tab 2: Mandatfördelning ──
    with tab2:
        st.plotly_chart(make_mandate_bar(mandates["total"]), use_container_width=True, key="mandate_bar_tab2")

        st.divider()
        st.subheader("Mandatprognos med osäkerhetsintervall")
        st.caption(
            "Diamant = faktiskt 2022-resultat. Skuggat område = 90 % konfidensintervall "
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

        # Riksdagshemicykel
        st.subheader("Riksdagen – visuell fördelning")
        fig_hem = go.Figure()
        seat_list = []
        for p in ["SD", "M", "KD", "L", "C", "MP", "V", "S"]:
            seat_list.extend([(p, PARTY_COLORS.get(p, "#888"))] * mandates["total"].get(p, 0))

        x_pos, y_pos, colors_hem, hover_texts = [], [], [], []
        seats_per_row = [55, 58, 60, 62, 64, 50]
        idx = 0
        for row, n_seats in enumerate(seats_per_row):
            r = 1 + row * 0.2
            angles = np.linspace(np.pi, 0, min(n_seats, len(seat_list) - idx))
            for angle in angles:
                if idx >= len(seat_list):
                    break
                p, color = seat_list[idx]
                x_pos.append(r * np.cos(angle))
                y_pos.append(r * np.sin(angle))
                colors_hem.append(color)
                hover_texts.append(PARTY_NAMES.get(p, p))
                idx += 1

        fig_hem.add_trace(go.Scatter(
            x=x_pos, y=y_pos, mode="markers",
            marker=dict(color=colors_hem, size=8, line=dict(width=0.5, color="white")),
            text=hover_texts, hoverinfo="text",
        ))
        fig_hem.update_layout(
            height=300, showlegend=False,
            xaxis=dict(visible=False, range=[-1.6, 1.6]),
            yaxis=dict(visible=False, range=[-0.1, 1.4]),
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_hem, use_container_width=True, key="hemisphere_tab2")

    # ── Tab 3: Valkretsar ──
    with tab3:
        st.subheader("Partistöd per valkrets")
        const_names = sorted(CONSTITUENCIES_2022.keys())
        sel_const = st.selectbox("Välj valkrets", const_names, key="tab3_const_sel")

        # Beräkna predicted vote share per valkrets med uniform swing
        # Använder raw_est – samma estimat som mandatfördelningen
        _swing = {p: raw_est.get(p, 0) - NATIONAL_2022.get(p, 0) for p in PARTIES}
        _c22 = CONSTITUENCIES_2022[sel_const]
        _raw = {p: max(0.0, _c22.get(p, 0) + _swing.get(p, 0)) for p in PARTIES}
        _tot = sum(_raw.values())
        _pred = {p: _raw[p] / _tot * 100 if _tot > 0 else 0.0 for p in PARTIES}

        const_detail_rows = []
        for p in PARTIES:
            v22 = _c22.get(p, 0.0)
            v26 = _pred.get(p, 0.0)
            const_detail_rows.append({
                "parti_kod": p,
                "Parti": PARTY_NAMES.get(p, p),
                "2022 (%)": round(v22, 1),
                "Prediktion 2026 (%)": round(v26, 1),
                "Förändring (pp)": round(v26 - v22, 1),
            })
        const_detail_df = pd.DataFrame(const_detail_rows)

        # Stapeldiagram
        _chart_colors = [PARTY_COLORS.get(p, "#888") for p in PARTIES]
        fig_const = go.Figure()
        fig_const.add_trace(go.Bar(
            name="Valresultat 2022",
            x=const_detail_df["Parti"],
            y=const_detail_df["2022 (%)"],
            marker_color=_chart_colors,
            opacity=0.4,
            marker_pattern_shape="/",
            hovertemplate="%{x}<br>Valresultat 2022: <b>%{y:.1f}%</b><extra></extra>",
        ))
        fig_const.add_trace(go.Bar(
            name="Prediktion 2026",
            x=const_detail_df["Parti"],
            y=const_detail_df["Prediktion 2026 (%)"],
            marker_color=_chart_colors,
            opacity=0.95,
            text=const_detail_df["Prediktion 2026 (%)"].round(1).astype(str) + "%",
            textposition="outside",
            hovertemplate="%{x}<br>Prediktion 2026: <b>%{y:.1f}%</b><extra></extra>",
        ))
        fig_const.update_layout(
            **ECONOMIST_BASE,
            barmode="group",
            title=dict(
                text=f"{sel_const} — partistöd 2022 vs prediktion 2026",
                font=dict(size=13, color="#111213"),
            ),
            xaxis=dict(showgrid=False, showline=True, linecolor="#cccccc", tickfont=dict(size=11)),
            yaxis=dict(
                showgrid=True, gridcolor="#ebebeb", zeroline=False, ticksuffix="%",
                range=[0, max(const_detail_df["Prediktion 2026 (%)"].max(),
                              const_detail_df["2022 (%)"].max()) * 1.2],
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
            .format({"2022 (%)": "{:.1f}", "Prediktion 2026 (%)": "{:.1f}", "Förändring (pp)": "{:+.1f}"})
            .map(_color_const_chg, subset=["Förändring (pp)"]),
            hide_index=True, use_container_width=True,
        )

        st.divider()
        st.subheader("Fasta mandat per valkrets – prognos vs 2022")

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
            ["Prognos", "2022 (faktiskt)", "Förändring (prognos − 2022)"],
            horizontal=True,
            key="const_vy",
        )

        if vy == "Prognos":
            st.caption("Beräknade fasta valkretsmandat baserat på aktuell opinion.")
            st.dataframe(fixed_df, use_container_width=True)
        elif vy == "2022 (faktiskt)":
            st.caption("Faktiska mandat från riksdagsvalet 11 september 2022.")
            st.dataframe(df_2022, use_container_width=True)
        else:
            st.caption("Positivt tal = prognosen ger fler mandat än 2022. Negativt = färre.")
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
        st.caption("Ljus stapel = 2022 faktiskt, mörk stapel = prognos.")
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

Processbruset $\sigma_{\mathrm{proc}} = 0{,}07$ procentenheter per dag (≈ 0,5 pp per
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

**Riksdagsspärren.** Partier med skattat stöd under 4,0 % exkluderas från
mandatberäkningen. **Övriga partier** beräknas som residualen
$100\% - \sum_p x_p$ per undersökning och smoothas med samma modell, men ingår
inte i mandatberäkningen.
""")

        st.subheader("2. Institutsviktning")
        st.markdown(r"""
Varje opinionsinstut tilldelas en vikt $w_k$ baserad på träffsäkerheten mot
riksdagsvalet 2022. För varje institut $k$ beräknas medelabsolut fel (MAE) i
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
Steed, 1980). Låt $r_{p,c}$ beteckna valresultatet 2022 för parti $p$ i valkrets
$c$ och $\bar{r}_p$ rikssnittet 2022. Det geografiska bidraget definieras:

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
| Valmyndigheten | Kandidatlistor 2026 & valresultat 2022 | [val.se](https://www.val.se) |
| okfse/sweden-geojson | GeoJSON-karta över Sveriges 21 län | [GitHub](https://github.com/okfse/sweden-geojson) |
| Botten Ada (ada_code) | Inspiration för modellstruktur | [GitHub](https://github.com/MansMeg/ada_code) |
| Curtice & Steed (1980) | Uniform swing-modellen | *The British General Election of 1979* |

Valresultat per valkrets är hämtade från Valmyndighetens officiella slutresultat och
utgör referensdata för geografisk offset och institutsviktning.
""")

        st.subheader("7. Begränsningar & modellantaganden")
        st.markdown(r"""
**Uniform swing.** Modellen antar konstanta regionala mönster sedan 2022. Geografiska
rörelser — t.ex. differentierat tapp i storstäder kontra glesbygd — fångas inte upp,
vilket kan ge systematiska fel i enskilda valkretsar.

**Övriga partier.** Övriga ingår inte i mandatberäkningen. Modellen kan inte fördela
Övrigas stöd på enskilda partier utan partispecifik polldata, vilket innebär att
ett genombrott nära 4 %-gränsen inte modelleras.

**Institutsvikter baserade på ett enda val.** Vikterna kalibreras mot 2022 och
riskerar att återspegla idiosynkratiska fel snarare än strukturell träffsäkerhet.
Med fler historiska val (t.ex. 2018, 2014) skulle skattningarna bli mer robusta.

**Personkryss.** Kandidatprediktionen baseras enbart på listordning. Historiskt
krysspådrag kan avsevärt förändra vem som väljs in, särskilt inom S och M.

**Karta.** Stockholm, Skåne och Västra Götaland innehåller flera valkretsar vars
mandat aggregeras till länet i kartvisningen.
""")

        st.subheader("8. Backtesting — träffsäkerhet inför valet 2022")
        st.markdown(r"""
Out-of-sample-validering: modellen kördes retrospektivt för varje referensdatum
under det sista året före riksdagsvalet 11 september 2022. Felet mäts som
differensen $\hat{e}_p - r_p$ (procentenheter) per parti och datum. Aggregerade
mått: **MAE** (medelabsolut fel) och **RMSE** (root mean squared error).
""")
        with st.spinner("Beräknar backtesting..."):
            bt_df = compute_backtesting(polls_df, house_weights_df)

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
            title=dict(text="MAE och RMSE per referensdatum — inför valet 2022", font=dict(size=13, color="#111213")),
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
            "mellan de senaste mätningarna."
        )

        # ── Hur sannolikt är det att… ──
        st.divider()
        st.subheader("Hur sannolikt är det att…")

        _draws = sim["draws"]
        _n = sim["n_sims"]
        _at = sim["above_threshold"]

        # Beräkna röstandelar per block
        _bloc_v_votes = sum(_draws.get(p, np.zeros(_n)) for p in ["S", "V", "MP", "C"])
        _bloc_h_votes = sum(_draws.get(p, np.zeros(_n)) for p in ["M", "L", "KD", "SD"])
        _svmp_votes   = sum(_draws.get(p, np.zeros(_n)) for p in ["S", "V", "MP"])
        _scmp_votes   = sum(_draws.get(p, np.zeros(_n)) for p in ["S", "C", "MP"])
        _gov_votes    = sum(_draws.get(p, np.zeros(_n)) for p in ["M", "L", "KD"])

        def _fmt_pct(p_val):
            if p_val >= 0.95: return ">95 %"
            if p_val <= 0.05: return "<5 %"
            return f"{p_val*100:.0f} %"

        def _verdict(p_val):
            if p_val >= 0.95: return "Väldigt troligt"
            if p_val >= 0.70: return "Troligt"
            if p_val >= 0.30: return "Osäkert"
            if p_val >= 0.05: return "Osannolikt"
            return "Väldigt osannolikt"

        _scenarios = [
            ("Magdalena Anderssons regeringsunderlag har större stöd än Ulf Kristerssons?",
             float((_bloc_v_votes > _bloc_h_votes).mean())),
            ("Ulf Kristerssons regeringsunderlag har större stöd än Magdalena Anderssons?",
             float((_bloc_h_votes > _bloc_v_votes).mean())),
            ("S, V och MP har en majoritet av väljarna (utan C)?",
             float((_svmp_votes > 50).mean())),
            ("S, C och MP har en majoritet av väljarna (utan V)?",
             float((_scmp_votes > 50).mean())),
            ("Är SD större än regeringspartierna (M+L+KD) tillsammans?",
             float((_draws.get("SD", np.zeros(_n)) > _gov_votes).mean())),
            ("MP ligger över spärren?",    _at.get("MP", 0)),
            ("L ligger över spärren?",     _at.get("L", 0)),
            ("KD ligger över spärren?",    _at.get("KD", 0)),
            ("C ligger över spärren?",     _at.get("C", 0)),
            ("Samtliga riksdagspartier ligger över spärren?",
             float(np.mean(np.all(
                 np.stack([_draws.get(p, np.zeros(_n)) >= THRESHOLD for p in PARTIES]), axis=0
             )))),
            ("M är större än SD?",
             float((_draws.get("M", np.zeros(_n)) > _draws.get("SD", np.zeros(_n))).mean())),
        ]

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
        p_none   = 1.0 - p_h_maj - p_v_maj

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
            "σ total inkluderar 1,0 % strukturell osäkerhet."
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

1. Varje kandidat tilldelas en *hemvalkrets* — den valkrets där de har
   sitt lägsta ordningsnummer (bäst listplacering). Det speglar var de är
   starkast förankrade, vilket i praktiken ofta sammanfaller med var de
   blivit personkryssade tidigare val.
2. Valkretsar med flest mandat tilldelas kandidater först. Om en
   kandidats hemvalkrets är en annan fylls platsen istället av nästa
   tillgängliga kandidat på listan.

**Utjämningsmandat:**
Utöver de fasta valkretsmandaten fördelas normalt 39 utjämningsmandat
nationellt för att göra riksdagen proportionell. Modellen identifierar
vilka kandidater som är näst på tur per parti — de som har bäst
listplacering i sin hemvalkrets men inte vunnit ett fast mandat.
Utjämningsmandat är inte knutna till en specifik valkrets; *hemvalkrets*
i tabellen visar var kandidaten är starkast listad, inte var mandatet
formellt tilldelas.

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

        st.subheader("Institutsvikter – träffsäkerhet mot 2022 års val")
        st.caption(
            "MAE = medelabsolut fel i procentenheter mot faktiskt valresultat. "
            "Lägre MAE → högre vikt. Institut utan 2022-data får standardvikt 1,0."
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
                f"(MAE mot 2022 års val: {_ind_mae:.3f} pp)."
            )
        else:
            st.caption("ℹ️ Indikator saknas i 2022-data och får standardvikt 1,0.")

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
            title=dict(text="Institutsvikter baserade på träffsäkerhet 2022", font=dict(size=13, color="#111213")),
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
        days_left = max(0, (ELECTION_2026 - datetime.now()).days)
        st.markdown(
            "Applicerar en **uniform swing-modell** på valresultaten 2022 per region och "
            "kommun. Modellen tar det aktuella nationella opinionsläget och fördelar "
            "förändringen sedan 2022 lika i alla kommuner och regioner. "
            "Data från **SCB PX-Web** och **okfse/sweden-geojson**."
        )

        st.markdown("""
**Uniform swing** innebär att den nationella förändringen sedan 2022 appliceras lika
i alla kommuner. Om SD nationellt gått från 20,5 % → 22,0 % (+1,5 pp) får varje
kommun +1,5 pp på sin lokala 2022-siffra — oavsett om kommunen är SD-stark eller svag.

Det är en förenkling, men transparent och vanlig i valanalys.

`prediktion = 2022-lokalt + nationell opinionssving (sedan 2022)`

Institutsviktning tillämpas på mandatprognosen och simuleringen.
Alla estimat bygger på Kalman-smoothade pollsiffror utan historisk korrigering.
**Lokalpartier** ingår inte i modellen — de kan ha ett betydande stöd i enskilda kommuner.
Källa: SCB PX-Web · okfse/sweden-geojson · MansMeg/SwedishPolls.
""")

        # ── Kontroller ──
        col_radio, col_view = st.columns([2, 1])
        with col_radio:
            val_type = st.radio(
                "Valtyp",
                ["Riksdag per kommun", "Regionval per region", "Kommunalval per kommun"],
                horizontal=False,
                key="map_val_type",
            )
        with col_view:
            view_opts = ["Ledande parti"] + [PARTY_NAMES.get(p, p) for p in PARTIES]
            view_sel = st.selectbox("Färgläggning", view_opts, key="map_view_sel")

        if view_sel == "Ledande parti":
            view_mode = "leading"
        else:
            party_name_to_code = {v: k for k, v in PARTY_NAMES.items()}
            view_mode = party_name_to_code.get(view_sel, "S")

        # ── Hämta SCB-data ──
        is_kommunal = False
        ovriga_per_area = {}   # fylls i för regionval och kommunalval
        if val_type == "Riksdag per kommun":
            with st.spinner("Hämtar riksdagsvalresultat (290 kommuner) från SCB…"):
                scb_df = load_scb_results(SCB_RIKSDAG_URL, "ME0104B7")
            scb_df = scb_df[scb_df["region_code"].str.match(r"^\d{4}$")].copy()
            geo = load_geojson_url(MUNI_GEOJSON_URL)
            featureidkey = "properties.id"
            id_col = "region_code"
            map_title = "Riksdagsprediktion per kommun — uniform swing"

        elif val_type == "Regionval per region":
            with st.spinner("Hämtar regionvalsresultat (20 regioner) från SCB…"):
                scb_df = load_scb_results(
                    SCB_REGIONVAL_URL, "ME0104B5",
                    region_codes=SCB_REGIONVAL_CODES,
                )
                scb_ovriga_reg = load_scb_results(
                    SCB_REGIONVAL_URL, "ME0104B5",
                    region_codes=SCB_REGIONVAL_CODES,
                    party_codes=["ÖVRIGA"],
                )
            scb_df = scb_df[scb_df["region_code"].isin(SCB_REGIONVAL_TO_GEOJSON)].copy()
            scb_df["region_code"] = scb_df["region_code"].map(SCB_REGIONVAL_TO_GEOJSON)
            # Bygg ÖVRIGA-dict med regionnamn som nyckel (efter mappning)
            scb_ovriga_reg = scb_ovriga_reg[
                scb_ovriga_reg["region_code"].isin(SCB_REGIONVAL_TO_GEOJSON)
            ].copy()
            scb_ovriga_reg["region_code"] = scb_ovriga_reg["region_code"].map(SCB_REGIONVAL_TO_GEOJSON)
            ovriga_per_area = (
                scb_ovriga_reg.set_index("region_code")["pct_2022"].to_dict()
            )
            geo = load_geojson_url(REGION_GEOJSON_URL)
            featureidkey = "properties.name"
            id_col = "region_code"
            map_title = "Regionvalsprediktion per region — uniform swing"

        else:  # Kommunalval
            is_kommunal = True
            with st.spinner("Hämtar kommunalvalsresultat (290 kommuner) från SCB…"):
                scb_df = load_scb_results(SCB_KOMMUNVAL_URL, "ME0104B2")
                scb_ovriga_df = load_scb_results(
                    SCB_KOMMUNVAL_URL, "ME0104B2",
                    party_codes=["ÖVRIGA"],
                )
            scb_df = scb_df[scb_df["region_code"].str.match(r"^\d{4}$")].copy()
            # Bygg dict: region_code → ÖVRIGA-procent 2022
            ovriga_per_area = (
                scb_ovriga_df[scb_ovriga_df["region_code"].str.match(r"^\d{4}$")]
                .set_index("region_code")["pct_2022"]
                .to_dict()
            )
            geo = load_geojson_url(MUNI_GEOJSON_URL)
            featureidkey = "properties.id"
            id_col = "region_code"
            map_title = "Kommunalvalsprediktion per kommun — uniform swing"

        if scb_df.empty:
            st.warning(
                "Kunde inte hämta data från SCB. Kontrollera internetanslutningen. "
                "SCB:s API kan ibland vara temporärt otillgängligt."
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

            # ── Applicera uniform swing (riksdagssvingen sedan 2022 appliceras lokalt) ──
            # Alltid NATIONAL_2022 som referens: sving = raw_est[p] − riksdag_2022[p]
            # För kommunalval: partierna normaliseras till (100% − ÖVRIGA%) per kommun
            predicted_df = apply_uniform_swing(
                scb_df, raw_est, NATIONAL_2022,
                ovriga_per_area=ovriga_per_area,
            )

            # ── Karta ──
            with st.spinner("Renderar karta…"):
                fig_map = make_regional_map(
                    predicted_df, geo, featureidkey, id_col,
                    view_mode, map_title, name_map=name_map_geo,
                )
            st.plotly_chart(fig_map, use_container_width=True, key="regional_map_tab6")

            # ── Detaljvy per vald kommun/region ──
            st.divider()
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
            area_2022 = scb_df[scb_df["region_code"] == sel_area_code]

            pred_dict = dict(zip(area_pred["party"], area_pred["pct_predicted"]))
            hist_dict = dict(zip(area_2022["party"], area_2022["pct_2022"]))

            detail_rows = []
            for p in PARTIES:
                pred_val = pred_dict.get(p, 0.0)
                hist_val = hist_dict.get(p, 0.0)
                detail_rows.append({
                    "parti_kod": p,
                    "Parti": PARTY_NAMES.get(p, p),
                    "2022 (%)": round(hist_val, 1),
                    "Prediktion 2026 (%)": round(pred_val, 1),
                    "Förändring (pp)": round(pred_val - hist_val, 1),
                })
            # Lägg till ÖVRIGA för regionval och kommunalval — antas hålla sin 2022-nivå
            ov_pct = ovriga_per_area.get(sel_area_code, 0.0)
            if ov_pct > 0:
                detail_rows.append({
                    "parti_kod": "ÖVRIGA",
                    "Parti": "Lokala partier (ÖVRIGA)",
                    "2022 (%)": round(ov_pct, 1),
                    "Prediktion 2026 (%)": round(ov_pct, 1),
                    "Förändring (pp)": 0.0,
                })
            detail_df = pd.DataFrame(detail_rows)

            # Stapeldiagram: bara riksdagspartierna (ej ÖVRIGA)
            chart_df = detail_df[detail_df["parti_kod"].isin(PARTIES)]
            chart_colors = [PARTY_COLORS.get(p, "#888") for p in chart_df["parti_kod"]]
            fig_detail = go.Figure()
            fig_detail.add_trace(go.Bar(
                name="Valresultat 2022",
                x=chart_df["Parti"],
                y=chart_df["2022 (%)"],
                marker_color=chart_colors,
                opacity=0.45,
                marker_pattern_shape="/",
            ))
            fig_detail.add_trace(go.Bar(
                name="Prediktion 2026",
                x=chart_df["Parti"],
                y=chart_df["Prediktion 2026 (%)"],
                marker_color=chart_colors,
                opacity=0.95,
                text=chart_df["Prediktion 2026 (%)"].round(1).astype(str) + "%",
                textposition="outside",
            ))
            fig_detail.update_layout(
                **ECONOMIST_BASE,
                barmode="group",
                title=dict(
                    text=f"{sel_area_name} — 2022 jämfört med prediktion 2026",
                    font=dict(size=13, color="#111213"),
                ),
                xaxis=dict(
                    showgrid=False, showline=True,
                    linecolor="#cccccc", tickfont=dict(size=11),
                ),
                yaxis=dict(
                    showgrid=True, gridcolor="#ebebeb",
                    zeroline=False, ticksuffix="%",
                    range=[0, max(chart_df["Prediktion 2026 (%)"].max(),
                                  chart_df["2022 (%)"].max()) * 1.2],
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
                .format({"2022 (%)": "{:.1f}", "Prediktion 2026 (%)": "{:.1f}", "Förändring (pp)": "{:+.1f}"})
                .map(_color_chg, subset=["Förändring (pp)"])
            )
            st.dataframe(display_detail, hide_index=True, use_container_width=True)

            # ── Nationell sving-tabell ──
            st.divider()
            st.subheader("Nationell svängning sedan 2022")
            st.caption(
                "Visar den nationella opinionsförändringen sedan 2022 som appliceras "
                "uniformt i alla kommuner och regioner."
            )
            swing_rows = []
            for p in PARTIES:
                cur = float(raw_est.get(p, 0))
                # Använd alltid riksdagsvalet 2022 som referens
                ref = float(NATIONAL_2022.get(p, 0))
                opinion_swing = round(cur - ref, 1)
                swing_rows.append({
                    "Parti": PARTY_NAMES.get(p, p),
                    "Riksdag 2022 (%)": round(ref, 1),
                    "Nu i polls (%)": round(cur, 1),
                    "Opinionssving (pp)": f"{opinion_swing:+.1f}",
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
                .format({"Riksdag 2022 (%)": "{:.1f}", "Nu i polls (%)": "{:.1f}"})
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
                    file_name="regional_prediktion_2026.csv",
                    mime="text/csv",
                )


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
