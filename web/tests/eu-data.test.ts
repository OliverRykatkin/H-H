/** EU-valets release: separat kedja under eu2029/, verifierad mot manifestet. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { PARTIES } from "@contracts/constants";
import { createReader, eu, manifest } from "../src/lib/release";
import { euBacktest, euNational, euSimulation } from "../src/lib/eu";

describe("EU-release", () => {
  it("är en egen kedja, skild från riksdagens", () => {
    expect(eu.manifest().release).not.toBe(manifest().release);
    expect(eu.dir.endsWith("eu2029")).toBe(true);
  });

  it("mandaten summerar till antalet i valet och simuleringen täcker alla partier", () => {
    const nat = euNational();
    expect(Object.values(nat.seats).reduce((a, b) => a + b, 0)).toBe(nat.seatsTotal);
    expect(euSimulation().parties.map((p) => p.party).sort()).toEqual([...PARTIES].sort());
    expect(nat.estimates.reduce((a, e) => a + e.share, 0)).toBeCloseTo(100, 3);
    expect(nat.electionDateProvisional).toBe(true);
  });

  it("backtesten har med båda valen", () => {
    expect(euBacktest().years.map((y) => y.year)).toEqual([2019, 2024]);
  });

  it("avvisar en fil vars innehåll inte stämmer med manifestet", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "eu-"));
    fs.cpSync(eu.dir, dir, { recursive: true });
    const e = eu.entry("national.json");
    fs.writeFileSync(path.join(dir, e.object), "{}");
    expect(() => createReader(dir, "x").readBytes("national.json")).toThrow();
  });
});
