# DECISIONS.md: beslut som återstår

Varje punkt har ett förslag. Markera **Beslut:** när du har bestämt dig. Punkterna D1–D5 efterfrågas i uppdraget. D6–D20 kom fram under inventeringen.

---

## Efterfrågade i uppdraget

### D1. Kodlicens
**Förslag: MIT.** Kort, välkänd och kompatibel med att datan ligger under CC BY-NC 4.0, eftersom kod och data licensieras separat. Alternativet är Apache-2.0 om du vill ha ett uttryckligt patentskydd. AGPL-3.0 stoppar att någon kör en egen kommersiell kopia som tjänst, men skrämmer bort bidrag och medier som vill bygga in komponenter.
Repot `OliverRykatkin/H-H` är redan publikt men **saknar licensfil**. I dag betyder det "alla rättigheter förbehållna".
**Beslut:** ☐

### D2. Domänstruktur
**Förslag:**
- `mandatorn.se`: sajten.
- `data.mandatorn.se`: releaser, manifest och `latest/`.
- `beta.mandatorn.se`: staging tills pariteten är godkänd.
- `lab.mandatorn.se`: Streamlit-labbet på Cloud Run, gärna bakom inloggning eller utan indexering.

DNS ligger i dag hos One.com. Antingen behålls One.com med CNAME/ALIAS mot CloudFront, eller så flyttas zonen till Route 53 (0,5 USD/månad, smidigare med Terraform). Apex-domänen `mandatorn.se` mot CloudFront kräver ALIAS/ANAME, som One.com troligen inte stöder. **Route 53 rekommenderas.**
Staging: samma AWS-konto, separata buckets och prefix (enklast), eller ett separat konto (renare isolering).
**Beslut:** ☐

### D3. Verbal sannolikhetsskala
I dag (Simulering-fliken, rad ~4190): ≥95 / ≥70 / ≥30 / ≥5 %. Visas som ">95 %" och "<5 %".
Uppdragets förslag: <10 "Väldigt osannolikt", 10–40 "Osannolikt", 40–60 "Jämnt", 60–90 "Troligt", >90 "Väldigt troligt". Visas som "<1 %" och ">99 %".
**Förslag:** uppdragets skala, men med gränserna 0,10 / 0,35 / 0,65 / 0,90, så att "Jämnt" blir ett bredare och ärligare mittband. Gränsfall avrundas mot "Jämnt". Med 10 000 dragningar är upplösningen 0,01 %, så "<1 %" och ">99 %" fungerar.
**Beslut:** ☐

### D4. Fördröjning för publik nowcast
**Förslag:** 10 minuter för partnern under valnatten, som i uppdraget. Gäller från 20:00 till dess att 95 % av distrikten är räknade, sedan 0. Inställningen ligger i konfigurationen och kan sättas till 0 utan omdeploy.
**Beslut:** ☐

### D5. Hur länge dragningar sparas
**Förslag:**
- senaste releasen: alltid
- en release per dygn: 400 dagar
- valdagens release, och kvällen före: för alltid
- övriga: 7 dagar

Med ~300 kB per dragningsfil blir det under 150 MB per år.
**Beslut:** ☐

---

## Nya beslut från inventeringen

### D6. Mandatreglerna: paritet med Streamlit eller med vallagen?
Uppdraget kräver noll avvikelse mot Streamlit, och att TS-porten ska följa vallagen. Den nuvarande koden avviker från vallagen på flera punkter (PARITY A1–A4, A10):
- 12 %-regeln saknas
- nationell divisor 1,2 i stället för 1,0
- utjämningsprocedur och placering per valkrets
- spärrbas bland 8 partier i stället för alla giltiga röster
- lika värden avgörs deterministiskt i stället för med lottning

Det går inte att uppfylla båda kraven. **Förslag:**
1. Fas 1 bryter ut koden med de nuvarande reglerna och visar noll avvikelse mot Streamlit.
2. En separat PR, `seats-vallag`, rättar reglerna, både i Python och i Streamlit-labbet. Det rör inte prognosmetoden, bara hur mandaten räknas. Den verifieras mot de officiella utfallen 2018, 2022 och 2026.
3. TS-porten byggs mot den rättade versionen.

Rättelsen är en ändring av modellen i snäv mening, så den kräver ditt uttryckliga godkännande.
**Beslut:** ☐

### D7. Opinionsinstitutens villkor
SwedishPolls är CC0. **Novus allmänna villkor** säger däremot att de "ber att få se text som publiceras" och förbehåller sig rätten att rätta. Det går inte att uppfylla för automatiska ingresser och `/institut/novus`. Villkoren för övriga institut (Verian, Demoskop, Ipsos, Indikator, Sentio, Infostat) har inte hittats.
**Förslag:** publicera partisiffror och aggregat som fakta med källa, men skriv till Novus innan `/institut/<slug>` och `institutsbias.csv` lanseras. Ett skriftligt OK i inkorgen räcker. Märk mätningsdata som "källa: respektive institut via SwedishPolls (CC0)".
**Beslut:** ☐

### D8. Kandidatdata och GDPR
`latest/kandidater.csv` och `/kandidat/<slug>` innehåller namn, ålder, kön och hemkommun. Det är personuppgifter, även om de är allmänna handlingar. Valmyndighetens villkor förbjuder att data används så att enskilda personer röjs i strid med GDPR.
**Förslag:**
- Publicera namn, parti, valkrets, listplats och sannolikhet.
- **Inte** ålder eller hemkommun i öppna CSV-filer.
- Skriv en kort intresseavvägning (berättigat intresse: samhällsinformation om val) på `/integritet`.
- Ge en kontaktadress för begäran om rättelse.
**Beslut:** ☐

### D9. Kartdata
okfse/sweden-geojson har ingen licensfil ("Feel free to reuse"). Regionfilen bygger på ett repo som delvis använder OpenStreetMap (**ODbL, dela lika**), vilket kan krocka med CC BY-NC.
**Förslag:** byt till Lantmäteriets öppna gränsdata (CC0), förenklade till kommun-, region- och valkretsgränser och publicerade som egna vektorfiler (PMTiles eller GeoJSON) i releasen. Då är kartan inte längre beroende av GitHub.
**Beslut:** ☐

### D10. Kandidatlistor efter valet 2026
Prognosen gäller valet 2030, men det finns inga kandidatlistor för 2030 förrän 2030. **Förslag:** fram till dess visar kandidatsidorna **de som valdes 2026** (från Valmyndighetens `valda`, utfall) med en tydlig markering. `kandidater.csv` med sannolikheter aktiveras när listorna för 2030 publiceras. Alternativet är att använda listorna från 2026 som en approximation, vilket är missvisande.
**Beslut:** ☐

### D11. Nya beräkningar mot "modellen ska inte ändras"
Uppdraget förutsätter utdata som modellen inte producerar i dag (PARITY N1–N7):
- mandatfördelning per valkrets i simuleringen
- sannolikhet att bli invald
- institutsbias
- intervall för kommuner och regioner
- rekordval

Inget av det ändrar metoden (samma dragningar och samma mandatmotor), men det är ny kod. **Förslag:** godkänn N1–N5 och N7 som tillägg i fas 1 och 2. De bygger alla på att `allocate_all_mandates` körs per dragning, vilket tar ~10 s per release. N6 (historiska valresultat sedan 1970) läggs i fas 2.
**Beslut:** ☐

### D12. Arkiv för 2026
Inga releaser sparades före valet 2026. **Förslag:** räkna om historiken för `/arkiv/2026` med dagens kod och `reference_date` per dag. Märk den "rekonstruerad med modellversion X". Den visar då inte exakt vad sajten visade då. Alternativet är att börja arkivet med 2030.
**Beslut:** ☐

### D13. Diagrambibliotek i frontend
Plotly (~1 MB) spräcker JS-budgeten på 200 kB. **Förslag:** Observable Plot (~60 kB gz) eller egen SVG via d3-scale/d3-shape (~20 kB) för trend och intervall. uPlot för långa tidsserier om det behövs.
**Beslut:** ☐

### D14. Webbstatistik
**Förslag:** Plausible Cloud (EU-hostat, ~9 EUR/månad). Alternativet är självhostad Umami. Plausible kräver ingen drift.
**Beslut:** ☐

### D15. Övervakning utanför GitHub
Heartbeat-jobbet är självt ett schemalagt workflow och stängs av efter 60 dagar utan aktivitet. **Förslag:** publish-jobbet pingar Healthchecks.io (gratisnivån) efter varje lyckad körning. Utebliven ping i 30 timmar ger e-post.
**Beslut:** ☐

### D16. Var mätningarna kommer ifrån
Uppdraget säger att mätningar läggs in som PR mot `data/polls/`. I dag läses allt live från SwedishPolls. **Förslag:** SwedishPolls är primär källa via ett synk-jobb som öppnar en PR med diffen. Manuella PR:er för mätningar som SwedishPolls inte har (eller har sent). `data/polls/` innehåller en committad kopia, och det är den som är indata till modellen.
**Beslut:** ☐

### D17. Svingformeln för valkretsar (PARITY A7)
Valkretsvyerna använder rå sving, Regional-fliken nollsummerad. **Förslag:** behåll båda i fas 1 för paritet, och samordna till den nollsummerade i samma PR som D6.
**Beslut:** ☐

### D18. Metodtexter och inaktuella etiketter (PARITY A6)
**Förslag:** rätta dem i Streamlit nu, i en liten egen PR. Det gäller σ_proc 0,07 → 0,10, "mot 2022" → 2026, valkretsflikens "2022 (faktiskt)" och kandidattextens algoritmbeskrivning. Den nya sajtens `/om` skrivs om från grunden.
Sidhuvudets caption "*Nils Silverström — ett svenskt försök till FiveThirtyEight*": är det avsiktligt?
**Beslut:** ☐

### D19. Läckage i backtesten (PARITY A8)
**Förslag:** kalibrera institutsvikterna för backtest år X mot val X−4, så att 2026 testas med vikter från 2022 och 2022 med vikter från 2018. Det ändrar de backtest-siffror som visas, men inte prognosen.
**Beslut:** ☐

### D20. Cloud Run efter lanseringen
Streamlit körs med `--min-instances 1`, vilket kostar ungefär 15–25 USD i månaden även utan trafik. **Förslag:** när den statiska sajten är live, sätt `min-instances 0` och flytta labbet till `lab.mandatorn.se`.
**Beslut:** ☐
