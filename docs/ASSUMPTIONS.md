# ASSUMPTIONS.md: antaganden under inventeringen

Antaganden som gjorts i stället för att gissa i koden. Säg till om något är fel.

| # | Antagande | Varför det spelar roll |
|---|---|---|
| A-1 | "Lokala prognoser baserade på historiska avvikelser från rikssnittet" i uppdraget motsvarar dagens additiva modell: valkretsens avvikelse från rikssnittet 2026 plus nationellt estimat (uniform swing). Det gäller både `estimate_constituency_votes` och `apply_uniform_swing`. | Ingen ny lokal modell byggs |
| A-2 | Uppdragets "12 % i valkrets" och personvalsspärren avser riksdagsvalet. För KF och RF används feedens `valomradessparrProcent` (2 respektive 3 %) som i dag. | Golden tests för kommun och region |
| A-3 | Paritet avser samma `reference_date` och seed. Streamlit läser `datetime.now()`, så verifieringen kör båda versionerna med ett fast datum. | Ett jämförelseskript i fas 1 |
| A-4 | `institutsbias.csv` mäter avvikelsen mot **Kalman-aggregatet samma dag** (exklusive mätningen själv) under innevarande mandatperiod, och mot valresultatet för mätningar de sista 30 dagarna före ett val. Uppdraget anger inte referensen. | Definitionen påverkar siffrorna kraftigt |
| A-5 | `latest/timeseries.csv` med p5/p50/p95 tar p50 från Kalman-medelvärdet och p5/p95 som ±1,645·σ ur RTS-variansen, inte ur Monte Carlo. Trendserien har ingen simulering i dag. | Intervallens innebörd ska stå i `.schema.json` |
| A-6 | Simulatorn för valnatten 2022 kräver den gamla XLSX-baserade 2018-baslinjen (`data_loader`). Det finns ingen data för EU-valet 2024 i repot. Simulatorn för 2026 finns (`data/valnatt_2026.csv.gz`). | Omfattningen av fas 3 |
| A-7 | Den regions-GeoJSON som `load_geojson()` hämtar i `main()` används inte i någon synlig vy och kan tas bort i den nya sajten. | Prestanda |
| A-8 | Streamlit ska fortsätta deployas till Cloud Run under fas 1–2. Paketutbrytningen deployas till Cloud Run som vanligt efter varje steg (enligt den stående instruktionen att deploya efter testade ändringar). | Parallell drift |
| A-9 | Kostnadsuppskattningen i `ARCHITECTURE.md` bygger på AWS listpriser enligt min kunskap och är inte kontrollerad mot dagens prislista. | Budgetlarmets nivå |
| A-10 | "Inget parti avviker mer än X pp från samma instituts förra mätning" i kvalitetsgrinden: X sätts preliminärt till 4 pp för parti över 10 % och 2,5 pp för övriga, och summan av andelarna till [97, 101] %. | Konfigurerbart. Kalibreras mot historiken i fas 1. |
| A-11 | **Referensdatumet avrundas till dygnets början** (`forecast.reference_day`). Tidigare läste modellen klockslaget, så prognosen skiftade under dygnet. Antalet dagar kvar till valet (horisonten i simuleringen) och simuleringens 365-dagarsfönster räknades från klockslaget, så mandatintervallen kunde ändras vid lunch. Nu är prognosen konstant inom ett dygn. Den är identisk med den tidigare koden vid midnatt (paritetstest 254/254). | Reproducerbara releaser (samma indata + datum + seed ger samma id). Bättre Streamlit-cache. |
