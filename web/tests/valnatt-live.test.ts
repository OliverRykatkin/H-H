import { describe, expect, it, vi } from "vitest";
import type { NowcastLive } from "@contracts/contracts";
import { NBSP } from "../src/lib/text/grammar";
import { POLL_INTERVAL_MS, belowThreshold, feedWarning, liveSummary, startPoller } from "../src/lib/islands/livePoll";

function fakeDoc(state = "visible") {
  const listeners: (() => void)[] = [];
  return {
    visibilityState: state,
    addEventListener: (_: string, fn: () => void) => listeners.push(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.splice(listeners.indexOf(fn), 1),
    fire() { listeners.forEach((f) => f()); },
    listeners,
  };
}

const nc: NowcastLive = {
  schemaVersion: 1, election: "2030-09-08", baselineYear: 2026, feedUpdatedAt: "2030-09-08T22:00:00",
  publishedAt: "2030-09-08T22:00:00", nCounted: 1752, nTotal: 6312, nComparable: 1500, voteShareCounted: 0.25,
  raw: { M: 0.2, L: 0.05, C: 0.07, KD: 0.06, S: 0.28, V: 0.08, MP: 0.06, SD: 0.18 },
  nowcast: { M: 0.205, L: 0.039, C: 0.07, KD: 0.062, S: 0.281, V: 0.084, MP: 0.061, SD: 0.175 },
  seats: { M: 76, L: 0, C: 26, KD: 23, S: 104, V: 31, MP: 23, SD: 66 }, fixedSeats: {},
  blocs: [{ name: "Högerblocket", parties: ["M", "L", "KD", "SD"], seats: 165, share: 48.1 },
          { name: "Vänsterblocket", parties: ["S", "V", "MP", "C"], seats: 184, share: 49.6 }],
  final: null,
};

describe("pollning", () => {
  it("pollar var 45:e sekund och pausar när fliken döljs", async () => {
    vi.useFakeTimers();
    const doc = fakeDoc();
    const tick = vi.fn();
    const stop = startPoller(tick, { doc, setTimer: (f, ms) => setTimeout(f, ms), clearTimer: (id) => clearTimeout(id as never) });
    expect(POLL_INTERVAL_MS).toBe(45_000);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(tick).toHaveBeenCalledTimes(1);
    doc.visibilityState = "hidden"; doc.fire();
    await vi.advanceTimersByTimeAsync(200_000);
    expect(tick).toHaveBeenCalledTimes(1);
    doc.visibilityState = "visible"; doc.fire();       // omedelbar tick vid återkomst
    await vi.advanceTimersByTimeAsync(0);
    expect(tick).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(tick).toHaveBeenCalledTimes(3);
    stop();
    await vi.advanceTimersByTimeAsync(100_000);
    expect(tick).toHaveBeenCalledTimes(3);
    expect(doc.listeners.length).toBe(0);
    vi.useRealTimers();
  });

  it("startar inte när fliken är dold från början", async () => {
    vi.useFakeTimers();
    const tick = vi.fn();
    startPoller(tick, { doc: fakeDoc("hidden"), setTimer: (f, ms) => setTimeout(f, ms), clearTimer: (id) => clearTimeout(id as never) });
    await vi.advanceTimersByTimeAsync(100_000);
    expect(tick).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("live-texter", () => {
  it("sammanfattar läget", () => {
    expect(liveSummary(nc)).toBe(
      `Klockan 22.00 var 1${NBSP}752 av 6${NBSP}312 valdistrikt räknade (25 procent av rösterna). ` +
      "Enligt nowcasten får Vänsterblocket 184 av 349 mandat och därmed egen majoritet. " +
      "Största parti är Socialdemokraterna med 28,1 procent.");
  });
  it("utan räknade distrikt bara läget", () => {
    expect(liveSummary({ ...nc, nCounted: 0, feedUpdatedAt: null })).toBe(`Hittills är 0 av 6${NBSP}312 valdistrikt räknade (25 procent av rösterna).`);
  });
  it("varnar bara när flödet uttryckligen svarar fel", () => {
    expect(feedWarning(null, nc)).toBeNull();
    expect(feedWarning({}, nc)).toBeNull();
    expect(feedWarning({ feedOk: true }, nc)).toBeNull();
    expect(feedWarning({ feedOk: false, feedError: "x" }, nc)).toBe("Valmyndighetens resultat svarar inte just nu — siffrorna är från klockan 22.00.");
    expect(feedWarning({ feedOk: false }, { feedUpdatedAt: null })).toBe("Valmyndighetens resultat svarar inte just nu — siffrorna är från senaste lyckade hämtningen.");
  });
  it("partier under spärren", () => {
    expect(belowThreshold(nc)).toBe("Under spärren: Liberalerna.");
    expect(belowThreshold({ nowcast: { M: 0.3 } })).toBeNull();
  });
});
