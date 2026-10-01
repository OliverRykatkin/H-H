/**
 * Efter `astro build`: sitemap.xml + robots.txt, kontroll av unika titlar/beskrivningar,
 * OG-bilder per sida (resvg, DM Sans) och prestandabudget.
 *
 *   node scripts/postbuild.mjs [dist] [--no-og]
 *
 * Avslutar med kod 1 om budgeten eller unikhetskraven bryts.
 */
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(process.argv.find((a, i) => i > 1 && !a.startsWith("--")) ?? path.join(here, "..", "dist"));
const site = (process.env.PUBLIC_SITE_URL || "https://mandatorn.se").replace(/\/$/, "");
const withOg = !process.argv.includes("--no-og");
const HTML_BUDGET = 150 * 1024;
const JS_BUDGET_GZ = 200 * 1024;
const problems = [];

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "_data" || e.name === "og") continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith(".html")) out.push(p);
  }
  return out;
}

const decode = (s) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
const pages = walk(dist).map((file) => {
  const html = fs.readFileSync(file, "utf-8");
  const rel = path.relative(dist, file).split(path.sep).join("/");
  const route = rel === "index.html" ? "/" : rel.endsWith("/index.html") ? `/${rel.slice(0, -"index.html".length)}` : `/${rel}`;
  return {
    file, route, html, size: Buffer.byteLength(html),
    title: decode(html.match(/<title>([^<]*)<\/title>/)?.[1] ?? ""),
    description: decode(html.match(/<meta name="description" content="([^"]*)"/)?.[1] ?? ""),
    noindex: /<meta name="robots" content="noindex"/.test(html),
  };
});
const indexable = pages.filter((p) => !p.noindex && p.route !== "/404.html");

// ── sitemap.xml + robots.txt ──
fs.writeFileSync(path.join(dist, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  indexable.map((p) => `  <url><loc>${site}${p.route}</loc></url>`).sort().join("\n") + "\n</urlset>\n");
fs.writeFileSync(path.join(dist, "robots.txt"), `User-agent: *\nAllow: /\nDisallow: /status/\n\nSitemap: ${site}/sitemap.xml\n`);

// ── Unika titlar och beskrivningar ──
for (const key of ["title", "description"]) {
  const seen = new Map();
  for (const p of indexable) {
    if (!p[key]) problems.push(`${p.route}: saknar ${key}`);
    else if (seen.has(p[key])) problems.push(`${p.route}: samma ${key} som ${seen.get(p[key])}`);
    else seen.set(p[key], p.route);
  }
}

// ── Prestandabudget ──
const gz = (buf) => zlib.gzipSync(buf, { level: 9 }).length;
const jsCache = new Map();
function jsClosure(src, seen = new Set()) {
  if (seen.has(src)) return seen;
  const file = path.join(dist, src.replace(/^\//, ""));
  if (!fs.existsSync(file)) return seen;
  seen.add(src);
  const code = fs.readFileSync(file, "utf-8");
  // Bara statiska importer räknas till första vyn; dynamiska import() laddas lazy (t.ex. kartan).
  for (const m of code.matchAll(/(?:^|[;\s}])import\s*(?:[^'"()]*?from\s*)?["'](\.{1,2}\/[^"']+\.js)["']/g)) {
    jsClosure(path.posix.join(path.posix.dirname(src), m[1]), seen);
  }
  return seen;
}
let maxJs = { route: "", bytes: 0 }, maxHtml = { route: "", bytes: 0 };
for (const p of pages) {
  if (p.size > HTML_BUDGET) problems.push(`${p.route}: HTML ${(p.size / 1024).toFixed(0)} kB > 150 kB`);
  if (p.size > maxHtml.bytes) maxHtml = { route: p.route, bytes: p.size };
  const srcs = new Set();
  for (const m of p.html.matchAll(/<script[^>]+src="(\/_astro\/[^"]+\.js)"/g)) jsClosure(m[1], srcs);
  for (const m of p.html.matchAll(/component-url="(\/_astro\/[^"]+\.js)"/g)) {
    if (!/client="(visible|idle|media)"/.test(p.html.slice(Math.max(0, p.html.indexOf(m[0]) - 400), p.html.indexOf(m[0]) + 400))) jsClosure(m[1], srcs);
  }
  for (const m of p.html.matchAll(/renderer-url="(\/_astro\/[^"]+\.js)"/g)) jsClosure(m[1], srcs);
  const inline = [...p.html.matchAll(/<script type="module">([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("");
  for (const m of inline.matchAll(/["'](\/_astro\/[^"']+\.js)["']/g)) jsClosure(m[1], srcs);
  let bytes = gz(Buffer.from(inline));
  for (const s of srcs) {
    if (/maplibre/i.test(s)) continue; // kartan undantas (laddas lazy)
    if (!jsCache.has(s)) jsCache.set(s, gz(fs.readFileSync(path.join(dist, s.replace(/^\//, "")))));
    bytes += jsCache.get(s);
  }
  if (bytes > JS_BUDGET_GZ) problems.push(`${p.route}: JS ${(bytes / 1024).toFixed(0)} kB gzip > 200 kB`);
  if (bytes > maxJs.bytes) maxJs = { route: p.route, bytes };
}

// ── OG-bilder ──
if (withOg) {
  const { Resvg } = await import("@resvg/resvg-js");
  const font = path.join(here, "fonts", "DMSans.ttf");
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const wrap = (text, max) => {
    const words = text.split(/\s+/); const lines = []; let cur = "";
    for (const w of words) { if ((cur + " " + w).trim().length > max) { lines.push(cur); cur = w; } else cur = (cur + " " + w).trim(); }
    if (cur) lines.push(cur);
    return lines;
  };
  for (const p of indexable) {
    const title = p.title.replace(/ – Mandatorn$/, "");
    const tl = wrap(title, 28).slice(0, 3);
    const dl = wrap(p.description, 62).slice(0, 3);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#ffffff"/><rect width="1200" height="14" fill="#0b5cad"/>
<text x="72" y="110" font-family="DM Sans" font-size="34" font-weight="700" fill="#0b5cad">Mandatorn</text>
${tl.map((l, i) => `<text x="72" y="${210 + i * 76}" font-family="DM Sans" font-size="64" font-weight="700" fill="#111213">${esc(l)}</text>`).join("")}
${dl.map((l, i) => `<text x="72" y="${210 + tl.length * 76 + 30 + i * 42}" font-family="DM Sans" font-size="30" fill="#5c5f63">${esc(l)}</text>`).join("")}
<text x="72" y="590" font-family="DM Sans" font-size="24" fill="#5c5f63">mandatorn.se</text></svg>`;
    const png = new Resvg(svg, { font: { fontFiles: [font], loadSystemFonts: false, defaultFontFamily: "DM Sans" } }).render().asPng();
    const name = p.route === "/" ? "index" : p.route.replace(/^\/|\/$/g, "");
    const out = path.join(dist, "og", `${name}.png`);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, png);
  }
}

console.log(`${pages.length} sidor (${indexable.length} i sitemap). Största HTML: ${maxHtml.route} ${(maxHtml.bytes / 1024).toFixed(0)} kB. ` +
  `Mest JS i första vyn: ${maxJs.route} ${(maxJs.bytes / 1024).toFixed(1)} kB gzip.${withOg ? " OG-bilder skrivna." : ""}`);
if (problems.length) {
  console.error(`\n${problems.length} problem:\n` + problems.slice(0, 50).map((p) => `  - ${p}`).join("\n"));
  process.exit(1);
}
