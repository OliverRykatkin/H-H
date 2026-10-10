"""EU-valnatten: feed-schema, EU-simulatorn (valnatten 2024) och release under eu2029/."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta

import pytest

from mandatorn_model import contracts as C
from mandatorn_model import eu_publish, nowcast_live as NL, val_feed as vf
from mandatorn_model.constants import PARTIES
from mandatorn_model.election import EU2029
from mandatorn_model.storage import LocalStorage, PrefixedStorage

START = datetime(2024, 6, 9, 21, 0)


def test_index_och_filer_for_eu_valet():
    text = ("a" * 32 + "  ./p/e/EU-val_2024_preliminar_00_E.zip\n" + "b" * 32 + "  ./s/e/EU-val_2024_slutlig_00_E.zip\n")
    idx = vf.parse_index(text)
    assert vf.find_eu_file(idx, preliminary=True)[0] == "./p/e/EU-val_2024_preliminar_00_E.zip"
    assert vf.find_eu_file(idx, preliminary=False)[0] == "./s/e/EU-val_2024_slutlig_00_E.zip"
    assert vf.index_url(2024, "euval") == "https://resultat.val.se/resultatfiler/euval2024/index.md5"
    assert vf.index_url(2026).endswith("/val2026/index.md5")


def test_download_anvander_euval_katalog(monkeypatch):
    seen = []
    monkeypatch.setattr(vf, "_http_get", lambda url, timeout=120: seen.append(url) or b"x")
    vf.download_file(2024, "./p/e/EU-val_2024_preliminar_00_E.zip", prefix="euval")
    assert seen == ["https://resultat.val.se/resultatfiler/euval2024/p/e/EU-val_2024_preliminar_00_E.zip"]


def test_windows1252_i_zip_tolkas():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x_mandatfordelning_00_E.json", json.dumps({"namn": "Miljöpartiet"}, ensure_ascii=False).encode("cp1252"))
    assert vf.extract_mandatfordelning(buf.getvalue())["namn"] == "Miljöpartiet"


@pytest.fixture(scope="module")
def night(tmp_path_factory):
    out = tmp_path_factory.mktemp("eu-night")
    eu_publish.run(str(out), datetime(2026, 10, 10), n_sims=200)
    storage = PrefixedStorage(LocalStorage(out), EU2029.release_prefix)
    src = NL.ReplaySource("eu2024", START, timedelta(hours=1), end=START + timedelta(hours=12))
    ids = NL.run(src, storage, election="2024-06-09", baseline_year=2019, interval=0, compute=NL.compute_state_eu,
                 log=lambda m: None)
    return out, storage, ids


def _state(storage):
    m = C.Manifest.model_validate_json(storage.get("manifest.json"))
    f = next(f for f in m.files if f.path == "nowcast.json")
    return m, C.EuNowcastLive.model_validate_json(storage.get(f.object))


def test_simulatorn_publicerar_nowcast_i_eu_kedjan(night):
    out, storage, ids = night
    assert len(ids) >= 8
    m, state = _state(storage)
    assert m.mode == "nowcast"
    assert {"national.json", "simulation.json", "backtest.json", "nowcast.json"} <= {f.path for f in m.files}
    assert not (out / "manifest.json").exists()          # riksdagens kedja rörs inte


def test_nowcast_nar_det_officiella_utfallet(night):
    _, storage, _ = night
    _, state = _state(storage)
    assert sum(state.seats.values()) == state.seatsTotal == 21
    assert state.nCounted > 6000 and state.voteShareCounted > 0.9
    assert sum(abs(state.seats[p] - state.finalSeats.get(p, 0)) for p in PARTIES) // 2 <= 1
    assert max(abs(state.nowcast[p] - state.final[p]) for p in PARTIES) < 0.01


def test_tidig_nowcast_har_farre_distrikt_an_slutet(night):
    out, storage, ids = night
    first = C.Manifest.model_validate_json(storage.get(f"releases/{ids[0]}/manifest.json"))
    f = next(f for f in first.files if f.path == "nowcast.json")
    early = C.EuNowcastLive.model_validate_json(storage.get(f.object))
    _, late = _state(storage)
    assert early.nCounted < late.nCounted and early.voteShareCounted < late.voteShareCounted
