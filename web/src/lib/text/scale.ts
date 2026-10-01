/**
 * Verbal sannolikhetsskala och procentvisning. Reglerna kommer från
 * contracts/verbal_scale.json (via @contracts/constants) — samma källa som
 * mandatorn_model/text.py. Visar aldrig 0 % eller 100 % från simuleringar.
 */
import { VERBAL_SCALE } from "@contracts/constants";

interface Step {
  below?: number;
  atMost?: number;
  label: string;
}

const steps = VERBAL_SCALE.steps as Step[];
const display = VERBAL_SCALE.display;

export function verbal(p: number): string {
  for (const s of steps) {
    if (s.below !== undefined && p < s.below) return s.label;
    if (s.atMost !== undefined && p <= s.atMost) return s.label;
    if (s.below === undefined && s.atMost === undefined) return s.label;
  }
  throw new Error(`Ingen etikett för p=${p}`);
}

/**
 * Pythons round() avrundar exakta halvor till jämnt tal; samma här för identisk visning.
 * Bara exakt .5 (som flyttal) räknas som halva, precis som i Python.
 */
export function roundHalfEven(x: number): number {
  const f = Math.floor(x);
  if (x - f === 0.5) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

/** "58 %", "<1 %", ">99 %" (samma som mandatorn_model.text.display_pct). */
export function displayPct(p: number): string {
  if (p < display.min) return display.belowMin;
  if (p > display.max) return display.aboveMax;
  return `${roundHalfEven(p * 100)} %`;
}

/** Löptext: "58 procents sannolikhet", "mindre än 1 procents sannolikhet", "över 99 procents sannolikhet". */
export function probabilityPhrase(p: number): string {
  if (p < display.min) return "mindre än 1 procents sannolikhet";
  if (p > display.max) return "över 99 procents sannolikhet";
  return `${roundHalfEven(p * 100)} procents sannolikhet`;
}

/** Etikett i gemener för löptext: "jämnt", "väldigt troligt". */
export function verbalLower(p: number): string {
  return verbal(p).toLocaleLowerCase("sv-SE");
}

/** Värdet som löptext: "64 procent", "mindre än 1 procent", "över 99 procent". */
export function probabilityValue(p: number): string {
  if (p < display.min) return "mindre än 1 procent";
  if (p > display.max) return "över 99 procent";
  return `${roundHalfEven(p * 100)} procent`;
}
