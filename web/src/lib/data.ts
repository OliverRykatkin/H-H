/** Typade genvägar till releasens filer (vid bygget). */
import type {
  Archive, Area, Backtest, Elected, Constituency, Institutes, Mandates, Margins, National, Polls, Probabilities,
  Simulation, Timeseries, ValnattIndex,
} from "@contracts/contracts";
import { hasFile, paths, readJSON } from "./release";

export const national = () => readJSON<National>("national.json");
export const timeseries = () => readJSON<Timeseries>("timeseries.json");
export const polls = () => readJSON<Polls>("polls.json");
export const mandates = () => readJSON<Mandates>("mandates.json");
export const simulation = () => readJSON<Simulation>("simulation.json");
export const probabilities = () => readJSON<Probabilities>("probabilities.json");
export const margins = () => readJSON<Margins>("margins.json");
export const institutes = () => readJSON<Institutes>("institutes.json");
export const backtest = (year: number) => readJSON<Backtest>(`backtest/${year}.json`);
export const valnattIndex = () => (hasFile("valnatt/2026/index.json") ? readJSON<ValnattIndex>("valnatt/2026/index.json") : null);

export const constituencies = (): Constituency[] =>
  paths("valkrets/").map((p) => readJSON<Constituency>(p)).sort((a, b) => a.name.localeCompare(b.name, "sv"));
export const kommuner = (): Area[] =>
  paths("kommun/").map((p) => readJSON<Area>(p)).sort((a, b) => a.name.localeCompare(b.name, "sv"));
export const regioner = (): Area[] =>
  paths("region/").map((p) => readJSON<Area>(p)).sort((a, b) => a.name.localeCompare(b.name, "sv"));

/** Skattat stöd i dag med 90 % intervall, ur tidsserien (sista punkten). */
export function todayBand(key: string) {
  const ts = timeseries();
  const s = ts.series[key];
  if (!s) return null;
  const i = ts.dates.length - 1;
  return { p5: s.p5[i], p50: s.p50[i], p95: s.p95[i] };
}

export const elected = () => (hasFile("elected/2026.json") ? readJSON<Elected>("elected/2026.json") : null);
export const archive = (year: number) => (hasFile(`archive/${year}.json`) ? readJSON<Archive>(`archive/${year}.json`) : null);
