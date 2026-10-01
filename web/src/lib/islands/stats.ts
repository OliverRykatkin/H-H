/** Statistik över simuleringsdragningar — samma definitioner som numpy/Python i pipelinen. */

/** numpy.percentile med standardinterpolation ("linear"). */
export function percentile(sorted: ArrayLike<number>, q: number): number {
  const n = sorted.length;
  if (n === 0) return NaN;
  const pos = (q / 100) * (n - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(n - 1, lo + 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export interface CoalitionStats {
  n: number;
  prob: number;
  mean: number;
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
  histogram: Map<number, number>;
}

/** Summera valda partiers mandat per dragning → P(≥ majority) och fördelning (int(np.percentile) som i Python). */
export function coalitionStats(seats: Record<string, ArrayLike<number>>, parties: string[], majority = 175): CoalitionStats {
  const cols = parties.map((p) => seats[p]).filter(Boolean);
  const n = cols.length ? cols[0].length : Object.values(seats)[0]?.length ?? 0;
  const sums = new Float64Array(n);
  for (const c of cols) for (let i = 0; i < n; i++) sums[i] += c[i];
  let hits = 0, total = 0;
  const histogram = new Map<number, number>();
  for (let i = 0; i < n; i++) {
    if (sums[i] >= majority) hits++;
    total += sums[i];
    histogram.set(sums[i], (histogram.get(sums[i]) ?? 0) + 1);
  }
  const sorted = Float64Array.from(sums).sort();
  const pc = (q: number) => Math.trunc(percentile(sorted, q));
  return {
    n, prob: n ? hits / n : 0, mean: n ? total / n : 0,
    p5: pc(5), p25: pc(25), median: Math.trunc(percentile(sorted, 50)), p75: pc(75), p95: pc(95), histogram,
  };
}
