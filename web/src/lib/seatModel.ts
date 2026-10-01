/**
 * Port av mandatorn_model/seats.py:allocate_all_mandates — nationella andelar →
 * röster per valkrets (uniform swing med nollsummerad sving) → vallagen (seats.ts).
 * Seat-modellen exporteras av mandatorn_model/seat_model_export.py.
 */
import { allocateRiksdag, pySum, sumRows, type Constituency, type SeatsByParty } from "./seats";

export interface SeatModelConstituency {
  name: string;
  seats: number;
  valid_votes: number | null;
  shares: Record<string, number>;
}

export interface SeatModel {
  version: number;
  parties: string[];
  baseline: Record<string, number>;
  baseline_others: number;
  total_seats: number;
  constituencies: SeatModelConstituency[];
}

export interface Allocation {
  fixed: Record<string, SeatsByParty>;
  adjustment: SeatsByParty;
  total: SeatsByParty;
  fixed_total: SeatsByParty;
  constituency_votes: Record<string, Record<string, number>>;
  eligible_parties: string[];
  national_norm: Record<string, number>;
  adjustment_by_constituency: Record<string, SeatsByParty>;
  returned: [string, string][];
  share_all: Record<string, number>;
  others: number;
}

function norm8(d: Record<string, number>, parties: string[]): Record<string, number> {
  const tot = pySum(parties.map((p) => d[p] ?? 0));
  const out: Record<string, number> = {};
  for (const p of parties) out[p] = tot > 0 ? ((d[p] ?? 0) / tot) * 100 : 0;
  return out;
}

/** seats.estimate_constituency_votes */
export function estimateConstituencyVotes(
  nationalEst: Record<string, number>,
  shares: Record<string, number>,
  model: SeatModel,
): Record<string, number> {
  const ps = model.parties;
  const nat = norm8(nationalEst, ps);
  const base = norm8(model.baseline, ps);
  const result: Record<string, number> = {};
  for (const p of ps) {
    const local = p in shares ? shares[p] : (model.baseline[p] ?? 0);
    result[p] = Math.max(0, local + nat[p] - base[p]);
  }
  const total = pySum(ps.map((p) => result[p]));
  if (!(total > 0)) return result;
  const out: Record<string, number> = {};
  for (const p of ps) out[p] = (result[p] / total) * 100;
  return out;
}

/** seats.allocate_all_mandates(national_est_raw, others=None) */
export function allocateAllMandates(
  nationalEstRaw: Record<string, number>,
  model: SeatModel,
  othersIn: number | null = null,
): Allocation {
  const ps = model.parties;
  const s8: Record<string, number> = {};
  for (const p of ps) s8[p] = Math.max(0, nationalEstRaw[p] ?? 0);
  const tot8 = pySum(ps.map((p) => s8[p]));
  const others = othersIn ?? (tot8 < 99.5 ? Math.max(0, 100 - tot8) : model.baseline_others);
  const shareAll: Record<string, number> = {};
  for (const p of ps) shareAll[p] = tot8 > 0 ? (s8[p] / tot8) * (100 - others) : 0;

  const constList: Constituency[] = [];
  const constVotes: Record<string, Record<string, number>> = {};
  for (const c of model.constituencies) {
    const cShares = estimateConstituencyVotes(shareAll, c.shares, model);
    const othersC = Math.max(0, 100 - pySum(ps.map((p) => c.shares[p] ?? 0)));
    const valid = c.valid_votes || c.seats * 25_000;
    constVotes[c.name] = cShares;
    const votes: Record<string, number> = {};
    for (const p of ps) votes[p] = ((((cShares[p] / 100) * (100 - othersC)) / 100) * valid);
    constList.push({ name: c.name, fixed_seats: c.seats, valid_votes: valid, votes });
  }
  const nationalValid = pySum(constList.map((c) => c.valid_votes));
  const nationalVotes: Record<string, number> = {};
  for (const p of ps) nationalVotes[p] = (shareAll[p] / 100) * nationalValid;
  const r = allocateRiksdag(constList, nationalVotes, nationalValid, model.total_seats);

  const fixed: Record<string, SeatsByParty> = {};
  for (const c of model.constituencies) {
    const row: SeatsByParty = {};
    for (const p of ps) row[p] = r.fixed[c.name][p] ?? 0;
    fixed[c.name] = row;
  }
  const fixedTotal: SeatsByParty = {};
  for (const p of ps) fixedTotal[p] = model.constituencies.reduce((s, c) => s + fixed[c.name][p], 0);
  const adjustment: SeatsByParty = {};
  for (const [p, n] of Object.entries(sumRows(r.adjustment))) if (n) adjustment[p] = n;
  const eligTotal = pySum(r.eligible.map((p) => shareAll[p]));
  const nationalNorm: Record<string, number> = {};
  if (eligTotal) for (const p of r.eligible) nationalNorm[p] = (shareAll[p] / eligTotal) * 100;
  const total: SeatsByParty = {};
  for (const p of ps) total[p] = r.total[p] ?? 0;
  const adjBy: Record<string, SeatsByParty> = {};
  for (const c of model.constituencies) adjBy[c.name] = { ...r.adjustment[c.name] };

  return {
    fixed, adjustment, total, fixed_total: fixedTotal, constituency_votes: constVotes,
    eligible_parties: r.eligible, national_norm: nationalNorm, adjustment_by_constituency: adjBy,
    returned: r.returned, share_all: shareAll, others,
  };
}
