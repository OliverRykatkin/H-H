import { describe, expect, it } from "vitest";
import { euLiveSummary } from "../src/lib/islands/livePoll";
import { eu } from "../src/lib/release";

const nc = {
  feedUpdatedAt: "2029-06-09T22:00:00+02:00", voteShareCounted: 0.11, nCounted: 700, nTotal: 6275,
  nowcast: { S: 0.25, M: 0.18, SD: 0.15 }, seats: { S: 5, M: 4, SD: 3 }, seatsTotal: 21,
};

describe("EU-valnatten", () => {
  it("sammanfattar läget med största parti och mandat av 21", () => {
    const s = euLiveSummary(nc);
    expect(s).toContain("700 av 6");
    expect(s).toContain("11 procent");
    expect(s).toContain("5 av 21 mandat");
  });

  it("säger inget om utfall innan något är räknat", () => {
    expect(euLiveSummary({ ...nc, nCounted: 0 })).not.toContain("största parti");
  });

  it("EU-releasen innehåller öppen data med schema", () => {
    expect(eu.paths("open/").filter((p) => p.endsWith(".csv")).sort()).toEqual(["open/eu_backtest.csv", "open/eu_partier.csv"]);
    expect(eu.hasFile("open/draws.parquet")).toBe(true);
  });
});
