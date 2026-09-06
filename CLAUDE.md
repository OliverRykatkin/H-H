# Mandatorn – Projektöversikt för Claude Code

## Vad projektet är

**Mandatorn** (internt: Riksdagsprediction) är en interaktiv webb-app byggd i Python/Streamlit som aggregerar svenska riksdagsopinionsmätningar och beräknar en fullständig mandatprognos inför riksdagsvalet 2026.

Live-app: `https://mandatorn.se` (Google Cloud Run, region `europe-north1`).
Backup-URL: `https://mandatorn-851345615769.europe-north1.run.app`.
Legacy Streamlit Cloud-deploy (`riksdagsprediction.streamlit.app`) — avvecklas.

---

## GitHub-repo

Lokalt namn: `Riksdagsprediction`. GitHub-remote: `OliverRykatkin/H-H` (branch `main`).
Aktiv feature-branch i utveckling: `feature/nowcast` — innehåller nowcasting-modulerna.

## Filstruktur

```
riksdagsprediction/
├── app.py                    # Streamlit-appen (~4 400 rader)
├── nowcast.py                # Delta-baserad nowcasting-algoritm (valprognos.se-metoden)
├── val_feed.py               # Live-feed-klient: RD-röster + KF/RF-mandat + valkretsstruktur
├── muni_mandates.py          # Opinionsbaserad kommunal/regional mandatmodell (full Sainte-Laguë)
├── data_loader.py            # Hämtar 2018+2022 valdistriktsdata från Valmyndigheten
├── validate_nowcast.py       # Offline-validering mot 2022 års val
├── fetch_scb_cache.py        # Pre-hämtar 2022 SCB-data → data/scb_2022.json
├── fetch_muni_cache.py       # Pre-hämtar 2022 KF/RF-struktur → data/muni_structure_2022.json
├── tests/
│   └── test_nowcast.py       # Pytest-enhetstester (10 st)
├── data/
│   ├── scb_2022.json         # Committad — pre-cachad SCB 2022-data (~550 kB)
│   ├── muni_structure_2022.json  # Committad — KF/RF-valkretsstruktur 2022 (~93 kB)
│   ├── raw/                  # Gitignored — XLSX-råfiler (laddas on-demand)
│   └── cache/                # Gitignored — CSV-cache för nowcast
├── logo.svg                  # Hemicykel-logotyp (520×152 px)
├── favicon.svg / favicon.png # Favicon som trendgraf
├── requirements.txt          # Produktionsberoenden
├── requirements-dev.txt      # + pytest för utveckling
├── runtime.txt               # Python-version (legacy, Streamlit Cloud)
├── Dockerfile                # Cloud Run-container (Python 3.11-slim + Streamlit)
├── .dockerignore             # Utesluter data/raw, data/cache, tests, CLAUDE.md
├── .streamlit/config.toml    # Server-config (headless, CORS off för Cloud Run)
├── README.md
└── CLAUDE.md                 # Den här filen
```

**App-koden är fortfarande dominerad av `app.py`.** Sedan maj 2026 finns dock
separata moduler för nowcasting — de hålls avsiktligt utanför app.py för att
isolera ny logik från den 4 000-radersfilen fram till efter september-valet.

---

## Teknisk stack

| Komponent | Val |
|---|---|
| UI-framework | Streamlit ≥ 1.35 |
| Datavisualisering | Plotly (go + express) |
| Databehandling | Pandas, NumPy |
| Datahämtning | requests (live från GitHub + Valmyndigheten) |
| Deployment | Google Cloud Run (region `europe-north1`) |

---

## Datakällor

**Live-hämtning vid varje körning (1 h - 24 h cache):**
- **Opinionsundersökningar:** `https://raw.githubusercontent.com/MansMeg/SwedishPolls/master/Data/Polls.csv`
- **GeoJSON-karta:** `https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_regions.geojson`
- **Kandidatdata 2026:** `https://data.val.se/filer/val2026/parti/kandidaturer.csv`

**Pre-cachad (committad i repot):**
- **2022 SCB-data (riksdag/region/kommun):** `data/scb_2022.json` — genereras
  av `python fetch_scb_cache.py`. `load_scb_results()` i app.py läser filen
  först, faller tillbaka på live SCB PX-Web-API om filen saknas eller queryn
  inte är cachad. Skippar ~6-12 sek per Cloud Run-cold-start.

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
- **Svingen är nollsummerad** (`compute_national_swing`): polls och 2022
  normaliseras till samma bas (andel bland de 8 riksdagspartierna) innan
  differensen tas, så svingen summerar till ~0. Annars förstärker
  per-område-normaliseringen stora partiers sving proportionellt mot deras lokala
  storlek (t.ex. M i Nacka fick −1,9 istf −1,7). Används i `apply_uniform_swing`,
  mandatuppskattningen och sving-tabellen på Regional-fliken.

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
| 📊 Opinion | Kalman-trendgraf per parti **+ blocktidslinje (Höger vs Vänster)**, partistöd-tabell, mandatprognos, stöd per valkrets |
| 🏛️ Mandat | Mandatöversikt, konfidensintervall, blockanalys, **mandatmarginal** (nationellt + per valkrets + landets jämnaste mandat) |
| 🗺️ Valkretsar | Mandattabeller + detaljerade stapeldiagram per valkrets |
| 🎲 Simulering | Monte Carlo-sannolikheter, koalitionsanalys, majoritetsanalys |
| 👤 Kandidater | Förväntade invalda baserat på Valmyndighetens listor |
| 📍 Regional & kommunal | Region- och kommunprognos via SCB-data (selectbox + stapeldiagram) **+ opinionsbaserad mandatuppskattning** för KF/RF (full kommunal Sainte-Laguë via `muni_mandates`, lokalpartier hållna vid 2022, jämförelse mot 2022 års mandat, alltid tillgänglig) |
| 📋 Data | Rådata, institutvikter |
| ℹ️ Metod | Metodbeskrivning, backtesting |
| 🌙 Valnatt | **Alltid synlig.** Live-räkningen är standardvyn (hämtar Valmyndighetens feed direkt): RD-nowcast + full riksdagsmandat-fördelning + förväntade invalda **+ live KF/RF-mandatfördelning** per vald kommun/region. Innan räkningen börjat visas hela grafiken med **2022 års resultat som utgångsläge** (RD-mandat + KF/RF), som byts mot live-siffror så fort distrikt rapporteras in. **Demon** (uppspelning av 2022) ligger i en expander längst ned (utfälld tills live-data finns). |
| 🙋 Om mig | Författarinfo |

---

## Nowcasting-modulen (`nowcast.py` + `data_loader.py`)

Implementerar valprognos.se:s delta-baserade realtidsmetod för valnatten.
Källa: ["Nowcasting på valnatten – metod och utvärdering"](https://www.nationalekonomi.se/artikel/nowcasting-pa-valnatten-metod-och-utvardering-fran-valprognos-se/).

**Grundidé:** prognosen baseras på *förändringar* (deltas) i röstandel jämfört
med ett baslinjeval bland räknade distrikt, inte absoluta nivåer. Motverkar
systematisk snedvridning från räkningsordningen (små distrikt rapporterar först).

**Publika funktioner i `nowcast.py`:**
- `compute_nowcast(counted, baseline, parties)` — kärnalgoritmen
- `project_mandates(nowcast, ...)` — Sainte-Laguë mandatfördelning (4 %-spärr)
- `simulate_election_night(actual, baseline, counting_order, ...)` — backtest-motor
- `modified_sainte_lague(votes, ...)` — duplicerad från app.py (medveten redundans,
  refaktorera efter valet 2026)

**Data:** `data_loader.load_aligned_pair()` returnerar `(baseline_2018, actual_2022)`
inner-joinade på distriktskod (5 316 av 6 264 ordinarie 2022-distrikt;
~948 droppas pga boundary changes — fixas senare via jamforelser-filen).

**Validerat:** `python validate_nowcast.py` reproducerar artikelns halveringseffekt
vid 5 % täckning (0.42→0.18 pe vs artikelns 1.03→0.52 pe). Absoluta skillnaden
beror på storleksbaserad räkningsordningsproxy istället för riktiga tidsstämplar.

**Test:** `pip install -r requirements-dev.txt && pytest tests/` — 48 cases
(10 `nowcast.py`, 28 `val_feed.py`, 10 `muni_mandates.py`).

**Kommunal/regional mandatmodell (`muni_mandates.py`):** opinionsbaserad
mandatuppskattning för kommun-/regionfullmäktige (Regional-fliken). Full modell:
uniform swing (nationell riksdagssving sedan 2022) appliceras per valkrets på
**riksdagspartierna**; **lokala partier antas få samma resultat som 2022** (ingen
opinionsdata finns) och konkurrerar med i modellen. Sedan Sainte-Laguë (divisor
1,2) för fasta mandat per valkrets + utjämningsmandat (divisor 1,0) + 2/3 %-spärr.
Utan utjämningsmandat är de fasta mandaten slutgiltiga. Struktur (mandat/valkrets,
utjämning, spärr, 2022-röster per parti, 2022-mandat, partimetadata) läses från
committad `data/muni_structure_2022.json` (~515 kB, genererad av
`fetch_muni_cache.py` från KF/RF-feedfilernas `valkretsLista`). UI visar
mandatuppskattningen jämte 2022 års mandat (Δ). **Validering:** nollsving
reproducerar 2022 års officiella mandatfördelning **exakt för alla 310 områden**
(inkl. lokalpartier). Lokalpartier utan `partiforkortning` i feeden nyklas på
partikod (`parse_area_structure`).

**Live-feed (`val_feed.py`):** Valmyndigheten publicerar preliminära resultat som
zippade JSON-filer; `index.md5` listar alla filer med md5. För riksdag (RD) ligger
hela riket i EN fil: `./p/rd/Val_<datum>_preliminar_00_RD.zip`. Publika funktioner:
- `fetch_live(year=2026, preliminary=True)` — index → hitta RD-fil → ladda ner →
  md5-verifiera → parsa. Returnerar `FeedResult`.
- `FeedResult.counted()` — räknade ordinarie distrikt i `compute_nowcast`-schemat.
- `parse_rostfordelning(data)` / `parse_rd_zip(bytes)` — offline-parsning.
- `fetch_area_mandat(year, valtyp, kod)` — officiell KF/RF-mandatfördelning
  (kommun/region) direkt ur feedens `mandatfordelning`-block → `AreaMandat`.
- `parse_area_structure(data)` — valkretsstruktur + 2022-röster (för cachen).

Verifierad mot 2022 (`val2022`-filerna ligger kvar): 6264/6264 distrikt joinar mot
baslinjen, nationella andelar matchar XLSX inom ±0,02 pe. Röster:
`rosterPaverkaMandat.antalRoster` = giltiga; distriktskod (`"01800101"`) → int
matchar `district_id`. Poll max ~1 gång/minut (Valmyndighetens rekommendation).
Full teknisk beskrivning för 2026 kommer ~2026-09-13; formatet är identiskt med
2022 (nya summeringar på riks-/läns-/kommunnivå tillkommer).

**Valnatt-flikens sektioner** (efter den befintliga demo-tabellen):
1. **Riksdagen — mandatfördelning enligt nowcast** — kör `nowcast`-rösterna
   genom `allocate_all_mandates()` (samma motor som opinionsfliken) → full
   mandat-bar, tabell med fasta/utjämning/totalt, blockmajoritets-metrics.
2. **Per valkrets** — selectbox + tabell med röstandel och fasta mandat per parti
   för den valda valkretsen.
3. **Förväntade invalda enligt nowcast** — återanvänder `predict_elected_candidates()`
   + `predict_adjustment_*()`-mappningen från Kandidater-fliken, driven av
   nowcast-mandaten istället för opinions-mandaten.

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
- [x] ~~SCB-kommundata laddas synkront och kan göra appen trög~~ — cachas nu
      i `data/scb_2022.json` (genererad av `fetch_scb_cache.py`)
- [x] ~~Inga automatiska tester~~ — pytest finns för `nowcast.py` (tests/, 10 cases)
- [ ] `app.py` är ~4 000+ rader – uppdelning väntar tills efter valet 2026
- [x] ~~Nowcast: live-feed mot `resultat.val.se/val2026/...`~~ — klar i
      `val_feed.py`. Pollar `index.md5` → hämtar den nationella RD-zip:en
      (`./p/rd/Val_<datum>_preliminar_00_RD.zip`) → md5-verifierar → parsar
      röstfördelningen till distrikts-schemat. Kopplad till Valnatt-fliken via
      `_fetch_live_nowcast()` (60 s cache, baslinje = 2022). Live aktiveras
      2026-09-13 eller via `?live=1`.
- [ ] Nowcast: demo-fliken använder fortfarande storlekssortering som
      räkningsordningsproxy. Live-feeden innehåller `rapporteringsTid` per
      distrikt (riktiga tidsstämplar) — demo-backtestet kan nu byta till
      faktisk räkningsordning via `val_feed` istället för PDF-parsning.
- [ ] Nowcast: ~948 distrikt droppas pga 2018→2022 boundary changes; bör
      hanteras via `data/raw/jamforelser-2018-2022-valdistrikt.xlsx`. Samma
      gäller live: distrikt utan 2022-motsvarighet droppas ur deltaberäkningen
      (`_fetch_live_nowcast` rapporterar antalet).
- [ ] Nowcast live: `_load_baseline_2022()` laddar 2022-XLSX on-demand (~30 s
      cold-start på Cloud Run). Överväg att pre-cacha till committad JSON som
      SCB-datan (`fetch_scb_cache.py`-mönstret) inför valnatten.

---

## Köra lokalt

```bash
# Produktionsmiljö
pip install -r requirements.txt
streamlit run app.py

# Utvecklingsmiljö (inkl. pytest)
pip install -r requirements-dev.txt
pytest tests/
python validate_nowcast.py   # Reproducerar valprognos.se:s MAE-siffror

# Uppdatera SCB-cachen (körs sällan, bara om SCB rättar 2022-siffror)
python fetch_scb_cache.py    # → data/scb_2022.json
```

**OBS Windows arm64:** Streamlits transitiva beroenden (httptools, pyarrow)
bygger inte på arm64. Kör Streamlit i molnet eller på x86_64. Nowcast-modulerna
fungerar dock fristående lokalt.

## Deploya (Google Cloud Run)

Förutsättningar:
- `gcloud` CLI installerad (`winget install --id Google.CloudSDK` på Windows)
- Inloggad: `gcloud auth login`
- Projekt aktivt: `gcloud config set project mandatorn-prod`
- Billing kopplat till projektet
- API:er aktiverade: `run`, `cloudbuild`, `artifactregistry`

Deploy från repo-roten (en rad):

```powershell
gcloud run deploy mandatorn --source . --region europe-north1 --allow-unauthenticated --memory 1Gi --cpu 1 --min-instances 1 --max-instances 3 --port 8080 --timeout 3600
```

Cloud Build packar `Dockerfile` → pushar till Artifact Registry → deployar.
Första bygget: 3-5 min. Subsequent: 1-2 min (cache reuse på pip-layern).

Custom domain `mandatorn.se` är mappad via `gcloud beta run domain-mappings`.
DNS hostas på One.com. SSL-cert utfärdas automatiskt av Google (Let's Encrypt).

**Legacy:** Streamlit Community Cloud (`share.streamlit.io`) — avvecklas
efter Cloud Run-cutover bekräftats stabil.

---

## Viktiga varningar vid kodändringar

- **`sigma_process_per_day`** finns i tre funktionssignaturer – ändra alltid alla tre synkront
- **Plotly bar charts:** Använd INTE `text`-attributet på `go.Bar` – det blöder in i hover oavsett `hovertemplate`. Använd layout `annotations` istället för stapeletiketter
- **Favicon:** `favicon.png` genereras från `favicon.svg` via cairosvg. Om du ändrar SVG:n, regenerera PNG:n
- **Logo:** Inline base64-SVG i `app.py` – om `logo.svg` saknas faller den tillbaka på `st.title("Mandatorn")`
- **Sainte-Laguë** finns i två varianter: `app.py:modified_sainte_lague()` och `nowcast.py:modified_sainte_lague()`. Synka båda vid ändring. (Avsiktlig duplikation tills app.py styckas efter valet.)
- **Valnatt-fliken** läggs in i `app.py` via `_tab_labels.insert(8, ...)` — om tab-strukturen ändras, kontrollera att unpacking-raderna (`tab1, tab2, ...`) fortsatt matchar.
