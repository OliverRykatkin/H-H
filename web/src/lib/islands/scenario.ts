/** Scenarioberäkning: egna andelar → mandat med samma motor som pipelinen (seatModel.ts). */
import { BLOC_PARTIES, TOTAL_SEATS, THRESHOLD } from "@contracts/constants";
import { allocateAllMandates, type SeatModel } from "../seatModel";

export interface ScenarioResult {
  total: Record<string, number>;
  /** Andel av alla giltiga röster som spärren prövas mot. */
  shareAll: Record<string, number>;
  belowThreshold: string[];
  blocs: { name: string; seats: number; majority: boolean }[];
  sum8: number;
}

export function runScenario(shares: Record<string, number>, model: SeatModel): ScenarioResult {
  const clean: Record<string, number> = {};
  for (const p of model.parties) clean[p] = Number.isFinite(shares[p]) ? Math.max(0, shares[p]) : 0;
  const alloc = allocateAllMandates(clean, model);
  const total: Record<string, number> = {};
  for (const p of model.parties) total[p] = alloc.total[p] ?? 0;
  const majority = Math.floor(TOTAL_SEATS / 2) + 1;
  return {
    total,
    shareAll: alloc.share_all,
    belowThreshold: model.parties.filter((p) => (alloc.share_all[p] ?? 0) < THRESHOLD),
    blocs: Object.entries(BLOC_PARTIES).map(([name, ps]) => {
      const seats = ps.reduce((s, p) => s + (total[p] ?? 0), 0);
      return { name, seats, majority: seats >= majority };
    }),
    sum8: model.parties.reduce((s, p) => s + clean[p], 0),
  };
}
