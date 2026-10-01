/** Hjälpare för geografisidorna (kommun/region/valkrets): unika sluggar och kopplingar. */
import type { Area } from "@contracts/contracts";
import mapping from "../../scripts/geo/kommun_valkrets.json";
import { kommuner, regioner } from "../lib/data";

const KOMMUN_VALKRETS: Record<string, string> = (mapping as { kommun_valkrets: Record<string, string> }).kommun_valkrets;

/** Kommunens URL-slug: Area.slug, med kod tillagd vid krock (t.ex. Habo/Håbo → habo). */
export function kommunSlugs(): Map<string, string> {
  const all = kommuner();
  const count = new Map<string, number>();
  for (const a of all) count.set(a.slug, (count.get(a.slug) ?? 0) + 1);
  return new Map(all.map((a) => [a.code, (count.get(a.slug) ?? 0) > 1 ? `${a.slug}-${a.code}` : a.slug]));
}

export function kommunHref(code: string): string {
  return `/kommun/${kommunSlugs().get(code)}/`;
}

export function regionHref(a: Area): string {
  return `/region/${a.slug}/`;
}

/** Regionen (län) en kommun ligger i; Gotland saknar regionval. */
export function regionForKommun(code: string): Area | undefined {
  return regioner().find((r) => r.code === code.slice(0, 2));
}

export function kommunerInValkrets(name: string): Area[] {
  return kommuner().filter((k) => KOMMUN_VALKRETS[k.code] === name);
}

export function kommunerInRegion(lan: string): Area[] {
  return kommuner().filter((k) => k.code.startsWith(lan));
}

export function valkretsForKommun(code: string): string | undefined {
  return KOMMUN_VALKRETS[code];
}

/** Sortera partier: riksdagspartierna först i vald ordning, därefter övriga efter storlek. */
export function partyOrder(values: Record<string, number>, national: readonly string[]): string[] {
  const rest = Object.keys(values).filter((p) => !national.includes(p)).sort((a, b) => values[b] - values[a]);
  return [...national.filter((p) => p in values), ...rest];
}
