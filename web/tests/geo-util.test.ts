import { describe, expect, it } from "vitest";
import { CONSTITUENCIES } from "@contracts/constants";
import { kommunSlugs, kommunerInRegion, kommunerInValkrets, regionForKommun, valkretsForKommun } from "../src/components/GeoUtil";
import { kommuner, regioner } from "../src/lib/data";

describe("geografi", () => {
  it("varje kommun har en unik URL-slug (Habo/Håbo får kod)", () => {
    const slugs = [...kommunSlugs().values()];
    expect(slugs).toHaveLength(290);
    expect(new Set(slugs).size).toBe(290);
    expect(slugs).toContain("habo-0643");
    expect(slugs).toContain("habo-0305");
    expect(kommunSlugs().get("0180")).toBe("stockholm");
  });

  it("varje kommun ligger i exakt en riksdagsvalkrets och alla 29 valkretsar täcks", () => {
    const names = new Set(kommuner().map((k) => valkretsForKommun(k.code)));
    expect(names.has(undefined)).toBe(false);
    expect([...names].sort()).toEqual(Object.keys(CONSTITUENCIES).sort());
    expect(kommunerInValkrets("Stockholms stad").map((k) => k.code)).toEqual(["0180"]);
    expect(kommunerInValkrets("Malmö").map((k) => k.code)).toEqual(["1280"]);
  });

  it("kommuner hittar sin region; Gotland saknar regionval", () => {
    expect(regionForKommun("0180")?.name).toBe("Stockholm");
    expect(regionForKommun("0980")).toBeUndefined();
    const total = regioner().reduce((n, r) => n + kommunerInRegion(r.code).length, 0);
    expect(total).toBe(289);
  });
});
