interface HoverSeries { n: string; c: string; v: (number | null)[]; lo?: (number | null)[]; hi?: (number | null)[] }
interface HoverData { x: number[]; l: string[]; s: HoverSeries[]; T: number; B: number; d?: number; u?: string }

const NS = "http://www.w3.org/2000/svg";
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
  svg.append(g);

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

  function show(ev: PointerEvent) {
    const r = svg.getBoundingClientRect();
    const i = nearest(((ev.clientX - r.left) / r.width) * vbW);
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
    tip.hidden = true;
  }

  svg.addEventListener("pointermove", show);
  svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("pointercancel", hide);
}

document.querySelectorAll<SVGSVGElement>("svg[data-hover]").forEach(init);
