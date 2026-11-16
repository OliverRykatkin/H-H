"""Polymarket-marknader om svensk regeringsbildning — extern jämförelseserie.

Marknadsdata går INTE in i prognosmodellen (Kalman, simulering, mandat). Den hämtas,
sparas som tidsserie och visas bredvid modellens egna sannolikheter.

    python -m mandatorn_model.markets            # hämta, skriv data/markets/latest.json + history.jsonl
    python -m mandatorn_model.markets --dry-run  # hämta och skriv ut, ändra inget

Källa: Polymarkets publika Gamma API (ingen nyckel). Pris = Polymarkets visade pris
(`outcomePrices[0]`: mittpunkt mellan bud och utbud, annars senaste avslut när spreaden är > 10 cent).

Obs: marknaderna gäller regeringsbildningen efter valet 2026, inte valet 2030.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
MARKETS_DIR = REPO / "data" / "markets"
LATEST_PATH = MARKETS_DIR / "latest.json"
HISTORY_PATH = MARKETS_DIR / "history.jsonl"

GAMMA_URL = "https://gamma-api.polymarket.com/events"
EVENT_URL = "https://polymarket.com/event/{slug}"
USER_AGENT = "Mandatorn/1.0 (mandatorn.se)"
TIMEOUT = 30

# slug → kort svensk titel. Lägg till 2030-marknader här när de finns.
EVENTS: dict[str, str] = {
    "next-prime-minister-of-sweden": "Nästa statsminister",
    "which-coalition-will-form-the-next-swedish-government": "Nästa regeringskoalition",
}

# Marknadens kandidat → modellens fråga (questions.toml). Den som jämförs är inte samma sak:
# marknaden gäller regeringsbildningen efter valet 2026, modellen "större stöd" i ett val idag.
COMPARISONS: list[dict] = [
    {"event": "next-prime-minister-of-sweden", "label": "Magdalena Andersson", "question": "vansterunderlaget-storre"},
    {"event": "next-prime-minister-of-sweden", "label": "Ulf Kristersson", "question": "hogerunderlaget-storre"},
]

MIN_DISPLAY_P = 0.005     # marknader under 0,5 % sparas inte (placeholders och chanslösa)
PRICE_DECIMALS = 4


def _price(market: dict) -> float | None:
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not raw:
        return None
    try:
        return float(raw[0])
    except (TypeError, ValueError):
        return None


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def parse_event(event: dict, title: str) -> dict:
    """Gamma-event → {slug, title, url, endDate, volume, liquidity, outcomes[{label, p, bid, ask}]}."""
    outcomes = []
    for m in event.get("markets", []):
        if m.get("closed") or not m.get("active", True):
            continue
        p = _price(m)
        label = (m.get("groupItemTitle") or m.get("question") or "").strip()
        if p is None or not label or p < MIN_DISPLAY_P:
            continue
        outcomes.append({"label": label, "p": round(p, PRICE_DECIMALS),
                         "bid": _num(m.get("bestBid")), "ask": _num(m.get("bestAsk"))})
    outcomes.sort(key=lambda o: -o["p"])
    return {
        "slug": event["slug"], "title": title, "url": EVENT_URL.format(slug=event["slug"]),
        "endDate": (event.get("endDate") or "")[:10] or None,
        "volume": round(_num(event.get("volume")) or 0.0),
        "liquidity": round(_num(event.get("liquidity")) or 0.0),
        "outcomes": outcomes,
    }


def fetch_event(slug: str, session: requests.Session | None = None) -> dict:
    get = (session or requests).get
    r = get(GAMMA_URL, params={"slug": slug}, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise LookupError(f"Polymarket har inget event med slug {slug!r}")
    return data[0]


def fetch_snapshot(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    with requests.Session() as s:
        events = [parse_event(fetch_event(slug, s), title) for slug, title in EVENTS.items()]
    return {"fetchedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Polymarket", "events": events}


def _prices(snapshot: dict) -> dict[str, dict[str, float]]:
    return {e["slug"]: {o["label"]: o["p"] for o in e["outcomes"]} for e in snapshot["events"]}


def history_row(snapshot: dict) -> dict:
    """Kompakt rad för tidsserien: {t, p: {slug: {label: pris}}}."""
    return {"t": snapshot["fetchedAt"], "p": _prices(snapshot)}


def last_history_row(path: Path = HISTORY_PATH) -> dict | None:
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = json.loads(line)
    return last


def save(snapshot: dict, latest: Path = LATEST_PATH, history: Path = HISTORY_PATH) -> bool:
    """Skriver latest.json alltid; lägger till en historikrad bara om något pris ändrats. True = historik ändrad."""
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    row = history_row(snapshot)
    prev = last_history_row(history)
    if prev is not None and prev["p"] == row["p"]:
        return False
    with open(history, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return True


def load_latest(path: Path = LATEST_PATH) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def comparison_rows(snapshot: dict, questions: dict[str, float]) -> list[dict]:
    """[{event, label, marketP, questionId, modelP}] för de jämförelser som finns i både marknad och modell."""
    by_event = {e["slug"]: {o["label"]: o["p"] for o in e["outcomes"]} for e in snapshot["events"]}
    rows = []
    for c in COMPARISONS:
        p = by_event.get(c["event"], {}).get(c["label"])
        if p is None or c["question"] not in questions:
            continue
        rows.append({"event": c["event"], "label": c["label"], "marketP": p,
                     "questionId": c["question"], "modelP": questions[c["question"]]})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="skriv ut utan att spara")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        snap = fetch_snapshot()
    except (requests.RequestException, LookupError, KeyError, ValueError) as e:
        print(f"Kunde inte hämta Polymarket: {e}", file=sys.stderr)
        return 1
    for e in snap["events"]:
        top = ", ".join(f"{o['label']} {o['p'] * 100:.1f} %" for o in e["outcomes"][:4])
        print(f"{e['title']} (volym ${e['volume']:,}, likviditet ${e['liquidity']:,}): {top}")
    if args.dry_run:
        return 0
    changed = save(snap)
    print("Historik uppdaterad." if changed else "Oförändrade priser — ingen ny historikrad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
