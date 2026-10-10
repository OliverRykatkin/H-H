"""Valprofiler: allt som skiljer ett val från ett annat (partier, mandatregel, datum, feed)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mandatorn_model import constants as C


@dataclass(frozen=True)
class ElectionProfile:
    key: str
    name: str
    election_date: datetime          # preliminär för EU-valet 2029 (D-EU1)
    seats: int
    threshold: float                 # andel av giltiga röster i riket
    first_divisor: float
    parties: tuple[str, ...]
    constituencies: int              # 0 = en riksvalkrets utan utjämning
    feed_valtyp: str                 # valtyp i Valmyndighetens feed
    feed_prefix: str                 # katalog under resultat.val.se/resultatfiler/
    release_prefix: str              # prefix i datalagret ("" = huvudreleasen)


RD2026 = ElectionProfile(
    key="rd2026", name="Riksdagsvalet", election_date=C.NEXT_ELECTION, seats=C.TOTAL_SEATS,
    threshold=C.THRESHOLD / 100, first_divisor=1.2, parties=tuple(C.PARTIES),
    constituencies=29, feed_valtyp="RD", feed_prefix="val", release_prefix="",
)

EU2029 = ElectionProfile(
    key="eu2029", name="EU-valet", election_date=datetime(2029, 6, 9), seats=21,
    threshold=0.04, first_divisor=1.2, parties=tuple(C.PARTIES),
    constituencies=0, feed_valtyp="E", feed_prefix="euval", release_prefix="eu2029/",
)

PROFILES = {p.key: p for p in (RD2026, EU2029)}
