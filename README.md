# Mandatorn

En interaktiv opinionsaggregator och mandatprognos för riksdagsvalet 2026, byggd med Python och Streamlit.

🔗 **[Öppna appen — mandatorn.se](https://mandatorn.se)**

---

## Vad appen gör

- Hämtar och aggregerar alla tillgängliga svenska riksdagsopinionsmätningar från [MansMeg/SwedishPolls](https://github.com/MansMeg/SwedishPolls)
- Beräknar viktat medelvärde med tidsviktning (30 dagars halveringstid) och institutsviktning baserad på träffsäkerhet 2026
- Prognosticerar mandatfördelning per valkrets med modifierad Sainte-Laguë (första divisor 1,2)
- Kör 10 000 Monte Carlo-simuleringar med sannolikheter för olika utfall och koalitioner
- Visar regional och kommunal prognos via uniform swing-modell på Valmyndighetens resultat 2026
- **Nowcasting på valnatten** (delta-baserad realtidsmetod) — projiceras till full riksdagsmandat-fördelning och förväntade invalda ledamöter

## Flikar

| Flik | Innehåll |
|---|---|
| 📊 Opinion | Trendgraf per parti + blocktidslinje, partistöd, mandatprognos, stöd per valkrets |
| 🏛️ Mandat | Detaljerad mandatanalys med konfidensintervall och hemicykelvy |
| 🗺️ Valkretsar | Mandattabeller och partidetaljer per valkrets |
| 🎲 Simulering | Sannolikheter för utfall, Monte Carlo, koalitionsanalys |
| 👤 Kandidater | Förväntade invalda baserat på Valmyndighetens kandidatlistor |
| 📍 Regional & kommunal | Kommunal- och regionvalsprognos utifrån valresultatet 2026 |
| 📋 Data | Rådata för undersökningar och institutsvikter |
| ℹ️ Metod | Fullständig metodbeskrivning och backtesting |
| 🌙 Valnatt | Uppspelning av valnatten 2026 i verklig räkningsordning — nowcast mot råräkning, mandat och invalda |

## Datakällor

- **Opinionsundersökningar:** [MansMeg/SwedishPolls](https://github.com/MansMeg/SwedishPolls)
- **Valresultat 2026 (riksdag, kommun, region):** [Valmyndigheten](https://www.val.se) (pre-cachat i `data/`)
- **Kandidatdata 2026:** Valmyndigheten open data API
- **GeoJSON-kartor:** [okfse/sweden-geojson](https://github.com/okfse/sweden-geojson)

## Köra lokalt

```bash
# Klona repot
git clone https://github.com/OliverRykatkin/H-H.git Riksdagsprediction
cd Riksdagsprediction

# Installera beroenden
pip install -r requirements.txt

# Starta appen
streamlit run app.py
```

## Publiceringspipelinen (statisk sajt + öppen data)

Modellen ligger i `mandatorn_model/` och körs utan Streamlit. Varje körning ger en
oföränderlig, kontrollsummerad release; se `docs/ARCHITECTURE.md`.

```bash
pip install -r requirements-dev.txt
pytest                                                # modell, vallag-golden tests, publicering
python -m mandatorn_model.publish --out dist-data     # kör modellen → lokal release
python -m mandatorn_model.publish --out dist-data --reference-date 2026-10-01   # återskapa en dag
```

Samma indata (`data/polls/Polls.csv` + baslinjefilerna), referensdatum och seed ger
samma release-id (verifierat mellan Linux x86 och Windows arm64).

### Lägga in en mätning
1. Mätningarna läses från `data/polls/Polls.csv` (SwedishPolls-format). Jobbet
   *Synka mätningar från SwedishPolls* öppnar en PR automatiskt var tredje timme vid
   förändring. Mätningar som saknas där läggs till som en rad i filen i en egen PR.
2. När PR:en slås ihop till `main` körs *Publicera*: först kvalitetsgrinden, sedan
   modellen, och sist publiceringen.
3. **Flaggad körning:** om grinden hittar något (orimlig summa, fältperiod i framtiden,
   stort hopp mot institutets förra mätning, dubblett) publiceras inget och ett issue
   öppnas. Godkänn genom att lägga till flaggornas id i `data/polls/quality_ack.txt`,
   eller kör *Publicera* manuellt med `force`.

### Rätta en release
Releaser raderas aldrig. Rätta indata, kör *Publicera* manuellt (`workflow_dispatch`)
med `supersedes = <gammalt release-id>` och logga rättelsen i `CHANGELOG-data.md`.
Lokalt: `python -m mandatorn_model.publish --out <mål> --supersedes <id>`.
Den gamla releasens manifest får då `supersededBy` satt, och klienten visar en markering.

### Rulla tillbaka
`python -m mandatorn_model.publish --out s3://<data-bucket> --distribution-id <id> --rollback <release-id>`
pekar om `manifest.json` (och `latest/`) till en tidigare release. Inget raderas.

### Sajten (`web/`)
```bash
python -m mandatorn_model.publish --out dist-data   # en release att rendera mot
cd web && npm ci
npm run dev        # http://localhost:4321 — releasen serveras under /_data
npx vitest run     # golden tests (mandat Python↔TS), mallmotorn, öar
npm run build      # 725 sidor + sitemap, OG-bilder och prestandabudget (dist/)
```
I produktion pekar `PUBLIC_DATA_URL` på `https://data.mandatorn.se`. Klienten verifierar varje fil mot manifestet och uppdaterar ingress och nyckeltal när en nyare release finns.

### Infrastruktur
AWS (S3 + CloudFront i `eu-north-1`) beskrivs som kod i `infra/`; se `infra/README.md`.

## Deploya på Google Cloud Run

```powershell
gcloud run deploy mandatorn --source . --region europe-north1 \
  --allow-unauthenticated --memory 1Gi --cpu 1 \
  --min-instances 1 --max-instances 3 --port 8080 --timeout 3600
```

Custom domain `mandatorn.se` är mappad via `gcloud beta run domain-mappings`. Se `CLAUDE.md` för utförlig deploy-dokumentation.

## Disclaimer

Detta är en oberoende statistisk modell baserad på publicerade opinionsmätningar.
Den utgör inte ett officiellt valresultat eller en politisk rekommendation.
Alla prognoser är förenade med osäkerhet.

## Licens

Kod: MIT (se `LICENSE`). Publicerad data: CC BY-NC 4.0; kommersiell licens tecknas separat.
