/**
 * Svensk grammatik för genererade texter: partier och block som substantivfraser,
 * räkneord med genus, sifferformat (sv-SE) och listor.
 *
 * Sifferformat görs för hand (inte Intl) så att utdata är identisk i Node och alla
 * webbläsare: decimalkomma, hårt mellanslag (U+00A0) som tusentalsavgränsare och
 * typografiskt minustecken (U+2212).
 */
import { PARTY_NAMES } from "@contracts/constants";

export type Numerus = "singular" | "plural";
export type Genus = "utrum" | "neutrum";

export interface NounPhrase {
  /** Namnet i bestämd form, t.ex. "Moderaterna", "Centerpartiet", "Högerblocket". */
  name: string;
  numerus: Numerus;
  genus: Genus;
}

export const NBSP = " ";
export const MINUS = "−";

const PLURAL_PARTIES = new Set(["M", "L", "KD", "S", "SD", "O"]);

/** Riksdagsparti (eller "O" = Övriga) som substantivfras. */
export function party(code: string): NounPhrase {
  const name = PARTY_NAMES[code] ?? code;
  if (PLURAL_PARTIES.has(code)) return { name, numerus: "plural", genus: "utrum" };
  if (code in PARTY_NAMES) return { name, numerus: "singular", genus: "neutrum" };
  return localParty(name);
}

/**
 * Lokalt parti: numerus gissas ur namnets form. "-erna"/"-arna" → plural
 * ("Sverigedemokraterna"), "-et" → neutrum singular ("Skånepartiet"), annars utrum.
 */
export function localParty(name: string): NounPhrase {
  const last = name.trim().split(/\s+/).pop()?.toLowerCase() ?? "";
  if (/(erna|arna|orna)$/.test(last)) return { name, numerus: "plural", genus: "utrum" };
  if (/(et|tet)$/.test(last)) return { name, numerus: "singular", genus: "neutrum" };
  return { name, numerus: "singular", genus: "utrum" };
}

/** Block (bestämd form neutrum singular): "Högerblocket", "Vänsterblocket". */
export function bloc(name: string): NounPhrase {
  return { name, numerus: "singular", genus: "neutrum" };
}

/** Personligt pronomen i subjektsform: "de", "det", "den". */
export function pronoun(np: NounPhrase): string {
  if (np.numerus === "plural") return "de";
  return np.genus === "neutrum" ? "det" : "den";
}

/** Predikativt adjektiv: adjective(np, "stor", "stort", "stora"). */
export function adjective(np: NounPhrase, utrum: string, neutrum: string, plural: string): string {
  if (np.numerus === "plural") return plural;
  return np.genus === "neutrum" ? neutrum : utrum;
}

const WORDS_UTRUM = ["noll", "en", "två", "tre", "fyra", "fem", "sex", "sju", "åtta", "nio", "tio", "elva", "tolv"];

/** Räkneord 0–12 i ord, annars siffror. Genus påverkar bara 1 ("en"/"ett"). */
export function numberWord(n: number, genus: Genus = "utrum"): string {
  if (!Number.isInteger(n) || n < 0 || n > 12) return formatInteger(n);
  if (n === 1) return genus === "neutrum" ? "ett" : "en";
  return WORDS_UTRUM[n];
}

/** "ett mandat", "två mandat", "13 mandat"; "en procentenhet", "två procentenheter". */
export function counted(n: number, singular: string, plural: string, genus: Genus): string {
  return `${numberWord(n, genus)} ${Math.abs(n) === 1 ? singular : plural}`;
}

export function seats(n: number): string {
  return counted(n, "mandat", "mandat", "neutrum");
}

function groupThousands(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

/** Heltal med tusentalsavgränsare: 1448 → "1 448". */
export function formatInteger(n: number): string {
  const r = Math.round(n);
  const s = groupThousands(String(Math.abs(r)));
  return r < 0 ? MINUS + s : s;
}

/** Decimaltal med fast antal decimaler: 24.3456 → "24,3". */
export function formatNumber(x: number, decimals = 1): string {
  const fixed = Math.abs(x).toFixed(decimals);
  const [i, d] = fixed.split(".");
  const neg = x < 0 && Number(fixed) !== 0;
  return (neg ? MINUS : "") + groupThousands(i) + (d ? "," + d : "");
}

/** "24,3 procent". */
export function percent(x: number, decimals = 1): string {
  return `${formatNumber(x, decimals)} procent`;
}

/** Singular bara för exakt "1" utan decimaler ("en procentenhet"); "1,0 procentenheter". */
function ppUnit(formatted: string): string {
  return formatted === "1" ? "procentenhet" : "procentenheter";
}

/** Förändring i procentenheter med tecken: "+1,0 procentenheter", "−0,7 procentenheter". */
export function signedPp(x: number, decimals = 1): string {
  const v = Number(x.toFixed(decimals));
  const f = formatNumber(v, decimals);
  return `${v > 0 ? "+" : ""}${f} ${ppUnit(f.replace(MINUS, ""))}`;
}

/** Storlek utan tecken: "0,4 procentenheter". */
export function pp(x: number, decimals = 1): string {
  const f = formatNumber(Math.abs(Number(x.toFixed(decimals))), decimals);
  return `${f} ${ppUnit(f)}`;
}

/** "A", "A och B", "A, B och C". */
export function list(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} och ${items[items.length - 1]}`;
}

/** Numerus för en uppräkning av fraser: flera led → plural. */
export function listPhrase(nps: NounPhrase[]): NounPhrase {
  if (nps.length === 1) return nps[0];
  return { name: list(nps.map((n) => n.name)), numerus: "plural", genus: "utrum" };
}

export function capitalize(s: string): string {
  return s.length ? s[0].toLocaleUpperCase("sv-SE") + s.slice(1) : s;
}

/** Genitiv: "Stockholm" → "Stockholms", "Västerås" → "Västerås", "Luleå" → "Luleås". */
export function genitive(name: string): string {
  return /[sxz]$/i.test(name) ? name : `${name}s`;
}

/** Sammanfoga meningar och se till att varje mening börjar med versal och slutar med punkt. */
export function sentences(parts: (string | null | undefined | false)[]): string {
  return parts
    .filter((p): p is string => typeof p === "string" && p.trim().length > 0)
    .map((p) => {
      const t = capitalize(p.trim());
      return /[.!?]$/.test(t) ? t : `${t}.`;
    })
    .join(" ");
}
