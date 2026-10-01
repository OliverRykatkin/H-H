import { useEffect, useMemo, useState } from "react";
import { formatNumber } from "../lib/text/grammar";
import { PARTIES, PARTY_COLORS, PARTY_NAMES, THRESHOLD, TOTAL_SEATS } from "@contracts/constants";
import { fetchManifest, fetchVerified } from "../lib/client/release";
import type { SeatModel } from "../lib/seatModel";
import { runScenario } from "../lib/islands/scenario";

interface Props {
  initial: Record<string, number>;
  baselineSeats: Record<string, number>;
}

// Handskriven formatering (lib/text/grammar): samma tecken i Node och webbläsare → ingen hydreringsdiff.
const fmt1 = { format: (v: number) => formatNumber(v, 1) };

/** Textfält med eget utkast: accepterar komma och punkt, uppdaterar bara vid giltigt tal. */
function ShareField({ id, value, onCommit }: { id: string; value: number; onCommit: (v: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? fmt1.format(value);
  const parse = (t: string) => {
    const v = Number(t.trim().replace(",", "."));
    return t.trim() !== "" && Number.isFinite(v) && v >= 0 && v <= 100 ? v : null;
  };
  return (
    <input
      id={id} type="text" inputMode="decimal" autoComplete="off" value={shown}
      aria-invalid={draft != null && parse(draft) == null}
      onChange={(e) => {
        setDraft(e.target.value);
        const v = parse(e.target.value);
        if (v != null) onCommit(v);
      }}
      onBlur={() => setDraft(null)}
      onKeyDown={(e) => { if (e.key === "Enter") setDraft(null); }}
      style={{ width: "5.5em", textAlign: "right" }}
    />
  );
}

export default function ScenarioCalc({ initial, baselineSeats }: Props) {
  const [model, setModel] = useState<SeatModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shares, setShares] = useState<Record<string, number>>(() =>
    Object.fromEntries(PARTIES.map((p) => [p, Math.round((initial[p] ?? 0) * 10) / 10])),
  );

  useEffect(() => {
    fetchManifest()
      .then((m) => fetchVerified<SeatModel>(m, "seat_model.json"))
      .then(setModel)
      .catch((e: Error) => setError(e.message));
  }, []);

  const result = useMemo(() => (model ? runScenario(shares, model) : null), [model, shares]);
  const set = (p: string, v: number) => setShares((s) => ({ ...s, [p]: Number.isFinite(v) ? v : 0 }));
  const reset = () => setShares(Object.fromEntries(PARTIES.map((p) => [p, Math.round((initial[p] ?? 0) * 10) / 10])));

  return (
    <section className="card scenario" aria-labelledby="scenario-h">
      <h3 id="scenario-h" style={{ marginTop: 0 }}>Räkna själv: egna andelar → mandat</h3>
      <p className="small muted">
        Ange andel av alla röster. Det som blir över till 100 % räknas som övriga partier. Mandaten räknas med samma motor som prognosen
        (vallagen: {fmt1.format(THRESHOLD)} %-spärr i landet, 12 % i valkrets, jämkade uddatalsmetoden, utjämningsmandat).
        Spärren prövas mot andel av alla giltiga röster, med övriga partier på valresultatets nivå.
      </p>
      {error && <p className="banner error" role="alert">Kunde inte ladda mandatmodellen: {error}</p>}
      <div className="scenario-grid">
        {PARTIES.map((p) => {
          const id = `sc-${p}`;
          return (
            <div key={p} className="scenario-row">
              <label htmlFor={id}>
                <span className="swatch" style={{ background: PARTY_COLORS[p] }} />
                {PARTY_NAMES[p]}
              </label>
              <input
                type="range" min={0} max={45} step={0.1} value={shares[p]} aria-label={`${PARTY_NAMES[p]}, andel i procent (reglage)`}
                onChange={(e) => set(p, parseFloat(e.target.value))}
              />
              <ShareField id={id} value={shares[p]} onCommit={(v) => set(p, v)} />
              <span aria-hidden="true">%</span>
            </div>
          );
        })}
      </div>
      <p className="small">
        Summa: <strong>{fmt1.format(result?.sum8 ?? Object.values(shares).reduce((a, b) => a + b, 0))} %</strong>{" "}
        <span className="muted">(övriga partier: {fmt1.format(Math.max(0, 100 - (result?.sum8 ?? Object.values(shares).reduce((a, b) => a + b, 0))))} %; summerar andelarna till 100 antas övriga ligga kvar på valresultatets nivå)</span>{" "}
        <button type="button" onClick={reset}>Återställ till prognosen</button>
      </p>
      <div aria-live="polite">
        {result && (
          <>
            <div className="table-scroll">
              <table>
                <caption>Mandat med dina andelar jämfört med prognosen i dag.</caption>
                <thead>
                  <tr><th>Parti</th><th className="r">Andel av alla röster</th><th className="r">Mandat</th><th className="r">Prognos</th></tr>
                </thead>
                <tbody>
                  {PARTIES.map((p) => (
                    <tr key={p}>
                      <td>{PARTY_NAMES[p]}{result.belowThreshold.includes(p) && <span className="small neg"> · under spärren</span>}</td>
                      <td className="r">{fmt1.format(result.shareAll[p] ?? 0)} %</td>
                      <td className="r"><strong>{result.total[p]}</strong></td>
                      <td className="r muted">{baselineSeats[p] ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              {result.blocs.map((b) => (
                <span key={b.name} style={{ marginRight: "1.2em" }}>
                  {b.name}: <strong>{b.seats}</strong> av {TOTAL_SEATS}{b.majority ? " — egen majoritet" : ""}
                </span>
              ))}
            </p>
          </>
        )}
        {!result && !error && <p className="muted">Laddar mandatmodellen …</p>}
      </div>
    </section>
  );
}
