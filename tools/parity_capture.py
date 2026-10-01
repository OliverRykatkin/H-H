"""Fångar allt som Streamlit-appen ritar, för paritetstest mellan två versioner.

Kör app.main() mot en Streamlit-stubbe där widgets returnerar sina standardvärden,
med fryst klocka och nätverkssvar från lokala filer, och sparar en ordnad lista av
alla anrop (grafer som Plotly-JSON, tabeller som CSV, metrics och texter).

    python tools/parity_capture.py <repo> <ut.json> --now 2026-10-01T12:00:00 --fixtures <katalog>

Första gången hämtas nätverkssvaren och sparas i --fixtures; därefter används de.
Jämför två fångster med tools/parity_compare.py.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock


def _build_streamlit_stub(log: list):
    def _cache(*a, **k):
        return a[0] if a and callable(a[0]) else (lambda f: f)

    def _first(options, index=0):
        options = list(options)
        return options[index] if options else None

    def _record(kind):
        def _f(*args, **kwargs):
            log.append((kind, args, kwargs))
            return MagicMock()
        return _f

    st = MagicMock()
    st.cache_data = _cache
    st.cache_resource = _cache
    st.columns.side_effect = lambda spec, **k: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
    st.radio.side_effect = lambda label, options, index=0, **k: _first(options, index)
    st.selectbox.side_effect = lambda label, options, index=0, **k: _first(options, index)
    st.select_slider.side_effect = lambda label, options=None, value=None, **k: value if value is not None else _first(options)
    st.slider.side_effect = lambda label, min_value=None, max_value=None, value=None, **k: value
    st.multiselect.side_effect = lambda label, options, default=None, **k: default or []
    st.checkbox.side_effect = lambda label, value=False, **k: value
    st.toggle.side_effect = lambda label, value=False, **k: value
    st.number_input.side_effect = lambda label, min_value=None, max_value=None, value=None, **k: value
    st.text_input.side_effect = lambda label, value="", **k: value
    st.button.return_value = False
    st.query_params = {}
    for kind in ("plotly_chart", "dataframe", "table", "metric", "markdown", "caption", "write",
                 "header", "subheader", "info", "success", "warning", "error", "download_button",
                 "title", "latex", "progress"):
        setattr(st, kind, MagicMock(side_effect=_record(kind)))
    return st


def _serialize(obj):
    import pandas as pd
    try:
        import plotly.graph_objects as go
    except ImportError:  # pragma: no cover
        go = None
    if go is not None and isinstance(obj, go.Figure):
        return {"figure": json.loads(obj.to_json())}
    if hasattr(obj, "data") and obj.__class__.__name__ == "Styler":
        obj = obj.data
    if isinstance(obj, pd.DataFrame):
        return {"dataframe": obj.to_csv()}
    if isinstance(obj, pd.Series):
        return {"series": obj.to_csv()}
    if isinstance(obj, (bytes, bytearray)):
        return {"bytes_sha256": hashlib.sha256(obj).hexdigest(), "len": len(obj)}
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    return f"<{type(obj).__name__}>"


def _freeze_clock(now: _dt.datetime, repo: Path):
    class FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.replace(tzinfo=tz)

        @classmethod
        def today(cls):
            return now

    class FrozenDate(_dt.date):
        @classmethod
        def today(cls):
            return now.date()

    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None) or ""
        if not f or not Path(f).resolve().is_relative_to(repo):
            continue
        if getattr(mod, "datetime", None) is _dt.datetime:
            mod.datetime = FrozenDatetime
        if getattr(mod, "date", None) is _dt.date:
            mod.date = FrozenDate


def _patch_network(fixtures: Path):
    import requests

    real_get = requests.get
    fixtures.mkdir(parents=True, exist_ok=True)

    def fake_get(url, *args, **kwargs):
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        path = fixtures / key
        if not path.exists():
            resp = real_get(url, *args, **kwargs)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            (fixtures / f"{key}.url").write_text(url)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = path.read_bytes()
        resp.url = url
        resp.encoding = "utf-8"
        return resp

    requests.get = fake_get


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    ap.add_argument("--now", required=True)
    ap.add_argument("--fixtures", required=True)
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    now = _dt.datetime.fromisoformat(args.now)
    log: list = []
    sys.modules["streamlit"] = _build_streamlit_stub(log)
    sys.path.insert(0, str(repo))
    _patch_network(Path(args.fixtures))

    import app  # noqa: F401  (laddar även mandatorn_model om den finns)
    _freeze_clock(now, repo)
    app.main()

    out = [{"kind": k, "args": _serialize(list(a)), "kwargs": _serialize(kw)} for k, a, kw in log]
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"{len(out)} anrop fångade → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
