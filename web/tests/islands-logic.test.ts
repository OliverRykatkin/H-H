import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { coalitionStats, percentile } from "@/lib/islands/stats";
import { runScenario } from "@/lib/islands/scenario";
import type { SeatModel } from "@/lib/seatModel";

describe("percentile (numpy linear)", () => {
  it("matchar numpy för jämna och udda längder", () => {
    expect(percentile([1, 2, 3, 4], 50)).toBe(2.5);
    expect(percentile([1, 2, 3, 4, 5], 5)).toBeCloseTo(1.2);
    expect(percentile([10], 95)).toBe(10);
  });
});

describe("coalitionStats", () => {
  it("summerar partier per dragning och räknar P(≥175)", () => {
    const seats = { A: [100, 90, 80, 70], B: [80, 85, 90, 95] }; // summor 180,175,170,165
    const s = coalitionStats(seats, ["A", "B"]);
    expect(s.n).toBe(4);
    expect(s.prob).toBe(0.5);
    expect(s.mean).toBe(172.5);
    expect(s.median).toBe(172);          // int(172.5)
    expect(s.histogram.get(175)).toBe(1);
  });
  it("tom koalition ger 0 mandat i alla dragningar", () => {
    const s = coalitionStats({ A: [1, 2] }, []);
    expect(s.n).toBe(2);
    expect(s.prob).toBe(0);
    expect(s.mean).toBe(0);
  });
});

describe("runScenario", () => {
  const golden = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, "../../tests/golden/random_seat_cases.json"), "utf-8"),
  ) as { seat_model: SeatModel };
  const model = golden.seat_model;

  it("fördelar 349 mandat och markerar partier under spärren", () => {
    const r = runScenario({ M: 20, L: 3.5, C: 7, KD: 6, S: 29, V: 9, MP: 6.5, SD: 19 }, model);
    expect(Object.values(r.total).reduce((a, b) => a + b, 0)).toBe(349);
    expect(r.total.L).toBe(0);
    expect(r.belowThreshold).toContain("L");
    expect(r.blocs.map((b) => b.name)).toEqual(["Högerblocket", "Vänsterblocket"]);
  });

  it("negativa och ogiltiga värden behandlas som 0", () => {
    const r = runScenario({ M: 25, L: -3, C: Number.NaN, KD: 6, S: 30, V: 10, MP: 6, SD: 23 }, model);
    expect(r.total.L).toBe(0);
    expect(r.total.C).toBe(0);
    expect(Object.values(r.total).reduce((a, b) => a + b, 0)).toBe(349);
  });
});
