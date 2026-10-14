import { PARTY_NAMES } from "@contracts/constants";
import { formatShare } from "./text/grammar";

const nf0 = new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 });

/** 24,3 % — strax under 4 %-spärren (3,95–3,99) visas med två decimaler, se formatShare. */
export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? "–" : `${digits === 1 ? formatShare(v) : nf0.format(v)} %`;
/** +1,2 / −0,4 (procentenheter, typografiskt minus) */
export const signed = (v: number | null | undefined, digits = 1) => {
  if (v == null || Number.isNaN(v)) return "–";
  const r = Number(v.toFixed(digits));
  const s = new Intl.NumberFormat("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Math.abs(r));
  return r > 0 ? `+${s}` : r < 0 ? `−${s}` : s;
};
export const signedInt = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0");
export const int = (v: number) => nf0.format(v);
export const partyName = (p: string) => PARTY_NAMES[p] ?? p;
export const dateSv = (iso: string) =>
  new Intl.DateTimeFormat("sv-SE", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Stockholm" }).format(new Date(iso));
export const changeClass = (v: number | null | undefined, eps = 0.05) => (v == null ? "" : v > eps ? "pos" : v < -eps ? "neg" : "");

export function slugify(text: string): string {
  return text.toLowerCase().replace(/ä/g, "a").replace(/å/g, "a").replace(/ö/g, "o")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
