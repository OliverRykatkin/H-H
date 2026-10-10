import { useEffect, useState } from "react";
import type { EuNowcastLive, Manifest } from "@contracts/contracts";
import { PARTIES, PARTY_COLORS, PARTY_NAMES } from "@contracts/constants";
import { dataBase, fetchManifest, fetchVerified } from "../lib/client/release";
import { formatInteger, formatNumber } from "../lib/text/grammar";
import { belowThreshold, euLiveSummary, feedWarning, updatedClock, type FeedStatus } from "../lib/islands/livePoll";

interface Props { initial: EuNowcastLive | null }

const ORDER = ["V", "S", "MP", "C", "L", "KD", "M", "SD"];

async function loadStatus(): Promise<FeedStatus | null> {
  try {
    const r = await fetch(`${dataBase()}/status.json`, { cache: "no-cache" });
    return r.ok ? ((await r.json()) as FeedStatus) : null;
  } catch {
    return null;
  }
}

/** Live-läget på EU-valnatten. Renderar inget förrän EU-releasen har mode "nowcast". */
export default function EuValnattLive({ initial }: Props) {
  const [nc, setNc] = useState<EuNowcastLive | null>(initial);
  const [status, setStatus] = useState<FeedStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let lastRelease = "";
    const refresh = async (m: Manifest) => {
      if (m.mode !== "nowcast" || !m.files.some((f) => f.path === "nowcast.json")) return;
      const st = await loadStatus();
      if (alive) setStatus(st);
      if (m.release === lastRelease) return;
      try {
        const data = await fetchVerified<EuNowcastLive>(m, "nowcast.json");
        if (!alive) return;
        lastRelease = m.release;
        setNc(data);
        setError(null);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    const onNowcast = (ev: Event) => { void refresh((ev as CustomEvent<Manifest>).detail); };
    document.addEventListener("mandatorn:nowcast", onNowcast);
    fetchManifest().then(refresh).catch(() => undefined);
    return () => { alive = false; document.removeEventListener("mandatorn:nowcast", onNowcast); };
  }, []);

  if (!nc) return null;
  const year = nc.election.slice(0, 4);
  const warning = feedWarning(status, nc);
  const under = belowThreshold(nc);
  const t = updatedClock(nc);
  const max = Math.max(...PARTIES.map((p) => Math.max(nc.nowcast[p] ?? 0, nc.raw[p] ?? 0))) * 100;
  const yMax = Math.ceil(max / 5) * 5 + 5;
  const W = 760, H = 240, L = 34, B = 24, T = 10;
  const gw = (W - L) / PARTIES.length;
  const bw = gw * 0.34;
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);
  const seated = ORDER.filter((p) => (nc.seats[p] ?? 0) > 0);
  const majority = Math.floor(nc.seatsTotal / 2) + 1;

  return (
    <section className="card valnatt-live" aria-labelledby="evl-h" aria-live="polite">
      <h2 id="evl-h" style={{ marginTop: 0 }}>EU-valnatten {year} — live</h2>
      {warning && <p className="banner warn" role="status">{warning}</p>}
      {error && <p className="banner error" role="alert">Kunde inte hämta senaste nowcasten: {error}</p>}
      <p>{euLiveSummary(nc)}</p>
      <div className="grid grid-3">
        <div className="metric"><div className="label">Räknade distrikt</div><div className="value">{formatInteger(nc.nCounted)}</div><div className="sub">av {formatInteger(nc.nTotal)}</div></div>
        <div className="metric"><div className="label">Andel av rösterna</div><div className="value">{formatInteger(Math.round(nc.voteShareCounted * 100))} %</div><div className="sub">jämfört med förra valet</div></div>
        <div className="metric"><div className="label">Uppdaterat</div><div className="value">{t ?? "–"}</div><div className="sub">Valmyndighetens räkning</div></div>
      </div>

      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Råräkning och nowcast per parti">
        {[0, 10, 20, 30, 40].filter((v) => v <= yMax).map((v) => (
          <g key={v}><line x1={L} x2={W} y1={y(v)} y2={y(v)} stroke="#ebebeb" /><text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#5c5f63">{v}</text></g>
        ))}
        {PARTIES.map((p, i) => {
          const x0 = L + i * gw + gw * 0.14;
          const raw = (nc.raw[p] ?? 0) * 100, now = (nc.nowcast[p] ?? 0) * 100;
          return (
            <g key={p}>
              <rect x={x0} y={y(raw)} width={bw} height={y(0) - y(raw)} fill="#c8c8c8" role="img" aria-label={`${PARTY_NAMES[p]} råräkning ${formatNumber(raw, 1)} %`} />
              <rect x={x0 + bw} y={y(now)} width={bw} height={y(0) - y(now)} fill={PARTY_COLORS[p]} role="img" aria-label={`${PARTY_NAMES[p]} nowcast ${formatNumber(now, 1)} %`} />
              <text x={x0 + bw} y={H - 8} textAnchor="middle" fontSize="12">{p}</text>
            </g>
          );
        })}
      </svg>
      <p className="small muted">Grå = råräkning, färg = nowcast (andel av alla röster). {under}</p>

      <h3>Mandat enligt nowcasten</h3>
      <div role="img" aria-label={seated.map((p) => `${PARTY_NAMES[p]} ${nc.seats[p]} mandat`).join(", ")}
        style={{ position: "relative", display: "flex", height: "2.2rem", borderRadius: 4, overflow: "hidden", border: "1px solid var(--c-border)" }}>
        {seated.map((p) => (
          <div key={p} style={{ flex: `${nc.seats[p]} 0 0`, background: PARTY_COLORS[p] }} />
        ))}
        <div aria-hidden="true" style={{ position: "absolute", top: 0, bottom: 0, left: `${((majority - 0.5) / nc.seatsTotal) * 100}%`, borderLeft: "2px dashed #111" }} />
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Parti</th><th className="r">Råräkning</th><th className="r">Nowcast</th><th className="r">Mandat</th></tr></thead>
          <tbody>
            {PARTIES.map((p) => (
              <tr key={p}>
                <td><span className="swatch" style={{ background: PARTY_COLORS[p] }} />{PARTY_NAMES[p]}</td>
                <td className="r">{formatNumber((nc.raw[p] ?? 0) * 100, 1)} %</td>
                <td className="r"><strong>{formatNumber((nc.nowcast[p] ?? 0) * 100, 1)} %</strong></td>
                <td className="r">{formatInteger(nc.seats[p] ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
