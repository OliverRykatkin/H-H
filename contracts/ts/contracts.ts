/* Genererad av tools/gen_contracts.py — redigera inte för hand. */

export const SCHEMA_VERSION = 1;

// ── Area.schema.json ──
export interface Area {
  code: string;
  kind: "kommun" | "region";
  kommunSeats?: AreaSeats | null;
  kommunval?: AreaShares | null;
  name: string;
  regionSeats?: AreaSeats | null;
  regionval?: AreaShares | null;
  riksdag?: AreaShares | null;
  schemaVersion?: number;
  slug: string;
}
/**
 * This interface was referenced by `Area`'s JSON-Schema
 * via the `definition` "AreaSeats".
 */
export interface AreaSeats {
  baseline: {
    [k: string]: number;
  };
  nAdjustment: number;
  names: {
    [k: string]: string;
  };
  now: {
    [k: string]: number;
  };
  stage: string;
  threshold: number;
  totalSeats: number;
}
/**
 * This interface was referenced by `Area`'s JSON-Schema
 * via the `definition` "AreaShares".
 */
export interface AreaShares {
  baseline: {
    [k: string]: number;
  };
  now: {
    [k: string]: number;
  };
  others?: number;
  p5?: {
    [k: string]: number;
  } | null;
  p95?: {
    [k: string]: number;
  } | null;
}

// ── Backtest.schema.json ──
export interface Backtest {
  rows: {
    [k: string]: string | number | null;
  }[];
  schemaVersion?: number;
  year: number;
}

// ── Constituency.schema.json ──
export interface Constituency {
  baseline: {
    [k: string]: number;
  };
  fixedBaseline: {
    [k: string]: number;
  };
  fixedNow: {
    [k: string]: number;
  };
  margins: SeatMargin[];
  name: string;
  now: {
    [k: string]: number;
  };
  schemaVersion?: number;
  /**
   * P(k fasta mandat) per parti ur simuleringen (D11/N1)
   */
  seatDistribution?: {
    [k: string]: {
      [k: string]: number;
    };
  } | null;
  seats: number;
  slug: string;
}
/**
 * This interface was referenced by `Constituency`'s JSON-Schema
 * via the `definition` "SeatMargin".
 */
export interface SeatMargin {
  gainPp: number | null;
  losePp: number | null;
  party: "M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD";
}

// ── Institutes.schema.json ──
export interface Institutes {
  bias: {
    [k: string]: string | number | null;
  }[];
  schemaVersion?: number;
  weights: {
    [k: string]: string | number | null;
  }[];
}

// ── Mandates.schema.json ──
export interface Mandates {
  baselineConstituencies: {
    [k: string]: {
      [k: string]: number;
    };
  };
  /**
   * Fasta mandat per valkrets och parti
   */
  constituencies: {
    [k: string]: {
      [k: string]: number;
    };
  };
  parties: PartySeats[];
  schemaVersion?: number;
}
/**
 * This interface was referenced by `Mandates`'s JSON-Schema
 * via the `definition` "PartySeats".
 */
export interface PartySeats {
  adjustment: number;
  baseline: number;
  fixed: number;
  party: "M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD";
  total: number;
}

// ── Manifest.schema.json ──
export interface Manifest {
  files: FileEntry[];
  /**
   * Referensdatum för körningen (ISO 8601, Europe/Stockholm-dygn)
   */
  generatedAt: string;
  /**
   * SHA-256 över all indata (mätningar, baslinjefiler, konfiguration)
   */
  inputHash: string;
  mode: "forecast" | "nowcast" | "final";
  /**
   * Git-commit för modellkoden
   */
  modelVersion: string;
  pollsIncluded: PollsIncluded;
  /**
   * SHA-256 över det kanoniska filindexet
   */
  release: string;
  schemaVersion?: number;
  seed: number;
  supersededBy?: string | null;
}
/**
 * This interface was referenced by `Manifest`'s JSON-Schema
 * via the `definition` "FileEntry".
 */
export interface FileEntry {
  /**
   * Innehållsadresserad nyckel i datalagret, t.ex. 'files/<sha256>.json'
   */
  object: string;
  /**
   * Logisk sökväg i releasen, t.ex. 'national.json'
   */
  path: string;
  sha256: string;
  size: number;
}
/**
 * This interface was referenced by `Manifest`'s JSON-Schema
 * via the `definition` "PollsIncluded".
 */
export interface PollsIncluded {
  count: number;
  /**
   * Senaste fältperiodens slutdatum (YYYY-MM-DD)
   */
  latestFieldEnd: string | null;
  latestPublished: string;
}

// ── Margins.schema.json ──
export interface Margins {
  closest: {
    [k: string]: string | number | null;
  }[];
  national: {
    [k: string]: {
      [k: string]: number | null;
    };
  };
  schemaVersion?: number;
}

// ── National.schema.json ──
export interface National {
  baselineYear: number;
  belowThreshold: ("M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD")[];
  blocs: Bloc[];
  daysLeft: number;
  estimates: PartyEstimate[];
  largestParty: "M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD";
  latestPoll: string;
  nextElection: string;
  referenceDate: string;
  schemaVersion?: number;
  /**
   * Punktprognos, totala mandat per parti
   */
  seats: {
    [k: string]: number;
  };
  /**
   * Nollsummerad nationell sving sedan baslinjevalet (pp)
   */
  swing: {
    [k: string]: number;
  };
  trend: TrendRow[];
}
/**
 * This interface was referenced by `National`'s JSON-Schema
 * via the `definition` "Bloc".
 */
export interface Bloc {
  name: string;
  pMajority: number;
  parties: ("M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD")[];
  seats: number;
  share: number;
}
/**
 * This interface was referenced by `National`'s JSON-Schema
 * via the `definition` "PartyEstimate".
 */
export interface PartyEstimate {
  /**
   * Valresultat i baslinjevalet (procent)
   */
  baseline: number | null;
  change: number | null;
  name: string;
  pAboveThreshold?: number | null;
  party: "M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD" | "O";
  /**
   * Simuleringens totala σ (pp)
   */
  sd?: number | null;
  /**
   * Skattad röstandel i procent (8 partier normerade till 100; O separat)
   */
  share: number;
}
/**
 * This interface was referenced by `National`'s JSON-Schema
 * via the `definition` "TrendRow".
 */
export interface TrendRow {
  /**
   * Parti- eller blocknyckel
   */
  key: string;
  lastElection: number | null;
  monthAgo: number | null;
  name: string;
  now: number;
  yearAgo: number | null;
}

// ── Polls.schema.json ──
export interface Polls {
  polls: Poll[];
  schemaVersion?: number;
}
/**
 * This interface was referenced by `Polls`'s JSON-Schema
 * via the `definition` "Poll".
 */
export interface Poll {
  fieldFrom: string | null;
  fieldTo: string | null;
  institute: string;
  n: number | null;
  published: string;
  shares: {
    [k: string]: number | null;
  };
}

// ── Probabilities.schema.json ──
export interface Probabilities {
  questions: Probability[];
  schemaVersion?: number;
}
/**
 * This interface was referenced by `Probabilities`'s JSON-Schema
 * via the `definition` "Probability".
 */
export interface Probability {
  display: string;
  id: string;
  label: string;
  p: number;
  text: string;
}

// ── ReleaseIndex.schema.json ──
export interface ReleaseIndex {
  releases: ReleaseIndexEntry[];
  schemaVersion?: number;
}
/**
 * This interface was referenced by `ReleaseIndex`'s JSON-Schema
 * via the `definition` "ReleaseIndexEntry".
 */
export interface ReleaseIndexEntry {
  generatedAt: string;
  mode: "forecast" | "nowcast" | "final";
  release: string;
  supersededBy?: string | null;
}

// ── Simulation.schema.json ──
export interface Simulation {
  blocHistogram: {
    [k: string]: {
      [k: string]: number;
    };
  };
  /**
   * P(≥175), P(inget block) och mandathistogram per block
   */
  blocs: {
    [k: string]: {
      [k: string]: number;
    };
  };
  coalitions: Coalition[];
  horizonDays: number;
  nSims: number;
  parties: SeatDistribution[];
  schemaVersion?: number;
  seed: number;
}
/**
 * This interface was referenced by `Simulation`'s JSON-Schema
 * via the `definition` "Coalition".
 */
export interface Coalition {
  mean: number;
  med: number;
  name: string;
  p25: number;
  p5: number;
  p75: number;
  p95: number;
  parties: ("M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD")[];
  prob: number;
}
/**
 * This interface was referenced by `Simulation`'s JSON-Schema
 * via the `definition` "SeatDistribution".
 */
export interface SeatDistribution {
  mean: number;
  median: number;
  p25: number;
  p5: number;
  p75: number;
  p95: number;
  pAboveThreshold: number;
  party: "M" | "L" | "C" | "KD" | "S" | "V" | "MP" | "SD";
  sdHorizon: number;
  sdPolls: number;
  sdTotal: number;
}

// ── Timeseries.schema.json ──
export interface Timeseries {
  dates: string[];
  elections: {
    [k: string]: string;
  }[];
  schemaVersion?: number;
  /**
   * Per parti (inkl. O) och block
   */
  series: {
    [k: string]: SeriesBand;
  };
}
/**
 * This interface was referenced by `Timeseries`'s JSON-Schema
 * via the `definition` "SeriesBand".
 */
export interface SeriesBand {
  p5: number[];
  p50: number[];
  p95: number[];
}

// ── ValnattIndex.schema.json ──
export interface ValnattIndex {
  curve: {
    [k: string]: string | number | null;
  }[];
  schemaVersion?: number;
  times: string[];
  year: number;
}

// ── ValnattState.schema.json ──
export interface ValnattState {
  final: {
    [k: string]: number;
  };
  maeNowcast: number;
  maeRaw: number | null;
  nCounted: number;
  nTotal: number;
  nowcast: {
    [k: string]: number;
  };
  raw: {
    [k: string]: number;
  } | null;
  schemaVersion?: number;
  seats: {
    [k: string]: number;
  };
  time: string;
  voteShareCounted: number;
  year: number;
}
