"""Jämför två fångster från parity_capture.py.

Mandat och heltal måste vara identiska. Flyttal får avvika med högst --tol
(standard 1e-9) — allt annat (texter, ordning, antal anrop) måste vara identiskt.

    python tools/parity_compare.py gammal.json ny.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys


def _cmp_csv(a: str, b: str, tol: float, path: str, diffs: list):
    import pandas as pd
    da, db = pd.read_csv(io.StringIO(a)), pd.read_csv(io.StringIO(b))
    if list(da.columns) != list(db.columns) or da.shape != db.shape:
        diffs.append(f"{path}: tabellform {da.shape}/{list(da.columns)[:5]} ≠ {db.shape}/{list(db.columns)[:5]}")
        return
    for c in da.columns:
        for i, (x, y) in enumerate(zip(da[c], db[c])):
            _cmp(x, y, tol, f"{path}[{i},{c}]", diffs)


def _cmp(a, b, tol: float, path: str, diffs: list):
    if len(diffs) > 50:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        if "dataframe" in a and "dataframe" in b:
            return _cmp_csv(a["dataframe"], b["dataframe"], tol, path, diffs)
        if set(a) != set(b):
            diffs.append(f"{path}: nycklar {sorted(set(a) ^ set(b))[:5]}")
        for k in sorted(set(a) & set(b)):
            _cmp(a[k], b[k], tol, f"{path}.{k}", diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: längd {len(a)} ≠ {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _cmp(x, y, tol, f"{path}[{i}]", diffs)
    elif isinstance(a, bool) or isinstance(b, bool) or isinstance(a, int) and isinstance(b, int):
        if a != b:
            diffs.append(f"{path}: {a!r} ≠ {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if not (math.isclose(a, b, rel_tol=tol, abs_tol=tol) or (math.isnan(a) and math.isnan(b))):
            diffs.append(f"{path}: {a!r} ≠ {b!r}")
    elif a != b:
        if isinstance(a, str) and isinstance(b, str) and (a.lower() == "nan") == (b.lower() == "nan") == True:
            return
        diffs.append(f"{path}: {str(a)[:80]!r} ≠ {str(b)[:80]!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--tol", type=float, default=1e-9)
    args = ap.parse_args()
    old = json.load(open(args.old, encoding="utf-8"))
    new = json.load(open(args.new, encoding="utf-8"))
    diffs: list = []
    if len(old) != len(new):
        diffs.append(f"antal anrop {len(old)} ≠ {len(new)}")
    for i, (a, b) in enumerate(zip(old, new)):
        if a["kind"] != b["kind"]:
            diffs.append(f"anrop {i}: {a['kind']} ≠ {b['kind']}")
            break
        _cmp(a["args"], b["args"], args.tol, f"#{i}:{a['kind']}.args", diffs)
        _cmp(a["kwargs"], b["kwargs"], args.tol, f"#{i}:{a['kind']}.kwargs", diffs)
    if diffs:
        print(f"PARITET FALLERAR ({len(diffs)} skillnader, visar max 50):")
        for d in diffs[:50]:
            print("  ", d)
        return 1
    print(f"Paritet OK: {len(old)} anrop identiska (flyttal inom {args.tol}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
