/**
 * Tidsberoende fraser, räknade mot releasens generatedAt (inte klientens klocka) och
 * valdatum, i Europe/Stockholm-dygn. Efter valdagen sägs aldrig "X dagar kvar".
 */
import { BASELINE_ELECTION_DATE, NEXT_ELECTION_DATE } from "@contracts/constants";
import { formatInteger, numberWord } from "./grammar";

const DAY_MS = 86_400_000;

/**
 * Kalenderdag (YYYY-MM-DD) i Europe/Stockholm. Tidsstämplar utan tidszon (som
 * releasens generatedAt, "2026-10-01T00:00:00") tolkas redan som svensk lokal tid.
 */
export function stockholmDay(iso: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(iso)) return iso.slice(0, 10);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Stockholm", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Antal kalenderdagar från a till b (b − a). */
export function daysBetween(a: string, b: string): number {
  const [ya, ma, da] = stockholmDay(a).split("-").map(Number);
  const [yb, mb, db] = stockholmDay(b).split("-").map(Number);
  return Math.round((Date.UTC(yb, mb - 1, db) - Date.UTC(ya, ma - 1, da)) / DAY_MS);
}

function year(date: string): string {
  return date.slice(0, 4);
}

function dayCount(n: number): string {
  return n === 1 ? "en dag" : `${n <= 12 ? numberWord(n) : formatInteger(n)} dagar`;
}

export type ElectionPhase = "before" | "electionDay" | "after";

export interface ElectionTiming {
  phase: ElectionPhase;
  /** Dagar kvar (before), 0 (electionDay) eller dagar sedan (after). */
  days: number;
  electionYear: string;
  electionDate: string;
}

/**
 * Var i valcykeln releasen befinner sig. Ligger generatedAt efter `nextElection`
 * räknas tiden sedan det valet; annars kvar till det.
 */
export function electionTiming(generatedAt: string, nextElection: string = NEXT_ELECTION_DATE): ElectionTiming {
  const d = daysBetween(generatedAt, nextElection);
  const base = { electionYear: year(nextElection), electionDate: nextElection };
  if (d > 0) return { phase: "before", days: d, ...base };
  if (d === 0) return { phase: "electionDay", days: 0, ...base };
  return { phase: "after", days: -d, ...base };
}

/**
 * Hel mening om tiden till eller från valet:
 *   "Det är 1 438 dagar kvar till valet 2030."
 *   "Det är en dag kvar till valet 2030."
 *   "I dag är det valdag."
 *   "Valet 2030 hölls i går." / "Valet 2030 hölls för 12 dagar sedan."
 */
export function electionCountdown(generatedAt: string, nextElection: string = NEXT_ELECTION_DATE): string {
  const t = electionTiming(generatedAt, nextElection);
  if (t.phase === "electionDay") return "I dag är det valdag.";
  if (t.phase === "after") {
    return t.days === 1 ? `Valet ${t.electionYear} hölls i går.` : `Valet ${t.electionYear} hölls för ${dayCount(t.days)} sedan.`;
  }
  return `Det är ${dayCount(t.days)} kvar till valet ${t.electionYear}.`;
}

/** Tid sedan baslinjevalet: "Riksdagsvalet 2026 hölls för 18 dagar sedan." (null före valet). */
export function sinceBaselineElection(generatedAt: string, baseline: string = BASELINE_ELECTION_DATE): string | null {
  const d = daysBetween(baseline, generatedAt);
  if (d < 0) return null;
  if (d === 0) return `Riksdagsvalet ${year(baseline)} hålls i dag.`;
  if (d === 1) return `Riksdagsvalet ${year(baseline)} hölls i går.`;
  return `Riksdagsvalet ${year(baseline)} hölls för ${dayCount(d)} sedan.`;
}

/** Klockslag i svensk stil: "2026-09-13T22:00:00" → "22.00". */
export function clock(iso: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}.${m[2]}` : iso;
}
