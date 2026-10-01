/** Ren logik för live-läget på valnatten: pollning med paus när fliken är dold, och texter. */
import type { NowcastLive } from "@contracts/contracts";
import { PARTY_NAMES } from "@contracts/constants";
import { formatInteger, formatNumber, list } from "../text/grammar";
import { clock } from "../text/time";

export const POLL_INTERVAL_MS = 45_000;

export interface FeedStatus {
  feedOk?: boolean;
  feedError?: string | null;
  feedCheckedAt?: string;
  feedUpdatedAt?: string | null;
}

interface DocLike {
  visibilityState: string;
  addEventListener(type: "visibilitychange", fn: () => void): void;
  removeEventListener(type: "visibilitychange", fn: () => void): void;
}

export interface PollerDeps {
  doc: DocLike;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (id: unknown) => void;
  interval?: number;
}

/**
 * Anropar tick var `interval` ms medan sidan syns. Pausar när fliken döljs och kör en
 * omedelbar tick när den blir synlig igen. Returnerar en stop-funktion.
 */
export function startPoller(tick: () => unknown, deps: PollerDeps): () => void {
  const interval = deps.interval ?? POLL_INTERVAL_MS;
  let timer: unknown = null;
  let stopped = false;
  const schedule = () => {
    if (stopped || deps.doc.visibilityState === "hidden") return;
    timer = deps.setTimer(async () => {
      timer = null;
      try { await tick(); } finally { schedule(); }
    }, interval);
  };
  const onVisibility = () => {
    if (deps.doc.visibilityState === "hidden") {
      if (timer != null) deps.clearTimer(timer);
      timer = null;
    } else if (timer == null && !stopped) {
      Promise.resolve(tick()).finally(schedule);
    }
  };
  deps.doc.addEventListener("visibilitychange", onVisibility);
  schedule();
  return () => {
    stopped = true;
    if (timer != null) deps.clearTimer(timer);
    deps.doc.removeEventListener("visibilitychange", onVisibility);
  };
}

/** "21.30" ur flödets tid, eller null. */
export function updatedClock(nc: Pick<NowcastLive, "feedUpdatedAt">): string | null {
  return nc.feedUpdatedAt ? clock(nc.feedUpdatedAt) : null;
}

/** Löptext om läget, t.ex. "Klockan 22.00 var 1 752 av 6 312 valdistrikt räknade (25 procent av rösterna)." */
export function liveSummary(nc: NowcastLive): string {
  const t = updatedClock(nc);
  const share = Math.round(nc.voteShareCounted * 100);
  const head = `${t ? `Klockan ${t} var` : "Hittills är"} ${formatInteger(nc.nCounted)} av ${formatInteger(nc.nTotal)} valdistrikt räknade (${share} procent av rösterna).`;
  const lead = [...nc.blocs].sort((a, b) => b.seats - a.seats)[0];
  if (!lead || nc.nCounted === 0) return head;
  const majority = lead.seats >= 175 ? "egen majoritet" : "inte egen majoritet";
  const big = Object.entries(nc.nowcast).sort((a, b) => b[1] - a[1])[0];
  return `${head} Enligt nowcasten får ${lead.name} ${formatInteger(lead.seats)} av 349 mandat och därmed ${majority}. ` +
    `Största parti är ${PARTY_NAMES[big[0]] ?? big[0]} med ${formatNumber(big[1] * 100, 1)} procent.`;
}

/** Varningstext om Valmyndighetens flöde inte svarar, annars null. Okänd/tom status → ingen varning. */
export function feedWarning(status: FeedStatus | null | undefined, nc: Pick<NowcastLive, "feedUpdatedAt">): string | null {
  if (!status || status.feedOk !== false) return null;
  const t = updatedClock(nc);
  return `Valmyndighetens resultat svarar inte just nu — siffrorna är från ${t ? `klockan ${t}` : "senaste lyckade hämtningen"}.`;
}

/** Partier som enligt nowcasten hamnar under 4 %-spärren. */
export function belowThreshold(nc: Pick<NowcastLive, "nowcast">): string | null {
  const under = Object.entries(nc.nowcast).filter(([, v]) => v < 0.04).map(([p]) => PARTY_NAMES[p] ?? p);
  return under.length ? `Under spärren: ${list(under)}.` : null;
}
