interface HoverSeries { pk?: string[]; n: string; c: string; v: (number | null)[]; lo?: (number | null)[]; hi?: (number | null)[] }
interface HoverData { x: number[]; l: string[]; s: HoverSeries[]; T: number; B: number; d?: number; u?: string; polls?: boolean; t0?: number; t1?: number; L?: number; R?: number; W?: number; y0?: number; y1?: number }
interface PollsData { parties: string[]; inst: string[]; polls: (string | number | null)[][] }
interface Dot { x: number; y: number; si: number; poll: (string | number | null)[] }

const NS = "http://www.w3.org/2000/svg";
const MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"];
const dateLabel = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;
let pollsPromise: Promise<PollsData | null> | undefined;
async function fetchPolls(): Promise<PollsData | null> {
  try {
    const r = await fetch("/charts/polls.json");
    return r.ok ? ((await r.json()) as PollsData) : null;
  } catch {
    return null;
  }
}
const loadPolls = () => (pollsPromise ??= fetchPolls());
const num = (v: number, d: number) => v.toFixed(d).replace(".", ",");

function init(svg: SVGSVGElement) {
  const data: HoverData = JSON.parse(svg.dataset.hover ?? "null");
  const fig = svg.parentElement;
  if (!data || !fig || !data.x.length) return;
  const digits = data.d ?? 1, unit = data.u ?? " %";
  const vbW = svg.viewBox.baseVal.width;

  const g = document.createElementNS(NS, "g");
  g.setAttribute("pointer-events", "none");
  g.setAttribute("visibility", "hidden");
  const rule = document.createElementNS(NS, "line");
  rule.setAttribute("y1", String(data.T));
  rule.setAttribute("y2", String(data.B));
  rule.setAttribute("stroke", "#555");
  rule.setAttribute("stroke-width", "1");
  g.append(rule);
  const dots = data.s.map((s) => {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("r", "3.5");
    c.setAttribute("fill", s.c);
    c.setAttribute("stroke", "#fff");
    c.setAttribute("stroke-width", "1.5");
    g.append(c);
    return c;
  });
  const ring = document.createElementNS(NS, "circle");
  ring.setAttribute("r", "5");
  ring.setAttribute("fill", "none");
  ring.setAttribute("stroke", "#111");
  ring.setAttribute("stroke-width", "1.5");
  ring.setAttribute("visibility", "hidden");
  g.append(ring);
  svg.append(g);
  const pollDots: Dot[] = [];

  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  fig.append(tip);

  const yOf = (v: number) => {
    const y0 = Number(svg.dataset.y0), y1 = Number(svg.dataset.y1);
    return data.T + (1 - (v - y0) / (y1 - y0 || 1)) * (data.B - data.T);
  };

  function nearest(px: number) {
    let lo = 0, hi = data.x.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (data.x[m] <= px) lo = m; else hi = m; }
    return Math.abs(data.x[lo] - px) <= Math.abs(data.x[hi] - px) ? lo : hi;
  }

  if (data.polls) {
    loadPolls().then((pd) => {
      if (!pd) return;
      const idx = new Map<string, number>(pd.parties.map((p, i): [string, number] => [p, i + 2]));
      const grp = document.createElementNS(NS, "g");
      grp.setAttribute("pointer-events", "none");
      const L = data.L!, R = data.R!, W = data.W!, t0 = data.t0!, t1 = data.t1!;
      for (const poll of pd.polls) {
        const t = Date.parse(poll[0] as string);
        if (t < t0 || t > t1) continue;
        const x = L + ((t - t0) / (t1 - t0)) * (W - L - R);
        data.s.forEach((s, si) => {
          let sum = 0;
          for (const p of s.pk ?? []) {
            const v = poll[idx.get(p) ?? -1];
            if (v == null) return;
            sum += v as number;
          }
          const y = Math.min(data.B, Math.max(data.T, yOf(sum)));
          const c = document.createElementNS(NS, "circle");
          c.setAttribute("cx", x.toFixed(1));
          c.setAttribute("cy", y.toFixed(1));
          c.setAttribute("r", "2");
          c.setAttribute("fill", s.c);
          c.setAttribute("fill-opacity", "0.5");
          grp.append(c);
          pollDots.push({ x, y, si, poll: [...poll.slice(0, 1), pd.inst[poll[1] as number], sum] });
        });
      }
      const first = svg.querySelector("polygon")?.parentElement;
      svg.insertBefore(grp, first ?? g);
    });
  }

  function showPoll(d: Dot, ev: PointerEvent) {
    const r = svg.getBoundingClientRect();
    rule.setAttribute("x1", String(d.x));
    rule.setAttribute("x2", String(d.x));
    dots.forEach((c) => c.setAttribute("visibility", "hidden"));
    ring.setAttribute("cx", String(d.x));
    ring.setAttribute("cy", String(d.y));
    ring.setAttribute("visibility", "visible");
    const s = data.s[d.si];
    tip.replaceChildren();
    const head = document.createElement("strong");
    head.textContent = `${d.poll[1]} · ${dateLabel(d.poll[0] as string)}`;
    const line = document.createElement("div");
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = s.c;
    line.append(sw, `${s.n} ${num(d.poll[2] as number, digits)}${unit} (mätning)`);
    tip.append(head, line);
    g.setAttribute("visibility", "visible");
    tip.hidden = false;
    const px = (d.x / vbW) * r.width;
    const flip = px > r.width / 2;
    tip.style.left = `${px + (flip ? -12 : 12)}px`;
    tip.style.transform = flip ? "translateX(-100%)" : "none";
    void ev;
  }

  function show(ev: PointerEvent) {
    const r = svg.getBoundingClientRect();
    const vx = ((ev.clientX - r.left) / r.width) * vbW;
    const vy = ((ev.clientY - r.top) / r.width) * vbW;
    const reach = (9 * vbW) / r.width;
    let best: Dot | null = null, bd = reach * reach;
    for (const d of pollDots) {
      const dx = d.x - vx;
      if (dx * dx > bd) continue;
      const dd = dx * dx + (d.y - vy) ** 2;
      if (dd <= bd) { bd = dd; best = d; }
    }
    if (best) return showPoll(best, ev);
    ring.setAttribute("visibility", "hidden");
    const i = nearest(vx);
    const x = data.x[i];
    rule.setAttribute("x1", String(x));
    rule.setAttribute("x2", String(x));
    const rows: { s: HoverSeries; v: number }[] = [];
    data.s.forEach((s, k) => {
      const v = s.v[i];
      if (v == null) { dots[k].setAttribute("visibility", "hidden"); return; }
      dots[k].setAttribute("visibility", "visible");
      dots[k].setAttribute("cx", String(x));
      dots[k].setAttribute("cy", String(yOf(v)));
      rows.push({ s, v });
    });
    if (data.s.length > 2) rows.sort((a, b) => b.v - a.v);
    tip.replaceChildren();
    const head = document.createElement("strong");
    head.textContent = data.l[i];
    tip.append(head);
    for (const { s, v } of rows) {
      const line = document.createElement("div");
      const sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = s.c;
      const lo = s.lo?.[i], hi = s.hi?.[i];
      line.append(sw, `${s.n} ${num(v, digits)}${unit}`);
      if (lo != null && hi != null) {
        const range = document.createElement("span");
        range.className = "muted";
        range.textContent = ` (${num(lo, digits)}–${num(hi, digits)})`;
        line.append(range);
      }
      tip.append(line);
    }
    g.setAttribute("visibility", "visible");
    tip.hidden = false;
    const px = (x / vbW) * r.width;
    const flip = px > r.width / 2;
    tip.style.left = `${px + (flip ? -12 : 12)}px`;
    tip.style.transform = flip ? "translateX(-100%)" : "none";
  }

  function hide() {
    g.setAttribute("visibility", "hidden");
    ring.setAttribute("visibility", "hidden");
    tip.hidden = true;
  }

  svg.addEventListener("pointermove", show);
  svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("pointercancel", hide);
}

document.querySelectorAll<SVGSVGElement>("svg[data-hover]").forEach(init);
