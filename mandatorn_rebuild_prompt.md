# Uppdrag: Bygg om mandatorn.se från Streamlit till statisk webbapp med versionerad, öppen datapublicering

## Bakgrund

Mandatorn (mandatorn.se) är en svensk valprognos som idag körs som en Streamlit-app. Den aggregerar publicerade opinionsmätningar med ett Kalmanfilter och räknar ned till:

- nationellt partistöd över tid med osäkerhet
- lokala prognoser för varje kommun och region, baserade på historiska avvikelser från rikssnittet
- mandatfördelning per valkrets, inklusive utjämningsmandat och spärrar
- vilka namngivna kandidater som väntas bli invalda
- mandatmarginaler: hur långt varje parti är från att vinna eller tappa ett (fast) mandat, nationellt och per valkrets
- nowcast på valnatten utifrån Valmyndighetens preliminära rösträkning
- metodbeskrivning

Målet är samma funktionalitet som idag, i en arkitektur som tål trafiktoppar, är billig att drifta, ger delbara och indexerbara sidor och publicerar öppen data.

Vi har två förebilder:

- **valprognos.se** för datalagret: statiska filer, read-only-data i oföränderliga, kontrollsummerade JSON-releaser med ett pekarmanifest, inget API eller databas i produktion.
- **bottenada.se** för innehållet: indexerbara sidor per parti och institut, datadrivna ingresser, sannolikhetsfrågor i klarspråk, trendtabeller, arkiv per val och en sida med öppen data på stabila adresser.

**Modellen ska inte ändras.** Python-koden för Kalmanfilter, lokal nedbrytning, mandatberäkning, kandidatprognos och nowcast behålls. Det vi bygger om är hur resultaten publiceras och presenteras.

## Fastställda beslut (ska inte utvärderas om)

| Område | Beslut |
|---|---|
| Hosting | AWS: S3 i `eu-north-1` (Stockholm) och CloudFront för både sajt och data. Ingen Cloudflare. |
| Infrastruktur | Allt som kod med Terraform. Budgetlarm från dag ett. |
| Autentisering CI→AWS | GitHub Actions OIDC. Inga långlivade nycklar i repot. |
| Lagringsabstraktion | Tunn adapter mot S3-kompatibelt API, så att vi kan byta leverantör (Bunny, Hetzner, R2) utan att röra pipeline eller frontend. |
| Frontend | Astro med statisk förrendering och React-öar för interaktiva komponenter. TypeScript. |
| Kartor | MapLibre GL, laddas lazy. |
| Repo | Publikt GitHub-repo. |
| Pipeline | GitHub Actions, triggas av händelser plus en daglig körning. |
| Publicering | Oföränderliga hashade releaser och ett manifest som pekare, plus stabila `latest`-alias för öppna CSV-filer. |
| Licens öppen data | CC BY-NC 4.0. Kommersiell licens för medier och företag tecknas separat. Ingen SA-klausul om inte källdata kräver det. |
| Kod | Öppen källkod. Föreslå licens i `DECISIONS.md`. |
| Nowcast | Partnern först, publiken efter en konfigurerbar fördröjning. Ingest på Fly.io i region `arn` (Stockholm). Byggs i fas 3. |
| Streamlit | Behålls som internt labb för prototyper. Den publika sajten ersätter den utåt. |
| Webbstatistik | Plausible eller motsvarande cookie-fritt verktyg. Ingen cookie-banner. |

## Arbetssätt

Arbeta i faser. Stanna och vänta på mitt godkännande efter fas 0 och fas 1. Gissa inte om något är oklart i den befintliga koden. Fråga, eller skriv ner antagandet i `docs/ASSUMPTIONS.md`.

Streamlit-appen ska fungera parallellt hela tiden.

---

## Fas 0: Inventering (ingen ny kod)

1. Läs igenom hela repot. Kartlägg varje Streamlit-sida, flik, widget, tabell, graf, karta, nedladdning och text.
2. För varje vy, dokumentera:
   - vilka indata den använder (filer, funktioner, cache)
   - vad som räknas fram i förväg och vad som räknas om interaktivt (sliders, val av område, koalitioner, scenarion, egna röstandelar)
   - vilka beräkningar som är tunga, t.ex. Monte Carlo-dragningar, och hur lång tid en full körning tar idag
3. Kartlägg alla datakällor (opinionsmätningar, valresultat, kandidatlistor, SCB-data osv.) och **deras licenser**. Om någon källa kräver "dela lika" eller förbjuder vidarepublicering påverkar det licensbeslutet. Flagga det direkt.
4. Leverera `docs/PARITY.md`: en tabell med varje funktion, nuvarande implementation, ny implementation (förberäknad JSON eller klientberäkning) och hur paritet ska verifieras.
5. Leverera `docs/ARCHITECTURE.md` som konkretiserar besluten ovan för just denna kodbas.
6. Leverera `docs/DECISIONS.md` med de beslut som återstår för mig, minst:
   - kodlicens
   - domänstruktur (t.ex. `mandatorn.se` för sajten, `data.mandatorn.se` för releaser)
   - gränserna för den verbala sannolikhetsskalan
   - fördröjningen för publik nowcast
   - hur länge dragningar ska sparas

**Stopp. Vänta på godkännande.**

---

## Målarkitektur

### 1. Modellpipeline (Python, befintlig kod)

- Bryt ut all beräkningslogik ur Streamlit-filerna till ett paket, t.ex. `mandatorn_model/`, utan beroende på `streamlit`. Streamlit-labbet importerar sedan samma paket.
- Exportkommando: `python -m mandatorn_model.publish` som kör modellen och skriver alla publika artefakter till `dist-data/`.
- Datakontrakt med Pydantic. Generera JSON Schema och TypeScript-typer från dem.
- Deterministiska körningar: fast seed per release. Seed, modellversion (git-commit) och indatans hash står i manifestet, så att vem som helst kan återskapa en release.

### 2. Datapublicering

**Releaser**
- Varje körning ger en release med innehållsbaserat id (SHA-256).
- Filerna delas upp efter användning: nationell översikt, en fil per valkrets, kommun och region, kandidatlistor, mandatmarginaler, tidsserier och sannolikhetsfrågor. Ingen vy ska behöva hämta all data.
- Datafiler publiceras under hashade sökvägar med `Cache-Control: public, max-age=31536000, immutable`. Oförändrade filer återanvänds mellan releaser.

**Manifest**
- `manifest.json` (under 100 kB) innehåller: `schemaVersion`, `release`, `generatedAt`, `modelVersion`, `seed`, `inputHash`, `mode` (`forecast` | `nowcast` | `final`), `pollsIncluded` (antal och senaste fältperiod), `supersededBy` (null eller release-id) samt en filindex med sökväg, storlek och SHA-256 per fil.
- Manifestet serveras med kort kant-cache (`s-maxage=5`) och `no-cache` i webbläsaren.
- Publiceringsordning: alla datafiler först, manifestet sist. Bytet är atomärt.
- Alla tidigare manifest sparas under `releases/<id>/manifest.json`, och en `releases/index.json` listar dem.

**Klienten**
- Verifierar storlek och SHA-256 på varje fil (`crypto.subtle`), avvisar okända schemaversioner och visar ett tydligt fel i stället för felaktiga siffror.
- Visar en tydlig markering om aktuell release har ersatts.

**Rättelser**
- Releaser raderas aldrig. En felaktig release rättas genom en ny release, och den gamla får `supersededBy` satt. Logga rättelser i `CHANGELOG-data.md` och visa dem på `/data`.

**Öppen data på stabila adresser**
- `latest/`-alias som skrivs om vid varje release, i Botten Adas format:
  - `latest/timeseries.csv` med datum och p5/p50/p95 per parti
  - `latest/institutsbias.csv` med en rad per institut och parti: antal mätningar, andel över och under, medel- och medianavvikelse i procentenheter och i procent av partiets storlek
  - `latest/kommuner.csv`, `latest/regioner.csv` och `latest/valkretsar.csv` med prognos och intervall
  - `latest/mandat.csv` med förväntade mandat och sannolikhetsfördelning per parti och valkrets
  - `latest/kandidater.csv` med sannolikhet att bli invald
  - `latest/draws.parquet` med ett urval av simuleringsdragningar
- Samma filer finns även i varje release, så att historiska versioner går att hämta.
- Varje CSV har ett tillhörande `.schema.json` med kolumnbeskrivningar. Licensen och hur Mandatorn ska anges som källa står i filhuvud eller README.
- Filerna kan slås av eller på var för sig via konfiguration.

**Lagring och gallring**
- Sammanfattningar sparas för alltid. Dragningar sparas för den senaste releasen, en release per dygn samt valdagen. Övriga dragningar rensas av en S3-livscykelregel.

### 3. Infrastruktur (AWS, Terraform)

- S3-buckets i `eu-north-1`: en för sajten och en för data. Ingen publik åtkomst direkt mot S3. All läsning går via CloudFront med Origin Access Control.
- En CloudFront-distribution per domän, med cache-policyer enligt avsnitt 2 och CORS för `data.`-domänen.
- Ett separat prefix `partner/` som bara nås med signerade CloudFront-URL:er eller cookies (för nowcast-partner, se avsnitt 7).
- En IAM-roll för GitHub Actions via OIDC, begränsad till skrivning i rätt buckets och invalidering av rätt distributioner.
- AWS Budgets-larm på en låg nivå, plus larm på ovanligt hög CloudFront-trafik.
- Lagringsadapter i Python (`mandatorn_model/storage.py`) mot S3-API:et med operationerna `put_immutable`, `put_pointer`, `list_releases` och `invalidate`. Inga AWS-specifika anrop utanför adaptern.
- Dokumentera månadskostnaden vid normal trafik och vid valnattstrafik i `ARCHITECTURE.md`.

### 4. Frontend (Astro, React-öar)

- Astro med statisk förrendering. React används bara för interaktiva komponenter: kartor, diagram, koalitionsbyggare och scenariokontroller.
- Förrenderade sidor innehåller ingresstext och det som syns ovanför vecket. Allt övrigt hämtas från releasen. Varje sida hämtar senaste manifestet när den laddas och uppdaterar siffror och ingress i klienten om en nyare release finns.
- Interaktivitet som idag sker i Python flyttas till klienten där det går:
  - Porta mandatberäkningen till TypeScript: jämkade uddatalsmetoden med första divisor 1,2, spärrar (4 % nationellt, 12 % i valkrets), fasta och utjämningsmandat, samt personvalsspärren. Kontrollera reglerna mot gällande vallag och befintlig Python-kod. Om de skiljer sig, flagga det och ändra ingenting på egen hand.
  - Golden tests: kör Python- och TS-implementationen på samma fall (valen 2018 och 2022 plus syntetiska kantfall som lika jämförelsetal, parti precis på spärren, parti under 4 % nationellt men över 12 % i en valkrets). Resultaten ska vara identiska.
  - Sannolikheter förberäknas i Python. Godtyckliga villkor (t.ex. egen koalition) räknas i klienten på dragningsurvalet.
- Osäkerhet visas konsekvent: intervall i diagram, sannolikheter för mandat, spärr och invald.
- Mobile first, svenska, WCAG 2.1 AA. Kartorna faller tillbaka på tabeller om WebGL saknas.
- Designtokens (färger, typsnitt, partifärger) i en enda fil. Jag lägger in varumärket senare.
- Statiska sidor: `/om` (metod), `/data` (öppen data, licens, rättelselogg), `/licens` (kommersiell licens och kontakt), `/status` (build, release och tid för senaste körning, som `/version.json`), `/integritet`.

### 5. Innehåll inspirerat av Botten Ada

Botten Ada renderar sidorna på en server på Heroku. Vi kopierar innehållsmönstren men förrenderar statiskt.

- **Datadriven ingress** överst på varje sida, genererad ur releasen. Exempel: "Just nu är det fördel för X. Om det var val i dag skulle regeringsunderlaget med 76 procents sannolikhet bli störst." Motsvarande för kommun, valkrets och kandidat. Bygg en mallmotor med svenska grammatikregler (genus, plural, pronomen) och golden tests för texterna. Inga texter skrivs för hand per release.
- **Verbal sannolikhetsskala**, definierad på ett ställe och använd överallt. Utgångsförslag: under 10 % "Väldigt osannolikt", 10–40 % "Osannolikt", 40–60 % "Jämnt", 60–90 % "Troligt", över 90 % "Väldigt troligt". Visa aldrig 0 % eller 100 % från simuleringar. Använd "<1 %" och ">99 %".
- **"Hur sannolikt är det att …"-kort**, definierade deklarativt i en konfigurationsfil: blockmajoritet, varje parti över spärren, A större än B, rekordval och sämsta val, samt Mandatorn-specifika frågor som "M tar ett fast mandat till i Stockholms län" och "NN blir invald".
- **Trendtabell** med nuvarande skattning och förändring mot en månad sedan, ett år sedan och senaste valet, för partier och block.
- **Entitetssidor:** `/parti/<slug>`, `/institut/<slug>` (husbias), `/kommun/<slug>`, `/region/<slug>`, `/valkrets/<slug>` och `/kandidat/<slug>`. Varje sida har egen title, beskrivning, OG-bild, kanonisk URL och schema.org JSON-LD. Generera `sitemap.xml` och `robots.txt` vid bygget.
- **Senaste mätningarna** som tabell med institut, fältperiod och partiandelar, med valbar förändring.
- **Arkiv per val:** `/arkiv/<år>` som visar prognosens utveckling fram till valdagen och utfallet, byggt på sparade releaser.
- **Prestandabudget:** högst 150 kB HTML per förrenderad sida. Botten Adas sidor väger 0,9–1,6 MB eftersom hela datan bäddas in i varje sida, och det ska vi undvika.
- **Tidsberoende texter** ("X dagar kvar till valet") räknas mot releasens `generatedAt` och valets datum. Testa före, under och efter valdagen. Botten Ada visade fortfarande "19 dagar kvar" efter valet.

### 6. Publiceringsrytm och kvalitetsgrind

**Utlösare**
- **Ny mätning:** en mätning läggs in som PR mot `data/polls/` (manuellt eller via skript), och sammanslagningen triggar en körning. Det är den primära utlösaren.
- **Extern källa:** om vi läser från en extern källa (t.ex. ett publikt repo med mätningar) körs ett schemalagt jobb som jämför och öppnar en PR vid förändring. Lägg schemat på udda minuter, aldrig på hel timme, eftersom GitHubs schemalagda körningar ofta försenas där.
- **Daglig körning** även utan nya mätningar, så att tidsberoende osäkerhet och texter hålls aktuella.
- **Manuell körning** via `workflow_dispatch`.

**Ombyggnad av sajten**
- Sidorna byggs om och laddas upp vid varje ny mätning och en gång per dygn. Data kan publiceras oftare utan ombygge, eftersom klienten läser senaste manifestet.

**Kvalitetsgrind före publicering**
- Andelarna för varje mätning summerar till ett rimligt intervall.
- Fältperioden är rimlig och inte i framtiden.
- Inget parti avviker mer än ett konfigurerbart antal procentenheter från samma instituts förra mätning eller från aggregatet.
- Ingen dubblett finns.
- Modellens utdata håller sig inom rimliga gränser (t.ex. 349 mandat totalt, sannolikheter mellan 0 och 1).
- Flaggade körningar publiceras inte automatiskt. De öppnar ett issue och väntar på mitt godkännande.

**Övervakning**
- Heartbeat: ett jobb kontrollerar dagligen att en lyckad körning har skett inom förväntat intervall, och larmar annars.
- Publika repon får sina schemalagda workflows avstängda efter 60 dagar utan aktivitet. Heartbeat-jobbet ska upptäcka det.

### 7. Nowcast-läge (fas 3)

- En ingest-process på Fly.io i region `arn` hämtar Valmyndighetens preliminära resultat med ett konfigurerbart intervall (utgångsläge 60 sekunder). Den kör nowcast-modellen och publicerar releaser med `mode: "nowcast"`.
- **Partnern först:** varje nowcast-release skrivs först till `partner/` (signerade URL:er). Samma release blir publik efter en konfigurerbar fördröjning (utgångsläge 10 minuter, kan sättas till 0). Fördröjningen gäller bara under valnatten.
- Klienten pollar manifestet var 30–60 sekund i nowcast-läge och uppdaterar utan omladdning.
- En simulator spelar upp valnatten 2022 (och EU-valet 2024) från sparade data i rapporteringsordning. Den fungerar som integrationstest och som demo för redaktioner.
- Om Valmyndigheten inte svarar ligger senaste giltiga release kvar och statussidan visar det.
- Runbook i `docs/RUNBOOK.md`.

### 8. CI/CD

- **Vid push:** lint, typkontroll, enhetstester, golden tests mellan Python och TS, test av mallmotorn och kontroll av prestandabudgeten.
- **Vid ny mätning, daglig körning eller manuell körning:** kvalitetsgrind, modellkörning, publicering, ombygge av sajten, uppladdning och CloudFront-invalidering av HTML och manifest.
- Förhandsmiljö per PR (separat prefix eller distribution).
- Staging på `beta.mandatorn.se` tills paritet är godkänd.

---

## Fas 1: Datakontrakt, pipeline och infrastruktur

- Bryt ut modellen från Streamlit utan att ändra resultaten. Verifiera mot Streamlit-appen: noll avvikelse för mandat, bara avrundningsfel för andelar.
- Implementera Pydantic-kontrakt, JSON Schema, TS-typer, manifest, hashning, `latest`-alias, lagringsadapter och publicering till en lokal katalog.
- Terraform för AWS (S3, CloudFront, OIDC-roll och budgetlarm), körbart mot ett staging-konto eller staging-prefix.
- Visa att samma indata ger samma release-id.

**Stopp. Vänta på godkännande.**

## Fas 2: Frontend med paritet och innehåll

Bygg vyerna i den ordning `PARITY.md` prioriterar. Börja med nationell översikt och mandatfördelning, därefter valkrets, kommun och region, kandidater, mandatmarginaler, partier och institut, `/data`, arkiv och metod. Lägg till ingresser, sannolikhetskort och trendtabeller. Bocka av i `PARITY.md` allteftersom.

## Fas 3: Nowcast, simulator och drift

Enligt avsnitt 7. Ska vara klart och testat inför EU-valet i juni 2029.

---

## Definition of done

- Varje rad i `PARITY.md` är verifierad.
- Golden tests för mandatberäkning och ingresstexter är gröna.
- Lighthouse ≥ 90 på mobil för startsidan och en kommunsida.
- Första vyn laddar under 200 kB JS (gzip) exklusive karta. Ingen förrenderad HTML-sida överstiger 150 kB.
- Alla entitetssidor finns i `sitemap.xml` och har unik title, beskrivning och OG-bild.
- Öppna CSV-filer finns på `latest/` och i varje release, med schema och licens.
- En release kan återskapas exakt från seed, modellversion och indata.
- Sajten fungerar med Streamlit avstängd.
- `README.md` beskriver hur man lägger in en mätning, kör pipelinen, publicerar, rättar en release och rullar tillbaka.

## Uttryckliga icke-mål

- Ingen ändring av modellens metod eller parametrar.
- Ingen databas eller server som den publika sajten är beroende av.
- Inga användarkonton.
- Ingen Cloudflare.
