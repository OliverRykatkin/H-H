/** Golden tests för mallmotorn (web/src/lib/text). Förväntade texter är granskade för hand. */
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import type { Constituency, National, Simulation } from "@contracts/contracts";
import {
  adjective, bloc, capitalize, counted, formatInteger, formatNumber, genitive, list, listPhrase, localParty,
  numberWord, party, percent, pp, pronoun, seats, sentences, signedPp,
} from "@/lib/text/grammar";
import { clock, daysBetween, electionCountdown, electionTiming, sinceBaselineElection, stockholmDay } from "@/lib/text/time";
import { displayPct, probabilityPhrase, probabilityValue, verbal } from "@/lib/text/scale";
import {
  areaIngress, constituencyIngress, instituteIngress, nationalIngress, partyIngress, valnattIngress,
} from "@/lib/text/ingress";

const NBSP = " ";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const fx = <T = any>(n: string): T => JSON.parse(readFileSync(new URL(`./fixtures/text/${n}`, import.meta.url), "utf-8"));
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const GEN = "2026-10-01T00:00:00";

describe("grammatik", () => {
  test("partier: numerus, genus och pronomen", () => {
    for (const p of ["M", "L", "KD", "S", "SD"]) expect(pronoun(party(p))).toBe("de");
    for (const p of ["C", "V", "MP"]) expect(pronoun(party(p))).toBe("det");
    expect(party("O")).toEqual({ name: "Övriga", numerus: "plural", genus: "utrum" });
    expect(party("C").name).toBe("Centerpartiet");
    expect(pronoun(bloc("Högerblocket"))).toBe("det");
  });

  test("lokala partier", () => {
    expect(pronoun(localParty("Väsbys Bästa"))).toBe("den");
    expect(pronoun(localParty("Skånepartiet"))).toBe("det");
    expect(pronoun(localParty("Kristna Värdepartiet"))).toBe("det");
    expect(pronoun(localParty("Vägvalet"))).toBe("det");
    expect(pronoun(localParty("Pensionärerna"))).toBe("de");
  });

  test("adjektivkongruens", () => {
    expect(adjective(party("S"), "stor", "stort", "stora")).toBe("stora");
    expect(adjective(party("C"), "stor", "stort", "stora")).toBe("stort");
    expect(adjective(localParty("Väsbys Bästa"), "stor", "stort", "stora")).toBe("stor");
  });

  test("räkneord med genus", () => {
    expect(numberWord(1)).toBe("en");
    expect(numberWord(1, "neutrum")).toBe("ett");
    expect(numberWord(2, "neutrum")).toBe("två");
    expect(numberWord(12)).toBe("tolv");
    expect(numberWord(13)).toBe("13");
    expect(numberWord(1448)).toBe(`1${NBSP}448`);
    expect(seats(1)).toBe("ett mandat");
    expect(seats(2)).toBe("två mandat");
    expect(seats(73)).toBe("73 mandat");
    expect(counted(1, "procentenhet", "procentenheter", "utrum")).toBe("en procentenhet");
    expect(counted(3, "procentenhet", "procentenheter", "utrum")).toBe("tre procentenheter");
  });

  test("sifferformat sv-SE", () => {
    expect(formatInteger(6312)).toBe(`6${NBSP}312`);
    expect(formatInteger(6767429)).toBe(`6${NBSP}767${NBSP}429`);
    expect(formatInteger(-1500)).toBe(`−1${NBSP}500`);
    expect(formatNumber(24.3456)).toBe("24,3");
    expect(formatNumber(-0.74)).toBe("−0,7");
    expect(formatNumber(-0.04)).toBe("0,0");
    expect(formatNumber(1234.5, 2)).toBe(`1${NBSP}234,50`);
    expect(percent(28.6147)).toBe("28,6 procent");
    expect(signedPp(1.0139)).toBe("+1,0 procentenheter");
    expect(signedPp(-0.6548)).toBe("−0,7 procentenheter");
    expect(signedPp(1, 0)).toBe("+1 procentenhet");
    expect(pp(0.3562)).toBe("0,4 procentenheter");
    expect(pp(-0.6)).toBe("0,6 procentenheter");
  });

  test("listor, versaler, genitiv och meningar", () => {
    expect(list([])).toBe("");
    expect(list(["M"])).toBe("M");
    expect(list(["M", "KD"])).toBe("M och KD");
    expect(list(["M", "KD", "SD"])).toBe("M, KD och SD");
    expect(listPhrase([party("C")]).numerus).toBe("singular");
    expect(listPhrase([party("C"), party("V")])).toEqual({
      name: "Centerpartiet och Vänsterpartiet", numerus: "plural", genus: "utrum",
    });
    expect(capitalize("åtta mandat")).toBe("Åtta mandat");
    expect(genitive("Stockholm")).toBe("Stockholms");
    expect(genitive("Västerås")).toBe("Västerås");
    expect(genitive("Luleå")).toBe("Luleås");
    expect(sentences(["de skulle få ett mandat", null, "", "klart."])).toBe("De skulle få ett mandat. Klart.");
  });
});

describe("tid", () => {
  test("Stockholmsdygn", () => {
    expect(stockholmDay("2026-10-01T00:00:00")).toBe("2026-10-01");
    expect(stockholmDay("2026-09-13T22:30:00Z")).toBe("2026-09-14"); // sommartid UTC+2
    expect(stockholmDay("2026-12-31T23:30:00Z")).toBe("2027-01-01"); // vintertid UTC+1
    expect(stockholmDay("2026-12-31T22:30:00Z")).toBe("2026-12-31");
    expect(daysBetween("2026-10-01T00:00:00", "2030-09-08")).toBe(1438);
  });

  test("före, på och efter valdagen", () => {
    expect(electionCountdown(GEN)).toBe(`Det är 1${NBSP}438 dagar kvar till valet 2030.`);
    expect(electionCountdown("2030-08-28T00:00:00")).toBe("Det är elva dagar kvar till valet 2030.");
    expect(electionCountdown("2030-09-06T00:00:00")).toBe("Det är två dagar kvar till valet 2030.");
    expect(electionCountdown("2030-09-07T00:00:00")).toBe("Det är en dag kvar till valet 2030.");
    expect(electionCountdown("2030-09-08T00:00:00")).toBe("I dag är det valdag.");
    expect(electionCountdown("2030-09-08T21:59:00Z")).toBe("I dag är det valdag.");
    expect(electionCountdown("2030-09-09T00:00:00")).toBe("Valet 2030 hölls i går.");
    expect(electionCountdown("2030-09-20T00:00:00")).toBe("Valet 2030 hölls för tolv dagar sedan.");
    expect(electionCountdown("2031-10-14T00:00:00")).toBe("Valet 2030 hölls för 401 dagar sedan.");
    expect(electionTiming("2030-09-09T00:00:00")).toEqual({
      phase: "after", days: 1, electionYear: "2030", electionDate: "2030-09-08",
    });
  });

  test("aldrig 'kvar' efter valet", () => {
    for (let d = 0; d < 60; d++) {
      const day = new Date(Date.UTC(2030, 8, 9 + d)).toISOString().slice(0, 10);
      expect(electionCountdown(`${day}T00:00:00`)).not.toMatch(/kvar/);
    }
  });

  test("tid sedan baslinjevalet och klockslag", () => {
    expect(sinceBaselineElection("2026-09-12T00:00:00")).toBeNull();
    expect(sinceBaselineElection("2026-09-13T00:00:00")).toBe("Riksdagsvalet 2026 hålls i dag.");
    expect(sinceBaselineElection("2026-09-14T00:00:00")).toBe("Riksdagsvalet 2026 hölls i går.");
    expect(sinceBaselineElection(GEN)).toBe("Riksdagsvalet 2026 hölls för 18 dagar sedan.");
    expect(clock("2026-09-13T22:00:00")).toBe("22.00");
  });
});

describe("verbal skala (samma regler som mandatorn_model/text.py)", () => {
  test.each([
    [0.0, "Väldigt osannolikt"], [0.099, "Väldigt osannolikt"], [0.1, "Osannolikt"],
    [0.349, "Osannolikt"], [0.35, "Jämnt"], [0.5, "Jämnt"], [0.65, "Jämnt"],
    [0.651, "Troligt"], [0.9, "Troligt"], [0.901, "Väldigt troligt"], [1.0, "Väldigt troligt"],
  ])("verbal(%s) = %s", (p, label) => expect(verbal(p)).toBe(label));

  test.each([
    [0.0, "<1 %"], [0.0099, "<1 %"], [0.01, "1 %"], [0.5, "50 %"], [0.99, "99 %"], [0.9901, ">99 %"],
    [1.0, ">99 %"], [0.125, "12 %"], [0.135, "14 %"], [0.545, "55 %"],
  ])("displayPct(%s) = %s", (p, txt) => expect(displayPct(p)).toBe(txt));

  test("löptext", () => {
    expect(probabilityPhrase(0.5793)).toBe("58 procents sannolikhet");
    expect(probabilityPhrase(0.004)).toBe("mindre än 1 procents sannolikhet");
    expect(probabilityPhrase(0.999)).toBe("över 99 procents sannolikhet");
    expect(probabilityValue(0.6361)).toBe("64 procent");
  });
});

describe("ingresser ur riktiga releasen (2026-10-01)", () => {
  const nat = fx<National>("national.json");
  const sim = fx<Simulation>("simulation.json");

  test("nationellt", () => {
    expect(nationalIngress(nat, sim, GEN)).toBe(
      "Just nu är det fördel för Vänsterblocket. Om det vore val i dag skulle Vänsterblocket få 176 av 349 mandat " +
        "och därmed egen majoritet. I valet 2030 får Vänsterblocket egen majoritet med 58 procents sannolikhet (jämnt). " +
        "Största parti är Socialdemokraterna med 28,6 procent. De har ökat med 0,6 procentenheter sedan valet 2026. " +
        "Liberalerna, Kristdemokraterna och Miljöpartiet är inte säkra på att klara spärren i valet 2030 " +
        `(64, 86 respektive 86 procents sannolikhet). Det är 1${NBSP}438 dagar kvar till valet 2030.`,
    );
  });

  test("parti i plural respektive neutrum singular", () => {
    expect(partyIngress("M", nat, sim)).toBe(
      "Moderaterna har i dag stöd av 20,9 procent av väljarna, 1,0 procentenheter mer än i valet 2026. " +
        "De skulle få 73 mandat om det vore val i dag. " +
        "I valet 2030 väntas Moderaterna få mellan 58 och 92 mandat (90 procents intervall).",
    );
    expect(partyIngress("C", nat, sim)).toBe(
      "Centerpartiet har i dag stöd av 7,1 procent av väljarna, lika mycket som i valet 2026. " +
        "Det skulle få 25 mandat om det vore val i dag. I valet 2030 väntas Centerpartiet få upp till 38 mandat " +
        "(90 procents intervall), men det kan också hamna utanför riksdagen. " +
        "Sannolikheten att det klarar riksdagsspärren är 92 procent.",
    );
    expect(partyIngress("L", nat, sim)).toContain("0,7 procentenheter mindre än i valet 2026");
    expect(partyIngress("L", nat, sim)).toContain("Sannolikheten att de klarar riksdagsspärren är 64 procent.");
  });

  test("valkrets", () => {
    expect(constituencyIngress(fx<Constituency>("constituency-stockholms-stad.json"), nat)).toBe(
      "I valkretsen Stockholms stad är Socialdemokraterna största parti med 26,8 procent om det vore val i dag. " +
        "De skulle få åtta av valkretsens 29 fasta mandat. Fördelningen av de fasta mandaten är densamma som i valet 2026. " +
        "Närmast att ta ytterligare ett fast mandat är Sverigedemokraterna, som behöver 0,4 procentenheter mer. " +
        "Närmast att tappa ett är Socialdemokraterna, med en marginal på 0,9 procentenheter.",
    );
    expect(constituencyIngress(fx<Constituency>("constituency-gotland.json"), nat)).toContain(
      "De skulle få ett av valkretsens två fasta mandat.",
    );
  });

  test("kommun och region", () => {
    expect(areaIngress(fx("kommun-0180.json"))).toBe(
      "Om det vore val i dag skulle Socialdemokraterna bli största parti i kommunvalet i Stockholms kommun med 26,6 procent. " +
        "De skulle få 27 av 101 mandat i kommunfullmäktige, lika många som i valet 2026.",
    );
    expect(areaIngress(fx("region-01.json"))).toBe(
      "Om det vore val i dag skulle Socialdemokraterna bli största parti i regionvalet i Region Stockholm med 28,2 procent. " +
        "De skulle få 43 av 149 mandat i regionfullmäktige, jämfört med 42 i valet 2026.",
    );
  });

  test("institut", () => {
    const inst = fx("institutes.json");
    expect(instituteIngress("Demoskop", inst)).toBe(
      "Mandatorn har jämfört 52 mätningar från Demoskop med opinionstrenden. Jämfört med trenden överskattar institutet " +
        "Moderaterna mest (+0,5 procentenheter i snitt) och underskattar Socialdemokraterna mest (−0,6 procentenheter). " +
        "Inför valet 2026 låg institutets mätningar i snitt 1,60 procentenheter från resultatet, " +
        "vilket ger vikten 0,82 i aggregeringen.",
    );
    expect(instituteIngress("Okänt", inst)).toBe("Okänt saknar mätningar i jämförelsen.");
  });

  test("valnatt", () => {
    expect(valnattIngress(fx("valnatt-2200.json"))).toBe(
      `Klockan 22.00 på valnatten 2026 var 1${NBSP}752 av 6${NBSP}312 valdistrikt räknade, med 25 procent av rösterna. ` +
        "Nowcasten låg då i snitt 0,13 procentenheter från slutresultatet per parti, " +
        "jämfört med 0,29 procentenheter för råräkningen.",
    );
    const empty = { ...fx("valnatt-2200.json"), nCounted: 0, time: "2026-09-13T20:40:00", maeRaw: null };
    expect(valnattIngress(empty)).toBe("Klockan 20.40 på valnatten 2026 hade inga valdistrikt rapporterats ännu.");
  });
});

describe("ingresser i syntetiska lägen", () => {
  const nat = fx<National>("national.json");
  const sim = fx<Simulation>("simulation.json");

  test("jämnt läge, ingen egen majoritet i dag och risk för inget block", () => {
    const n = clone(nat);
    const s = clone(sim);
    n.blocs[0].pMajority = 0.45;
    n.blocs[1].pMajority = 0.43;
    n.blocs[0].seats = 174;
    n.blocs[1].seats = 175;
    s.blocs["Inget block"] = { pMajority: 0.12 };
    const t = nationalIngress(n, s, GEN);
    expect(t).toMatch(/^Just nu är det jämnt mellan blocken\. /);
    expect(t).toContain("Om det vore val i dag skulle Vänsterblocket få 175 av 349 mandat och därmed egen majoritet.");
    expect(t).toContain("I valet 2030 får Högerblocket egen majoritet med 45 procents sannolikhet (jämnt).");
    expect(t).toContain("Med 12 procents sannolikhet får inget av blocken egen majoritet.");
    n.blocs[0].seats = 172;
    n.blocs[1].seats = 174;
    expect(nationalIngress(n, s, GEN)).toContain(
      "skulle Vänsterblocket bli störst med 174 av 349 mandat, men utan egen majoritet.",
    );
  });

  test("partier under spärren: ett, flera och inga osäkra", () => {
    const n = clone(nat);
    n.belowThreshold = ["L"];
    expect(nationalIngress(n, sim, GEN)).toContain("Liberalerna ligger under riksdagsspärren på 4 procent.");
    n.belowThreshold = ["L", "KD"];
    expect(nationalIngress(n, sim, GEN)).toContain(
      "Liberalerna och Kristdemokraterna ligger under riksdagsspärren på 4 procent.",
    );
    n.belowThreshold = [];
    for (const e of n.estimates) e.pAboveThreshold = e.party === "MP" ? 0.7 : 1;
    expect(nationalIngress(n, sim, GEN)).toContain("Miljöpartiet klarar spärren i valet 2030 med 70 procents sannolikhet.");
    for (const e of n.estimates) e.pAboveThreshold = 1;
    expect(nationalIngress(n, sim, GEN)).toContain("Samtliga riksdagspartier ligger över spärren.");
  });

  test("största parti i singular och minskning", () => {
    const n = clone(nat);
    n.largestParty = "C";
    const c = n.estimates.find((e) => e.party === "C");
    if (c) c.change = -1.25;
    expect(nationalIngress(n, sim, GEN)).toContain(
      "Största parti är Centerpartiet med 7,1 procent. Det har minskat med 1,3 procentenheter sedan valet 2026.",
    );
  });

  test("valdagen och efter valet 2030", () => {
    expect(nationalIngress(nat, sim, "2030-09-09T00:00:00")).toMatch(/Valet 2030 hölls i går\.$/);
    expect(nationalIngress(nat, sim, "2030-09-08T00:00:00")).toMatch(/I dag är det valdag\.$/);
  });

  test("parti utanför riksdagen", () => {
    const n = clone(nat);
    const s = clone(sim);
    n.seats.MP = 0;
    const d = s.parties.find((p) => p.party === "MP");
    if (d) d.p95 = 0;
    expect(partyIngress("MP", n, s)).toContain("Det skulle inte komma in i riksdagen om det vore val i dag.");
    expect(partyIngress("MP", n, s)).not.toContain("väntas");
  });

  test("valkrets med vinster och förluster", () => {
    const c = clone(fx<Constituency>("constituency-stockholms-stad.json"));
    c.fixedNow.M = 7;
    c.fixedNow.L = 1;
    expect(constituencyIngress(c, nat)).toContain(
      "Jämfört med valet 2026 skulle Moderaterna vinna ett mandat och Liberalerna förlora ett.",
    );
    c.fixedNow.SD = 4;
    c.fixedNow.S = 6;
    expect(constituencyIngress(c, nat)).toContain(
      "Jämfört med valet 2026 skulle Sverigedemokraterna vinna två mandat, Moderaterna vinna ett mandat, " +
        "Liberalerna förlora ett och Socialdemokraterna förlora två.",
    );
  });

  test("lokalt parti störst i fullmäktige och många övriga", () => {
    const k = clone(fx("kommun-0180.json"));
    k.kommunSeats.now = { VB: 30, S: 27 };
    k.kommunSeats.names.VB = "Väsbys Bästa";
    k.kommunval.others = 12.1;
    const t = areaIngress(k);
    expect(t).toContain("Väsbys Bästa skulle få 30 av 101 mandat i kommunfullmäktige, jämfört med 0 i valet 2026.");
    expect(t).toContain("Lokala och övriga partier fick 12,1 procent i valet 2026 och antas behålla sitt stöd.");
  });
});
