/**
 * Golden tests för TS-porten av mandatberäkningen. Facit:
 *  - Valmyndighetens officiella utfall 2022 och 2026 (tests/golden/riksdag_*.json)
 *  - syntetiska kantfall (tests/golden/synthetic.json, samma som tests/test_vallag.py)
 *  - slumpade fall med Pythons resultat (tests/golden/random_seat_cases.json)
 * Resultaten ska vara identiska med Python, inte bara rimliga.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { allocateRiksdag, jamkade, pySum, type Constituency } from "../src/lib/seats";
import { allocateAllMandates, type SeatModel } from "../src/lib/seatModel";

const GOLDEN = fileURLToPath(new URL("../../tests/golden/", import.meta.url));
const load = (name: string) => JSON.parse(readFileSync(GOLDEN + name, "utf-8"));

describe("officiella utfall", () => {
  for (const year of [2022, 2026]) {
    it(`återskapar ${year} exakt per valkrets`, () => {
      const g = load(`riksdag_${year}.json`);
      const r = allocateRiksdag(g.constituencies, g.national_votes, g.valid_votes, g.total_seats);
      expect(r.total).toEqual(g.official_total);
      expect(Object.values(r.total).reduce((a: number, b) => a + (b as number), 0)).toBe(349);
      for (const c of g.constituencies) {
        expect(r.fixed[c.name], c.name).toEqual(c.official_fixed);
        expect(r.adjustment[c.name], c.name).toEqual(c.official_adjustment);
      }
      expect(r.returned).toEqual([]);
    });
  }
});

describe("syntetiska kantfall", () => {
  const cases = load("synthetic.json").cases as any[];
  const run = (id: string) => {
    const c = cases.find((x) => x.id === id);
    return [c, allocateRiksdag(c.constituencies, c.national_votes, c.national_valid, c.total_seats)] as const;
  };

  it("lika jämförelsetal avgörs deterministiskt", () => {
    const [c, r] = run("lika-jamforelsetal");
    expect(r.total).toEqual(c.expected.total);
    expect(r.fixed).toEqual(c.expected.fixed);
  });

  it("parti precis på spärren deltar", () => {
    const [c, r] = run("precis-pa-sparren");
    expect(r.eligible).toEqual(c.expected_eligible);
    expect(r.total.D).toBeUndefined();
    expect(Object.values(r.total).reduce((a, b) => a + b, 0)).toBe(c.total_seats);
  });

  it("12 % i valkrets ger bara fasta mandat där", () => {
    const [c, r] = run("tolv-procent-i-valkrets");
    expect(r.eligible).toEqual(c.expected_eligible);
    expect(r.fixed.K2.L ?? 0).toBe(1);
    expect(r.entitlement.L).toBeUndefined();
    expect(Object.values(r.entitlement).reduce((a, b) => a + b, 0)).toBe(c.total_seats - r.fixed.K2.L);
    expect(r.total.L).toBe(1);
    expect(Object.values(r.total).reduce((a, b) => a + b, 0)).toBe(c.total_seats);
  });

  it("återföring vid överhäng", () => {
    const [c, r] = run("aterforing-vid-overhang");
    const [ent] = jamkade(c.national_votes, c.total_seats);
    expect(r.entitlement).toEqual(ent);
    expect(ent.R).toBe(1);
    expect(r.total.R).toBe(ent.R);
    expect(Object.values(r.total).reduce((a, b) => a + b, 0)).toBe(c.total_seats);
    expect(r.returned).toContainEqual(["K3", "R"]);
    expect(r.returned).toHaveLength(2);
    expect(r.fixed.K3.R ?? 0).toBe(0);
  });

  it("jämkade metoden: första divisor 1,2", () => {
    const [seats, won] = jamkade({ A: 120, B: 100 }, 1);
    expect(seats).toEqual({ A: 1, B: 0 });
    expect(won.A).toEqual([100]);
    expect(jamkade({ A: 120, B: 100 }, 2)[0]).toEqual({ A: 1, B: 1 });
  });
});

describe("slumpade fall identiska med Python", () => {
  const data = load("random_seat_cases.json");
  const model = data.seat_model as SeatModel;

  for (const c of data.riksdag_cases as any[]) {
    it(c.id, () => {
      const r = allocateRiksdag(c.constituencies as Constituency[], c.national_votes, c.national_valid, c.total_seats);
      expect(r.fixed).toEqual(c.expected.fixed);
      expect(r.adjustment).toEqual(c.expected.adjustment);
      expect(r.total).toEqual(c.expected.total);
      expect(r.entitlement).toEqual(c.expected.entitlement);
      expect(r.eligible).toEqual(c.expected.eligible);
      expect(r.returned).toEqual(c.expected.returned);
    });
  }

  for (const c of data.shares_cases as any[]) {
    it(c.id, () => {
      const m = allocateAllMandates(c.shares, model);
      for (const [k, v] of Object.entries(c.expected)) {
        // Flyttal jämförs exakt (toEqual på number är ===): samma aritmetik som Python.
        expect((m as any)[k], k).toEqual(v);
      }
    });
  }
});

describe("pySum", () => {
  it("kompenserad summering som Python ≥ 3.12", () => {
    // sum([0.1]*10) == 1.0 i Python 3.12+, men 0.9999999999999999 med naiv summering
    expect(pySum(Array(10).fill(0.1))).toBe(1);
    expect(pySum([1e16, 1, -1e16])).toBe(1);
  });
});
