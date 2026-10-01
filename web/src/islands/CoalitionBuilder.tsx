import { useEffect, useMemo, useState } from "react";
import { PARTIES, PARTY_COLORS, PARTY_NAMES } from "@contracts/constants";
import { fetchManifest } from "../lib/client/release";
import { fetchVerifiedBytes } from "../lib/islands/verifiedBytes";
import { coalitionStats } from "../lib/islands/stats";
import { displayPct, verbal } from "../lib/text/scale";

type Columns = Record<string, ArrayLike<number>>;

async function loadDraws(): Promise<Columns> {
  const m = await fetchManifest();
  const buf = await fetchVerifiedBytes(m, "open/draws.parquet");
  const { parquetReadObjects } = await import("hyparquet");
  const columns = PARTIES.map((p) => `seats_${p}`);
  const rows = (await parquetReadObjects({ file: buf, columns })) as Record<string, number>[];
  const out: Columns = {};
  for (const p of PARTIES) out[p] = Int16Array.from(rows, (r) => Number(r[`seats_${p}`]));
  return out;
}

export default function CoalitionBuilder({ initial = ["S", "V", "MP", "C"] }: { initial?: string[] }) {
  const [cols, setCols] = useState<Columns | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>(initial);

  useEffect(() => {
    loadDraws().then(setCols).catch((e: Error) => setError(
      /compression|codec|unsupported/i.test(e.message)
        ? "Dragningsfilen är komprimerad med ett format som webbläsaren inte kan läsa ännu."
        : e.message,
    ));
  }, []);

  const stats = useMemo(() => (cols ? coalitionStats(cols, picked) : null), [cols, picked]);
  const toggle = (p: string) => setPicked((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));
  const maxBin = stats ? Math.max(1, ...stats.histogram.values()) : 1;
  const bins = stats ? [...stats.histogram.entries()].sort((a, b) => a[0] - b[0]) : [];

  return (
    <section className="card" aria-labelledby="cb-h">
      <h3 id="cb-h" style={{ marginTop: 0 }}>Bygg en egen koalition</h3>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="small muted">Välj partier. Sannolikheten räknas på simuleringens dragningar (samma som ovan).</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1rem", marginTop: "0.5rem" }}>
          {PARTIES.map((p) => (
            <label key={p} style={{ whiteSpace: "nowrap" }}>
              <input type="checkbox" checked={picked.includes(p)} onChange={() => toggle(p)} />{" "}
              <span className="swatch" style={{ background: PARTY_COLORS[p] }} />{PARTY_NAMES[p]}
            </label>
          ))}
        </div>
      </fieldset>
      <div aria-live="polite" style={{ marginTop: "0.75rem" }}>
        {error && <p className="banner error" role="alert">{error}</p>}
        {!cols && !error && <p className="muted">Laddar dragningarna …</p>}
        {stats && (
          <>
            <p>
              {picked.length ? picked.join(" + ") : "Inga partier valda"}: egen majoritet (minst 175 mandat) med{" "}
              <strong>{displayPct(stats.prob)}</strong> sannolikhet ({verbal(stats.prob).toLocaleLowerCase("sv-SE")}).
              Median {stats.median} mandat, 90 % intervall {stats.p5}–{stats.p95}.
            </p>
            <svg className="chart" viewBox="0 0 760 120" role="img" aria-label={`Fördelning av koalitionens mandat, median ${stats.median}`}>
              {bins.map(([seats, count]) => {
                const x = 10 + (seats / 349) * 740;
                const h = (count / maxBin) * 90;
                return <rect key={seats} x={x} y={100 - h} width={2} height={h} fill={seats >= 175 ? "#1f8f78" : "#aaa"} />;
              })}
              <line x1={10 + (175 / 349) * 740} x2={10 + (175 / 349) * 740} y1={4} y2={100} stroke="#111" strokeDasharray="4 3" />
              <text x={14 + (175 / 349) * 740} y={14} fontSize="11">175</text>
              <text x={10} y={116} fontSize="11" fill="#5c5f63">0</text>
              <text x={750} y={116} fontSize="11" fill="#5c5f63" textAnchor="end">349</text>
            </svg>
          </>
        )}
      </div>
    </section>
  );
}
