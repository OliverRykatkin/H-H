# RUNBOOK: valnatten

Live-nowcasten körs som Fly-appen `mandatorn-nowcast` (region `arn`). Den hämtar Valmyndighetens preliminära räkning varje minut och publicerar releaser med `mode: "nowcast"` direkt till alla, utan fördröjning (D4). Sajten pollar manifestet och uppdateras utan omladdning. Uppsättningen beskrivs i `deploy/nowcast/README.md`.

## Veckan före

- [ ] **Kör simulatorn mot staging.** Kör workflowen *Valnatt-simulator* manuellt, eller lokalt:
  ```bash
  python -m mandatorn_model.publish --out s3://mandatorn-staging-data --force
  python -m mandatorn_model.nowcast_live --out s3://mandatorn-staging-data --replay 2026 --step-minutes 20 --interval 5
  ```
  Kontrollera att `beta.mandatorn.se/valnatt/` visar live-läget och växlar tillbaka.
- [ ] **Kontrollera baslinjen.** Filen `data/baseline_districts_<förra valet>.csv.gz` ska finnas och ha alla ordinarie distrikt (`python fetch_valnatt.py --baseline <år>`).
- [ ] **Kontrollera flödet.** Valmyndighetens tekniska beskrivning för året ska vara läst, och `index.md5` för `val<år>` ska svara.
- [ ] **Kontrollera kapaciteten.** Se kostnadskalkylen för valnatten i `docs/ARCHITECTURE.md` §9. Höj budgetlarmet tillfälligt (`monthly_budget_usd`) och tröskeln för CloudFront-larmet (`cloudfront_requests_alarm_per_5min`).
- [ ] **Kontrollera hemligheterna.** `fly secrets list -a mandatorn-nowcast` ska visa `OUT`, `AWS_ROLE_ARN` och `DATA_DISTRIBUTION_ID`.

## Dagen före

- [ ] **Färsk prognosrelease.** Kör *Publicera* (manuellt) så att den senaste prognosen ligger som grund för nowcast-releaserna.
- [ ] **Deploya.**
  ```bash
  fly deploy --config deploy/nowcast/fly.toml --dockerfile deploy/nowcast/Dockerfile .
  fly scale count 0 -a mandatorn-nowcast
  ```
- [ ] **Testa skrivrättigheterna.** Kör en simulator mot produktionsbucketen under ett prefix som inte används, eller en körning med `--replay` mot staging från Fly-maskinen (`fly ssh console`).

## Valkvällen

1. **Klockan 19.55: starta.**
   ```bash
   fly scale count 1 -a mandatorn-nowcast
   fly logs -a mandatorn-nowcast
   ```
   Innan de första distrikten rapporterats publiceras inget. Loggen och `status.json` visar `feedOk: true`.
2. **Övervaka:**
   - **Loggen:** en rad per ny release ("N/M distrikt, X % av rösterna → release …").
   - **`https://data.mandatorn.se/status.json`:** `mode: nowcast`, `feedOk`, `feedCheckedAt`, `feedUpdatedAt`.
   - **`https://mandatorn.se/status/`:** senaste release och körning.
   - **CloudFront-larmet.**
3. **Om Valmyndigheten inte svarar** (`feedOk: false`, `feedError` i status): ligger den senaste giltiga releasen kvar, och appen försöker igen varje minut. Gör inget annat än att bevaka. Kommer den inte tillbaka på mer än 10 minuter, kontrollera Valmyndighetens driftinformation.
4. **Stoppa eller återuppta:** `fly scale count 0` respektive `fly scale count 1`. Appen fortsätter från det senaste läget, eftersom ett oförändrat läge ger samma release.
5. **Fel siffror publicerade?** Rulla tillbaka till en tidigare release (inget raderas) och stoppa appen:
   ```bash
   fly scale count 0 -a mandatorn-nowcast
   python -m mandatorn_model.publish --out s3://mandatorn-prod-data --distribution-id <id> --rollback <release-id>
   ```
   Release-id:n listas i `https://data.mandatorn.se/releases/index.json`.

## Efter natten

- [ ] **Stoppa appen** när räkningen är klar: `fly scale count 0 -a mandatorn-nowcast`.
- [ ] **Sista nowcast-releasen** ligger kvar som aktuell tills det slutliga resultatet finns.
- [ ] **När det slutliga resultatet finns:**
  1. Kör `python fetch_election_<år>.py`, `python fetch_muni_cache.py <år>`, `python fetch_elected_<år>.py` och `python fetch_valnatt.py <år>`.
  2. Byt baslinje (som efter 2026).
  3. Publicera med `mode = "final"` i `publish.toml`, därefter tillbaka till `forecast`.
- [ ] **Arkivera:** `python tools/build_archive.py <år>`. Lägg till rättelser i `CHANGELOG-data.md`.
- [ ] Återställ budgetlarm och trafiklarm.
