"""Publicering: determinism, idempotens, rättelser, latest-alias och kontrakt."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest

from mandatorn_model import contracts as C
from mandatorn_model import publish as P

REF = datetime(2026, 10, 1)
N_SIMS = 300  # litet för snabba tester; samma kodväg som 10 000


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    res = P.run(str(out), reference_date=REF, n_sims=N_SIMS)
    return out, res


def _manifest(out):
    return C.Manifest.model_validate_json((out / "manifest.json").read_bytes())


def test_samma_indata_ger_samma_release_id(published, tmp_path):
    out, res = published
    again = P.run(str(tmp_path), reference_date=REF, n_sims=N_SIMS)
    assert again["release"] == res["release"]


def test_annan_seed_ger_annan_release(published, tmp_path):
    _, res = published
    other = P.run(str(tmp_path), reference_date=REF, n_sims=N_SIMS, seed=7)
    assert other["release"] != res["release"]


def test_manifest_stammer_mot_filerna(published):
    out, res = published
    m = _manifest(out)
    assert m.release == res["release"] and m.schemaVersion == C.SCHEMA_VERSION
    assert m.seed == 42 and m.mode == "forecast" and m.supersededBy is None
    assert len((out / "manifest.json").read_bytes()) < 100_000
    for f in m.files:
        data = (out / f.object).read_bytes()
        assert len(data) == f.size
        assert hashlib.sha256(data).hexdigest() == f.sha256
    paths = {f.path for f in m.files}
    for required in ("national.json", "timeseries.json", "mandates.json", "simulation.json",
                     "probabilities.json", "valkrets/stockholms-stad.json", "kommun/0180.json",
                     "region/01.json", "open/mandat.csv", "open/mandat.schema.json"):
        assert required in paths


def test_release_id_ar_hash_av_filindex(published):
    out, _ = published
    m = _manifest(out)
    index = json.dumps([[f.path, f.sha256] for f in sorted(m.files, key=lambda f: f.path)],
                       separators=(",", ":")).encode()
    assert hashlib.sha256(index).hexdigest() == m.release


def test_ompublicering_skriver_inga_nya_filer(published):
    out, res = published
    again = P.run(str(out), reference_date=REF, n_sims=N_SIMS)
    assert again["release"] == res["release"] and again["written"] == 0


def test_filer_ar_immutable_och_manifest_kort_cache(published):
    out, _ = published
    m = _manifest(out)
    meta = json.loads((out / (m.files[0].object + ".meta.json")).read_text())
    assert meta["CacheControl"] == "public, max-age=31536000, immutable"
    assert "no-cache" in json.loads((out / "manifest.json.meta.json").read_text())["CacheControl"]


def test_latest_alias_och_schema(published):
    out, _ = published
    for name in ("timeseries", "institutsbias", "kommuner", "regioner", "valkretsar", "mandat"):
        assert (out / "latest" / f"{name}.csv").exists()
        schema = json.loads((out / "latest" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert schema["license"] == "CC BY-NC 4.0" and schema["columns"]
    assert not (out / "latest" / "kandidater.csv").exists()  # avstängd i publish.toml (D10)
    assert "CC BY-NC 4.0" in (out / "latest" / "README.md").read_text(encoding="utf-8")


def test_rattelse_satter_superseded_by(tmp_path):
    first = P.run(str(tmp_path), reference_date=datetime(2026, 9, 30), n_sims=N_SIMS)
    second = P.run(str(tmp_path), reference_date=REF, n_sims=N_SIMS, supersedes=first["release"])
    old = C.Manifest.model_validate_json((tmp_path / "releases" / first["release"] / "manifest.json").read_bytes())
    assert old.supersededBy == second["release"]
    idx = C.ReleaseIndex.model_validate_json((tmp_path / "releases" / "index.json").read_bytes())
    by_id = {e.release: e for e in idx.releases}
    assert by_id[first["release"]].supersededBy == second["release"]
    assert by_id[second["release"]].supersededBy is None
    assert _manifest(tmp_path).release == second["release"]


def test_mandat_och_sannolikheter_rimliga(published):
    out, _ = published
    m = _manifest(out)
    get = lambda p: json.loads((out / next(f.object for f in m.files if f.path == p)).read_bytes())
    nat = get("national.json")
    assert sum(nat["seats"].values()) == 349
    for q in get("probabilities.json")["questions"]:
        assert 0 <= q["p"] <= 1 and q["display"] not in ("0 %", "100 %")
    vk = get("valkrets/stockholms-stad.json")
    for party, dist in vk["seatDistribution"].items():
        assert abs(sum(dist.values()) - 1) < 1e-3, party


def test_slugify():
    assert P.slugify("Västra Götaland") == "vastra-gotaland"
    assert P.slugify("Skåne N/Ö") == "skane-n-o"
    assert P.slugify("Stockholms stad") == "stockholms-stad"
