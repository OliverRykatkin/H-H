import { useEffect, useRef, useState } from "react";
import { formatInteger, formatNumber } from "../lib/text/grammar";
import type { Manifest, ValnattState } from "@contracts/contracts";
import { PARTIES, PARTY_COLORS, PARTY_NAMES } from "@contracts/constants";
import { fetchManifest, fetchVerified } from "../lib/client/release";
import { valnattIngress } from "../lib/text/ingress";

interface Props { times: string[]; initialTime: string; initial: ValnattState }

// Handskriven formatering (lib/text/grammar): samma tecken i Node och webbläsare → ingen hydreringsdiff.
const fmt1 = { format: (v: number) => formatNumber(v, 1) };
const fmt2 = { format: (v: number) => formatNumber(v, 2) };
const label = (hhmm: string) => `${hhmm.slice(0, 2)}.${hhmm.slice(2)}`;

export default function ValnattReplay({ times, initialTime, initial }: Props) {
  const [idx, setIdx] = useState(Math.max(0, times.indexOf(initialTime)));
  const [state, setState] = useState<ValnattState>(initial);
  const [error, setError] = useState<string | null>(null);
  const manifest = useRef<Promise<Manifest> | null>(null);
  const cache = useRef(new Map<string, ValnattState>([[initialTime, initial]]));

  useEffect(() => {
    const t = times[idx];
    const hit = cache.current.get(t);
    if (hit) { setState(hit); return; }
    manifest.current ??= fetchManifest();
    let live = true;
    manifest.current
      .then((m) => fetchVerified<ValnattState>(m, `valnatt/2026/${t}.json`))
      .then((s) => { cache.current.set(t, s); if (live) { setState(s); setError(null); } })
      .catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [idx, times]);

  const max = Math.max(...PARTIES.map((p) => Math.max(state.final[p] ?? 0, state.nowcast[p] ?? 0, state.raw?.[p] ?? 0))) * 100;
  const yMax = Math.ceil(max / 5) * 5 + 5;
  const W = 760, H = 260, L = 34, B = 24, T = 10;
  const gw = (W - L) / PARTIES.length;
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);

  return (
    <section aria-labelledby="vn-h">
      <h2 id="vn-h">Spela upp natten</h2>
      <label htmlFor="vn-time"><strong>Klockan {label(times[idx])}</strong> (13–14 september 2026)</label>
      <input
        id="vn-time" type="range" min={0} max={times.length - 1} step={1} value={idx}
        onChange={(e) => setIdx(parseInt(e.target.value, 10))}
        aria-valuetext={`klockan ${label(times[idx])}`} style={{ width: "100%" }}
      />
      {error && <p className="banner error" role="alert">{error}</p>}
      <div aria-live="polite">
        <p className="lede">{valnattIngress(state)}</p>
        <div className="grid grid-4">
          <div className="card metric"><div className="label">Räknade distrikt</div><div className="value">{formatInteger(state.nCounted)}</div><div className="sub">av {formatInteger(state.nTotal)}</div></div>
          <div className="card metric"><div className="label">Andel av rösterna</div><div className="value">{Math.round(state.voteShareCounted * 100)} %</div></div>
          <div className="card metric"><div className="label">Fel, råräkning</div><div className="value">{state.maeRaw == null ? "–" : `${fmt2.format(state.maeRaw)} pe`}</div><div className="sub">snitt per parti</div></div>
          <div className="card metric"><div className="label">Fel, nowcast</div><div className="value">{fmt2.format(state.maeNowcast)} pe</div><div className="sub">snitt per parti</div></div>
        </div>
      </div>
      <figure>
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Råräkning, nowcast och slutresultat per parti">
          {[0, 10, 20, 30].filter((v) => v <= yMax).map((v) => (
            <g key={v}><line x1={L} x2={W} y1={y(v)} y2={y(v)} stroke="#ebebeb" /><text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#5c5f63">{v}</text></g>
          ))}
          {PARTIES.map((p, i) => {
            const x0 = L + i * gw + gw * 0.15, bw = gw * 0.32;
            const raw = (state.raw?.[p] ?? 0) * 100, nc = state.nowcast[p] * 100, fin = state.final[p] * 100;
            return (
              <g key={p}>
                {state.raw && <rect x={x0} y={y(raw)} width={bw} height={y(0) - y(raw)} fill="#c8c8c8"><title>Råräkning {fmt1.format(raw)} %</title></rect>}
                <rect x={x0 + bw} y={y(nc)} width={bw} height={y(0) - y(nc)} fill={PARTY_COLORS[p]}><title>Nowcast {fmt1.format(nc)} %</title></rect>
                <path d={`M${x0 + bw * 1.5},${y(fin) - 6} l6,6 l-6,6 l-6,-6 z`} fill="#111"><title>Slutresultat {fmt1.format(fin)} %</title></path>
                <text x={x0 + bw} y={H - 6} textAnchor="middle" fontSize="12">{p}</text>
              </g>
            );
          })}
        </svg>
        <figcaption className="small muted">Grå = råräkning, färg = nowcast, svart romb = slutresultat 2026.</figcaption>
      </figure>
      <div className="table-scroll">
        <table>
          <caption>Röstandel och mandat enligt nowcasten klockan {label(times[idx])}.</caption>
          <thead><tr><th>Parti</th><th className="r">Råräkning</th><th className="r">Nowcast</th><th className="r">Slutresultat</th><th className="r">Mandat (nowcast)</th></tr></thead>
          <tbody>
            {PARTIES.map((p) => (
              <tr key={p}>
                <td>{PARTY_NAMES[p]}</td>
                <td className="r">{state.raw ? `${fmt1.format(state.raw[p] * 100)} %` : "–"}</td>
                <td className="r">{fmt1.format(state.nowcast[p] * 100)} %</td>
                <td className="r">{fmt1.format(state.final[p] * 100)} %</td>
                <td className="r">{state.seats[p] ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
