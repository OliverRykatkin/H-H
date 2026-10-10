import type { APIRoute } from "astro";
import { PARTIES } from "@contracts/constants";
import * as D from "../../lib/data";

/** Mätpunkter till trendgraferna (hämtas lazy av chartHover): [datum, institutindex, ...andel per parti]. */
export const GET: APIRoute = () => {
  const from = D.timeseries().dates[0];
  const inst: string[] = [];
  const rows = D.polls().polls
    .map((p) => ({ p, d: p.fieldTo ?? p.published }))
    .filter(({ d }) => d >= from)
    .sort((a, b) => a.d.localeCompare(b.d))
    .map(({ p, d }) => {
      let i = inst.indexOf(p.institute);
      if (i < 0) i = inst.push(p.institute) - 1;
      return [d, i, ...PARTIES.map((k) => (p.shares[k] == null ? null : Math.round(p.shares[k] * 10) / 10))];
    });
  return new Response(JSON.stringify({ parties: PARTIES, inst, polls: rows }), { headers: { "Content-Type": "application/json" } });
};
