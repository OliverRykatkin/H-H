# PARITY.md: funktionsparitet Streamlit → statisk sajt

Inventering av fas 0. Läget i koden är commit `922dd3e` (2026-09-29).
Radnummer avser `app.py` i den commiten.

**Kolumner**
- **Nu**: implementationen i Streamlit, med fil och funktion.
- **Ny**: `PRE` betyder förberäknad JSON eller CSV i releasen. `KLIENT` betyder att det räknas i webbläsaren. `STATISK` betyder förrenderad text.
- **Verifiering**: hur vi visar att resultatet är detsamma.
- **Prio**: byggordning i fas 2 (1 först).

Status: ☐ ej påbörjad · ◐ pågår · ☑ verifierad

Sist i dokumentet finns två avsnitt:
- *Nya funktioner som inte finns i dag*: sådant uppdraget kräver men som Streamlit saknar.
- *Avvikelser att besluta*: avvikelser mot vallagen och fel i nuvarande kod.

---

## 0. Globalt (sidhuvud och beräkningar som delas mellan flikar)

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 0.1 | Opinionsmätningar | `load_polls()`: SwedishPolls CSV live, med korrigering av Infostats PublDate | Pipeline: en kopia av mätningarna i `data/polls/` (PR-flöde) plus ett synk-jobb mot SwedishPolls. Releasen innehåller `polls.json`, de senaste N mätningarna. | Samma rader och samma PublDate-korrigering. Hash av indata i manifestet. | 1 | ☐ |
| 0.2 | Institutsvikter | `compute_house_weights()`: 1/MAE 90 dagar före valet 2026 | PRE `institutes.json` | Identiska vikter (exakt float) | 1 | ☐ |
| 0.3 | Nationellt estimat | `aggregate_polls_kalman()`: Kalman + RTS, ankrat i 2026-resultatet, fönster max(365, dagar sedan valet) | PRE `national.json` | Avvikelse < 1e-9 mot Streamlit för samma `reference_date` | 1 | ☐ |
| 0.4 | Trendserie | `aggregate_polls_kalman_timeseries()` i två segment (aug 2022 → valet 2026, valet 2026 → idag) som skalas mot `raw_est` i `main()` (rad ~3287–3315) | PRE `timeseries.json` och `latest/timeseries.csv` med p5/p50/p95 | Samma punkter. Skalningen och sammanfogningen flyttas till en funktion och testas. | 1 | ☐ |
| 0.5 | Punktprognos för mandat | `allocate_all_mandates(raw_est)` | PRE `mandates.json` med fasta mandat, utjämningsmandat och totalt per parti och valkrets. TS-port för scenarier i klienten. | Noll avvikelse i mandat, golden tests i Python och TS | 1 | ☐ |
| 0.6 | Monte Carlo | `run_simulation()`: 10 000 dragningar, seed 42, σ = polls + 1,0 + horisontterm, **bara nationellt** | PRE `simulation.json` (sammanfattning) och ett urval av dragningar `draws.parquet` för egna villkor i klienten | Samma seed ger identiska `party_mandates`, `bloc_h` och `bloc_v`. `reference_date` måste skickas in (i dag `datetime.now()`). | 1 | ☐ |
| 0.7 | Logga, favicon, typsnitt | inline base64 av `logo.svg`, DM Sans från Google Fonts | STATISK. DM Sans hostas själv: inga anrop till Google utan cookies, i linje med målet utan cookie-banner. | Visuell jämförelse | 1 | ☐ |
| 0.8 | Sidhuvudets texter | "Senaste undersökning", "om det vore val idag", "N dagar kvar" (mot `now()`), disclaimer | Ingress ur mallmotorn. Antalet dagar räknas mot releasens `generatedAt`. | Golden tests för texten före, under och efter valdagen | 1 | ☐ |
| 0.9 | Fyra nyckeltal (block mot 175, största parti, under spärren) | `main()` rad ~3350 | PRE i `national.json`. Förrenderas ovanför vecket. | Samma värden | 1 | ☐ |

## 1. 📊 Opinion → `/` (startsidan) och `/parti/<slug>`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 1.1 | Trendgraf: 8 partier + Övriga, 95 %-band, mätpunkter, 4 %-linje, streck vid valen | `make_trend_chart()` | React-ö (diagram) som läser `timeseries.json` och `polls.json` | Samma serier punkt för punkt | 1 | ☐ |
| 1.2 | Nedladdning av trenddata | `build_trend_data()`, utan intervall | `latest/timeseries.csv` med p5/p50/p95 | Kolumnen p50 ska vara lika med dagens CSV | 1 | ☐ |
| 1.3 | Blocktrend | `make_block_trend_chart()`, approximativt band | React-ö | Samma summor | 2 | ☐ |
| 1.4 | Stapel för partistöd och tabellen "Estimat per parti" (2026 %, nu %, Δ, spärr, Övriga) | `make_support_bar()` plus inline-tabell | Förrenderad tabell och liten ö | Samma värden | 1 | ☐ |
| 1.5 | Mandatstapel, mandattabell och blocknyckeltal | `make_mandate_bar()` | Förrenderad, ur `mandates.json` | Samma värden | 1 | ☐ |
| 1.6 | Väljare för valkrets och stöd i vald valkrets | Inline (rad ~3471–3578). **Rå sving** `raw_est − BASELINE`. | PRE `valkrets/<slug>.json`. Visas på `/valkrets/<slug>`. | Samma andelar. Se A7 om formeln för svingen. | 2 | ☐ |

## 2. 🏛️ Mandat → `/mandat`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 2.1 | Intervalldiagram i Economist-stil (90 %, IQR, 2026-romb) | `make_economist_mandate_chart()` | React-ö ur `simulation.json` | Samma percentiler | 1 | ☐ |
| 2.2 | Mandatöversikt och blocköversikt | inline | Förrenderad | Samma värden | 1 | ☐ |
| 2.3 | Nationell mandatmarginal (±1 mandat i pp) | `compute_national_margins()`, 0,05 s | PRE `margins/national.json` | Exakt samma marginaler | 3 | ☐ |
| 2.4 | Lokal marginal för fasta mandat i vald valkrets | `compute_constituency_margins()`, interaktivt, 0,26 s för alla 29 | PRE `margins/valkrets/<slug>.json` (alla 29 förberäknas) | Exakt | 3 | ☐ |
| 2.5 | Landets jämnaste fasta mandat (topp 15) | `compute_closest_fixed_seats()` | PRE `margins/closest.json` | Exakt | 3 | ☐ |

## 3. 🗺️ Valkretsar → `/valkrets/<slug>` och `/valkretsar`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 3.1 | Stöd i vald valkrets (stapel och tabell) | inline (rad ~3748), samma kod som 1.6 | PRE `valkrets/<slug>.json` | Samma andelar | 2 | ☐ |
| 3.2 | Fasta mandat per valkrets: prognos, 2026 och förändring (radio) | `compute_baseline_mandates()` plus `fixed_df` | Förrenderad tabell med flikar i klienten | Samma tabell | 2 | ☐ |
| 3.3 | Parti per valkrets, stapel | `make_constituency_bar()` | Ö på `/parti/<slug>` | Samma värden | 2 | ☐ |
| 3.4 | Karta | Saknas i dag. `load_geojson()` anropas i `main()`, men ingen vy ritar en karta. | MapLibre, lazy, faller tillbaka på tabell (ny funktion) | — | 2 | ☐ |

## 4. 🎲 Simulering → `/sannolikheter` och kort på entitetssidor

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 4.1 | "Hur sannolikt är det att…": 12 hårdkodade frågor, verbal skala ≥95/≥70/≥30/≥5 | inline i tab4 (rad ~4172–4243) | Deklarativ konfiguration `questions.yaml`. PRE `probabilities.json`. Skalan definieras på ett ställe (se DECISIONS D3). | Samma sannolikheter med samma seed | 2 | ☐ |
| 4.2 | Majoritet: tre nyckeltal och stapel | inline | PRE | Samma | 2 | ☐ |
| 4.3 | Histogram över blockens mandat | inline | Ö ur `simulation.json` (histogram förberäknat) | Samma klasser | 2 | ☐ |
| 4.4 | Tabell med 90 %-intervall per parti (σ polls, horisont, total, P över 4 %) | inline | PRE | Samma | 2 | ☐ |
| 4.5 | Boxdiagram över mandatspridning | inline | Ö (kvartiler förberäknade) | Samma | 3 | ☐ |
| 4.6 | Koalitionsanalys: 7 fasta koalitioner, P ≥ 175, fördelning | `make_coalition_chart()`, `make_coalition_mandate_dist()`, `COALITIONS` | PRE för de fasta koalitionerna. **KLIENT** för egna koalitioner (koalitionsbyggare) på `draws`. | P för de fasta koalitionerna ska vara lika med Python | 3 | ☐ |

## 5. 👤 Kandidater → `/kandidat/<slug>` och `/kandidater`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 5.1 | Kandidatlistor | `load_candidates()`: live från data.val.se, 4 s, dedupar listplatser | Pipeline: snapshot i releasen (`candidates.json`). Se DECISIONS D8 (GDPR) och D10 (listorna från 2026 eller 2030). | Samma lista | 4 | ☐ |
| 5.2 | Förväntat invalda via fasta mandat (deterministiskt, listordning, hemvalkrets) | `predict_elected_candidates()` | PRE `kandidater/<valkrets>.json` | Samma namn | 4 | ☐ |
| 5.3 | Utjämningsmandat → valkrets → kandidat | `predict_adjustment_constituencies()` / `_candidates()` | PRE | Samma namn | 4 | ☐ |
| 5.4 | Väljare för valkrets, tabell, könsfördelning | inline | Förrenderad per valkretssida | Samma | 4 | ☐ |
| 5.5 | Registreringsstatus per parti | inline | **Tas bort efter beslut**: gäller perioden före valet 2026 | — | — | ☐ |
| 5.6 | Nedladdningar `riksdagsprediction_kandidater.csv` | inline | `latest/kandidater.csv` | Samma rader | 4 | ☐ |

## 6. 📍 Regional & kommunal → `/kommun/<slug>` och `/region/<slug>`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 6.1 | Val av valtyp (RD per kommun, RF, KF) och område | radio och selectbox | En sida per kommun och region med RD- och KF-avsnitt (kommun) respektive RF (region) | — | 2 | ☐ |
| 6.2 | Uniform swing per område (nollsummerad sving) | `load_area_results()` + `apply_uniform_swing()`, 0,02–0,04 s | PRE `kommun/<kod>.json`, `region/<lan>.json`, `latest/kommuner.csv`, `latest/regioner.csv` | Exakt | 2 | ☐ |
| 6.3 | Stapel 2026 mot nu och detaljtabell (inkl. Övriga) | inline. `go.Bar` med `text=` bryter mot CLAUDE.md. | Ö eller förrenderad tabell | Samma | 2 | ☐ |
| 6.4 | Tabell över nationell sving | inline | PRE i `national.json` | Samma | 2 | ☐ |
| 6.5 | Tabell över alla områden och CSV | inline | `latest/kommuner.csv`, `regioner.csv` | Samma | 2 | ☐ |
| 6.6 | Mandatuppskattning KF/RF (lokala partier hålls vid 2026) | `muni_mandates.allocate_area_mandates()`, 0,04 s för alla 310 | PRE i respektive område-JSON | Exakt. Nollsving ger 2026 års mandat (309/310). | 2 | ☐ |
| 6.7 | Karta | `make_regional_map()` är **definierad men renderas inte**. GeoJSON hämtas live bara för namnen. | MapLibre, lazy. Namn och koder flyttas till releasen (oberoende av GeoJSON). Se DECISIONS D9 om kartlicensen. | — | 3 | ☐ |

## 7. 📋 Data → `/data`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 7.1 | Senaste mätningarna (reglage för antal rader) | inline | `/` och `/institut/<slug>`: tabell med valbar förändring | Samma rader | 2 | ☐ |
| 7.2 | Institutsvikter, tabell och stapel | inline. **Texten säger "mot 2022", koden räknar mot 2026.** | `/institut/<slug>` och `latest/institutsbias.csv` (ny, se N4) | Samma vikter | 3 | ☐ |
| 7.3 | Valresultat 2022 per valkrets | `CONSTITUENCIES_2022` | `/arkiv/2022` | Samma | 5 | ☐ |
| 7.4 | Mandatdata som CSV | `fixed_df` | `latest/valkretsar.csv`, `latest/mandat.csv` | Samma | 2 | ☐ |
| 7.5 | Licens, källor, rättelselogg | finns inte | STATISK `/data`, `/licens`, `CHANGELOG-data.md` | — | 3 | ☐ |

## 8. ℹ️ Metod → `/om`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 8.1 | Metodtext avsnitt 1–7 (markdown och LaTeX) | statisk. **Flera inaktuella uppgifter**, se A6. | STATISK. Formler med KaTeX vid bygget, ingen JS i klienten. | Granskas mot koden | 5 | ☐ |
| 8.2 | Backtesting med radio 2026/2022: MAE och RMSE per referensdatum, fel per parti | `compute_backtesting()`, 0,3 s per år | PRE `backtest/<år>.json` | Exakt | 5 | ☐ |

## 9. 🌙 Valnatt → `/valnatt` (uppspelning) och nowcast-läge (fas 3)

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 9.1 | Uppspelning av valnatten 2026: klockslag 20:40–04:00, råräkning, nowcast, facit, felkurva | `_render_valnatt_replay()`, `_valnatt_state()`, `_valnatt_error_curve()` | PRE `valnatt/2026/<HHMM>.json` (45 filer) och `curve.json` | Exakt samma nowcast per tidpunkt | 5 | ☐ |
| 9.2 | Mandat, valkretsar och invalda enligt nowcasten | `_render_rd_downstream()` | PRE per tidpunkt (mandat). Kandidater per tidpunkt efter beslut. | Exakt | 5 | ☐ |
| 9.3 | KF/RF-mandat 2026 per kommun och region | `_render_valnatt_local_mandates()` | Länkas till `/kommun/<slug>` och `/region/<slug>` (samma data) | Samma | 5 | ☐ |
| 9.4 | Live-nowcast mot Valmyndigheten | Borttagen 2026-09-29 (finns i git före `922dd3e`). `val_feed.fetch_live()` finns kvar. | Fas 3: ingest på Fly.io, releaser med `mode: nowcast`, fördröjning för partner | Simulatorn spelar upp 2026 (och 2022) | fas 3 | ☐ |

## 10. 🙋 Om mig → `/om#forfattare` eller `/kontakt`

| # | Funktion | Nu | Ny | Verifiering | Prio | Status |
|---|---|---|---|---|---|---|
| 10.1 | Författartext | statisk | STATISK | — | 5 | ☐ |

## 11. Nya statiska sidor (finns inte i dag)

`/data`, `/licens`, `/status` (+ `/version.json`), `/integritet`, `/arkiv/<år>`, `/institut/<slug>`, `sitemap.xml`, `robots.txt`. Byggs i fas 2 med prio 3–5.

---

## Nya funktioner som inte finns i dag

Uppdraget förutsätter delvis data som modellen **inte räknar fram i dag**. Att lägga till dem är nya beräkningar ovanpå befintlig metod, inte en metodändring, men det kräver ett beslut (DECISIONS D11).

| # | Uppdraget kräver | Läget i dag | Vad som krävs |
|---|---|---|---|
| N1 | `latest/mandat.csv`: sannolikhetsfördelning **per parti och valkrets** | `run_simulation` fördelar bara nationellt (349 mandat i ett steg) | Kör `allocate_all_mandates` per dragning (10 000 × ~1 ms ≈ 10 s, eller vektoriserat) |
| N2 | `latest/kandidater.csv`: **sannolikhet** att bli invald | Kandidatprognosen är deterministisk (listordning ur punktprognosen) | Kandidatprognos per dragning, eller härledd ur N1 (P(parti får ≥ k fasta mandat i valkrets)). Utjämningsplaceringen är dyr (0,57 s per anrop), så den behöver vektoriseras eller bara tas på ett urval. |
| N3 | Kort som "M tar ett fast mandat till i Stockholms län" | Finns inte | Följer av N1 |
| N4 | `latest/institutsbias.csv` per institut och parti (antal, andel över/under, medel/median i pp och %) | Bara MAE per institut (ett tal) | Ny deskriptiv beräkning mot Kalman-aggregatet eller valresultatet (ASSUMPTIONS A-4) |
| N5 | Kommun- och regionprognos **med intervall** | Bara punktprognos (uniform swing på `raw_est`) | Applicera svingen per dragning |
| N6 | Rekordval och sämsta val per parti | Finns inte | Historiska valresultat per parti (1921 och framåt, eller 1970 och framåt) som ny indata |
| N7 | Trendtabell mot en månad sedan, ett år sedan och senaste valet | Finns inte | Ur tidsserien. Billigt. |
| N8 | `/arkiv/<år>`: prognosens utveckling fram till valdagen | Finns inte (inga releaser sparade) | Releaser framöver. För 2026 kan historiken räknas om i efterhand med `reference_date` (se DECISIONS D12). |
| N9 | Simulator för valnatten 2022 och EU-valet 2024 | Uppspelning av 2026 finns. 2022 kräver `data_loader` (2018-baslinje). EU 2024-data saknas helt. | Fas 3 |

## Avvikelser att besluta

Inget av detta är ändrat. Uppdraget säger att avvikelser mot vallagen ska flaggas, inte rättas på egen hand.

| # | Avvikelse | Var | Påverkan |
|---|---|---|---|
| A1 | **12 %-regeln saknas.** Ett parti under 4 % nationellt men med minst 12 % i en valkrets får inte delta om de fasta mandaten där. | `allocate_all_mandates`, `run_simulation` | Liten i praktiken. Golden test-kantfallet i uppdraget misslyckas. |
| A2 | **Nationell fördelning med första divisor 1,2.** Vallagen (14 kap.) använder ren uddatalsmetod (1,0) för den nationella proportionella fördelningen vid utjämning. CLAUDE.md säger 1,0, koden använder 1,2. | `allocate_all_mandates` rad ~1463, `run_simulation` | Kan flytta ett mandat mellan stora och små partier. 2026 års utfall reproduceras ändå exakt. |
| A3 | **Utjämningsmandat** fördelas med Sainte-Laguë på *behovet*, inte enligt lagens procedur. Lagen: överhängspartier tas bort och det räknas om, sedan fördelas mandaten ett i taget per valkrets på jämförelsetal. | `allocate_all_mandates`, `predict_adjustment_constituencies` | Totalen per parti stämmer oftast. Placeringen per valkrets kan avvika. |
| A4 | **Spärrbasen** är andelen bland de 8 partierna (normaliserad till 100), inte andelen av alla giltiga röster. | `raw_est`, `allocate_all_mandates`, `run_simulation` | Ett parti på 3,95 % av alla röster blir ~4,01 % → kommer in. |
| A5 | **Personvalsspärren (5 %)** saknas. Kandidatprognosen bygger bara på listordning. | kandidatlogiken | Dokumenterad begränsning |
| A6 | **Inaktuella texter:** Metod-fliken säger σ_proc = 0,07 (koden 0,10); institutsvikter "mot 2022" (koden 2026); uniform swing "2022"; Data- och Valkretsflikarna "2022 (faktiskt)"; sidhuvudets caption "Nils Silverström"; kandidattexten beskriver en annan algoritm än koden. | se inventeringen | Rättas i Streamlit separat eller bara i den nya sajten |
| A7 | **Två svingformler.** Valkretsvyerna (tab1, tab3) använder rå sving `raw_est − BASELINE`. Regional-fliken använder nollsummerad sving. | rad ~3475, ~3748 och `compute_national_swing` | Små skillnader. Paritet ska avse respektive formel tills ett beslut finns. |
| A8 | **Läckage i backtesten.** Institutsvikterna kalibreras mot facit 2026 och används i båda backtesten (2026 och 2022). | `compute_backtesting` | Backtest-MAE ser för bra ut |
| A9 | `nowcast.modified_sainte_lague` har standardvärdet `first_divisor=1.4` (regeln före 2018). `project_mandates` använder det. | `nowcast.py` | Används inte i appen i dag, men är en fälla |
| A10 | Lika jämförelsetal avgörs deterministiskt (heap- och dict-ordning). Lagen föreskriver lottning. | alla Sainte-Laguë | Golden tests måste definiera regeln för lika värden och använda den i både Python och TS |
| A11 | `muni_mandates`: utjämningen hanterar inte överhäng och placerar inte mandaten på valkrets | `allocate_area_mandates` | Stämmer empiriskt för 2022 och 2026 (310/310 och 309/310) |
| A12 | `compute_backtesting_correction` och `make_regional_map` är död kod. Variabelnamnen `compute_2022_mandates`, `seats_2022_*` och `votes_2022` innehåller 2026 års data. | `app.py`, `muni_mandates.py`, strukturfilerna | Byt namn i fas 1 när koden bryts ut, med paritetstest |
