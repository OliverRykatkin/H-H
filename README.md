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

MIT
