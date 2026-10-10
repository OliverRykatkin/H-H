/** Typade genvägar till EU-valets release (eget prefix eu2029/). */
import type { EuBacktest, EuNational, EuSimulation } from "@contracts/contracts";
import { eu } from "./release";

export const euNational = () => eu.readJSON<EuNational>("national.json");
export const euSimulation = () => eu.readJSON<EuSimulation>("simulation.json");
export const euBacktest = () => eu.readJSON<EuBacktest>("backtest.json");

/** Mandat på rad för stapeln: samma vänster→höger-ordning som riksdagens. */
export const EU_ORDER = ["V", "S", "MP", "C", "L", "KD", "M", "SD"];
