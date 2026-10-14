/**
 * Geometri för riksdagens hemicykel: 349 platser i koncentriska rader, sorterade vänster → höger
 * på vinkel så att varje parti får en kil. Delas av SSR (Hemicycle.astro) och klientens live-uppdatering.
 */
export const HEMI_ORDER = ["V", "S", "MP", "C", "L", "KD", "M", "SD"] as const;
export const HEMI_VIEWBOX = "0 -40 600 350";
export const HEMI_DOT = 12.4; // prickens diameter (strokebredd)
export const MAJORITY_SEAT = 175;

const CX = 300, CY = 300, R_IN = 150, R_OUT = 288, ROWS = 10;

interface Dot { x: number; y: number; a: number }
const r1 = (v: number) => Math.round(v * 10) / 10;

export function hemicycleDots(total: number): Dot[] {
  const radii = Array.from({ length: ROWS }, (_, k) => R_IN + (k * (R_OUT - R_IN)) / (ROWS - 1));
  const sum = radii.reduce((s, r) => s + r, 0);
  const counts = radii.map((r) => Math.round((total * r) / sum));
  counts[ROWS - 1] += total - counts.reduce((s, n) => s + n, 0);
  const dots: Dot[] = [];
  radii.forEach((r, k) => {
    for (let j = 0; j < counts[k]; j++) {
      const a = Math.PI * (1 - j / (counts[k] - 1));
      dots.push({ x: CX + r * Math.cos(a), y: CY - r * Math.sin(a), a });
    }
  });
  return dots.sort((p, q) => q.a - p.a || p.x - q.x);
}

/** En sökväg per parti (nollängdssegment med runda ändar = prickar), i HEMI_ORDER. */
export function wedgePaths(seats: Record<string, number>, total: number): { party: string; d: string }[] {
  const dots = hemicycleDots(total);
  let i = 0;
  return HEMI_ORDER.map((party) => {
    const n = seats[party] ?? 0;
    const d = dots.slice(i, i + n).map((p) => `M${r1(p.x)} ${r1(p.y)}h0`).join("");
    i += n;
    return { party, d };
  });
}

/** Radiell linje vid mandat 175 (första platsen som ger majoritet) + etikettens läge. */
export function majorityLine(total: number) {
  const a = hemicycleDots(total)[MAJORITY_SEAT - 1].a;
  const at = (r: number) => ({ x: r1(CX + r * Math.cos(a)), y: r1(CY - r * Math.sin(a)) });
  const from = at(R_IN - 16), to = at(R_OUT + 14), label = at(R_OUT + 30);
  return { x1: from.x, y1: from.y, x2: to.x, y2: to.y, lx: label.x, ly: label.y };
}

export const HEMI_NUMBER_X = { left: 236, right: 364 } as const;
export const HEMI_NUMBER_Y = 262;
