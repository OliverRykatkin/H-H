/**
 * Datadrivna ingresser: genereras ur releasen, aldrig handskrivna per release.
 * Varje funktion returnerar en färdig text (en eller flera meningar).
 */
import type {
  Area, AreaSeats, AreaShares, Constituency, Institutes, National, PartyEstimate, Simulation, ValnattState,
} from "@contracts/contracts";
import { BASELINE_YEAR, NEXT_ELECTION_YEAR, PARTY_NAMES, TOTAL_SEATS } from "@contracts/constants";
import {
  bloc, capitalize, formatInteger, genitive, list, listPhrase, localParty, numberWord, party, percent, pp,
  pronoun, seats, sentences, signedPp, type NounPhrase,
} from "./grammar";
import { probabilityPhrase, probabilityValue, verbalLower } from "./scale";
import { clock, electionCountdown } from "./time";

const MAJORITY = Math.floor(TOTAL_SEATS / 2) + 1;
/** Skillnad i majoritetssannolikhet under vilken läget kallas jämnt. */
const EVEN_GAP = 0.1;
/** Partier med lägre sannolikhet än så att klara spärren nämns. */
const THRESHOLD_RISK = 0.9;

function argmax<T>(items: T[], key: (t: T) => number): T {
  return items.reduce((best, x) => (key(x) > key(best) ? x : best));
}

function changeClause(np: NounPhrase, change: number, year: number): string {
  const v = Number(change.toFixed(1));
  const who = capitalize(pronoun(np));
  if (v === 0) return `${who} ligger kvar på samma nivå som i valet ${year}`;
  return `${who} har ${v > 0 ? "ökat" : "minskat"} med ${pp(v)} sedan valet ${year}`;
}

// ── Nationellt ──────────────────────────────────────────────────────────────

export function nationalIngress(national: National, simulation: Simulation, generatedAt: string): string {
  const blocs = national.blocs;
  const leader = argmax(blocs, (b) => b.pMajority);
  const other = blocs.find((b) => b !== leader) ?? leader;
  const seatLeader = argmax(blocs, (b) => b.seats);
  const pNone = simulation.blocs["Inget block"]?.pMajority ?? Math.max(0, 1 - leader.pMajority - other.pMajority);

  const first = leader.pMajority - other.pMajority < EVEN_GAP
    ? "Just nu är det jämnt mellan blocken"
    : `Just nu är det fördel för ${bloc(leader.name).name}`;

  const today = seatLeader.seats >= MAJORITY
    ? `Om det vore val i dag skulle ${seatLeader.name} få ${seatLeader.seats} av ${TOTAL_SEATS} mandat och därmed egen majoritet`
    : `Om det vore val i dag skulle ${seatLeader.name} bli störst med ${seatLeader.seats} av ${TOTAL_SEATS} mandat, men utan egen majoritet`;

  const future = `I valet ${NEXT_ELECTION_YEAR} får ${leader.name} egen majoritet med ${probabilityPhrase(leader.pMajority)} (${verbalLower(leader.pMajority)})`;
  const none = pNone >= 0.05 ? `Med ${probabilityPhrase(pNone)} får inget av blocken egen majoritet` : null;

  const largest = national.estimates.find((e) => e.party === national.largestParty) as PartyEstimate;
  const largestNp = party(largest.party);
  const largestSentence = `Största parti är ${largestNp.name} med ${percent(largest.share)}`;
  const largestChange = largest.change != null ? changeClause(largestNp, largest.change, national.baselineYear) : null;

  return sentences([
    first, today, future, none, largestSentence, largestChange,
    thresholdSentence(national),
    electionCountdown(generatedAt),
  ]);
}

function thresholdSentence(national: National): string | null {
  if (national.belowThreshold.length) {
    const np = listPhrase(national.belowThreshold.map(party));
    return `${np.name} ligger under riksdagsspärren på 4 procent`;
  }
  const risky = national.estimates
    .filter((e) => e.party !== "O" && e.pAboveThreshold != null && e.pAboveThreshold < THRESHOLD_RISK)
    .sort((a, b) => (a.pAboveThreshold ?? 0) - (b.pAboveThreshold ?? 0));
  if (!risky.length) return "Samtliga riksdagspartier ligger över spärren";
  if (risky.length === 1) {
    const e = risky[0];
    return `${party(e.party).name} klarar spärren i valet ${NEXT_ELECTION_YEAR} med ${probabilityPhrase(e.pAboveThreshold ?? 0)}`;
  }
  const names = list(risky.map((e) => party(e.party).name));
  const v = risky.map((e) => probabilityValue(e.pAboveThreshold ?? 0).replace(" procent", ""));
  const values = `${v.slice(0, -1).join(", ")} respektive ${v[v.length - 1]}`;
  return `${names} är inte säkra på att klara spärren i valet ${NEXT_ELECTION_YEAR} (${values} procents sannolikhet)`;
}

// ── Parti ───────────────────────────────────────────────────────────────────

export function partyIngress(code: string, national: National, simulation: Simulation): string {
  const est = national.estimates.find((e) => e.party === code);
  if (!est) throw new Error(`Okänt parti ${code}`);
  const np = party(code);
  const who = capitalize(pronoun(np));
  const dist = simulation.parties.find((p) => p.party === code);
  const n = national.seats[code] ?? 0;

  const change = est.change ?? 0;
  const v = Number(change.toFixed(1));
  const vs = v === 0
    ? `lika mycket som i valet ${national.baselineYear}`
    : `${pp(v)} ${v > 0 ? "mer" : "mindre"} än i valet ${national.baselineYear}`;
  const now = `${np.name} har i dag stöd av ${percent(est.share)} av väljarna, ${vs}`;
  const seatsToday = n > 0
    ? `${who} skulle få ${seats(n)} om det vore val i dag`
    : `${who} skulle inte komma in i riksdagen om det vore val i dag`;
  const interval = !dist || dist.p95 === 0
    ? null
    : dist.p5 === 0
      ? `I valet ${NEXT_ELECTION_YEAR} väntas ${np.name} få upp till ${dist.p95} mandat (90 procents intervall), men ${pronoun(np)} kan också hamna utanför riksdagen`
      : `I valet ${NEXT_ELECTION_YEAR} väntas ${np.name} få mellan ${dist.p5} och ${dist.p95} mandat (90 procents intervall)`;
  const threshold = dist && dist.pAboveThreshold < 0.99
    ? `Sannolikheten att ${pronoun(np)} klarar riksdagsspärren är ${probabilityValue(dist.pAboveThreshold)}`
    : null;
  return sentences([now, seatsToday, interval, threshold]);
}

// ── Valkrets ────────────────────────────────────────────────────────────────

export function constituencyIngress(c: Constituency, national: National): string {
  const year = national.baselineYear;
  const codes = Object.keys(c.now);
  const largest = argmax(codes, (p) => c.now[p]);
  const np = party(largest);
  const s1 = `I valkretsen ${c.name} är ${np.name} största parti med ${percent(c.now[largest])} om det vore val i dag`;
  const s2 = `${capitalize(pronoun(np))} skulle få ${numberWord(c.fixedNow[largest] ?? 0, "neutrum")} av valkretsens ${numberWord(c.seats, "neutrum")} fasta mandat`;

  const diffs = codes
    .map((p) => ({ p, d: (c.fixedNow[p] ?? 0) - (c.fixedBaseline[p] ?? 0) }))
    .filter((x) => x.d !== 0)
    .sort((a, b) => b.d - a.d || a.p.localeCompare(b.p));
  let s3: string;
  if (!diffs.length) {
    s3 = `Fördelningen av de fasta mandaten är densamma som i valet ${year}`;
  } else {
    const gains = diffs.filter((x) => x.d > 0).map((x) => `${party(x.p).name} vinna ${seats(x.d)}`);
    const losses = diffs.filter((x) => x.d < 0).map((x) => `${party(x.p).name} förlora ${numberWord(-x.d, "neutrum")}`);
    s3 = `Jämfört med valet ${year} skulle ${list([...gains, ...losses])}`;
  }

  const gainable = c.margins.filter((m) => m.gainPp != null);
  const losable = c.margins.filter((m) => m.losePp != null && (c.fixedNow[m.party] ?? 0) > 0);
  const closestGain = gainable.length ? argmax(gainable, (m) => -(m.gainPp as number)) : null;
  const closestLose = losable.length ? argmax(losable, (m) => -(m.losePp as number)) : null;
  const s4 = closestGain
    ? `Närmast att ta ytterligare ett fast mandat är ${party(closestGain.party).name}, som behöver ${pp(closestGain.gainPp as number)} mer`
    : null;
  const s5 = closestLose
    ? `Närmast att tappa ett är ${party(closestLose.party).name}, med en marginal på ${pp(closestLose.losePp as number)}`
    : null;
  return sentences([s1, s2, s3, s4, s5]);
}

// ── Kommun och region ──────────────────────────────────────────────────────

function seatPartyNoun(code: string, s: AreaSeats): NounPhrase {
  return code in PARTY_NAMES ? party(code) : localParty(s.names[code] ?? code);
}

function shareParty(shares: AreaShares): string {
  const codes = Object.keys(shares.now);
  return argmax(codes, (p) => shares.now[p]);
}

export function areaIngress(area: Area, baselineYear: number = BASELINE_YEAR): string {
  const isKommun = area.kind === "kommun";
  const place = isKommun ? `${genitive(area.name)} kommun` : `Region ${area.name}`;
  const shares = isKommun ? (area.kommunval ?? area.riksdag) : area.regionval;
  const election = isKommun ? (area.kommunval ? "kommunvalet" : "riksdagsvalet") : "regionvalet";
  const assembly = isKommun ? "kommunfullmäktige" : "regionfullmäktige";
  const seatsData = isKommun ? area.kommunSeats : area.regionSeats;
  if (!shares) return sentences([`Det finns ingen prognos för ${place}`]);

  const largest = shareParty(shares);
  const np = party(largest);
  const s1 = `Om det vore val i dag skulle ${np.name} bli största parti i ${election} i ${place} med ${percent(shares.now[largest])}`;

  let s2: string | null = null;
  if (seatsData && seatsData.totalSeats > 0) {
    const top = argmax(Object.keys(seatsData.now), (p) => seatsData.now[p]);
    const topNp = seatPartyNoun(top, seatsData);
    const nNow = seatsData.now[top] ?? 0;
    const nBase = seatsData.baseline[top] ?? 0;
    const cmp = nNow === nBase ? `lika många som i valet ${baselineYear}` : `jämfört med ${nBase} i valet ${baselineYear}`;
    const subject = top === largest ? capitalize(pronoun(topNp)) : topNp.name;
    s2 = `${subject} skulle få ${nNow} av ${seatsData.totalSeats} mandat i ${assembly}, ${cmp}`;
  }
  const others = shares.others ?? 0;
  const s3 = others >= 5
    ? `Lokala och övriga partier fick ${percent(others)} i valet ${baselineYear} och antas behålla sitt stöd`
    : null;
  return sentences([s1, s2, s3]);
}

// ── Institut ────────────────────────────────────────────────────────────────

export function instituteIngress(institute: string, institutes: Institutes, baselineYear: number = BASELINE_YEAR): string {
  const rows = institutes.bias.filter((b) => b.institute === institute);
  const weight = institutes.weights.find((w) => w.institute === institute);
  const n = rows.reduce((m, r) => Math.max(m, Number(r.n ?? 0)), 0);
  const s1 = rows.length
    ? `Mandatorn har jämfört ${formatInteger(n)} mätningar från ${institute} med opinionstrenden`
    : `${institute} saknar mätningar i jämförelsen`;

  let s2: string | null = null;
  if (rows.length) {
    const over = argmax(rows, (r) => Number(r.mean_dev_pp));
    const under = argmax(rows, (r) => -Number(r.mean_dev_pp));
    const o = Number(over.mean_dev_pp), u = Number(under.mean_dev_pp);
    if (Math.max(Math.abs(o), Math.abs(u)) < 0.1) {
      s2 = "Institutet ligger nära trenden för samtliga partier";
    } else {
      const parts: string[] = [];
      if (o >= 0.1) parts.push(`överskattar institutet ${party(String(over.party)).name} mest (${signedPp(o)} i snitt)`);
      if (u <= -0.1) parts.push(`${parts.length ? "underskattar" : "underskattar institutet"} ${party(String(under.party)).name} mest (${signedPp(u)})`);
      s2 = `Jämfört med trenden ${list(parts)}`;
    }
  }
  const s3 = weight && weight.mae != null
    ? `Inför valet ${baselineYear} låg institutets mätningar i snitt ${pp(Number(weight.mae), 2)} från resultatet, vilket ger vikten ${String(Number(weight.weight).toFixed(2)).replace(".", ",")} i aggregeringen`
    : null;
  return sentences([s1, s2, s3]);
}

// ── Valnatt ─────────────────────────────────────────────────────────────────

export function valnattIngress(state: ValnattState): string {
  const at = `Klockan ${clock(state.time)} på valnatten ${state.year}`;
  if (state.nCounted === 0) return sentences([`${at} hade inga valdistrikt rapporterats ännu`]);
  const share = Math.round(state.voteShareCounted * 100);
  const s1 = `${at} var ${formatInteger(state.nCounted)} av ${formatInteger(state.nTotal)} valdistrikt räknade, med ${share} procent av rösterna`;
  const s2 = state.maeRaw != null
    ? `Nowcasten låg då i snitt ${pp(state.maeNowcast, 2)} från slutresultatet per parti, jämfört med ${pp(state.maeRaw, 2)} för råräkningen`
    : `Nowcasten låg då i snitt ${pp(state.maeNowcast, 2)} från slutresultatet per parti`;
  return sentences([s1, s2]);
}
