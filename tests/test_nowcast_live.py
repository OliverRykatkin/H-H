"""Fas 3: live-nowcast — simulatorn som integrationstest, baslinjemappning och felhantering."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import pytest

from mandatorn_model import contracts as C
from mandatorn_model import nowcast_live as NL
from mandatorn_model import publish as P
from mandatorn_model.storage import LocalStorage


@pytest.fixture()
def storage(tmp_path):
    P.run(str(tmp_path), reference_date=datetime(2026, 10, 1), n_sims=200)
    return LocalStorage(tmp_path)


def _manifest(st):
    return C.Manifest.model_validate_json(st.get("manifest.json"))


def _nowcast(st):
    m = _manifest(st)
    e = next(f for f in m.files if f.path == "nowcast.json")
    return C.NowcastLive.model_validate_json(st.get(e.object))


def test_simulator_spelar_upp_valnatten_2026(storage):
    before = _manifest(storage)
    src = NL.ReplaySource(2026, datetime(2026, 9, 13, 21, 0), timedelta(hours=1), end=datetime(2026, 9, 14, 4, 0))
    published = NL.run(src, storage, election="2026-09-13", baseline_year=2022, interval=0, sleep=lambda s: None,
                       log=lambda *a: None)
    assert len(published) == 8 and len(set(published)) == 8
    m = _manifest(storage)
    assert m.mode == "nowcast" and m.release == published[-1]
    # Alla prognosfiler finns kvar så att sajten fungerar under natten
    assert {f.path for f in before.files} <= {f.path for f in m.files}
    nc = _nowcast(storage)
    assert nc.nCounted > 6000 and sum(nc.seats.values()) == 349
    mae = sum(abs(nc.nowcast[p] - nc.final[p]) for p in nc.nowcast) / len(nc.nowcast) * 100
    assert mae < 0.3, mae
    status = json.loads(storage.get("status.json"))
    assert status["feedOk"] is True and status["mode"] == "nowcast"


def test_tidigt_pa_natten_slar_nowcast_raraakningen(storage):
    src = NL.ReplaySource(2026, datetime(2026, 9, 13, 21, 30), timedelta(hours=1), end=datetime(2026, 9, 13, 21, 30))
    NL.run(src, storage, election="2026-09-13", baseline_year=2022, interval=0, sleep=lambda s: None, log=lambda *a: None)
    nc = _nowcast(storage)
    err = lambda est: sum(abs(est[p] - nc.final[p]) for p in est) / len(est) * 100
    assert err(nc.nowcast) < err(nc.raw) / 2


def test_samma_lage_ger_samma_release(storage):
    rids = []
    for _ in range(2):
        src = NL.ReplaySource(2026, datetime(2026, 9, 13, 22, 0), timedelta(hours=1), end=datetime(2026, 9, 13, 22, 0))
        rids += NL.run(src, storage, election="2026-09-13", baseline_year=2022, interval=0, sleep=lambda s: None,
                       log=lambda *a: None)
    assert rids[0] == rids[1]


class _Broken:
    def fetch(self):
        raise ConnectionError("Valmyndigheten svarar inte")


def test_om_valmyndigheten_inte_svarar_ligger_senaste_release_kvar(storage):
    src = NL.ReplaySource(2026, datetime(2026, 9, 13, 22, 0), timedelta(hours=1), end=datetime(2026, 9, 13, 22, 0))
    NL.run(src, storage, election="2026-09-13", baseline_year=2022, interval=0, sleep=lambda s: None, log=lambda *a: None)
    good = _manifest(storage).release
    NL.run(_Broken(), storage, election="2026-09-13", baseline_year=2022, interval=0, max_iterations=2,
           sleep=lambda s: None, log=lambda *a: None)
    assert _manifest(storage).release == good
    status = json.loads(storage.get("status.json"))
    assert status["feedOk"] is False and "svarar inte" in status["feedError"]


def test_baslinje_mappas_via_foregaende_distrikt_och_delningar():
    current = pd.DataFrame([
        {"district_id": 1, "prev_codes": "01800101"},             # oförändrat
        {"district_id": 2, "prev_codes": "01800102|01800103"},    # sammanslaget
        {"district_id": 3, "prev_codes": "01800104"},             # delat på två
        {"district_id": 4, "prev_codes": "01800104"},
        {"district_id": 5, "prev_codes": ""},                     # nytt, ingen föregångare
    ])
    rows = []
    for code, tot in [("01800101", 100), ("01800102", 50), ("01800103", 30), ("01800104", 80)]:
        rows.append({"district_code": code, "total_valid_votes": tot, **{c: tot / 8 for c in NL.VOTE_COLS}})
    out = NL.align_baseline(current, pd.DataFrame(rows)).set_index("district_id")
    assert out.loc[1, "total_valid_votes"] == 100
    assert out.loc[2, "total_valid_votes"] == 80
    assert out.loc[3, "total_valid_votes"] == 40 and out.loc[4, "total_valid_votes"] == 40
    assert 5 not in out.index


@pytest.mark.skipif(not (NL.REPO / "data" / "raw" / "r-2018-per-valdistrikt.xlsx").exists(),
                    reason="2018 års distriktsdata saknas lokalt (data_loader laddar ner vid behov)")
def test_simulator_spelar_upp_valnatten_2022(storage):
    src = NL.ReplaySource(2022, datetime(2022, 9, 11, 21, 30), timedelta(hours=1), end=datetime(2022, 9, 12, 2, 30))
    published = NL.run(src, storage, election="2022-09-11", baseline_year=2018, interval=0, sleep=lambda s: None,
                       log=lambda *a: None)
    assert len(published) == 6
    nc = _nowcast(storage)
    mae = sum(abs(nc.nowcast[p] - nc.final[p]) for p in nc.nowcast) / len(nc.nowcast) * 100
    assert mae < 0.6, mae


def test_loggfel_paverkar_inte_status(storage):
    def bad_log(*a):
        raise UnicodeEncodeError("cp1252", "→", 0, 1, "kan inte koda")
    src = NL.ReplaySource(2026, datetime(2026, 9, 13, 22, 0), timedelta(hours=1), end=datetime(2026, 9, 13, 22, 0))
    published = NL.run(src, storage, election="2026-09-13", baseline_year=2022, interval=0, sleep=lambda s: None, log=bad_log)
    assert len(published) == 1
    assert json.loads(storage.get("status.json"))["feedOk"] is True
