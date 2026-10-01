"""Pre-hämta kommun-/regionvalsstruktur → data/muni_structure_<år>.json.

Laddar ner Valmyndighetens slutliga KF- (290 kommuner) och RF-filer (20 regioner)
för ett givet valår, extraherar valkretsstruktur (mandat per valkrets,
utjämningsmandat, spärr) och röster per parti och valkrets, och committar allt
som en enda JSON.

OBS: fältnamnen (`votes_2022`, `total_2022`, `seats_2022`) behålls oavsett år
för bakåtkompabilitet med muni_mandates.py och testerna — namnet betyder i
praktiken "baseline year". Byt vid en större refaktorering.

Filen driver den *opinionsbaserade* mandatuppskattningen på Regional-fliken
(full kommunal modell: Sainte-Laguë per valkrets + utjämningsmandat + spärr) och
levererar namn↔kod-mappningen för kommun-/region-selectboxarna.

Körs sällan — bara efter val eller om Valmyndigheten rättar siffror:
    python fetch_muni_cache.py          # default = 2026 (aktiv baslinje)
    python fetch_muni_cache.py 2022     # historisk baslinje
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from mandatorn_model.val_feed import (
    download_file,
    extract_mandatfordelning,
    fetch_index,
    find_area_file,
    parse_area_structure,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"


def out_path_for(year: int | str) -> Path:
    return DATA_DIR / f"muni_structure_{year}.json"


# Bakåtkompabilitet — kod som importerar OUT_PATH får 2022-filen.
OUT_PATH = out_path_for(2022)


def _codes_for(index: dict[str, str], valtyp: str, preliminary: bool = False) -> list[str]:
    """Plocka ut alla valområdeskoder för en valtyp ur manifestet."""
    stage = "p" if preliminary else "s"
    prefix = f"./{stage}/{valtyp.lower()}/"
    suffix = f"_{valtyp}.zip"
    codes = []
    for relpath in index:
        if relpath.startswith(prefix) and relpath.endswith(suffix):
            # ./s/kf/Val_20220911_slutlig_0180_KF.zip → "0180"
            kod = relpath[:-len(suffix)].split("_")[-1]
            if kod.isdigit():  # "OS" = summeringsfil, inget valområde
                codes.append(kod)
    return sorted(set(codes))


def _fetch_struct(index: dict[str, str], year, valtyp: str, kod: str,
                  preliminary: bool) -> dict | None:
    try:
        relpath, md5 = find_area_file(index, valtyp, kod, preliminary=preliminary)
    except LookupError:
        return None
    zip_bytes = download_file(year, relpath, expected_md5=md5)
    return parse_area_structure(extract_mandatfordelning(zip_bytes))


def _merge(final: dict | None, prelim: dict | None) -> tuple[dict | None, str]:
    """Slutliga röster + slutlig mandatfördelning om den finns, annars den
    preliminära mandatfördelningen (Länsstyrelsen fastställer mandaten först
    veckor efter valet) med de slutliga rösterna inlagda per valkrets."""
    if final and final["total_seats"] > 0:
        return final, "slutlig"
    if prelim is None or prelim["total_seats"] == 0:
        return final, "slutlig-utan-mandat" if final else "saknas"
    if final is None:
        return prelim, "preliminar"
    final_vk = {vk["kod"]: vk for vk in final["valkretsar"]}
    merged = dict(prelim)
    merged["valkretsar"] = [
        {**vk, **{k: final_vk[vk["kod"]][k] for k in ("total_2022", "votes_2022")}}
        if vk["kod"] in final_vk else vk
        for vk in prelim["valkretsar"]
    ]
    merged["party_meta"] = {**prelim["party_meta"], **final["party_meta"]}
    return merged, "slutliga-roster-preliminara-mandat"


def build(year: int | str = 2022, preliminary: bool = False) -> dict:
    index = fetch_index(year)
    out: dict = {"generated_from": f"val{year}", "KF": {}, "RF": {}, "stage": {}}

    for valtyp in ("KF", "RF"):
        codes = sorted(set(_codes_for(index, valtyp)) | set(_codes_for(index, valtyp, True)))
        print(f"{valtyp}: {len(codes)} valområden")
        for i, kod in enumerate(codes, 1):
            try:
                final = None if preliminary else _fetch_struct(index, year, valtyp, kod, False)
                prelim = None
                if final is None or final["total_seats"] == 0:
                    prelim = _fetch_struct(index, year, valtyp, kod, True)
                struct, stage = _merge(final, prelim)
                if struct is None:
                    print(f"  [{i}/{len(codes)}] {valtyp} {kod}: ingen fil")
                    continue
                out[valtyp][kod] = struct
                out["stage"][f"{valtyp}_{kod}"] = stage
                print(f"  [{i}/{len(codes)}] {valtyp} {kod} {struct['namn']}: "
                      f"{struct['total_seats']} mandat, {len(struct['valkretsar'])} vk ({stage})")
            except Exception as e:
                print(f"  [{i}/{len(codes)}] {valtyp} {kod}: FEL {type(e).__name__}: {e}")
            time.sleep(0.05)  # snäll mot servern

    return out


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = build(year, preliminary=False)
    path = out_path_for(year)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = path.stat().st_size / 1024
    n_kf, n_rf = len(data["KF"]), len(data["RF"])
    print(f"\nSkrev {path} ({size_kb:.0f} kB): {n_kf} kommuner, {n_rf} regioner")
