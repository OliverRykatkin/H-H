"""Datakontrakt för publicerade artefakter (Pydantic → JSON Schema → TypeScript).

Varje JSON-fil i en release valideras mot sin modell innan den skrivs.
SCHEMA_VERSION höjs vid brytande ändringar; klienten avvisar okända versioner.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

Party = Literal["M", "L", "C", "KD", "S", "V", "MP", "SD"]
PartyOrOther = Literal["M", "L", "C", "KD", "S", "V", "MP", "SD", "O"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Manifest ────────────────────────────────────────────────────────────────

class FileEntry(_Model):
    path: str = Field(description="Logisk sökväg i releasen, t.ex. 'national.json'")
    object: str = Field(description="Innehållsadresserad nyckel i datalagret, t.ex. 'files/<sha256>.json'")
    size: int
    sha256: str


class PollsIncluded(_Model):
    count: int
    latestFieldEnd: str | None = Field(description="Senaste fältperiodens slutdatum (YYYY-MM-DD)")
    latestPublished: str


class Manifest(_Model):
    schemaVersion: int = SCHEMA_VERSION
    release: str = Field(description="SHA-256 över det kanoniska filindexet")
    generatedAt: str = Field(description="Referensdatum för körningen (ISO 8601, Europe/Stockholm-dygn)")
    modelVersion: str = Field(description="Git-commit för modellkoden")
    seed: int
    inputHash: str = Field(description="SHA-256 över all indata (mätningar, baslinjefiler, konfiguration)")
    mode: Literal["forecast", "nowcast", "final"]
    pollsIncluded: PollsIncluded
    supersededBy: str | None = None
    files: list[FileEntry]


class ReleaseIndexEntry(_Model):
    release: str
    generatedAt: str
    mode: Literal["forecast", "nowcast", "final"]
    supersededBy: str | None = None


class ReleaseIndex(_Model):
    schemaVersion: int = SCHEMA_VERSION
    releases: list[ReleaseIndexEntry]


# ── Nationellt ──────────────────────────────────────────────────────────────

class PartyEstimate(_Model):
    party: PartyOrOther
    name: str
    share: float = Field(description="Skattad andel av alla giltiga röster i procent; övriga (O) antas som i baslinjevalet")
    baseline: float | None = Field(description="Valresultat i baslinjevalet (procent)")
    change: float | None
    sd: float | None = Field(default=None, description="Simuleringens totala σ (pp)")
    pAboveThreshold: float | None = None


class Bloc(_Model):
    name: str
    parties: list[Party]
    seats: int
    share: float
    pMajority: float


class TrendRow(_Model):
    key: str = Field(description="Parti- eller blocknyckel")
    name: str
    now: float
    monthAgo: float | None
    yearAgo: float | None
    lastElection: float | None


class National(_Model):
    schemaVersion: int = SCHEMA_VERSION
    referenceDate: str
    baselineYear: int
    nextElection: str
    daysLeft: int
    latestPoll: str
    estimates: list[PartyEstimate]
    seats: dict[str, int] = Field(description="Punktprognos, totala mandat per parti")
    blocs: list[Bloc]
    largestParty: Party
    belowThreshold: list[Party]
    swing: dict[str, float] = Field(description="Nollsummerad nationell sving sedan baslinjevalet (pp)")
    trend: list[TrendRow]


# ── Tidsserie ───────────────────────────────────────────────────────────────

class SeriesBand(_Model):
    p5: list[float]
    p50: list[float]
    p95: list[float]


class Timeseries(_Model):
    schemaVersion: int = SCHEMA_VERSION
    dates: list[str]
    series: dict[str, SeriesBand] = Field(description="Per parti (inkl. O) och block")
    elections: list[dict[str, str]]


class Poll(_Model):
    published: str
    fieldFrom: str | None
    fieldTo: str | None
    institute: str
    n: int | None
    shares: dict[str, float | None]


class Polls(_Model):
    schemaVersion: int = SCHEMA_VERSION
    polls: list[Poll]


# ── Mandat och simulering ───────────────────────────────────────────────────

class PartySeats(_Model):
    party: Party
    fixed: int
    adjustment: int
    total: int
    baseline: int


class Mandates(_Model):
    schemaVersion: int = SCHEMA_VERSION
    parties: list[PartySeats]
    constituencies: dict[str, dict[str, int]] = Field(description="Fasta mandat per valkrets och parti")
    baselineConstituencies: dict[str, dict[str, int]]


class SeatDistribution(_Model):
    party: Party
    mean: float
    p5: int
    p25: int
    median: int
    p75: int
    p95: int
    sdPolls: float
    sdHorizon: float
    sdTotal: float
    pAboveThreshold: float


class Coalition(_Model):
    name: str
    parties: list[Party]
    prob: float
    mean: float
    p5: int
    p25: int
    med: int
    p75: int
    p95: int


class Simulation(_Model):
    schemaVersion: int = SCHEMA_VERSION
    nSims: int
    seed: int
    horizonDays: int
    parties: list[SeatDistribution]
    blocs: dict[str, dict[str, float]] = Field(description="P(≥175), P(inget block) och mandathistogram per block")
    blocHistogram: dict[str, dict[str, int]]
    coalitions: list[Coalition]


class Probability(_Model):
    id: str
    text: str
    p: float
    label: str
    display: str


class Probabilities(_Model):
    schemaVersion: int = SCHEMA_VERSION
    questions: list[Probability]


# ── Valkretsar, kommuner, regioner ─────────────────────────────────────────

class SeatMargin(_Model):
    party: Party
    gainPp: float | None
    losePp: float | None


class Constituency(_Model):
    schemaVersion: int = SCHEMA_VERSION
    name: str
    slug: str
    seats: int
    baseline: dict[str, float]
    now: dict[str, float]
    fixedNow: dict[str, int]
    fixedBaseline: dict[str, int]
    seatDistribution: dict[str, dict[str, float]] | None = Field(
        default=None, description="P(k fasta mandat) per parti ur simuleringen (D11/N1)")
    margins: list[SeatMargin]


class AreaShares(_Model):
    baseline: dict[str, float]
    now: dict[str, float]
    p5: dict[str, float] | None = None
    p95: dict[str, float] | None = None
    others: float = 0.0


class AreaSeats(_Model):
    totalSeats: int
    threshold: float
    nAdjustment: int
    now: dict[str, int]
    baseline: dict[str, int]
    names: dict[str, str]
    stage: str


class Area(_Model):
    schemaVersion: int = SCHEMA_VERSION
    kind: Literal["kommun", "region"]
    code: str
    name: str
    slug: str
    riksdag: AreaShares | None = None
    kommunval: AreaShares | None = None
    regionval: AreaShares | None = None
    kommunSeats: AreaSeats | None = None
    regionSeats: AreaSeats | None = None


class Margins(_Model):
    schemaVersion: int = SCHEMA_VERSION
    national: dict[str, dict[str, float | None]]
    closest: list[dict[str, str | float | int | None]]


class Backtest(_Model):
    schemaVersion: int = SCHEMA_VERSION
    year: int
    rows: list[dict[str, str | float | int | None]]


class Institutes(_Model):
    schemaVersion: int = SCHEMA_VERSION
    weights: list[dict[str, str | float | int | None]]
    bias: list[dict[str, str | float | int | None]]


class ValnattState(_Model):
    schemaVersion: int = SCHEMA_VERSION
    year: int
    time: str
    nCounted: int
    nTotal: int
    voteShareCounted: float
    raw: dict[str, float] | None
    nowcast: dict[str, float]
    final: dict[str, float]
    maeRaw: float | None
    maeNowcast: float
    seats: dict[str, int]


class ValnattIndex(_Model):
    schemaVersion: int = SCHEMA_VERSION
    year: int
    times: list[str]
    curve: list[dict[str, str | float | None]]


class SeatModelConstituency(_Model):
    name: str
    seats: int
    valid_votes: int | None
    shares: dict[str, float]


class SeatModel(_Model):
    """Indata för mandatberäkningen i klienten (seatModel.ts). Skrivs oavrundad."""
    version: int
    parties: list[str]
    baseline: dict[str, float]
    baseline_others: float
    total_seats: int
    constituencies: list[SeatModelConstituency]


class ElectedMember(_Model):
    namn: str
    kandidatnummer: int
    parti: str
    valkrets: str
    valgrund: str
    slug: str


class Elected(_Model):
    """De invalda i baslinjevalet (D10). Bara namn, parti, valkrets och valgrund (D8)."""
    schemaVersion: int = SCHEMA_VERSION
    year: int
    members: list[ElectedMember]


class ArchiveDay(_Model):
    date: str
    daysLeft: int
    shares: dict[str, float]
    seatsMedian: dict[str, int]
    pThreshold: dict[str, float]
    pMajority: dict[str, float]


class Archive(_Model):
    """Prognosens utveckling fram till ett val (rekonstruerad, D12)."""
    schemaVersion: int = SCHEMA_VERSION
    year: int
    electionDate: str
    reconstructed: bool
    modelVersion: str
    nSims: int
    seed: int
    totalSeats: int
    note: str
    result: dict[str, dict[str, float]]
    days: list[ArchiveDay]


class NowcastBloc(_Model):
    name: str
    parties: list[Party]
    seats: int
    share: float


class NowcastLive(_Model):
    """Live-nowcast under valnatten (mode: nowcast). Andelar = andel av alla giltiga röster."""
    schemaVersion: int = SCHEMA_VERSION
    election: str = Field(description="Valdatum (YYYY-MM-DD)")
    baselineYear: int
    feedUpdatedAt: str | None = Field(description="Valmyndighetens senaste uppdateringstid")
    publishedAt: str
    nCounted: int
    nTotal: int
    nComparable: int = Field(description="Räknade distrikt som kunde jämföras med baslinjevalet")
    voteShareCounted: float = Field(description="Andel av baslinjevalets röster som räknats")
    raw: dict[str, float]
    nowcast: dict[str, float]
    seats: dict[str, int]
    fixedSeats: dict[str, dict[str, int]]
    blocs: list[NowcastBloc]
    final: dict[str, float] | None = Field(default=None, description="Slutresultat (bara i simulatorn)")


class ResultConstituency(_Model):
    name: str
    fixedSeats: int
    shares: dict[str, float]
    fixed: dict[str, int]
    adjustment: dict[str, int]


class ElectionResult(_Model):
    """Officiellt valresultat (Valmyndigheten) — nationellt och per valkrets."""
    schemaVersion: int = SCHEMA_VERSION
    year: int
    national: dict[str, float]
    seats: dict[str, int]
    constituencies: list[ResultConstituency]


ARTIFACT_MODELS: dict[str, type[_Model]] = {
    "ElectionResult": ElectionResult,
    "NowcastLive": NowcastLive,
    "Elected": Elected, "Archive": Archive,
    "SeatModel": SeatModel,
    "ValnattState": ValnattState, "ValnattIndex": ValnattIndex,
    "Manifest": Manifest, "ReleaseIndex": ReleaseIndex, "National": National,
    "Timeseries": Timeseries, "Polls": Polls, "Mandates": Mandates, "Simulation": Simulation,
    "Probabilities": Probabilities, "Constituency": Constituency, "Area": Area,
    "Margins": Margins, "Backtest": Backtest, "Institutes": Institutes,
}
