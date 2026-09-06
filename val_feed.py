"""Live-feed-klient för Valmyndighetens resultatfiler (valnatten).

Valmyndigheten publicerar preliminära resultat som zippade JSON-filer under
valkvällen. En manifest-fil (`index.md5`) listar samtliga filer med md5-checksumma;
filerna uppdateras löpande så fort nya distrikt rapporteras in. För riksdagsvalet
(RD) samlas *hela* riket i en enda fil:

    https://resultat.val.se/resultatfiler/val<år>/p/rd/Val_<datum>_preliminar_00_RD.zip

Zip:en innehåller `..._rostfordelning_00_RD.json` (röster per distrikt och parti)
samt en mandatfördelningsfil och sha256-signaturer.

Modulen:
    1. Hämtar `index.md5` och plockar ut den preliminära RD-filens relpath + md5.
    2. Laddar ner zip:en (och verifierar md5 mot manifestet).
    3. Parsar röstfördelningen till samma distrikts-schema som `compute_nowcast()`
       förväntar sig: district_id, total_valid_votes, votes_<P> per parti.

Källa: e-post från Valmyndigheten (2026-09) + teknisk beskrivning EU-valet 2024.
Rekommenderad pollningsfrekvens: max ~1 gång/minut (trafikhänsyn).

OBS: hämtar man 2022-års filer (`val2022`) får man färdiga slutresultat och kan
validera parsern offline. 2026-schemat är identiskt (nya summeringar tillkommer).
"""
from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from dataclasses import dataclass, field

import pandas as pd

from nowcast import PARTIES

RESULT_BASE = "https://resultat.val.se/resultatfiler"

# Distriktstyp för ordinarie valdistrikt (uppsamlingsdistrikt = brev-/utlandsröster
# räknade efter valnatten, exkluderas för att matcha baseline-schemat).
ORDINARIE = "valdistrikt"

_USER_AGENT = "Mandatorn/1.0 (+https://mandatorn.se; valnatt-nowcast)"


@dataclass
class FeedResult:
    """Parsat resultat från en RD-röstfördelningsfil."""

    districts: pd.DataFrame  # alla ordinarie distrikt (räknade + oräknade)
    updated_at: str  # senasteUppdateringstid (ISO)
    n_counted: int  # antalValdistriktRaknade (från filen, inkl. uppsamling)
    n_total: int  # antalValdistriktSomSkaRaknas
    n_updates: int  # antalUppdateringar
    stage: str  # rakningstillfalle ("preliminär"/"slutlig")
    meta: dict = field(default_factory=dict)

    def counted(self) -> pd.DataFrame:
        """Endast räknade ordinarie distrikt (redo för compute_nowcast)."""
        df = self.districts
        return df[df["counted"]].drop(columns=["counted", "rapporteringsTid"])

    @property
    def coverage_by_district(self) -> float:
        return self.n_counted / self.n_total if self.n_total else 0.0


# --------------------------------------------------------------------------- #
# Manifest (index.md5)
# --------------------------------------------------------------------------- #

def index_url(year: int | str) -> str:
    return f"{RESULT_BASE}/val{year}/index.md5"


def _http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_index(text: str) -> dict[str, str]:
    """Parsa `index.md5` → {relpath: md5}.

    Format per rad: `<md5><mellanslag><mellanslag><relpath>`, t.ex.
    `078e4911...  ./p/rd/Val_20220911_preliminar_00_RD.zip`.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        md5, relpath = parts
        if len(md5) == 32 and relpath.startswith("./"):
            out[relpath] = md5.lower()
    return out


def fetch_index(year: int | str, timeout: int = 60) -> dict[str, str]:
    return parse_index(_http_get(index_url(year), timeout=timeout).decode("utf-8"))


def find_area_file(index: dict[str, str], valtyp: str, kod: str,
                   preliminary: bool = True) -> tuple[str, str]:
    """Hitta (relpath, md5) för ett valområde i manifestet.

    Args:
        valtyp: "RD" (riksdag, kod "00"), "KF" (kommun, 4-siffrig kommunkod)
            eller "RF" (region, 2-siffrig länskod).
        kod: valområdeskoden, t.ex. "00", "0180", "25".
        preliminary: True → `./p/<typ>/`, False → `./s/<typ>/`.
    """
    valtyp = valtyp.upper()
    prefix = f"./{'p' if preliminary else 's'}/{valtyp.lower()}/"
    suffix = f"_{kod}_{valtyp}.zip"
    for relpath, md5 in index.items():
        if relpath.startswith(prefix) and relpath.endswith(suffix):
            return relpath, md5
    raise LookupError(
        f"Ingen {valtyp}-fil för kod {kod} "
        f"({'preliminär' if preliminary else 'slutlig'}) i manifestet "
        f"({len(index)} poster)"
    )


def find_rd_file(index: dict[str, str], preliminary: bool = True) -> tuple[str, str]:
    """Hitta den nationella RD-filens (relpath, md5) — hela riket ligger i _00_RD."""
    return find_area_file(index, "RD", "00", preliminary=preliminary)


# --------------------------------------------------------------------------- #
# Nedladdning + verifiering
# --------------------------------------------------------------------------- #

def download_file(year: int | str, relpath: str, expected_md5: str | None = None,
                  timeout: int = 120) -> bytes:
    """Ladda ner en fil från manifestet (relpath börjar med `./`)."""
    url = f"{RESULT_BASE}/val{year}/{relpath.lstrip('./')}"
    data = _http_get(url, timeout=timeout)
    if expected_md5 is not None:
        got = hashlib.md5(data).hexdigest()
        if got != expected_md5.lower():
            raise ValueError(
                f"md5-mismatch för {relpath}: väntade {expected_md5}, fick {got}"
            )
    return data


def _extract_json(zip_bytes: bytes, needle: str) -> dict:
    """Plocka ut och parsa den JSON-fil vars namn innehåller `needle`.

    Sign-filerna (`..._sign.sha256`) filtreras bort eftersom de inte är .json.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist()
                 if needle in n and n.endswith(".json")]
        if not names:
            raise ValueError(f"Ingen {needle}-JSON i zip: {zf.namelist()}")
        with zf.open(names[0]) as fh:
            return json.load(io.TextIOWrapper(fh, encoding="utf-8"))


def extract_rostfordelning(zip_bytes: bytes) -> dict:
    """Plocka ut röstfördelnings-JSON:en (röster per distrikt och parti)."""
    return _extract_json(zip_bytes, "rostfordelning")


def extract_mandatfordelning(zip_bytes: bytes) -> dict:
    """Plocka ut mandatfördelnings-JSON:en (mandat + röstandelar per valområde)."""
    return _extract_json(zip_bytes, "mandatfordelning")


# --------------------------------------------------------------------------- #
# Parsning → distrikts-DataFrame
# --------------------------------------------------------------------------- #

def _to_int(v, default: int = 0) -> int:
    """Robust int-tolkning: fält kan vara str, None eller strängen 'None'."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s in ("", "None", "null"):
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def parse_rostfordelning(data: dict, parties: list[str] = PARTIES) -> FeedResult:
    """Parsa en röstfördelnings-dict till FeedResult.

    Bygger en rad per ordinarie valdistrikt (uppsamlingsdistrikt exkluderas).
    Ett distrikt räknas som "counted" om det har giltiga röster > 0.

    Kolumner i districts-DataFrame:
        district_id (int64), total_valid_votes (int), votes_<P> per parti,
        rapporteringsTid (str|None), counted (bool).
    """
    parties = list(parties)
    rows = []
    for vd in data.get("valdistrikt", []):
        if vd.get("valdistriktstyp") != ORDINARIE:
            continue
        rf = vd.get("rostfordelning", {}).get("rosterPaverkaMandat", {})
        valid = _to_int(rf.get("antalRoster"))
        by_party = {
            pr.get("partiforkortning"): _to_int(pr.get("antalRoster"))
            for pr in rf.get("partiRoster", [])
        }
        rapport = vd.get("rapporteringsTid")
        if rapport in ("None", ""):
            rapport = None
        row = {
            "district_id": _to_int(vd.get("valdistriktskod")),
            "total_valid_votes": valid,
            "rapporteringsTid": rapport,
            "counted": valid > 0,
        }
        for p in parties:
            row[f"votes_{p}"] = by_party.get(p, 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["district_id"] = df["district_id"].astype("int64")

    return FeedResult(
        districts=df,
        updated_at=str(data.get("senasteUppdateringstid", "")),
        n_counted=_to_int(data.get("antalValdistriktRaknade")),
        n_total=_to_int(data.get("antalValdistriktSomSkaRaknas")),
        n_updates=_to_int(data.get("antalUppdateringar")),
        stage=str(data.get("rakningstillfalle", "")),
        meta={
            "valtillfalle": data.get("valtillfalle"),
            "valtyp": data.get("valtyp"),
        },
    )


def parse_rd_zip(zip_bytes: bytes, parties: list[str] = PARTIES) -> FeedResult:
    """Bekvämlighet: extrahera röstfördelning ur zip och parsa direkt."""
    return parse_rostfordelning(extract_rostfordelning(zip_bytes), parties)


# --------------------------------------------------------------------------- #
# Orkestrering (den publika ingångspunkten)
# --------------------------------------------------------------------------- #

def fetch_live(year: int | str = 2026, preliminary: bool = True,
               parties: list[str] = PARTIES) -> FeedResult:
    """Hämta senaste RD-resultatet: index → hitta fil → ladda ner → parsa.

    Verifierar md5 mot manifestet. Anropa max ~1 gång/minut.
    """
    index = fetch_index(year)
    relpath, md5 = find_rd_file(index, preliminary=preliminary)
    zip_bytes = download_file(year, relpath, expected_md5=md5)
    return parse_rd_zip(zip_bytes, parties)


# --------------------------------------------------------------------------- #
# Kommun-/regionval (KF/RF) — officiell mandatfördelning ur feeden
# --------------------------------------------------------------------------- #

@dataclass
class AreaMandat:
    """Officiell mandatfördelning för ett valområde (kommun eller region).

    Läses direkt ur feedens `mandatfordelning`-block — Valmyndigheten har redan
    tillämpat rätt regler (valkretsindelning, spärr, utjämningsmandat). Inkluderar
    lokala partier; den långa svansen av småpartier ligger i `ovriga_*`.
    """

    valtyp: str          # "KF" eller "RF"
    namn: str            # valområdets namn (kommun-/regionnamn)
    kod: str             # valområdeskod (kommunkod/länskod)
    updated_at: str      # senasteUppdateringstid
    stage: str           # rakningstillfalle
    n_counted: int       # antalValdistriktRaknade
    n_total: int         # antalValdistriktSomSkaRaknas
    threshold_pct: float  # valomradessparrProcent (2 % eller 3 %)
    total_valid_votes: int
    parties: pd.DataFrame  # per parti: förkortning, beteckning, färg, röster,
    #                        andel, mandat (totalt/fasta/utjämning)
    ovriga_andel: float
    ovriga_roster: int

    @property
    def total_seats(self) -> int:
        if self.parties.empty:
            return 0
        return int(self.parties["antalMandat"].sum())

    @property
    def coverage_by_district(self) -> float:
        return self.n_counted / self.n_total if self.n_total else 0.0


def parse_area_mandat(data: dict) -> AreaMandat:
    """Parsa en mandatfördelnings-dict (KF/RF) till AreaMandat.

    Slår ihop röstandelar (`rostfordelning.rosterPaverkaMandat.partiRoster`) med
    mandat (`mandatfordelning.partiLista`) på partikod. Partier med röster men
    utan mandat (under spärren) får 0 mandat.
    """
    vo = data.get("valomrade", {})
    rf = vo.get("rostfordelning", {}).get("rosterPaverkaMandat", {})
    seats_by_kod = {
        str(pl.get("partikod")): pl
        for pl in vo.get("mandatfordelning", {}).get("partiLista", [])
    }
    rows = []
    for pr in rf.get("partiRoster", []):
        kod = str(pr.get("partikod"))
        seat = seats_by_kod.get(kod, {})
        rows.append({
            "partiforkortning": pr.get("partiforkortning"),
            "partibeteckning": pr.get("partibeteckning"),
            "partikod": kod,
            "fargkod": pr.get("fargkod"),
            "antalRoster": _to_int(pr.get("antalRoster")),
            "andelRoster": float(pr.get("andelRoster") or 0.0),
            "antalMandat": _to_int(seat.get("antalMandat")),
            "antalFastaMandat": _to_int(seat.get("antalFastaMandat")),
            "antalUtjamningsmandat": _to_int(seat.get("antalUtjamningsmandat")),
        })
    parties = pd.DataFrame(rows)
    ovriga = rf.get("rosterOvrigaPartier", {}) or {}
    return AreaMandat(
        valtyp=str(data.get("valtyp", "")),
        namn=str(vo.get("namn", "")),
        kod=str(vo.get("kod", "")),
        updated_at=str(data.get("senasteUppdateringstid", "")),
        stage=str(data.get("rakningstillfalle", "")),
        n_counted=_to_int(vo.get("antalValdistriktRaknade")),
        n_total=_to_int(vo.get("antalValdistriktSomSkaRaknas")),
        threshold_pct=float(vo.get("valomradessparrProcent") or 0.0),
        total_valid_votes=_to_int(rf.get("antalRoster")),
        parties=parties,
        ovriga_andel=float(ovriga.get("andelRoster") or 0.0),
        ovriga_roster=_to_int(ovriga.get("antalRoster")),
    )


def parse_area_structure(data: dict, parties: list[str] = PARTIES) -> dict:
    """Extrahera valkretsstruktur + 2022-röster ur en KF/RF mandatfördelning.

    Används för att bygga en committad referenstabell (mandatantal per valkrets,
    utjämningsmandat, spärr) som driver den opinionsbaserade mandatuppskattningen
    på Regional-fliken. Returnerar en JSON-serialiserbar dict:

        {namn, kod, valtyp, threshold_pct, total_seats, n_utjamning,
         valkretsar: [{kod, namn, fasta, total_2022, votes_2022: {P: n}}]}

    votes_2022 innehåller bara de 8 riksdagspartierna; total_2022 är alla giltiga
    röster (inkl. lokala partier) så att korrekta andelar kan räknas.
    """
    vo = data.get("valomrade", {})

    def _votes8(rf_block: dict) -> dict:
        out = {p: 0 for p in parties}
        for pr in rf_block.get("partiRoster", []):
            fk = pr.get("partiforkortning")
            if fk in out:
                out[fk] = _to_int(pr.get("antalRoster"))
        return out

    valkretsar = []
    for vk in vo.get("valkretsLista", []) or []:
        rf = vk.get("rostfordelning", {}).get("rosterPaverkaMandat", {})
        fasta = sum(
            _to_int(pl.get("antalFastaMandat"))
            for pl in vk.get("mandatfordelning", {}).get("partiLista", [])
        )
        valkretsar.append({
            "kod": str(vk.get("kod", "")),
            "namn": str(vk.get("namnValkrets", "")),
            "fasta": fasta,
            "total_2022": _to_int(rf.get("antalRoster")),
            "votes_2022": _votes8(rf),
        })

    # Område utan valkretsindelning → behandla hela området som en valkrets.
    if not valkretsar:
        rf = vo.get("rostfordelning", {}).get("rosterPaverkaMandat", {})
        fasta = sum(
            _to_int(pl.get("antalFastaMandat"))
            for pl in vo.get("mandatfordelning", {}).get("partiLista", [])
        )
        valkretsar.append({
            "kod": str(vo.get("kod", "")),
            "namn": str(vo.get("namn", "")),
            "fasta": fasta,
            "total_2022": _to_int(rf.get("antalRoster")),
            "votes_2022": _votes8(rf),
        })

    mf = vo.get("mandatfordelning", {}).get("partiLista", [])
    return {
        "namn": str(vo.get("namn", "")),
        "kod": str(vo.get("kod", "")),
        "valtyp": str(data.get("valtyp", "")),
        "threshold_pct": float(vo.get("valomradessparrProcent") or 0.0),
        "total_seats": sum(_to_int(p.get("antalMandat")) for p in mf),
        "n_utjamning": sum(_to_int(p.get("antalUtjamningsmandat")) for p in mf),
        "valkretsar": valkretsar,
    }


def fetch_area_mandat(year: int | str, valtyp: str, kod: str,
                      preliminary: bool = True) -> AreaMandat:
    """Hämta och parsa mandatfördelningen för en kommun (KF) eller region (RF).

    Laddar bara mandatfördelnings-JSON:en ur zip:en (röstfördelningsfilen kan
    vara flera MB och behövs inte här). Anropa max ~1 gång/minut.
    """
    index = fetch_index(year)
    relpath, md5 = find_area_file(index, valtyp, kod, preliminary=preliminary)
    zip_bytes = download_file(year, relpath, expected_md5=md5)
    return parse_area_mandat(extract_mandatfordelning(zip_bytes))


if __name__ == "__main__":
    # Snabb röktest mot 2022 slutresultat (offline-validering).
    print("Hämtar 2022 slutlig RD...")
    res = fetch_live(2022, preliminary=False)
    df = res.districts
    counted = res.counted()
    total = counted["total_valid_votes"].sum()
    print(f"Distrikt: {len(df)} ordinarie, {len(counted)} räknade")
    print(f"Uppdaterad: {res.updated_at} | stage: {res.stage} | "
          f"täckning (distrikt): {res.coverage_by_district:.1%}")
    print("Nationella andelar:")
    for p in PARTIES:
        share = counted[f"votes_{p}"].sum() / total * 100
        print(f"  {p:<3}: {share:5.2f}%")
