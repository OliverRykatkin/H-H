/**
 * Mandatfördelning i riksdagsval enligt vallagen (2022:1600) 14 kap.
 * Exakt port av mandatorn_model/vallag.py — samma regler, samma tie-break och samma
 * flyttalsaritmetik (inklusive Pythons kompenserade sum(), se pySum), så att resultaten
 * blir identiska med Python. Verifieras av web/tests/seats.test.ts mot tests/golden/.
 */

export const NATIONAL_THRESHOLD = 0.04;
export const CONSTITUENCY_THRESHOLD = 0.12;
export const FIRST_DIVISOR = 1.2;

export type Votes = Record<string, number>;
export type SeatsByParty = Record<string, number>;

export function divisor(k: number): number {
  return k === 0 ? FIRST_DIVISOR : 2 * k + 1;
}

export function placementDivisor(k: number): number {
  return 2 * k + 1;
}

/** Strängjämförelse på kodpunkter (som Python), inte localeCompare. */
function cmpStr(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * Pythons inbyggda sum() över flyttal (CPython ≥ 3.12 använder Neumaier-kompenserad
 * summering). Krävs för bitidentiska resultat med Python.
 */
export function pySum(values: Iterable<number>): number {
  let result = 0;
  let c = 0;
  for (const x of values) {
    const t = result + x;
    if (Math.abs(result) >= Math.abs(x)) c += result - t + x;
    else c += x - t + result;
    result = t;
  }
  if (c !== 0 && Number.isFinite(c)) result += c;
  return result;
}

type Cand = [q: number, v: number, key: string];

/** Högst jämförelsetal; lika → högst röstetal; lika → nyckel i bokstavsordning. */
function pick(cands: Cand[]): string {
  let best = cands[0];
  for (let i = 1; i < cands.length; i++) {
    const c = cands[i];
    if (c[0] > best[0] || (c[0] === best[0] && (c[1] > best[1] || (c[1] === best[1] && cmpStr(c[2], best[2]) < 0)))) {
      best = c;
    }
  }
  return best[2];
}

/** Jämkade uddatalsmetoden. Returnerar [mandat per parti, jämförelsetal per tilldelat mandat]. */
export function jamkade(
  votes: Votes,
  nSeats: number,
  start?: SeatsByParty,
): [SeatsByParty, Record<string, number[]>] {
  const parties = Object.keys(votes);
  const seats: SeatsByParty = {};
  const won: Record<string, number[]> = {};
  for (const p of parties) {
    seats[p] = start?.[p] ?? 0;
    won[p] = [];
  }
  for (let i = 0; i < nSeats; i++) {
    const cands: Cand[] = [];
    for (const p of parties) {
      const v = votes[p];
      if (v > 0) cands.push([v / divisor(seats[p]), v, p]);
    }
    if (cands.length === 0) break;
    const p = pick(cands);
    won[p].push(votes[p] / divisor(seats[p]));
    seats[p] += 1;
  }
  return [seats, won];
}

export interface Constituency {
  name: string;
  fixed_seats: number;
  valid_votes: number;
  votes: Votes;
}

export interface RiksdagResult {
  fixed: Record<string, SeatsByParty>;
  adjustment: Record<string, SeatsByParty>;
  total: SeatsByParty;
  entitlement: SeatsByParty;
  eligible: string[];
  returned: [string, string][];
}

export function sumRows(rows: Record<string, SeatsByParty>): SeatsByParty {
  const out: SeatsByParty = {};
  for (const row of Object.values(rows)) for (const [p, n] of Object.entries(row)) out[p] = (out[p] ?? 0) + n;
  return out;
}

export function allocateRiksdag(
  constituencies: Constituency[],
  nationalVotes: Votes,
  nationalValid: number,
  totalSeats = 349,
): RiksdagResult {
  const eligible = Object.keys(nationalVotes)
    .filter((p) => nationalVotes[p] / nationalValid >= NATIONAL_THRESHOLD)
    .sort(cmpStr);
  const isEligible = new Set(eligible);

  // 1. Fasta valkretsmandat
  const fixed: Record<string, SeatsByParty> = {};
  const quotients: [q: number, v: number, vk: string, p: string][] = [];
  for (const c of constituencies) {
    const part: Votes = {};
    for (const [p, v] of Object.entries(c.votes)) {
      if (isEligible.has(p) || v / c.valid_votes >= CONSTITUENCY_THRESHOLD) part[p] = v;
    }
    const [seats, won] = jamkade(part, c.fixed_seats);
    const row: SeatsByParty = {};
    for (const [p, n] of Object.entries(seats)) if (n) row[p] = n;
    fixed[c.name] = row;
    for (const [p, qs] of Object.entries(won)) for (const q of qs) quotients.push([q, part[p], c.name, p]);
  }

  // 2. Hela landets fördelning (lokala 12 %-mandat dras av)
  let localOnly = 0;
  for (const row of Object.values(fixed)) for (const [p, n] of Object.entries(row)) if (!isEligible.has(p)) localOnly += n;
  const natVotes: Votes = {};
  for (const p of eligible) natVotes[p] = nationalVotes[p];
  const [entitlement] = jamkade(natVotes, totalSeats - localOnly);

  // 3. Återföring vid överhäng: lägst jämförelsetal först
  const returned: [string, string][] = [];
  const fixedTot: SeatsByParty = {};
  for (const p of eligible) {
    let s = 0;
    for (const row of Object.values(fixed)) s += row[p] ?? 0;
    fixedTot[p] = s;
  }
  for (const p of eligible) {
    const excess = fixedTot[p] - entitlement[p];
    if (excess > 0) {
      const own = quotients
        .filter((t) => t[3] === p)
        .map((t) => [t[0], -t[1], t[2]] as [number, number, string])
        .sort((a, b) => a[0] - b[0] || a[1] - b[1] || cmpStr(a[2], b[2]));
      for (const [, , vk] of own.slice(0, excess)) {
        fixed[vk][p] -= 1;
        if (fixed[vk][p] === 0) delete fixed[vk][p];
        returned.push([vk, p]);
      }
      fixedTot[p] -= excess;
    }
  }

  // 4. Utjämningsmandat, placerade med ojämkad uddatal
  const adjustment: Record<string, SeatsByParty> = {};
  for (const c of constituencies) adjustment[c.name] = {};
  for (const p of eligible) {
    const need = entitlement[p] - fixedTot[p];
    for (let i = 0; i < Math.max(0, need); i++) {
      const cands: Cand[] = [];
      for (const c of constituencies) {
        const v = c.votes[p] ?? 0;
        if (v <= 0) continue;
        const k = (fixed[c.name][p] ?? 0) + (adjustment[c.name][p] ?? 0);
        cands.push([v / placementDivisor(k), v, c.name]);
      }
      const vk = pick(cands);
      adjustment[vk][p] = (adjustment[vk][p] ?? 0) + 1;
    }
  }

  const total: SeatsByParty = {};
  for (const row of [...Object.values(fixed), ...Object.values(adjustment)]) {
    for (const [p, n] of Object.entries(row)) total[p] = (total[p] ?? 0) + n;
  }
  return { fixed, adjustment, total, entitlement, eligible, returned };
}
