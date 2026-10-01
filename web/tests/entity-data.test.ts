/** Entitetssidornas data: unika slug:ar och giltiga länkar mellan kandidat, parti och valkrets. */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { PARTIES } from "@contracts/constants";
import * as D from "../src/lib/data";
import { partyName, slugify } from "../src/lib/format";

describe("entitetssidor", () => {
  it("partisidornas slug:ar är unika", () => {
    const slugs = PARTIES.map((p) => slugify(partyName(p)));
    expect(new Set(slugs).size).toBe(PARTIES.length);
    expect(slugs).toContain("moderaterna");
    expect(slugs).toContain("miljopartiet");
  });

  it("institutsidornas slug:ar är unika och täcker alla institut med data", () => {
    const inst = D.institutes();
    const names = new Set<string>([
      ...D.polls().polls.map((p) => p.institute),
      ...inst.bias.map((b) => String(b.institute)),
      ...inst.weights.map((w) => String(w.institute)),
    ]);
    const slugs = [...names].map(slugify);
    expect(new Set(slugs).size).toBe(names.size);
    expect(slugs.every((s) => /^[a-z0-9-]+$/.test(s))).toBe(true);
  });

  it("de invalda: 349 med unika slug:ar och kända valkretsar", () => {
    const el = D.elected();
    expect(el).not.toBeNull();
    const members = el!.members;
    expect(members).toHaveLength(349);
    expect(new Set(members.map((m) => m.slug)).size).toBe(349);
    const known = new Set(D.constituencies().map((c) => c.name));
    expect(members.filter((m) => !known.has(m.valkrets))).toEqual([]);
  });

  it("de invalda per parti = Valmyndighetens officiella totaler 2026", () => {
    const counts: Record<string, number> = {};
    for (const m of D.elected()!.members) counts[m.parti] = (counts[m.parti] ?? 0) + 1;
    const golden = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "tests", "golden", "riksdag_2026.json"), "utf-8"));
    expect(counts).toEqual(golden.official_total);
  });

  it("inga personuppgifter utöver namn, parti, valkrets och valgrund (D8)", () => {
    const keys = new Set(D.elected()!.members.flatMap((m) => Object.keys(m)));
    expect([...keys].sort()).toEqual(["kandidatnummer", "namn", "parti", "slug", "valgrund", "valkrets"]);
  });
});
