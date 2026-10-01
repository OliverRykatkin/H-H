"""
Hämtar 2026 års slutliga riksdagsvalsresultat från Valmyndigheten och dumpar
till data/election_2026.json.

Källa: mandatfördelningsfilen i den slutliga RD-zip:en (Val_2026_slutlig_00_RD.zip).
Innehåller:
    - Nationellt röstresultat per parti (%)
    - Nationell mandatfördelning (fasta + utjämning + totalt)
    - Per valkrets: fasta mandat, röstandel per parti, mandat per parti
    - Per kommun: riksdagsröstandel per parti (summa över kommunens valdistrikt)

Filen används av app.py som ny baslinje (NATIONAL_2026 / CONSTITUENCIES_2026)
och som facit för institutvikter och backtesting-korrigering.

Körs en gång efter slutliga resultat publicerats. Om Valmyndigheten korrigerar
utfallet i efterhand, kör om.

Användning:
    python fetch_election_2026.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import mandatorn_model.val_feed as vf

# Valmyndighetens valkretsnamn → appens interna namn (kopia från app.py:VALKRETS_MAPPING).
VALKRETS_MAPPING = {
    "Stockholms kommun":            "Stockholms stad",
    "Stockholms län":               "Stockholms län",
    "Uppsala län":                  "Uppsala",
    "Södermanlands län":            "Södermanland",
    "Östergötlands län":            "Östergötland",
    "Jönköpings län":               "Jönköping",
    "Kronobergs län":               "Kronoberg",
    "Kalmar län":                   "Kalmar",
    "Gotlands län":                 "Gotland",
    "Blekinge län":                 "Blekinge",
    "Skåne läns norra och östra":   "Skåne N/Ö",
    "Skåne läns södra":             "Skåne S",
    "Skåne läns västra":            "Skåne V",
    "Malmö kommun":                 "Malmö",
    "Hallands län":                 "Halland",
    "Göteborgs kommun":             "Göteborg",
    "Västra Götalands läns norra":  "VG Norra",
    "Västra Götalands läns södra":  "VG Södra",
    "Västra Götalands läns västra": "VG Västra",
    "Västra Götalands läns östra":  "VG Östra",
    "Värmlands län":                "Värmland",
    "Örebro län":                   "Örebro",
    "Västmanlands län":             "Västmanland",
    "Dalarnas län":                 "Dalarna",
    "Gävleborgs län":               "Gävleborg",
    "Västernorrlands län":          "Västernorrland",
    "Jämtlands län":                "Jämtland",
    "Västerbottens län":            "Västerbotten",
    "Norrbottens län":              "Norrbotten",
}

PARTIES = vf.PARTIES  # ["M", "L", "C", "KD", "S", "V", "MP", "SD"]


def _extract_national(vo: dict) -> tuple[dict, dict, int]:
    """Nationellt röstresultat + mandat + total giltiga röster."""
    rf = vo["rostfordelning"]["rosterPaverkaMandat"]
    total = int(rf["antalRoster"])
    national = {}
    for pr in rf.get("partiRoster", []):
        fk = pr.get("partiforkortning")
        if fk in PARTIES:
            national[fk] = round(float(pr["andelRoster"]), 2)

    seats = {}
    for pl in vo["mandatfordelning"]["partiLista"]:
        fk = pl.get("partiforkortning")
        if fk in PARTIES:
            seats[fk] = {
                "total": int(pl["antalMandat"]),
                "fasta": int(pl["antalFastaMandat"]),
                "utjamning": int(pl["antalUtjamningsmandat"]),
            }
    return national, seats, total


def _extract_valkretsar(vo: dict) -> dict:
    """Per valkrets: {app_namn: {seats, M, L, ...SD, mandat_M, ...}}."""
    out = {}
    unmapped = []
    for vk in vo["valkretsLista"]:
        feed_name = vk["namnValkrets"]
        app_name = VALKRETS_MAPPING.get(feed_name)
        if not app_name:
            unmapped.append(feed_name)
            continue
        rf = vk["rostfordelning"]["rosterPaverkaMandat"]
        entry = {"seats": int(vk["totaltAntalFastaMandat"])}
        for pr in rf.get("partiRoster", []):
            fk = pr.get("partiforkortning")
            if fk in PARTIES:
                entry[fk] = round(float(pr["andelRoster"]), 2)
        # Mandatfördelning per parti i valkretsen
        vk_seats = {}
        for pl in (vk.get("mandatfordelning") or {}).get("partiLista", []):
            fk = pl.get("partiforkortning")
            if fk in PARTIES:
                vk_seats[fk] = {
                    "total": int(pl["antalMandat"]),
                    "fasta": int(pl["antalFastaMandat"]),
                    "utjamning": int(pl["antalUtjamningsmandat"]),
                }
        entry["mandat"] = vk_seats
        out[app_name] = entry

    if unmapped:
        print(f"VARNING: valkretsar utan mapping (hoppade över): {unmapped}",
              file=sys.stderr)
    return out


def _extract_kommuner(rostfordelning: dict) -> dict:
    """Riksdagsresultat per kommun: summa över kommunens alla valdistrikt
    (inkl. uppsamlingsdistrikt) → {kommunkod: {M: %, ..., SD: %}}, andel av
    kommunens giltiga röster."""
    votes: dict[str, dict[str, int]] = {}
    valid: dict[str, int] = {}
    for vd in rostfordelning["valdistrikt"]:
        rp = (vd.get("rostfordelning") or {}).get("rosterPaverkaMandat")
        if not rp:
            continue
        kod = str(vd["kommunkod"])
        valid[kod] = valid.get(kod, 0) + int(rp["antalRoster"])
        acc = votes.setdefault(kod, {p: 0 for p in PARTIES})
        for pr in rp.get("partiRoster", []):
            fk = pr.get("partiforkortning")
            if fk in PARTIES:
                acc[fk] += int(pr["antalRoster"])
    return {
        kod: {p: round(v / valid[kod] * 100, 2) for p, v in acc.items()}
        for kod, acc in sorted(votes.items()) if valid.get(kod)
    }


def main() -> int:
    print("Hamtar index fran Valmyndigheten (2026)...")
    idx = vf.fetch_index(2026)
    try:
        relpath, md5 = vf.find_rd_file(idx, preliminary=False)
    except LookupError:
        print("Slutlig RD-fil saknas ännu — försök igen efter Valmyndigheten "
              "publicerat slutliga siffror.", file=sys.stderr)
        return 1
    print(f"Fil: {relpath}")

    print("Laddar ner + verifierar md5...")
    data = vf.download_file(2026, relpath, expected_md5=md5)
    print(f"  {len(data):,} bytes")

    mf = vf._extract_json(data, "mandatfordelning")
    vo = mf["valomrade"]

    national, seats_national, total = _extract_national(vo)
    print()
    print(f"Nationellt slutresultat 2026 (total giltiga röster: {total:,}):")
    for p in PARTIES:
        print(f"  {p:3s}: {national.get(p, 0):5.2f}%  ->  {seats_national.get(p, {}).get('total', 0):3d} mandat")
    tot_seats = sum(s["total"] for s in seats_national.values())
    print(f"  Summa mandat (8 partier): {tot_seats}/349")

    valkretsar = _extract_valkretsar(vo)
    print()
    print(f"Valkretsar: {len(valkretsar)}/29 mappade")
    tot_seats_vk = sum(v["seats"] for v in valkretsar.values())
    print(f"  Summa fasta mandat: {tot_seats_vk}/310")

    kommuner = _extract_kommuner(vf._extract_json(data, "rostfordelning"))
    print(f"Kommuner (riksdagsresultat): {len(kommuner)}/290")

    out_path = Path(__file__).parent / "data" / "election_2026.json"
    out_path.parent.mkdir(exist_ok=True)

    payload = {
        "meta": {
            "kalla": "Valmyndigheten, slutlig mandatfördelning RD 2026",
            "fil": relpath,
            "md5": md5,
            "senasteUppdateringstid": mf.get("senasteUppdateringstid"),
            "rakningstillfalle": mf.get("rakningstillfalle"),
            "total_giltiga_roster": total,
            "hamtad": os.environ.get("SOURCE_DATE_EPOCH", ""),
        },
        "national": national,
        "seats_national": seats_national,
        "constituencies": valkretsar,
        "kommuner": kommuner,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
    print()
    print(f"Skrev: {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
