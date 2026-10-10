"""EU-prognosen: proxy, simulering, backtest och release under eget prefix."""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pytest

from mandatorn_model import contracts as C
from mandatorn_model import eu_forecast as F
from mandatorn_model import eu_publish
from mandatorn_model.constants import PARTIES
from mandatorn_model.election import EU2029
from mandatorn_model.polls import parse_polls
from mandatorn_model.publish import REPO
from mandatorn_model.storage import LocalStorage, PrefixedStorage

RESULTS = F.load_eu_results()
POLLS = parse_polls((REPO / "data/polls/Polls.csv").read_text(encoding="utf-8"))
REF = datetime(2026, 10, 10)


def test_avvikelse_ar_eu_minus_riksdag():
    dev = F.deviations(RESULTS, ["2024"])["2024"]
    eu = F.eu_shares(RESULTS["2024"])
    assert dev["MP"] == pytest.approx(eu["MP"] - 5.08)
    assert eu["O"] == pytest.approx(100 - sum(eu[p] for p in PARTIES))


def test_proxy_utan_historia_ar_nollavvikelse_och_summerar_till_100():
    proxy = F.Proxy.from_history(RESULTS, [])
    raw = {"M": 20, "L": 5, "C": 7, "KD": 6, "S": 28, "V": 8, "MP": 6, "SD": 20}
    shares = F.proxy_shares(raw, proxy, rd_others=1.59)
    assert sum(shares.values()) == pytest.approx(100.0)
    assert shares["S"] == pytest.approx(28 * 0.9841 * (100 - proxy.others) / (100 * 0.9841 - 0), rel=0.02)


def test_krympning_halverar_medelavvikelsen():
    full = F.Proxy.from_history(RESULTS, ["2019", "2024"], shrink=1.0)
    half = F.Proxy.from_history(RESULTS, ["2019", "2024"], shrink=0.5)
    assert all(half.shift[p] == pytest.approx(full.shift[p] / 2) for p in PARTIES)
    assert all(v >= F.DEV_SD_FLOOR for v in half.dev_sd.values())


def test_punktprognos_och_simulering_ger_21_mandat():
    fc = F.build_eu_forecast(POLLS, REF, n_sims=300)
    assert sum(fc.seats.values()) == EU2029.seats == 21
    assert sum(fc.shares.values()) == pytest.approx(100.0)
    totals = sum(fc.sim["seats"][p] for p in PARTIES)
    assert np.all(totals == 21)
    assert sum(fc.sim["p_largest"].values()) == pytest.approx(1.0)
    assert fc.days_left == (EU2029.election_date - REF).days


def test_samma_seed_ger_samma_dragningar():
    a = F.build_eu_forecast(POLLS, REF, seed=7, n_sims=200)
    b = F.build_eu_forecast(POLLS, REF, seed=7, n_sims=200)
    assert all((a.sim["seats"][p] == b.sim["seats"][p]).all() for p in PARTIES)


def test_backtest_anvander_inte_samma_vals_avvikelse():
    rows = F.backtest(POLLS, RESULTS)
    assert [r["year"] for r in rows] == [2019, 2024]
    assert rows[0]["adjustedFrom"] == [] and rows[0]["adjusted"] == pytest.approx(rows[0]["naive"])
    assert rows[1]["adjustedFrom"] == ["2019"]
    for r in rows:
        assert sum(r["seatsOfficial"].values()) == 21


def test_release_hamnar_under_eget_prefix(tmp_path):
    fc = F.build_eu_forecast(POLLS, REF, n_sims=200)
    release = eu_publish.build_release(fc, F.backtest(POLLS, RESULTS))
    for path, model in (("national.json", C.EuNational), ("simulation.json", C.EuSimulation),
                        ("backtest.json", C.EuBacktest)):
        model.model_validate_json(release.files[path][0])
    manifest, objects = eu_publish.assemble(release, dict(
        generatedAt=REF.isoformat(), modelVersion="test", seed=42, inputHash="x", mode="forecast",
        pollsIncluded=C.PollsIncluded(count=1, latestFieldEnd=None, latestPublished="2026-10-01")))
    base = LocalStorage(tmp_path)
    eu_publish.write(PrefixedStorage(base, EU2029.release_prefix), manifest, objects, {})
    assert (tmp_path / "eu2029" / "manifest.json").exists()
    assert not (tmp_path / "manifest.json").exists()      # riksdagens pekare rörs inte
    nat = json.loads((tmp_path / "eu2029" / "files" / manifest.files[1].object.split("/")[1]).read_bytes())
    assert nat["electionDateProvisional"] is True and nat["seatsTotal"] == 21
