"""Pre-hämta 2022 års kommun-/regionvalsstruktur → data/muni_structure_2022.json.

Laddar ner Valmyndighetens slutliga KF- (290 kommuner) och RF-filer (20 regioner)
för 2022, extraherar valkretsstruktur (mandat per valkrets, utjämningsmandat, spärr)
och 2022 års röster per parti och valkrets, och committar allt som en enda JSON.

Filen driver den *opinionsbaserade* mandatuppskattningen på Regional-fliken
(full kommunal modell: Sainte-Laguë per valkrets + utjämningsmandat + spärr) och
levererar namn↔kod-mappningen för kommun-/region-selectboxarna.

Körs sällan — bara om Valmyndigheten rättar 2022-siffror:
    python fetch_muni_cache.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from val_feed import (
    download_file,
    extract_mandatfordelning,
    fetch_index,
    find_area_file,
    parse_area_structure,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "muni_structure_2022.json"


def _codes_for(index: dict[str, str], valtyp: str, preliminary: bool = False) -> list[str]:
    """Plocka ut alla valområdeskoder för en valtyp ur manifestet."""
    stage = "p" if preliminary else "s"
    prefix = f"./{stage}/{valtyp.lower()}/"
    suffix = f"_{valtyp}.zip"
    codes = []
    for relpath in index:
        if relpath.startswith(prefix) and relpath.endswith(suffix):
            # ./s/kf/Val_20220911_slutlig_0180_KF.zip → "0180"
            codes.append(relpath[:-len(suffix)].split("_")[-1])
    return sorted(set(codes))


def build(year: int | str = 2022, preliminary: bool = False) -> dict:
    index = fetch_index(year)
    out: dict = {"generated_from": f"val{year}", "KF": {}, "RF": {}}

    for valtyp in ("KF", "RF"):
        codes = _codes_for(index, valtyp, preliminary=preliminary)
        print(f"{valtyp}: {len(codes)} valområden")
        for i, kod in enumerate(codes, 1):
            try:
                relpath, md5 = find_area_file(index, valtyp, kod, preliminary=preliminary)
                zip_bytes = download_file(year, relpath, expected_md5=md5)
                struct = parse_area_structure(extract_mandatfordelning(zip_bytes))
                out[valtyp][kod] = struct
                print(f"  [{i}/{len(codes)}] {valtyp} {kod} {struct['namn']}: "
                      f"{struct['total_seats']} mandat, {len(struct['valkretsar'])} vk")
            except Exception as e:
                print(f"  [{i}/{len(codes)}] {valtyp} {kod}: FEL {type(e).__name__}: {e}")
            time.sleep(0.05)  # snäll mot servern

    return out


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = build(2022, preliminary=False)
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = OUT_PATH.stat().st_size / 1024
    n_kf, n_rf = len(data["KF"]), len(data["RF"])
    print(f"\nSkrev {OUT_PATH} ({size_kb:.0f} kB): {n_kf} kommuner, {n_rf} regioner")
