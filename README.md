# Riksdagsprediction

En interaktiv opinionsaggregator och mandatprognos för riksdagsvalet 2026, byggd med Python och Streamlit.

🔗 **[Öppna appen](https://riksdagsprediction.streamlit.app)** *(uppdatera länken när du deployar)*

---

## Vad appen gör

- Hämtar och aggregerar alla tillgängliga svenska riksdagsopinionsmätningar från [MansMeg/SwedishPolls](https://github.com/MansMeg/SwedishPolls)
- Beräknar viktat medelvärde med tidsviktning (30 dagars halveringstid) och institutsviktning baserad på träffsäkerhet 2022
- Prognosticerar mandatfördelning per valkrets med modifierad Sainte-Laguë (första divisor 1,2)
- Kör 10 000 Monte Carlo-simuleringar med sannolikheter för olika utfall och koalitioner
- Visar regional och kommunal prognos via uniform swing-modell med data från SCB PX-Web

## Flikar

| Flik | Innehåll |
|---|---|
| 📊 Opinion | Trendgraf, partistöd, mandatprognos, partistöd per valkrets |
| 🏛️ Mandat | Detaljerad mandatanalys med konfidensintervall och hemicykelvy |
| 🗺️ Valkretsar | Mandattabeller och partidetaljer per valkrets |
| 🎲 Simulering | Sannolikheter för utfall, Monte Carlo, koalitionsanalys |
| 👤 Kandidater | Förväntade invalda baserat på Valmyndighetens kandidatlistor |
| 📍 Regional & kommunal | Kommunal- och regionvalsprognos via SCB-data |
| 📋 Data | Rådata för undersökningar och institutsvikter |
| ℹ️ Metod | Fullständig metodbeskrivning och backtesting |

## Datakällor

- **Opinionsundersökningar:** [MansMeg/SwedishPolls](https://github.com/MansMeg/SwedishPolls)
- **Valresultat per valkrets 2022:** [Valmyndigheten](https://www.val.se)
- **Kandidatdata 2026:** Valmyndigheten open data API
- **Kommunal- och regiondata:** SCB PX-Web API
- **GeoJSON-kartor:** [okfse/sweden-geojson](https://github.com/okfse/sweden-geojson)

## Köra lokalt

```bash
# Klona repot
git clone https://github.com/DITT-ANVÄNDARNAMN/riksdagsprediction.git
cd riksdagsprediction

# Installera beroenden
pip install -r requirements.txt

# Starta appen
streamlit run app.py
```

## Deploya på Streamlit Community Cloud

1. Pusha koden till ett GitHub-repo
2. Gå till [share.streamlit.io](https://share.streamlit.io) och logga in med GitHub
3. Välj ditt repo, branch (`main`) och fil (`app.py`)
4. Klicka **Deploy** — appen är live inom några minuter

## Disclaimer

Detta är en oberoende statistisk modell baserad på publicerade opinionsmätningar.
Den utgör inte ett officiellt valresultat eller en politisk rekommendation.
Alla prognoser är förenade med osäkerhet.

## Licens

MIT
