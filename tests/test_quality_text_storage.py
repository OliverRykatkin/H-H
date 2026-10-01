"""Kvalitetsgrind, verbal skala, sannolikhetsfrågor och lagringsadapter."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from mandatorn_model import quality as Q
from mandatorn_model.constants import PARTIES, THRESHOLD
from mandatorn_model.probabilities import evaluate_questions
from mandatorn_model.storage import IMMUTABLE, LocalStorage, S3Storage
from mandatorn_model.text import display_pct, verbal

CFG = {"share_sum_min": 88.0, "share_sum_max": 101.5, "max_jump_large_pp": 4.0, "max_jump_small_pp": 2.5,
       "large_party_pct": 10.0, "max_dev_from_aggregate_pp": 6.0, "recent_days": 120}
REF = datetime(2026, 10, 1)
OK = {"M": 20, "L": 5, "C": 7, "KD": 6, "S": 28, "V": 8, "MP": 6, "SD": 18}


def _poll(company, date, to=None, **over):
    row = {"Company": company, "PublDate": pd.Timestamp(date), "collectPeriodFrom": None,
           "collectPeriodTo": to, **OK, **over}
    return row


def _ids(rep):
    return {i for i, _ in rep.flags}


def test_kvalitet_ok():
    df = pd.DataFrame([_poll("Novus", "2026-09-01"), _poll("Novus", "2026-09-20", M=21)])
    assert Q.check_polls(df, REF, CFG).ok


def test_kvalitet_flaggar_summa_framtid_hopp_dubblett():
    df = pd.DataFrame([
        _poll("Novus", "2026-09-01"),
        _poll("Novus", "2026-09-20", M=27, S=21),                   # hopp +7 pp
        _poll("Sifo", "2026-09-21", S=50),                          # summa 120
        _poll("Ipsos", "2026-09-22", to="2026-12-01"),             # fältperiod i framtiden
        _poll("Demoskop", "2026-09-23"), _poll("Demoskop", "2026-09-23"),  # dubblett
    ])
    ids = _ids(Q.check_polls(df, REF, CFG))
    assert "jump:Novus:2026-09-20:M" in ids
    assert "sum:Sifo:2026-09-21" in ids
    assert "future:Ipsos:2026-09-22" in ids
    assert "duplicate:Demoskop:2026-09-23" in ids


def test_kvitterade_flaggor_blockerar_inte():
    df = pd.DataFrame([_poll("Novus", "2026-09-01"), _poll("Novus", "2026-09-20", M=27, S=21)])
    rep = Q.check_polls(df, REF, CFG).apply_acks({"jump:Novus:2026-09-20:M", "jump:Novus:2026-09-20:S"})
    assert rep.ok and len(rep.acknowledged) == 2


def test_gamla_matningar_granskas_inte():
    df = pd.DataFrame([_poll("Novus", "2025-01-01"), _poll("Novus", "2025-02-01", M=30)])
    assert Q.check_polls(df, REF, CFG).ok


@pytest.mark.parametrize("p,label", [
    (0.0, "Väldigt osannolikt"), (0.099, "Väldigt osannolikt"), (0.10, "Osannolikt"),
    (0.349, "Osannolikt"), (0.35, "Jämnt"), (0.5, "Jämnt"), (0.65, "Jämnt"),
    (0.651, "Troligt"), (0.90, "Troligt"), (0.901, "Väldigt troligt"), (1.0, "Väldigt troligt"),
])
def test_verbal_skala(p, label):
    assert verbal(p) == label


@pytest.mark.parametrize("p,txt", [(0.0, "<1 %"), (0.0099, "<1 %"), (0.01, "1 %"), (0.5, "50 %"),
                                   (0.99, "99 %"), (0.9901, ">99 %"), (1.0, ">99 %")])
def test_aldrig_noll_eller_hundra_procent(p, txt):
    assert display_pct(p) == txt


def _fake_sim(n=2000, seed=1):
    rng = np.random.default_rng(seed)
    means = {"M": 20, "L": 4.2, "C": 7, "KD": 5.5, "S": 29, "V": 8, "MP": 4.5, "SD": 19}
    draws = {p: np.maximum(0, rng.normal(m, 1.5, n)) for p, m in means.items()}
    tot = sum(draws.values())
    draws = {p: v / tot * 100 for p, v in draws.items()}
    return {"draws": draws, "n_sims": n,
            "above_threshold": {p: float((draws[p] >= THRESHOLD).mean()) for p in PARTIES},
            "party_mandates": {p: np.zeros(n, int) for p in PARTIES}}


def test_fragorna_ger_samma_svar_som_tidigare_inline_kod():
    sim = _fake_sim()
    d, at = sim["draws"], sim["above_threshold"]
    v = sum(d[p] for p in ["S", "V", "MP", "C"]); h = sum(d[p] for p in ["M", "L", "KD", "SD"])
    expected = [
        float((v > h).mean()), float((h > v).mean()),
        float((sum(d[p] for p in ["S", "V", "MP"]) > 50).mean()),
        float((sum(d[p] for p in ["S", "C", "MP"]) > 50).mean()),
        float((d["SD"] > sum(d[p] for p in ["M", "L", "KD"])).mean()),
        at["MP"], at["L"], at["KD"], at["C"],
        float(np.mean(np.all(np.stack([d[p] >= THRESHOLD for p in PARTIES]), axis=0))),
        float((d["M"] > d["SD"]).mean()),
    ]
    assert [q["p"] for q in evaluate_questions(sim)] == expected


def test_local_storage_immutable(tmp_path):
    s = LocalStorage(tmp_path)
    assert s.put_immutable("files/a.json", b"1", "application/json") is True
    assert s.put_immutable("files/a.json", b"2", "application/json") is False
    assert s.get("files/a.json") == b"1"
    s.put_pointer("manifest.json", b"x", "application/json")
    s.put_pointer("manifest.json", b"y", "application/json")
    assert s.get("manifest.json") == b"y"


class _FakeS3:
    def __init__(self):
        self.objects, self.calls = {}, []

    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def put_object(self, **kw):
        self.calls.append(kw)
        self.objects[kw["Key"]] = kw["Body"]

    def list_objects_v2(self, **kw):
        prefixes = sorted({k.split("/")[1] for k in self.objects if k.startswith("releases/") and k.count("/") >= 2})
        return {"CommonPrefixes": [{"Prefix": f"releases/{p}/"} for p in prefixes], "IsTruncated": False}


class _FakeCF:
    def __init__(self):
        self.batches = []

    def create_invalidation(self, DistributionId, InvalidationBatch):
        self.batches.append((DistributionId, InvalidationBatch))


def test_s3_adapter_cache_headers_och_invalidering():
    s3, cf = _FakeS3(), _FakeCF()
    st = S3Storage("bucket", client=s3, distribution_id="E1", cdn_client=cf)
    assert st.put_immutable("files/x.json", b"{}", "application/json", tags={"retention": "draws"})
    assert not st.put_immutable("files/x.json", b"{}", "application/json")
    assert s3.calls[0]["CacheControl"] == IMMUTABLE and s3.calls[0]["Tagging"] == "retention=draws"
    st.put_pointer("releases/abc/manifest.json", b"{}", "application/json")
    assert st.list_releases() == ["abc"]
    st.invalidate(["manifest.json"])
    assert cf.batches[0][0] == "E1" and cf.batches[0][1]["Paths"]["Items"] == ["/manifest.json"]
