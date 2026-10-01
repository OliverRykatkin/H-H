# ARCHITECTURE.md: målarkitektur för Mandatorn

Konkretiserar de fastställda besluten i `mandatorn_rebuild_prompt.md` för just den här kodbasen.
Läget i koden är commit `922dd3e`. Öppna punkter står i `DECISIONS.md`, antaganden i `ASSUMPTIONS.md`.

```
                    ┌──────────────── GitHub (publikt repo) ────────────────┐
  data/polls/*.csv ─┤ PR → merge ─┐                                         │
  SwedishPolls ─────┤ synk-jobb (udda minuter) → öppnar PR                   │
  Valmyndigheten ───┤ fetch_*.py (manuellt efter val)                        │
                    │             ▼                                          │
                    │  GitHub Actions: kvalitetsgrind → modell → publish     │
                    │             │ OIDC-roll (ingen nyckel i repot)         │
                    └─────────────┼────────────────────────────────────────-┘
                                  ▼
             mandatorn_model.storage (adapter: put_immutable / put_pointer / …)
                                  ▼
   S3 eu-north-1:  site-bucket            data-bucket
                   (Astro-bygge)          releases/<id>/…, files/<sha256>…, manifest.json, latest/…
                                  ▼ OAC (ingen publik S3)
   CloudFront:     mandatorn.se           data.mandatorn.se   (CORS, cache-policyer per prefix)
                                  ▼
   Webbläsare:     förrenderad HTML ──hämtar──► manifest.json ──► hashade JSON-filer (verifieras med SHA-256)
```

Streamlit-appen (`app.py`) körs vidare på Cloud Run som internt labb och importerar samma modellpaket. Den är aldrig ett beroende för den publika sajten.

---

## 1. Kodstruktur efter fas 1

```
mandatorn_model/                 # inget beroende på streamlit
  constants.py                   # PARTIES, färger, valkretsar, valdatum, HORIZON_K, regionkoder …
  baseline.py                    # läser data/election_2026.json → NATIONAL, CONSTITUENCIES, kommuner
  polls.py                       # load_polls (+ PublDate-korrigering), house weights
  kalman.py                      # _anchor_to_baseline, _obs_sigma, aggregate_*, kalman_smooth,
                                 # build_trend_series (dagens sammanfogning/skalning ur main())
  seats.py                       # modified_sainte_lague, allocate_all_mandates, estimate_constituency_votes,
                                 # compute_baseline_mandates
  simulation.py                  # run_simulation (+ per-valkrets-variant om D11 godkänns)
  margins.py                     # compute_national/constituency_margins, closest_fixed_seats
  candidates.py                  # load_candidates (nätverk separerat), predict_elected/adjustment_*
  regional.py                    # compute_national_swing, apply_uniform_swing, load_area_results
  muni.py                        # = muni_mandates.py
  nowcast.py, val_feed.py, data_loader.py   # flyttas in oförändrade
  backtest.py                    # compute_backtesting
  probabilities.py               # deklarativa frågor (questions.yaml) → sannolikheter
  text/                          # mallmotor (svensk grammatik), verbal skala
  contracts/                     # Pydantic-modeller → JSON Schema → TS-typer
  publish.py                     # python -m mandatorn_model.publish
  storage.py                     # adapter mot S3-API
  quality.py                     # kvalitetsgrind
web/                             # Astro + React-öar (TypeScript)
infra/                           # Terraform
app.py                           # Streamlit-labbet: bara UI, importerar mandatorn_model
```

**Utbrytningsregler** (från inventeringen):
- `@st.cache_data` tas bort i paketet. Streamlit-labbet lägger egna cache-omslag runt anropen.
- Allt som i dag läser `datetime.now()` (`aggregate_polls_kalman`, `run_simulation`, `_days_left` och andra) får ett obligatoriskt `reference_date`. `publish` sätter det till `generatedAt`, vilket krävs för determinism.
- Modulnivåns globala tillstånd (`BASELINE`, `CONSTITUENCIES`, `_ELECTION_2026`) skickas in explicit eller laddas en gång via `baseline.load()`.
- Beräkningar som i dag ligger inne i flikarna lyfts ut till funktioner. Det gäller sannolikhetsfrågorna och koalitionerna i tab4, sammanfogningen av trendserien i `main()` och valkretsprognosen i tab1 och tab3.
- **Paritetsgrind för fas 1:** ett skript kör Streamlit-versionen (git-taggen före utbrytningen) och paketet med samma `reference_date` och seed. Mandaten ska ha noll avvikelse, andelarna högst 1e-9.

## 2. Publiceringskommando och artefakter

`python -m mandatorn_model.publish --reference-date … --seed … --out dist-data/`

Filer per release (alla JSON valideras mot Pydantic och skrivs kanoniskt: sorterade nycklar, fast avrundning):

| Fil | Innehåll | Ungefärlig storlek |
|---|---|---|
| `national.json` | estimat, σ, block, nyckeltal, sving, ingressdata | < 10 kB |
| `timeseries.json` | dagliga p5/p50/p95 per parti och block från 2022-08 | ~150 kB (gz ~40) |
| `polls.json` | de senaste 200 mätningarna | ~40 kB |
| `institutes.json`, `institut/<slug>.json` | vikter och bias (N4) | < 20 kB |
| `mandates.json` | punktprognos: fasta, utjämning och totalt per parti och valkrets | ~10 kB |
| `simulation.json` | percentiler, histogram, P(spärr), P(block), koalitioner | ~30 kB |
| `probabilities.json` | svar på alla konfigurerade frågor | < 10 kB |
| `valkrets/<slug>.json` ×29 | andelar, fasta mandat, marginaler, kandidater | ~5 kB styck |
| `kommun/<kod>.json` ×290, `region/<lan>.json` ×20 | RD-, KF- och RF-prognos och KF/RF-mandat | ~3 kB styck |
| `margins/*.json` | nationellt och jämnaste mandat | < 10 kB |
| `backtest/<år>.json` | MAE och RMSE per referensdatum | < 20 kB |
| `valnatt/2026/*.json` | 45 tidpunkter + kurva | ~3 kB styck |
| `draws.parquet` | urval av dragningar (10 000 × 8 andelar int16 + mandat) | ~170–350 kB |
| `latest/*.csv` + `.schema.json` | öppen data enligt uppdraget | se respektive fil |

**Release-id** = SHA-256 över det kanoniska filindexet (sökväg + sha256 för varje fil, sorterat). Samma indata, seed och modellversion ger samma id. `generatedAt` ingår **inte** i id:t. Det står bara i manifestet. Annars skulle två identiska körningar få olika id.

**Manifest** (`manifest.json`, < 100 kB): `schemaVersion`, `release`, `generatedAt`, `modelVersion` (git-sha), `seed`, `inputHash` (sha256 av mätningar + baslinjefiler + konfiguration), `mode`, `pollsIncluded {count, latestFieldEnd}`, `supersededBy`, `files[] {path, size, sha256}`.

## 3. Datalagret i S3 och CloudFront

```
data-bucket/
  files/<sha256>.<ext>          # innehållsadresserat, immutable, återanvänds mellan releaser
  releases/<release-id>/manifest.json
  releases/index.json
  manifest.json                 # pekare, skrivs sist
  latest/*.csv, *.schema.json   # alias, skrivs om per release
```

- Filindexet i manifestet pekar på `files/<sha256>`. Det ger avduplicering gratis, och "oförändrade filer återanvänds" blir trivialt.
- Cache-policy för `files/*`: `public, max-age=31536000, immutable`.
- Cache-policy för `manifest.json` och `releases/index.json`: `s-maxage=5` i kanten och `no-cache` i webbläsaren.
- Cache-policy för `latest/*`: `max-age=300`. De invalideras vid varje release.
- **Publiceringsordning:** `put_immutable` för alla filer, sedan `releases/<id>/manifest.json`, sedan `index.json`, och sist `put_pointer(manifest.json)`. En S3-PUT av ett enskilt objekt är atomär, så bytet sker i ett steg.
- **Rättelse:** en ny release, och den gamla får `supersededBy`. Det sker genom att den gamla `releases/<id>/manifest.json` skrivs om. Det är det enda objektet som får skrivas om. Händelsen loggas i `CHANGELOG-data.md`.
- **Gallring:** dragningar läggs under en egen tagg (`retention=draws`). En S3-livscykelregel tar bort taggade objekt efter N dagar (se D5). Publish tar bort taggen på dygnets första release och på valdagens release, så att de sparas.

## 4. Terraform (`infra/`)

- `s3_site`, `s3_data`: blockerad publik åtkomst, versionering på för `data`, livscykelregel för dragningar.
- `cloudfront_site`, `cloudfront_data`: OAC, cache-policyer enligt ovan, CORS-svarshuvud på `data.`. (Inget `partner/`-prefix: nowcasten publiceras utan fördröjning, se DECISIONS D4.)
- ACM-certifikat i `us-east-1` (krävs för CloudFront).
- DNS: i dag hos One.com. Antingen CNAME där eller Route 53 (se D2).
- `iam_github_oidc`: OIDC-provider och roll med trust på `repo:OliverRykatkin/H-H:ref:refs/heads/main` (plus en separat roll med bara läsrätt för PR-förhandsvisning). Rollen får `s3:PutObject` och liknande på de två bucketarna och `cloudfront:CreateInvalidation` på de två distributionerna.
- `budgets`: månadsbudget (förslag 20 USD) med larm vid 50/80/100 %. CloudWatch-larm på CloudFront `Requests` och `BytesDownloaded` över ett tröskelvärde (CloudFront-mätvärden finns i `us-east-1`).
- Staging: separat state och prefix (`beta.mandatorn.se` med egen distribution) i samma konto, eller ett separat konto. Se D2.

## 5. Lagringsadaptern

`mandatorn_model/storage.py`:

```python
class Storage(Protocol):
    def put_immutable(self, key: str, data: bytes, content_type: str) -> None: ...   # no-op om objektet finns
    def put_pointer(self, key: str, data: bytes, content_type: str) -> None: ...     # kort cache
    def list_releases(self) -> list[str]: ...
    def invalidate(self, paths: list[str]) -> None: ...                              # CloudFront eller no-op
```

Implementationer:
- `LocalStorage(dir)` för `dist-data/` och tester.
- `S3Storage(endpoint, bucket, cdn)` med boto3. Det är den enda platsen med AWS-anrop.

Bunny, Hetzner och R2 är S3-kompatibla och behöver bara en annan endpoint och en annan `invalidate`.

## 6. Frontend (`web/`)

- Astro med statisk förrendering. Vid bygget läser Astro den senaste releasen från `dist-data/` lokalt, eller från CDN:et i CI, och förrenderar ingress och det som syns ovanför vecket.
- Klienten hämtar `manifest.json` vid laddning. Om release-id skiljer sig från det sidan byggdes med hämtas berörda filer, verifieras och uppdateras på plats.
- Verifiering: `crypto.subtle.digest('SHA-256')` och storleken kontrolleras mot manifestet. Okänd `schemaVersion` eller fel hash ger en felruta i stället för siffror.
- React-öar:
  - trenddiagram (en lättviktig lib, se D13)
  - MapLibre-karta (`client:visible`, lazy)
  - koalitionsbyggare (läser `draws.parquet` via `hyparquet` eller liknande, < 30 kB)
  - scenariokontroller (TS-porten av `seats.py`)
- TS-port av mandatmotorn: `web/src/lib/seats.ts`, med golden tests mot Python via gemensamma JSON-fall i `tests/golden/`.
- Designtokens i `web/src/styles/tokens.css`. Partifärgerna genereras ur `constants.py`, så att de är samma i Python och TS.
- Statiska sidor och entitetssidor enligt uppdraget. `sitemap.xml` och JSON-LD genereras vid bygget. OG-bilder genereras vid bygget med satori/resvg (statiska PNG:er per entitet).
- Webbstatistik: Plausible, eller självhostad Umami (D14). Inga cookies.

## 7. CI/CD (GitHub Actions)

| Workflow | Utlösare | Steg |
|---|---|---|
| `ci.yml` | push, PR | ruff, mypy, pytest (inkl. paritet och golden), tsc, vitest (golden och mallmotor), prestandabudget (storlek på HTML och JS) |
| `publish.yml` | merge till `data/polls/**`, `schedule: '17 5 * * *'` (udda minut), `workflow_dispatch` | kvalitetsgrind → publish → upload → astro build → upload site → invalidera HTML och manifest. Flaggad körning: inget publiceras, ett issue skapas. |
| `sync-polls.yml` | `schedule: '43 */3 * * *'` | diff mot SwedishPolls → PR |
| `heartbeat.yml` | `schedule: '07 8 * * *'` | kontrollerar att senaste `manifest.generatedAt` är < 30 h gammal och att `publish.yml` har kört. Larmar via issue och e-post. |
| `preview.yml` | PR | bygger mot staging-prefixet `previews/pr-<n>/` |

Varning: GitHub stänger av schemalagda workflows efter 60 dagar utan aktivitet i ett publikt repo. Heartbeat-jobbet ligger själv i ett schema och påverkas av samma regel. Larmet ska därför också gå via en extern tjänst som pingas av publish-jobbet (Healthchecks.io eller liknande, D15), så att utebliven ping larmar.

## 8. Nowcast (fas 3, i korthet)

- En liten tjänst på Fly.io (`arn`) i en loop: `val_feed.fetch_index` → ny md5? → `compute_nowcast` → publish med `mode: nowcast` direkt till det publika manifestet. Ingen fördröjning (DECISIONS D4).
- Simulator: `fetch_valnatt_2026.py` har redan rapporteringsordning och 2022-baslinje för 2026. Den återanvänds som integrationstest. 2022 och EU-valet 2024 kräver ny data.

## 9. Kostnadsuppskattning

Uppskattningen bygger på AWS publika priser enligt min kunskap och måste verifieras i AWS Pricing Calculator innan budgeten sätts. CloudFronts gratisnivå (1 TB och 10 miljoner förfrågningar per månad) antas gälla.

| Scenario | Antagande | Kostnad per månad |
|---|---|---|
| Normal månad | 50 000 sidvisningar × ~400 kB inklusive data, ~30 förfrågningar per visning | ~20 GB, 1,5 miljoner förfrågningar. Inom gratisnivån. S3 under 1 USD, Route 53 0,5 USD om det används. **≈ 1–2 USD** |
| Valnatt | 500 000 besökare som pollar manifestet var 30:e sekund i 4 timmar = 240 anrop var, plus ~1 MB data var | 120 miljoner förfrågningar ≈ 110 miljoner över gratisnivån × ~0,012 USD/10 000 ≈ **130 USD**. ~1,5 TB ≈ 0,5 TB × ~0,085 USD/GB ≈ **45 USD**. **≈ 175 USD för natten** |
| Valnatt med polling var 60:e sekund | samma | **≈ 110 USD** |
| Fly.io-ingest | shared-cpu-1x, 256 MB, på under valperioden | **≈ 2–5 USD** |

Den största kostnaden på valnatten är antalet förfrågningar mot manifestet, inte datamängden. Två åtgärder sänker den: polla var 60:e sekund, och låt manifestet cachas `s-maxage=5`. Det minskar inte antalet förfrågningar mot kanten men skyddar S3. Klienten ska dessutom sluta polla när fliken är dold (`document.visibilityState`).

## 10. Datakällor och licenser

Inventerat 2026-10-01. Ingen källa har ett dela lika-krav på själva siffrorna. Ingen förbjuder vidarepublicering. Flaggorna gäller kartdata, instituten och persondata (se DECISIONS D7–D9).

| Källa | Används till | Licens/villkor | Krock med CC BY-NC 4.0? |
|---|---|---|---|
| MansMeg/SwedishPolls `Polls.csv` | alla opinionsmätningar | Data **CC0**, kod MIT. Står bara i README; repot har ingen LICENSE-fil. | Nej |
| Valmyndigheten, resultatfiler (resultat.val.se) | baslinje 2026, KF/RF, valnatt | Fri användning, **källan ska anges** ("Ange Valmyndigheten som källa") | Nej. Källan måste anges i varje CSV-huvud och på `/data`. |
| Valmyndigheten, `kandidaturer.csv` (data.val.se) | kandidatprognos | Fri användning med angiven källa, men får inte röja enskilda i strid med GDPR | Licensen nej. **Persondata, se D8.** |
| okfse/sweden-geojson | kommun- och regionnamn (karta ej renderad) | Ingen licensfil, "Feel free to reuse". Kommunfilen bygger på Valmyndighetens/Opendatasofts data. Regionfilen bygger på ett repo som delvis använder **OSM (ODbL, dela lika)**. | **Oklart / möjligen dela lika.** Se D9 (byt till Lantmäteriet CC0). |
| Opinionsinstituten (Novus, Verian, Demoskop, Ipsos, Indikator, Sentio, Infostat) | ursprunget till mätningarna | Novus: upphovsrätt på rapporterna och önskemål om att granska text före publicering. Övriga: villkor ej hittade. | **Flagga, se D7** |
| SCB PX-Web | inte längre (bortbyggt i `922dd3e`) | — | — |
| Lantmäteriet öppna data | förslag för kartor | CC0 | Nej |

Källor:
- github.com/MansMeg/SwedishPolls
- val.se, pressrum: "resultatfiler från rösträkningen"
- val.se, "Om vår öppna data"
- github.com/okfse/sweden-geojson
- github.com/jnordgren/swedish_data_map_geojson
- novus.se, allmänna villkor
- lantmateriet.se, öppna data

## 11. Beräkningstid i dag

Mätt 2026-10-01 lokalt (Windows arm64), utan Streamlit-cache:

| Steg | Tid |
|---|---|
| import och inläsning av JSON-filerna | 1,8 s |
| `load_polls` (nätverk) | 0,1 s |
| Kalman (estimat + båda tidsseriesegmenten) | < 0,1 s |
| **`run_simulation` (10 000 dragningar, Python-loop)** | **2,3 s** |
| backtest 2026 + 2022 | 0,55 s |
| **`load_candidates` (nätverk)** | **4,0 s** |
| kandidatprognos (fasta + utjämning) | 0,6 s |
| mandatmarginaler (nationellt + 29 valkretsar + jämnaste) | 0,4 s |
| regionalt (RD/KF/RF + 310 områdesmandat) | 0,1 s |
| valnattens felkurva (45 tidpunkter) | 0,25 s |
| **En full körning, totalt** | **≈ 10 s** |

Med per-valkrets-simuleringen (D11, `allocate_all_mandates` × 10 000) tillkommer ~10 s, eller < 1 s om den vektoriseras. En release beräknas alltså på under en minut i CI. Tunga beräkningar är inget hinder för att förberäkna allt.
