"""Enhetstester för val_feed-modulen (live-feed-parsning).

Använder syntetiska fixtures — ingen nätverkstrafik. Verifierar manifest-parsning,
md5-verifiering, robust int-tolkning och JSON→DataFrame-mappning.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

import val_feed
from val_feed import (
    AreaMandat,
    FeedResult,
    _to_int,
    download_file,
    extract_mandatfordelning,
    extract_rostfordelning,
    find_area_file,
    find_rd_file,
    parse_area_mandat,
    parse_index,
    parse_rd_zip,
    parse_rostfordelning,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

INDEX_TEXT = (
    "078e4911d8706c9bdcd8f24c85de7200  ./p/rd/Val_20220911_preliminar_00_RD.zip\n"
    "a0f843ffb9a305e7bc84ecea5e57023a  ./s/rd/Val_20220911_slutlig_00_RD.zip\n"
    "33a90034017de6116d18aacba9118685  ./p/kf/Val_20220911_preliminar_0114_KF.zip\n"
    "\n"                       # tom rad ska ignoreras
    "garbage line without md5\n"  # felformad rad ska ignoreras
)


def _party_rost(fork, kod, n):
    return {"partiforkortning": fork, "partikod": kod, "antalRoster": n}


def make_rostfordelning():
    """Två ordinarie distrikt (ett räknat, ett oräknat) + ett uppsamlingsdistrikt."""
    return {
        "valtillfalle": "Val_20220911",
        "valtyp": "RD",
        "rakningstillfalle": "preliminär",
        "senasteUppdateringstid": "2022-09-11T22:47:30",
        "antalUppdateringar": "1215",
        "antalValdistriktRaknade": "1",
        "antalValdistriktSomSkaRaknas": "2",
        "valdistrikt": [
            {
                "namn": "Distrikt A",
                "valdistriktstyp": "valdistrikt",
                "valdistriktskod": "01800101",
                "rapporteringsTid": "2022-09-11T22:47:30",
                "totaltAntalRoster": "100",
                "rostfordelning": {
                    "rosterPaverkaMandat": {
                        "antalRoster": 100,
                        "partiRoster": [
                            _party_rost("M", "0001", 40),
                            _party_rost("S", "0002", 55),
                        ],
                        "rosterOvrigaPartier": {"antalRoster": 5},
                    }
                },
            },
            {
                "namn": "Distrikt B (oräknat)",
                "valdistriktstyp": "valdistrikt",
                "valdistriktskod": "01800102",
                "rapporteringsTid": "None",   # ännu ej rapporterat
                "totaltAntalRoster": "0",
                "rostfordelning": {
                    "rosterPaverkaMandat": {
                        "antalRoster": 0,
                        "partiRoster": [],
                        "rosterOvrigaPartier": {"antalRoster": 0},
                    }
                },
            },
            {
                "namn": "Uppsamlingsdistrikt 01",
                "valdistriktstyp": "uppsamlingsdistrikt",
                "valdistriktskod": "018001",
                "rapporteringsTid": "2022-09-14T18:37:39",
                "totaltAntalRoster": "5000",
                "rostfordelning": {
                    "rosterPaverkaMandat": {
                        "antalRoster": 5000,
                        "partiRoster": [_party_rost("M", "0001", 5000)],
                        "rosterOvrigaPartier": {"antalRoster": 0},
                    }
                },
            },
        ],
    }


def make_zip(rostfordelning: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Val_20220911_preliminar_rostfordelning_00_RD.json",
            json.dumps(rostfordelning, ensure_ascii=False),
        )
        zf.writestr("Val_20220911_preliminar_mandatfordelning_00_RD.json", "{}")
        zf.writestr("something_sign.sha256", "deadbeef")
    return buf.getvalue()


PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"]


# --------------------------------------------------------------------------- #
# parse_index / find_rd_file
# --------------------------------------------------------------------------- #

def test_parse_index_keeps_valid_skips_garbage():
    idx = parse_index(INDEX_TEXT)
    assert len(idx) == 3
    assert idx["./p/rd/Val_20220911_preliminar_00_RD.zip"] == (
        "078e4911d8706c9bdcd8f24c85de7200"
    )
    assert "garbage line without md5" not in idx


def test_parse_index_lowercases_md5():
    idx = parse_index("ABCDEF0123456789ABCDEF0123456789  ./p/rd/x_00_RD.zip")
    assert idx["./p/rd/x_00_RD.zip"] == "abcdef0123456789abcdef0123456789"


def test_find_rd_file_preliminary_vs_final():
    idx = parse_index(INDEX_TEXT)
    rel_p, md5_p = find_rd_file(idx, preliminary=True)
    assert rel_p == "./p/rd/Val_20220911_preliminar_00_RD.zip"
    rel_s, _ = find_rd_file(idx, preliminary=False)
    assert rel_s == "./s/rd/Val_20220911_slutlig_00_RD.zip"


def test_find_rd_file_missing_raises():
    with pytest.raises(LookupError):
        find_rd_file({"./p/kf/x_0114_KF.zip": "a" * 32}, preliminary=True)


# --------------------------------------------------------------------------- #
# _to_int
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value,expected",
    [
        (100, 100), ("100", 100), (100.0, 100), ("100.0", 100),
        (None, 0), ("None", 0), ("", 0), ("null", 0), ("skräp", 0),
    ],
)
def test_to_int_coercion(value, expected):
    assert _to_int(value) == expected


# --------------------------------------------------------------------------- #
# parse_rostfordelning
# --------------------------------------------------------------------------- #

def test_parse_excludes_uppsamlingsdistrikt():
    res = parse_rostfordelning(make_rostfordelning(), parties=PARTIES)
    assert len(res.districts) == 2  # bara de två ordinarie
    assert set(res.districts["district_id"]) == {1800101, 1800102}


def test_parse_counted_flag_and_filter():
    res = parse_rostfordelning(make_rostfordelning(), parties=PARTIES)
    counted = res.counted()
    assert len(counted) == 1
    assert counted.iloc[0]["district_id"] == 1800101
    assert "counted" not in counted.columns
    assert "rapporteringsTid" not in counted.columns


def test_parse_vote_mapping():
    res = parse_rostfordelning(make_rostfordelning(), parties=PARTIES)
    a = res.districts[res.districts["district_id"] == 1800101].iloc[0]
    assert a["votes_M"] == 40
    assert a["votes_S"] == 55
    assert a["votes_SD"] == 0        # inte närvarande → 0
    assert a["total_valid_votes"] == 100


def test_parse_metadata():
    res = parse_rostfordelning(make_rostfordelning(), parties=PARTIES)
    assert res.n_counted == 1
    assert res.n_total == 2
    assert res.n_updates == 1215
    assert res.stage == "preliminär"
    assert res.updated_at == "2022-09-11T22:47:30"
    assert res.coverage_by_district == 0.5


def test_district_id_is_int64():
    res = parse_rostfordelning(make_rostfordelning(), parties=PARTIES)
    assert res.districts["district_id"].dtype == "int64"


# --------------------------------------------------------------------------- #
# zip-extraktion + md5-verifiering
# --------------------------------------------------------------------------- #

def test_extract_and_parse_zip_roundtrip():
    zip_bytes = make_zip(make_rostfordelning())
    res = parse_rd_zip(zip_bytes, parties=PARTIES)
    assert isinstance(res, FeedResult)
    assert len(res.districts) == 2


def test_extract_raises_without_rostfordelning():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("only_mandatfordelning.json", "{}")
    with pytest.raises(ValueError, match="rostfordelning"):
        extract_rostfordelning(buf.getvalue())


def test_download_file_verifies_md5(monkeypatch):
    payload = b"hello world"
    good = hashlib.md5(payload).hexdigest()
    monkeypatch.setattr(val_feed, "_http_get", lambda url, timeout=120: payload)

    assert download_file(2026, "./p/rd/x_00_RD.zip", expected_md5=good) == payload
    with pytest.raises(ValueError, match="md5-mismatch"):
        download_file(2026, "./p/rd/x_00_RD.zip", expected_md5="0" * 32)


# --------------------------------------------------------------------------- #
# find_area_file (KF/RF/RD)
# --------------------------------------------------------------------------- #

def test_find_area_file_kf_rf():
    idx = {
        "./p/kf/Val_20220911_preliminar_0180_KF.zip": "a" * 32,
        "./p/rf/Val_20220911_preliminar_12_RF.zip": "b" * 32,
        "./p/rd/Val_20220911_preliminar_00_RD.zip": "c" * 32,
    }
    assert find_area_file(idx, "KF", "0180")[0].endswith("_0180_KF.zip")
    assert find_area_file(idx, "RF", "12")[0].endswith("_12_RF.zip")
    # find_rd_file är en tunn wrapper på find_area_file(RD, 00)
    assert find_rd_file(idx)[0].endswith("_00_RD.zip")


def test_find_area_file_missing_raises():
    with pytest.raises(LookupError):
        find_area_file({"./p/kf/x_0180_KF.zip": "a" * 32}, "KF", "9999")


# --------------------------------------------------------------------------- #
# parse_area_mandat (KF/RF mandatfördelning)
# --------------------------------------------------------------------------- #

def make_mandatfordelning():
    """KF-valområde: 2 riksdagspartier + 1 lokalt (under spärr, 0 mandat) + Övriga."""
    return {
        "valtyp": "KF",
        "rakningstillfalle": "preliminär",
        "senasteUppdateringstid": "2022-09-11T23:10:00",
        "valomrade": {
            "namn": "Testköping",
            "kod": "0180",
            "antalValdistriktRaknade": 8,
            "antalValdistriktSomSkaRaknas": 10,
            "valomradessparrProcent": 3.0,
            "rostfordelning": {
                "rosterPaverkaMandat": {
                    "antalRoster": 1000,
                    "partiRoster": [
                        {"partiforkortning": "M", "partikod": "0001",
                         "partibeteckning": "Moderaterna", "fargkod": "#66BEE6",
                         "antalRoster": 400, "andelRoster": 40.0},
                        {"partiforkortning": "S", "partikod": "0002",
                         "partibeteckning": "Socialdemokraterna", "fargkod": "#FF0000",
                         "antalRoster": 550, "andelRoster": 55.0},
                        {"partiforkortning": "FI", "partikod": "1234",
                         "partibeteckning": "Feministiskt initiativ", "fargkod": "#DD1177",
                         "antalRoster": 20, "andelRoster": 2.0},
                    ],
                    "rosterOvrigaPartier": {"antalRoster": 30, "andelRoster": 3.0},
                }
            },
            "mandatfordelning": {
                "partiLista": [
                    {"partiforkortning": "M", "partikod": "0001",
                     "antalMandat": 12, "antalFastaMandat": 11, "antalUtjamningsmandat": 1},
                    {"partiforkortning": "S", "partikod": "0002",
                     "antalMandat": 19, "antalFastaMandat": 18, "antalUtjamningsmandat": 1},
                    # FI saknas — under spärren
                ]
            },
        },
    }


def test_parse_area_mandat_basics():
    am = parse_area_mandat(make_mandatfordelning())
    assert isinstance(am, AreaMandat)
    assert am.valtyp == "KF"
    assert am.namn == "Testköping"
    assert am.kod == "0180"
    assert am.threshold_pct == 3.0
    assert am.n_counted == 8 and am.n_total == 10
    assert am.coverage_by_district == 0.8
    assert am.total_valid_votes == 1000
    assert am.total_seats == 31  # 12 + 19


def test_parse_area_mandat_includes_local_party_zero_seats():
    am = parse_area_mandat(make_mandatfordelning())
    fi = am.parties[am.parties["partiforkortning"] == "FI"].iloc[0]
    assert fi["andelRoster"] == 2.0
    assert fi["antalMandat"] == 0          # under spärren → 0 mandat men fortfarande listad
    assert am.ovriga_andel == 3.0
    assert am.ovriga_roster == 30


def test_parse_area_mandat_seat_merge_by_partikod():
    am = parse_area_mandat(make_mandatfordelning())
    m = am.parties[am.parties["partiforkortning"] == "M"].iloc[0]
    assert m["antalMandat"] == 12
    assert m["antalFastaMandat"] == 11
    assert m["antalUtjamningsmandat"] == 1


def test_extract_mandatfordelning_from_zip():
    import io as _io
    import zipfile as _zip
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as zf:
        zf.writestr("Val_x_rostfordelning_0180_KF.json", "{}")
        zf.writestr(
            "Val_x_mandatfordelning_0180_KF.json",
            json.dumps(make_mandatfordelning(), ensure_ascii=False),
        )
    data = extract_mandatfordelning(buf.getvalue())
    assert data["valtyp"] == "KF"
    am = parse_area_mandat(data)
    assert am.total_seats == 31


def test_download_file_builds_correct_url(monkeypatch):
    seen = {}
    def fake_get(url, timeout=120):
        seen["url"] = url
        return b"x"
    monkeypatch.setattr(val_feed, "_http_get", fake_get)
    download_file(2026, "./p/rd/Val_20260913_preliminar_00_RD.zip")
    assert seen["url"] == (
        "https://resultat.val.se/resultatfiler/val2026/"
        "p/rd/Val_20260913_preliminar_00_RD.zip"
    )
