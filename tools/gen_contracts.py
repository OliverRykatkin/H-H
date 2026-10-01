"""Generera JSON Schema och TypeScript-typer från mandatorn_model.contracts.

    python tools/gen_contracts.py          # skriver contracts/schema/*.json + contracts/ts/contracts.ts
    python tools/gen_contracts.py --check  # misslyckas om de genererade filerna är inaktuella (CI)

TypeScript genereras med json-schema-to-typescript via npx.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from mandatorn_model.contracts import ARTIFACT_MODELS, SCHEMA_VERSION  # noqa: E402

OUT_SCHEMA = REPO / "contracts" / "schema"
OUT_TS = REPO / "contracts" / "ts" / "contracts.ts"


def _strip_field_titles(node, top=True):
    """Pydantic sätter title på varje fält; json-schema-to-typescript gör då ett alias per fält."""
    if isinstance(node, dict):
        if not top and "title" in node and "properties" not in node:
            node.pop("title")
        for v in node.values():
            _strip_field_titles(v, top=False)
    elif isinstance(node, list):
        for v in node:
            _strip_field_titles(v, top=False)
    return node


def schemas() -> dict[str, str]:
    out = {}
    for name, model in ARTIFACT_MODELS.items():
        s = _strip_field_titles(model.model_json_schema())
        s["$id"] = f"https://data.mandatorn.se/schema/v{SCHEMA_VERSION}/{name}.json"
        out[f"{name}.schema.json"] = json.dumps(s, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return out


def typescript(schema_files: dict[str, str]) -> str:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("npx saknas (installera Node.js)")
    parts = [
        "/* Genererad av tools/gen_contracts.py — redigera inte för hand. */",
        f"export const SCHEMA_VERSION = {SCHEMA_VERSION};",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for fname, text in sorted(schema_files.items()):
            src = Path(tmp) / fname
            src.write_text(text, encoding="utf-8")
            res = subprocess.run(
                [npx, "--yes", "json-schema-to-typescript@15", "--input", str(src),
                 "--bannerComment", "", "--additionalProperties", "false", "--unreachableDefinitions"],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            parts.append(f"// ── {fname} ──\n" + res.stdout.strip())
    return dedupe("\n\n".join(parts) + "\n")


def dedupe(ts: str) -> str:
    """Delade typer (t.ex. FileEntry) genereras en gång per schema; behåll första."""
    seen, out = set(), []
    for block in ts.split("\n\n"):
        head = block.lstrip().split("\n", 1)[0]
        name = None
        for kw in ("export interface ", "export type "):
            if head.startswith(kw):
                name = head[len(kw):].split()[0].rstrip("{=")
        if name and name in seen:
            continue
        if name:
            seen.add(name)
        out.append(block)
    return "\n\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = schemas()
    ts = typescript(files)
    if args.check:
        stale = [f for f, t in files.items() if (OUT_SCHEMA / f).read_text(encoding="utf-8") != t] \
            if OUT_SCHEMA.exists() else list(files)
        if not OUT_TS.exists() or OUT_TS.read_text(encoding="utf-8") != ts:
            stale.append(str(OUT_TS.relative_to(REPO)))
        if stale:
            print("Inaktuella genererade kontrakt:", ", ".join(stale))
            return 1
        print("Kontrakten är aktuella.")
        return 0
    OUT_SCHEMA.mkdir(parents=True, exist_ok=True)
    for f, t in files.items():
        (OUT_SCHEMA / f).write_text(t, encoding="utf-8", newline="\n")
    OUT_TS.parent.mkdir(parents=True, exist_ok=True)
    OUT_TS.write_text(ts, encoding="utf-8", newline="\n")
    print(f"Skrev {len(files)} scheman och {OUT_TS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
