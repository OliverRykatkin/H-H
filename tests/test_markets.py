"""Polymarket-hämtning: parsning, historik och jämförelse (offline, inga nätverksanrop)."""
import json

from mandatorn_model import markets as MK

EVENT = {
    "slug": "next-prime-minister-of-sweden", "endDate": "2027-07-01T03:59:00Z", "volume": 12608411.7, "liquidity": 1218072.6,
    "markets": [
        {"groupItemTitle": "Magdalena Andersson", "outcomePrices": '["0.695", "0.305"]', "bestBid": 0.69, "bestAsk": 0.7,
         "active": True, "closed": False},
        {"groupItemTitle": "Ulf Kristersson", "outcomePrices": '["0.298", "0.702"]', "bestBid": 0.293, "bestAsk": 0.303,
         "active": True, "closed": False},
        {"groupItemTitle": "Jimmie Åkesson", "outcomePrices": '["0.0005", "0.9995"]', "bestBid": None, "bestAsk": 0.001,
         "active": True, "closed": False},                                           # under 0,5 % → bort
        {"groupItemTitle": "Candidate B", "outcomePrices": None, "active": True, "closed": False},   # placeholder
        {"groupItemTitle": "Stängd", "outcomePrices": '["0.5", "0.5"]', "active": True, "closed": True},
    ],
}


def _snap(prices=(0.695, 0.298), t="2026-11-16T10:00:00Z"):
    ev = json.loads(json.dumps(EVENT))
    ev["markets"][0]["outcomePrices"] = json.dumps([str(prices[0]), "x"])
    ev["markets"][1]["outcomePrices"] = json.dumps([str(prices[1]), "x"])
    return {"fetchedAt": t, "source": "Polymarket", "events": [MK.parse_event(ev, "Nästa statsminister")]}


def test_parse_event_filtrerar_och_sorterar():
    e = MK.parse_event(EVENT, "Nästa statsminister")
    assert [o["label"] for o in e["outcomes"]] == ["Magdalena Andersson", "Ulf Kristersson"]
    assert e["outcomes"][0]["p"] == 0.695 and e["outcomes"][0]["bid"] == 0.69
    assert e["endDate"] == "2027-07-01" and e["volume"] == 12608412 and e["liquidity"] == 1218073
    assert e["url"] == "https://polymarket.com/event/next-prime-minister-of-sweden"


def test_historik_skrivs_bara_vid_andrade_priser(tmp_path):
    latest, hist = tmp_path / "latest.json", tmp_path / "history.jsonl"
    assert MK.save(_snap(), latest, hist) is True
    assert MK.save(_snap(t="2026-11-16T16:00:00Z"), latest, hist) is False           # samma priser
    assert json.loads(latest.read_text(encoding="utf-8"))["fetchedAt"] == "2026-11-16T16:00:00Z"
    assert MK.save(_snap(prices=(0.70, 0.29), t="2026-11-17T04:00:00Z"), latest, hist) is True
    rows = [json.loads(line) for line in hist.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and rows[1]["p"]["next-prime-minister-of-sweden"]["Magdalena Andersson"] == 0.70


def test_jamforelse_kraver_bade_marknad_och_modellfraga():
    rows = MK.comparison_rows(_snap(), {"vansterunderlaget-storre": 0.6, "hogerunderlaget-storre": 0.4})
    assert {r["label"]: (r["marketP"], r["modelP"]) for r in rows} == {
        "Magdalena Andersson": (0.695, 0.6), "Ulf Kristersson": (0.298, 0.4)}
    assert MK.comparison_rows(_snap(), {"vansterunderlaget-storre": 0.6})[0]["label"] == "Magdalena Andersson"
    assert len(MK.comparison_rows(_snap(), {})) == 0
