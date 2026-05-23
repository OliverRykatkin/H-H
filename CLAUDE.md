# Mandatorn – Projektöversikt för Claude Code

## Vad projektet är

**Mandatorn** (internt: Riksdagsprediction) är en interaktiv webb-app byggd i Python/Streamlit som aggregerar svenska riksdagsopinionsmätningar och beräknar en fullständig mandatprognos inför riksdagsvalet 2026.

Live-app: `riksdagsprediction.streamlit.app` (uppdatera när deployad)

---

## Filstruktur

```
riksdagsprediction/
├── app.py            # Hela applikationen (~4 000+ rader), en enda fil
├── logo.svg          # Hemicykel-logotyp (520×152 px, SVG med partifärgade punkter)
├── favicon.svg       # Favicon som trendgraf (64×64 px)
├── favicon.png       # Konverterad PNG för Streamlit page_icon
├── requirements.txt  # Python-beroenden
├── runtime.txt       # Python-version för Streamlit Cloud
├── README.md         # Publik dokumentation
└── CLAUDE.md         # Den här filen
```

**Allt appkod finns i `app.py`. Det finns inga separata moduler.**

---

## Teknisk stack

| Komponent | Val |
|---|---|
| UI-framework | Streamlit ≥ 1.35 |
| Datavisualisering | Plotly (go + express) |
| Databehandling | Pandas, NumPy |
| Datahämtning | requests (live från GitHub + Valmyndigheten) |
| Deployment | Streamlit Community Cloud |

---

## Datakällor (live-hämtning vid varje körning)

- **Opinionsundersökningar:** `https://raw.githubusercontent.com/MansMeg/SwedishPolls/master/Data/Polls.csv`
- **GeoJSON-karta:** `https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_regions.geojson`
- **Kandidatdata 2026:** `https://data.val.se/filer/val2026/parti/kandidaturer.csv`
- **Kommunal-/regiondata:** SCB PX-Web API (dynamiska queries i appen)

---

## Modellarkitektur

### 1. Kalman-filter-aggregering
Tre funktioner delar samma logik:
- `aggregate_polls_kalman()` – aktuellt estimat per parti
- `aggregate_polls_kalman_timeseries()` – tidsserier för trendgraf
- `kalman_smooth()` – bakåtutjämnad serie

Viktig parameter: `sigma_process_per_day = 0.10` (process-brus; styr hur snabbt modellen reagerar på nya mätningar). Är satt i **alla tre funktionssignaturer** – ändra i alla om du justerar.

### 2. Valkrets-modell
Naiv uniform swing ("offset-modell"):
- Utgångsläge: faktiska valresultat per valkrets 2022
- Justering: nationell procentuell förändring appliceras proportionellt per valkrets
- Känd begränsning: fångar inte lokal variation utöver 2022 års avvikelsemönster

### 3. Mandatberäkning
- Modifierad Sainte-Laguë (första divisor 1,2 i valkretsar, 1,0 i landet)
- 310 fasta mandat (valkretsar) + 39 utjämningsmandat
- 4%-spärr nationellt
- Monte Carlo: 10 000 simuleringar med normalfördelad osäkerhet per parti

### 4. Utjämningsmandat
1. Räkna ut hur många mandat varje parti *borde* ha nationellt (Sainte-Laguë på riksnivå)
2. Subtrahera faktiskt vunna valkretssmandat → differensen = utjämningsmandat
3. Fördela dessa på valkretsar via skalad Sainte-Laguë (röstandel × valkretsstorlek som proxy-kvot)

---

## Appens flikar

| Flik | Nyckelinnehåll |
|---|---|
| 📊 Opinion | Kalman-trendgraf, partistöd-tabell, mandatprognos, stöd per valkrets |
| 🏛️ Mandat | Hemicykelvy, konfidensintervall, blockanalys |
| 🗺️ Valkretsar | Mandattabeller + detaljerade stapeldiagram per valkrets |
| 🎲 Simulering | Monte Carlo-sannolikheter, koalitionsanalys, majoritetsanalys |
| 👤 Kandidater | Förväntade invalda baserat på Valmyndighetens listor |
| 📍 Regional & kommunal | Region- och kommunprognos via SCB-data |
| 📋 Data | Rådata, institutvikter |
| ℹ️ Metod | Metodbeskrivning, backtesting |

---

## Partier och färger

```python
PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"]

PARTY_COLORS = {
    "M":  "#52BDEC",   # Ljusblå
    "L":  "#006AB3",   # Blå
    "C":  "#009933",   # Grön
    "KD": "#000077",   # Mörkblå
    "S":  "#E8112D",   # Röd
    "V":  "#AF0000",   # Mörkröd
    "MP": "#83CF39",   # Ljusgrön
    "SD": "#DDDD00",   # Gul
}
```

Valkrets-mapping: 29 svenska valkretsar med eget namn-schema (se `VALKRETS_MAPPING` i app.py rad ~43).

---

## Designsystem

- **Font:** DM Sans (logotyp), Arial/Helvetica (Plotly-grafer)
- **Layoutstil:** "Economist-inspirerad" – vit bakgrund, tunna gridlinjer (#ebebeb), subtil typografi
- **Konstanter:** `ECONOMIST_LAYOUT` och `ECONOMIST_BASE` (dicts) appliceras via `**`-unpacking i `update_layout()`

---

## Kända begränsningar och TODO

- [ ] Valkrets-modellen är naiv (uniform swing) – lokal variation fångas ej
- [ ] Institutvikterna är hårdkodade baserat på 2022 års prestation
- [ ] SCB-kommundata laddas synkront och kan göra appen trög
- [ ] Inga automatiska tester – all logik i en enda stor fil
- [ ] `app.py` är ~4 000+ rader – kandidat för uppdelning i moduler

---

## Köra lokalt

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploya (Streamlit Community Cloud)

1. Pusha till GitHub (`main`-branch, `app.py` i roten)
2. Gå till share.streamlit.io → New app → välj repo/branch/fil
3. Deploy

---

## Viktiga varningar vid kodändringar

- **`sigma_process_per_day`** finns i tre funktionssignaturer – ändra alltid alla tre synkront
- **Plotly bar charts:** Använd INTE `text`-attributet på `go.Bar` – det blöder in i hover oavsett `hovertemplate`. Använd layout `annotations` istället för stapeletiketter
- **Favicon:** `favicon.png` genereras från `favicon.svg` via cairosvg. Om du ändrar SVG:n, regenerera PNG:n
- **Logo:** Inline base64-SVG i `app.py` – om `logo.svg` saknas faller den tillbaka på `st.title("Mandatorn")`
