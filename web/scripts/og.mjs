/**
 * OG-/delningsbilder (1200×630) per sida, ritade som SVG och rastrerade med resvg.
 * Formspråket följer sajten: hemicykeln (src/lib/hemicycle.js, samma geometri som startsidan),
 * DM Sans, vit botten, partifärger. Varianter:
 *   hem     startsidan och /mandat/: hemicykel + blockens mandat
 *   prob    /sannolikheter/: blockens chans till egen majoritet som staplar
 *   parti   /parti/<slug>/: partiets stöd, mandat och dess egen kil i hemicykeln
 *   valkrets /valkrets/<slug>/: valkretsens mandat som prickar i partifärger
 *   allmän  allt annat: titel, beskrivning och hemicykeln som märke
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { HEMI_ORDER, HEMI_DOT, HEMI_NUMBER_X, HEMI_NUMBER_Y, hemicycleDots, majorityLine, wedgePaths } from "../src/lib/hemicycle.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const TOTAL = 349;
const INK = "#111213", MUTED = "#5c5f63", ACCENT = "#0b5cad", LEFT = "#c2405f", RIGHT = "#1f8f78", TRACK = "#ebebeb", GHOST = "#e4e4e4";
const COLORS = { M: "#52BDEC", L: "#006AB3", C: "#009933", KD: "#000077", S: "#E8112D", V: "#AF0000", MP: "#83CF39", SD: "#DDDD00" };
const NAMES = { M: "Moderaterna", L: "Liberalerna", C: "Centerpartiet", KD: "Kristdemokraterna", S: "Socialdemokraterna", V: "Vänsterpartiet", MP: "Miljöpartiet", SD: "Sverigedemokraterna" };
const MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"];
const VERBAL = JSON.parse(fs.readFileSync(path.join(here, "..", "..", "contracts", "verbal_scale.json"), "utf-8"));

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const nbsp = (s) => s.replace(/ /g, " ");
const slugify = (t) => t.toLowerCase().replace(/ä/g, "a").replace(/å/g, "a").replace(/ö/g, "o")
  .normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const comma = (x, d) => x.toFixed(d).replace(".", ",");
/** Som formatShare på sajten: strax under spärren som avrundas till 4,0 visas med två decimaler (nedåt). */
const share = (x) => (x < 4 && Number(x.toFixed(1)) >= 4 ? comma(Math.floor(x * 100 + 1e-9) / 100, 2) : comma(x, 1));
const roundHalfEven = (x) => { const f = Math.floor(x); return x - f === 0.5 ? (f % 2 === 0 ? f : f + 1) : Math.round(x); };
/** Samma regler som displayPct på sajten: aldrig 0 eller 100 från simuleringar. */
const displayPct = (p) => (p < VERBAL.display.min ? VERBAL.display.belowMin : p > VERBAL.display.max ? VERBAL.display.aboveMax : `${roundHalfEven(p * 100)} %`);

/** Radbrytning efter teckenantal; sista raden får "…" om texten inte ryms. */
function wrap(text, max, maxLines) {
  const lines = []; let cur = "";
  for (const w of text.split(/\s+/).filter(Boolean)) {
    if (cur && (cur + " " + w).length > max) { lines.push(cur); cur = w; } else cur = cur ? `${cur} ${w}` : w;
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) { const kept = lines.slice(0, maxLines); kept[maxLines - 1] = kept[maxLines - 1].replace(/[\s.,;:]*$/, "") + "…"; return kept; }
  return lines;
}

const text = (x, y, s, { size = 28, weight = 400, fill = INK, anchor = "start" } = {}) =>
  `<text x="${x}" y="${y}" font-family="DM Sans" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="${fill}">${esc(s)}</text>`;
const lines = (x, y, arr, step, opts) => arr.map((l, i) => text(x, y + i * step, l, opts)).join("");

const frame = (body, { stripe = ACCENT } = {}) =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#ffffff"/><rect width="1200" height="14" fill="${stripe}"/>${body}</svg>`;
const header = (right) => text(72, 100, "Mandatorn", { size: 34, weight: 700, fill: ACCENT }) + (right ? text(1128, 100, right, { size: 28, fill: MUTED, anchor: "end" }) : "");
const footer = (left) => text(72, 590, left, { size: 26, fill: MUTED }) + text(1128, 590, "mandatorn.se", { size: 26, fill: MUTED, anchor: "end" });

/** Hemicykeln: bågens ruta (588×300) placeras med övre vänstra hörnet i (x, y) och skalas med s. */
function hemi({ x, y, s, seats, colors = COLORS, numbers = null, majority = false, groups = null, dot = HEMI_DOT }) {
  const paths = (groups ?? wedgePaths(seats, TOTAL).map((w) => ({ d: w.d, color: colors[w.party] ?? GHOST }))).filter((w) => w.d)
    .map((w) => `<path d="${w.d}" stroke="${w.color}"/>`).join("");
  let extra = "";
  if (majority) {
    const m = majorityLine(TOTAL);
    extra += `<line x1="${m.x1}" y1="${m.y1}" x2="${m.x2}" y2="${m.y2}" stroke="${INK}" stroke-width="1.6" stroke-dasharray="5 4"/>` +
      text(m.lx, m.ly + 6, "175", { size: 17, weight: 700, anchor: "middle" });
  }
  if (numbers) {
    extra += text(HEMI_NUMBER_X.left, HEMI_NUMBER_Y, String(numbers.left), { size: 54, weight: 700, fill: LEFT, anchor: "middle" }) +
      text(HEMI_NUMBER_X.right, HEMI_NUMBER_Y, String(numbers.right), { size: 54, weight: 700, fill: RIGHT, anchor: "middle" });
  }
  return `<g transform="translate(${x - 6 * s} ${y - 6 * s}) scale(${s})"><g fill="none" stroke-linecap="round" stroke-width="${dot}">${paths}</g>${extra}</g>`;
}

const dateSv = (iso) => { const d = new Date(`${iso}T12:00:00Z`); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };

function homeSvg(ctx, label) {
  const { nat } = ctx;
  const left = nat.blocs.find((b) => b.name === "Vänsterblocket"), right = nat.blocs.find((b) => b.name === "Högerblocket");
  const blocks = [[left, LEFT], [right, RIGHT]].map(([b, color], i) => {
    const y0 = 232 + i * 175;
    const parties = HEMI_ORDER.filter((p) => ctx.blocParties[b.name].includes(p));
    const items = parties.map((p, k) => {
      const cx = 806 + (k % 2) * 160, cy = y0 + 48 + Math.floor(k / 2) * 34;
      return `<circle cx="${cx}" cy="${cy - 8}" r="8" fill="${COLORS[p]}"/>` + text(cx + 18, cy, `${p} ${nat.seats[p] ?? 0}`, { size: 24, weight: 700 });
    }).join("");
    return text(790, y0, b.name, { size: 30, weight: 700, fill: color }) + items +
      text(790, y0 + 118, `${b.seats} mandat, egen majoritet i valet: ${displayPct(b.pMajority)}`, { size: 20, fill: MUTED });
  }).join("");
  return frame(
    header(label) +
    hemi({ x: 60, y: 190, s: 1.15, seats: nat.seats, numbers: { left: left.seats, right: right.seats }, majority: true }) +
    blocks +
    footer(`Om det vore val i dag, uppdaterad ${dateSv(nat.referenceDate)}`));
}

function probSvg(ctx) {
  const { nat, sim } = ctx;
  const rows = [["Vänsterblocket", LEFT], ["Högerblocket", RIGHT]].map(([name, color], i) => {
    const p = nat.blocs.find((b) => b.name === name).pMajority, y = 320 + i * 120;
    return text(72, y, name, { size: 34, weight: 700, fill: color }) + text(1128, y, displayPct(p), { size: 44, weight: 700, anchor: "end" }) +
      `<rect x="72" y="${y + 20}" width="1056" height="40" rx="4" fill="${TRACK}"/><rect x="72" y="${y + 20}" width="${(1056 * p).toFixed(1)}" height="40" rx="4" fill="${color}"/>`;
  }).join("");
  return frame(
    header(`Riksdagsvalet ${nat.nextElection.slice(0, 4)}`) +
    text(72, 190, "Sannolikheter", { size: 76, weight: 700 }) +
    text(72, 240, `Chans att få egen majoritet (minst 175 mandat), ur ${nbsp(String(sim.nSims).replace(/\B(?=(\d{3})+(?!\d))/g, " "))} simuleringar`, { size: 28, fill: MUTED }) +
    rows + footer(`Uppdaterad ${dateSv(nat.referenceDate)}`));
}

function partySvg(ctx, code) {
  const { nat } = ctx;
  const est = nat.estimates.find((e) => e.party === code), color = COLORS[code];
  const colors = Object.fromEntries(HEMI_ORDER.map((p) => [p, p === code ? color : GHOST]));
  const seats = nat.seats[code] ?? 0;
  return frame(
    `<rect x="0" y="14" width="28" height="616" fill="${color}"/>` +
    header(`Riksdagsvalet ${nat.nextElection.slice(0, 4)}`) +
    text(72, 210, NAMES[code], { size: 84, weight: 700 }) +
    text(72, 360, `${share(est.share)} %`, { size: 104, weight: 700 }) + text(72, 405, "av rösterna om det vore val i dag", { size: 28, fill: MUTED }) +
    text(72, 500, `${seats} mandat`, { size: 52, weight: 700 }) + text(72, 540, `av ${TOTAL} i riksdagen`, { size: 26, fill: MUTED }) +
    hemi({ x: 650, y: 290, s: 0.82, seats: nat.seats, colors }) +
    footer(`Uppdaterad ${dateSv(nat.referenceDate)}`), { stripe: color });
}

function valkretsSvg(ctx, name, seatsByParty, title) {
  const n = HEMI_ORDER.reduce((s, p) => s + (seatsByParty[p] ?? 0), 0);
  // Få mandat → stora prickar i en rad eller två; många (Stockholm, Göteborg) → tätare rutnät.
  const small = n <= 20, perRow = small ? 10 : 14, step = small ? 72 : 50, r = small ? 30 : 20;
  let i = 0, dots = "";
  for (const p of HEMI_ORDER) for (let k = 0; k < (seatsByParty[p] ?? 0); k++, i++) {
    dots += `<circle cx="${72 + r + (i % perRow) * step}" cy="${330 + Math.floor(i / perRow) * step}" r="${r}" fill="${COLORS[p]}"/>`;
  }
  const rowsUsed = Math.ceil(n / perRow);
  const legend = HEMI_ORDER.filter((p) => seatsByParty[p]).map((p, k) =>
    `<circle cx="${902 + 8}" cy="${240 + k * 36 - 8}" r="9" fill="${COLORS[p]}"/>` + text(930, 240 + k * 36, `${p} ${seatsByParty[p]}`, { size: 26, weight: 700 })).join("");
  return frame(
    header(`Riksdagsvalet ${ctx.nat.nextElection.slice(0, 4)}`) +
    lines(72, 190, wrap(title, 24, 2), 78, { size: 70, weight: 700 }) +
    dots + legend +
    text(72, 330 + (rowsUsed - 1) * step + r + 50, `${n} mandat i valkretsen`, { size: 28, fill: MUTED }) +
    footer(`Prognos för ${dateSv(ctx.nat.referenceDate)}`));
}

/** Kommunens eller regionens egna mandat (inkl. lokala partier i grått) som liten hemicykel. */
function areaMotif(now, total) {
  const n = total || Object.values(now).reduce((a, b) => a + b, 0);
  if (!n) return null;
  const rows = Math.max(2, Math.min(10, Math.ceil(Math.sqrt(n / 4.5))));
  const sum = Array.from({ length: rows }, (_, k) => 150 + (k * 138) / (rows - 1)).reduce((a, b) => a + b, 0);
  const dot = Math.min(12.4 * 2.6, 0.8 * Math.min(138 / (rows - 1), (Math.PI * sum) / n));
  const dots = hemicycleDots(n, rows);
  const local = Object.keys(now).filter((p) => !HEMI_ORDER.includes(p)).sort((a, b) => now[b] - now[a]);
  let i = 0;
  const groups = [...HEMI_ORDER, ...local].map((p) => {
    const c = now[p] ?? 0;
    const d = dots.slice(i, i + c).map((q) => `M${Math.round(q.x * 10) / 10} ${Math.round(q.y * 10) / 10}h0`).join("");
    i += c;
    return { d, color: COLORS[p] ?? "#9a9a9a" };
  });
  return { groups, dot };
}

function generalSvg(ctx, p) {
  const title = p.title.replace(/ – Mandatorn$/, "");
  const eu = p.route.startsWith("/eu");
  const wide = eu ? 1056 : 640;
  const tl = wrap(title, Math.floor(wide / 36), 3);
  const dl = wrap(p.description, Math.floor(wide / 15), eu ? 4 : 5);
  const own = p.areaNow ? areaMotif(p.areaNow, p.areaTotal) : null;
  const motif = own ? hemi({ x: 790, y: 330, s: 0.58, groups: own.groups, dot: own.dot })
    : !eu && ctx.nat ? hemi({ x: 790, y: 330, s: 0.58, seats: ctx.nat.seats }) : "";
  return frame(
    header(eu ? "EU-valet 2029" : "") +
    lines(72, 200, tl, 74, { size: 64, weight: 700 }) +
    lines(72, 200 + tl.length * 74 + 14, dl, 40, { size: 28, fill: MUTED }) +
    motif + footer(""));
}

/** Skriver dist/og/<sida>.png för varje indexerbar sida. `readData(name)` läser en fil ur releasen. */
export async function renderOgImages({ dist, indexable, readData, releaseDir }) {
  const { Resvg } = await import("@resvg/resvg-js");
  const fontFiles = ["DMSans-Regular.ttf", "DMSans-Bold.ttf"].map((f) => path.join(here, "fonts", f));
  const nat = readData("national.json"), md = readData("mandates.json"), sim = readData("simulation.json");
  const ctx = { nat, sim, blocParties: { Vänsterblocket: ["S", "V", "MP", "C"], Högerblocket: ["M", "L", "KD", "SD"] } };
  const havePage = Boolean(nat && md);
  const valkrets = new Map(Object.entries(md?.constituencies ?? {}).map(([k, v]) => [slugify(k), [k, v]]));
  // Kommuner och regioner: egna mandat (inkl. lokala partier) som märke.
  const areas = new Map();
  try {
    const rel = JSON.parse(fs.readFileSync(path.join(releaseDir, "manifest.json"), "utf-8"));
    for (const f of rel.files.filter((q) => /^(kommun|region)\/[^/]+\.json$/.test(q.path))) {
      const a = readData(f.path);
      const seats = a?.kind === "region" ? a.regionSeats : a?.kommunSeats;
      if (a?.slug && seats?.now) areas.set(`${a.kind}/${a.slug}`, seats);
    }
  } catch { /* faller tillbaka på riksdagens fördelning */ }
  let n = 0, fallbacks = 0;
  for (const p of indexable) {
    let svg = null;
    const parti = p.route.match(/^\/parti\/([^/]+)\/$/), vk = p.route.match(/^\/valkrets\/([^/]+)\/$/);
    if (havePage) {
      if (p.route === "/") svg = homeSvg(ctx, `Riksdagsvalet ${nat.nextElection.slice(0, 4)}`);
      else if (p.route === "/mandat/") svg = homeSvg(ctx, "Mandatfördelning");
      else if (p.route === "/sannolikheter/" && sim) svg = probSvg(ctx);
      else if (parti) { const code = Object.keys(NAMES).find((c) => slugify(NAMES[c]) === parti[1]); if (code) svg = partySvg(ctx, code); }
      else if (vk && valkrets.has(vk[1])) { const [name, seats] = valkrets.get(vk[1]); svg = valkretsSvg(ctx, name, seats, p.title.replace(/ – Mandatorn$/, "")); }
    }
    if (!svg) {
      const am = p.route.match(/^\/(kommun|region)\/([^/]+)\/$/), seats = am && areas.get(`${am[1]}/${am[2]}`);
      svg = generalSvg(ctx, seats ? { ...p, areaNow: seats.now, areaTotal: seats.totalSeats } : p); if (p.route === "/") fallbacks++; }
    const png = new Resvg(svg, { font: { fontFiles, loadSystemFonts: false, defaultFontFamily: "DM Sans" } }).render().asPng();
    const name = p.route === "/" ? "index" : p.route.replace(/^\/|\/$/g, "");
    const out = path.join(dist, "og", `${name}.png`);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, png);
    n++;
  }
  return { written: n, fallbacks };
}
