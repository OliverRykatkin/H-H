"""mandatorn_model.constants — utbrutet ordagrant ur app.py (fas 1)."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta

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


# Riksdagsvalet 2022 – nationellt slutresultat (behålls som historisk konstant
# för backtesting mot 2022 års val — appens *aktiva* baslinje är nu 2026).
# Riksdagsvalet 2018 – nationellt slutresultat (facit för institutsvikterna i
# backtesten av 2022, DECISIONS D19).
NATIONAL_2018 = {
    "M": 19.84, "L": 5.49, "C": 8.61, "KD": 6.32,
    "S": 28.26, "V": 8.00, "MP": 4.41, "SD": 17.53,
}

NATIONAL_2022 = {
    "M": 19.10, "L": 4.61, "C": 6.71, "KD": 5.34,
    "S": 30.33, "V": 6.75, "MP": 5.08, "SD": 20.54,
}


# Valens datum
ELECTION_2026 = datetime(2026, 9, 13)


ELECTION_2022 = datetime(2022, 9, 11)
ELECTION_2018 = datetime(2018, 9, 9)


def _load_election_2026() -> dict:
    """Läser data/election_2026.json (genererad av fetch_election_2026.py)."""
    import json as _json
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "election_2026.json")
    if not _os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}


_ELECTION_2026 = _load_election_2026()


# Riksdagsvalet 2026 – nationellt slutresultat. Faller tillbaka till 2022 om
# election_2026.json saknas (t.ex. i lokal utveckling utan cachad fil).
NATIONAL_2026 = _ELECTION_2026.get("national", NATIONAL_2022).copy()


# Nationell mandatfördelning 2026 (per parti: total/fasta/utjamning).
SEATS_NATIONAL_2026 = _ELECTION_2026.get("seats_national", {})


# Aktiv baslinje för swing-, referens- och jämförelselogik. Alla nya
# beräkningar utgår från 2026 års utfall; koden som backtestar 2022 använder
# NATIONAL_2022 direkt.
BASELINE = NATIONAL_2026


BASELINE_YEAR = 2026


BASELINE_ELECTION_DATE = ELECTION_2026


# Nästa ordinarie riksdagsval (andra söndagen i september).
NEXT_ELECTION = datetime(2030, 9, 8)


NEXT_ELECTION_YEAR = 2030


TERM_DAYS = (NEXT_ELECTION - ELECTION_2026).days


# Trendgrafernas startpunkt och de val som markeras med streck.
TREND_START = ELECTION_2022 - timedelta(days=30)


TREND_ELECTIONS = [(ELECTION_2022, "Val 2022"), (ELECTION_2026, "Val 2026")]


# Horisontsosäkerhet i simuleringen: σ = K·sqrt(andel)·sqrt(dagar kvar / mandatperiod).
# K = 0,566 → ≈ 2 pp för ett 12,5 %-parti en hel period ut (S ≈ 3 pp, L ≈ 1,3 pp),
# i linje med partiernas rörelse 2018→2022 och 2022→2026 (RMS ≈ 1,6 pp).
HORIZON_K = 0.566


# ── Kart-URLs ──
MUNI_GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_municipalities.geojson"
)


REGION_GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_regions.geojson"
)


# GeoJSON-regionnamn ↔ 2-siffrig länskod (RF-filkod i Valmyndighetens feed).
# Gotland saknas (region-kommun, inget regionval).
REGION_NAME_TO_LAN = {
    "Stockholm": "01",      "Uppsala": "03",        "Södermanland": "04",
    "Östergötland": "05",   "Jönköping": "06",      "Kronoberg": "07",
    "Kalmar": "08",         "Blekinge": "10",       "Skåne": "12",
    "Halland": "13",        "Västra Götaland": "14", "Värmland": "17",
    "Örebro": "18",         "Västmanland": "19",    "Dalarna": "20",
    "Gävleborg": "21",      "Västernorrland": "22", "Jämtland": "23",
    "Västerbotten": "24",   "Norrbotten": "25",
}


LAN_TO_REGION_NAME = {v: k for k, v in REGION_NAME_TO_LAN.items()}


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


# Riksdagsvalet 2026 – per valkrets (laddas från data/election_2026.json).
# Faller tillbaka till 2022 om filen saknas. Detta är den aktiva baslinjen för
# swing-modellen och valkretsprognoser.
CONSTITUENCIES_2026 = _ELECTION_2026.get("constituencies", CONSTITUENCIES_2022)


CONSTITUENCIES = CONSTITUENCIES_2026  # ny alias för swing/baslinje-uppslag


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


ANCHOR_COMPANY = "Valresultat"


ANCHOR_SIGMA = 0.1  # pp — valresultatet är i praktiken exakt


VALNATT_START = datetime(2026, 9, 13, 20, 40)


VALNATT_END = datetime(2026, 9, 14, 4, 0)


VALNATT_STEP_MIN = 10
