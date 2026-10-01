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
├── app.py                    # Streamlit-labbet: bara UI, importerar mandatorn_model (~3 700 rader)
├── mandatorn_model/          # Modellen, fri från streamlit (utbruten 2026-10-01, paritet verifierad)
│   ├── constants.py          # partier, valkretsar, valdatum, baslinje (laddar data/election_2026.json)
│   ├── polls.py              # fetch_polls_text/parse_polls, compute_house_weights
│   ├── kalman.py             # Kalman + RTS, ankring i valresultatet, trenddata
│   ├── seats.py              # modified_sainte_lague, allocate_all_mandates, baslinjemandat
│   ├── simulation.py         # run_simulation (Monte Carlo)
│   ├── margins.py            # mandatmarginaler
│   ├── candidates.py         # kandidatlistor + förväntade invalda
│   ├── regional.py           # uniform swing per kommun/region
│   ├── backtest.py, valnatt.py
│   ├── nowcast.py            # Delta-baserad nowcasting-algoritm (valprognos.se-metoden)
│   ├── val_feed.py           # Valmyndighetens resultatfeed: RD-röster + KF/RF-mandat + valkretsstruktur
│   ├── muni_mandates.py      # Kommunal/regional mandatmodell (full Sainte-Laguë)
│   └── data_loader.py        # 2018+2022 valdistriktsdata (XLSX) för validate_nowcast
├── web/                      # Publika sajten: Astro 7 (statisk) + React-öar, läser releaser
│   ├── src/lib/release.ts    # Byggtid: läser + verifierar releasen (MANDATORN_RELEASE_DIR)
│   ├── src/lib/client/       # Klient: manifest, SHA-256-verifiering, live-uppdatering
│   ├── src/lib/seats.ts      # TS-port av vallag.py (bitidentisk, golden tests)
│   ├── src/lib/text/         # Mallmotor för ingresser (svensk grammatik, tid)
│   └── scripts/postbuild.mjs # sitemap, OG-bilder, unika titlar, prestandabudget
├── contracts/                # Genererat: JSON Schema + TS-typer + constants.ts (tools/gen_contracts.py)
├── tools/parity_capture.py   # Fångar allt app.main() ritar (fryst klocka, lokala nätverkssvar)
├── tools/parity_compare.py   # Jämför två fångster — paritetsgrind vid refaktorering
├── validate_nowcast.py       # Offline-validering mot 2022 års val
├── fetch_election_2026.py    # Slutligt RD 2026 (riks, valkrets, kommun) → data/election_2026.json
├── fetch_muni_cache.py       # KF/RF-struktur + röster → data/muni_structure_<år>.json
├── fetch_valnatt_2026.py     # Valnattens distriktsräkning 2026 → data/valnatt_2026.csv.gz
├── tests/
│   └── test_nowcast.py       # Pytest-enhetstester (10 st)
├── data/
│   ├── election_2026.json    # Committad — slutligt RD 2026: riks, valkrets, kommun (~80 kB)
│   ├── muni_structure_2026.json  # Committad — KF/RF 2026: struktur, röster, mandat (~530 kB)
│   ├── muni_structure_2022.json  # Committad — KF/RF 2022 (fallback per område)
│   ├── valnatt_2026.csv.gz   # Committad — valnattens räkning per distrikt + 2022-baslinje (~200 kB)
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

**Modellen ligger i `mandatorn_model/`** (ingen streamlit-import). `app.py` är bara
UI och lägger Streamlit-cache runt paketets funktioner (`st.cache_data(...)(fn)`
överst i filen). Ändra modellogik i paketet, inte i app.py. Vid refaktorering:
kör `tools/parity_capture.py` före och efter och jämför med `tools/parity_compare.py`
— hela appens utdata ska vara identisk. Ombyggnaden till statisk sajt styrs av
`mandatorn_rebuild_prompt.md` + `docs/` (PARITY, ARCHITECTURE, DECISIONS, ASSUMPTIONS).

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
- **Valresultat 2026 (Valmyndigheten):** `data/election_2026.json` (riks,
  valkrets, `kommuner` = RD-andel per kommun summerad över kommunens distrikt)
  och `data/muni_structure_2026.json` (KF/RF-röster + mandat; saknas slutlig
  mandatfördelning används den preliminära, se `stage`). `load_area_results()`
  i app.py bygger Regional-flikens baslinje ur dessa. SCB används inte längre
  (SCB:s PX-tabeller saknade 2026 per 2026-09-29).
- **Valnatten 2026:** `data/valnatt_2026.csv.gz` — preliminär räkning per
  ordinarie distrikt med `rapporteringsTid` och Valmyndighetens 2022-jämförelse
  (`antalRosterForegaendeVal`, omräknad till 2026 års indelning).

---

## Modellarkitektur

### 1. Kalman-filter-aggregering
Tre funktioner delar samma logik:
- `aggregate_polls_kalman()` – aktuellt estimat per parti
- `aggregate_polls_kalman_timeseries()` – tidsserier för trendgraf
- `kalman_smooth()` – bakåtutjämnad serie

**Ankring i valresultatet** (`_anchor_to_baseline`): efter `BASELINE_ELECTION_DATE`
släpps alla mätningar t.o.m. valdagen och valresultatet läggs in som första
observation (σ = 0,1 pp). Backtest med `reference_date` före valet påverkas inte.
Trend-/blockgrafen visar augusti 2022 → idag (`TREND_START`) med streck vid valen
(`TREND_ELECTIONS`): segmentet före valet 2026 körs oankrat, segmentet efter
startar i valresultatet (linjen hoppar på valdagen).

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
- Enligt vallagen (`mandatorn_model/vallag.py`, golden tests mot Valmyndighetens
  officiella utfall 2022 och 2026 per valkrets i `tests/golden/`):
  jämkade uddatalsmetoden (1,2; 3; 5 …) för fasta mandat och för landets fördelning,
  4 % i landet eller 12 % i valkretsen (bara fasta mandat där), återföring vid
  överhäng, utjämningsmandat placeras med *ojämkad* uddatal (1; 3; 5 …) på röster per
  valkrets. Lika jämförelsetal: högst röstetal, sedan partikod (lagen: lottning).
- Spärren prövas mot andel av alla giltiga röster (övriga antas = baslinjen, 1,59 %).
- 310 fasta mandat (valkretsar) + 39 utjämningsmandat
- Monte Carlo: 10 000 simuleringar med normalfördelad osäkerhet per parti.
  Inkluderar horisontterm `HORIZON_K·sqrt(andel)·sqrt(dagar kvar/TERM_DAYS)` mot
  `NEXT_ELECTION` (2030-09-08). Punktprognosen = "om det vore val idag".

### 4. Utjämningsmandat
1. Landets 349 mandat fördelas med jämkade uddatalsmetoden bland partier ≥ 4 %
2. Utjämningsmandat = landets fördelning − fasta mandat (återföring vid överhäng)
3. Placering per valkrets: ojämkad uddatal på prognostiserade röster (andel × valkretsens
   giltiga röster 2026, `valid_votes` i `data/election_2026.json`)

---

## Appens flikar

| Flik | Nyckelinnehåll |
|---|---|
| 📊 Opinion | Kalman-trendgraf per parti **+ blocktidslinje (Höger vs Vänster)**, partistöd-tabell, mandatprognos, stöd per valkrets |
| 🏛️ Mandat | Mandatöversikt, konfidensintervall, blockanalys, **mandatmarginal** (nationellt + per valkrets + landets jämnaste mandat) |
| 🗺️ Valkretsar | Mandattabeller + detaljerade stapeldiagram per valkrets |
| 🎲 Simulering | Monte Carlo-sannolikheter, koalitionsanalys, majoritetsanalys |
| 👤 Kandidater | Förväntade invalda baserat på Valmyndighetens listor |
| 📍 Regional & kommunal | Region- och kommunprognos: uniform swing på valresultatet 2026 (Valmyndigheten, selectbox + stapeldiagram) **+ opinionsbaserad mandatuppskattning** för KF/RF (full kommunal Sainte-Laguë via `muni_mandates`, lokalpartier hållna vid 2026, jämförelse mot 2026 års mandat) |
| 📋 Data | Rådata, institutvikter |
| ℹ️ Metod | Metodbeskrivning, backtesting |
| 🌙 Valnatt | **Uppspelning av valnatten 2026** (`_render_valnatt_replay`): klockslagsreglage 20:40–04:00, distrikten läggs till i verklig rapporteringsordning. Råräkning vs nowcast vs slutresultat 2026, felkurva över natten, därefter riksdagsmandat + förväntade invalda enligt nowcasten, och KF/RF-mandatfördelning 2026 per vald kommun/region. Ingen live-hämtning längre — återinför inför 2030 (se git-historik före 2026-09-29: `_fetch_live_nowcast`). |
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
uniform swing (nationell riksdagssving sedan 2026) appliceras per valkrets på
**riksdagspartierna**; **lokala partier antas få samma resultat som 2026** (ingen
opinionsdata finns) och konkurrerar med i modellen. Sedan Sainte-Laguë (divisor
1,2) för fasta mandat per valkrets + utjämningsmandat (divisor 1,0) + 2/3 %-spärr.
Utan utjämningsmandat är de fasta mandaten slutgiltiga. Struktur (mandat/valkrets,
utjämning, spärr, röster per parti, mandat, partimetadata) läses från committad
`data/muni_structure_2026.json` (genererad av `fetch_muni_cache.py` från KF/RF-
feedfilernas `valkretsLista`; faller per område tillbaka på 2022-filen). UI visar
mandatuppskattningen jämte 2026 års mandat (Δ). **Validering:** nollsving
reproducerar 2026 års mandatfördelning exakt för 309 av 310 områden — undantaget
Region Östergötland, som bara har preliminär mandatfördelning. Enkla valkretsar
saknar `antalFastaMandat` i 2026-filerna; `parse_area_structure` räknar då alla
mandat som fasta. Lokalpartier utan `partiforkortning` nyklas på partikod.

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

**Valnatt-flikens sektioner** (efter uppspelningen):
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
- [x] ~~SCB-kommundata laddas synkront~~ — ersatt av committad Valmyndighets-data 2026
- [x] ~~Inga automatiska tester~~ — pytest finns för `nowcast.py` (tests/, 10 cases)
- [ ] `app.py` är ~4 000+ rader – uppdelning väntar tills efter valet 2026
- [x] ~~Nowcast: live-feed mot `resultat.val.se/val2026/...`~~ — klar i
      `val_feed.py`. Pollar `index.md5` → hämtar den nationella RD-zip:en
      (`./p/rd/Val_<datum>_preliminar_00_RD.zip`) → md5-verifierar → parsar
      röstfördelningen till distrikts-schemat. Användes live valnatten 2026;
      Valnatt-fliken är nu en uppspelning (live-UI:t borttaget, finns i git).
- [x] ~~Nowcast-demo med storlekssortering som räkningsordning~~ — uppspelningen
      använder verklig `rapporteringsTid` från valnatten 2026.
- [ ] Nowcast: 1 253 av 6 312 distrikt 2026 är "Ej jämförbart" mot 2022
      (≈ 20 % av rösterna) och ingår inte i deltaberäkningen. Kan förbättras
      genom att summera `valdistriktskodForegaendeVal` mot 2022 års distrikt.

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

# Uppdatera valdata (körs sällan — t.ex. när Länsstyrelserna fastställt mandat)
python fetch_election_2026.py   # → data/election_2026.json
python fetch_muni_cache.py      # → data/muni_structure_2026.json
python fetch_valnatt_2026.py    # → data/valnatt_2026.csv.gz
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
- **Sainte-Laguë** finns i två varianter: `mandatorn_model/seats.py:modified_sainte_lague()` (riksdagen, divisor 1,2) och `mandatorn_model/nowcast.py:modified_sainte_lague()` (OBS standard `first_divisor=1.4`, se docs/PARITY.md A9). Samordnas i D6-steget.
- **Valnatt-fliken** läggs in i `app.py` via `_tab_labels.insert(8, ...)` — om tab-strukturen ändras, kontrollera att unpacking-raderna (`tab1, tab2, ...`) fortsatt matchar.

## Webben (fas 2) — viktigt vid ändringar
- **Talformat i React-öar:** använd `lib/text/grammar` (formatNumber/formatInteger), inte `Intl`/`toLocaleString` — tecknen skiljer mellan Node och webbläsare och ger hydreringsfel.
- **Ingen `<title>` i SVG inuti React-öar** (React 19 tömmer den vid SSR) — använd `aria-label`.
- **Sannolikheter visas alltid med `displayPct`/`verbal`** (aldrig 0 %/100 %); skalan definieras i `contracts/verbal_scale.json`.
- Konstanter (partier, färger, valdatum) genereras ur Python: kör `python tools/gen_contracts.py` efter ändring i `mandatorn_model/constants.py` eller `contracts.py`.
- Tomma miljövariabler ska behandlas som osatta (`||`, inte `??`).
