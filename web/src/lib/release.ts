/**
 * Läser en release vid bygget (Node). Varje fil verifieras mot manifestets
 * storlek och SHA-256 — ett bygge med korrupt data avbryts hellre än att visa fel siffror.
 *
 * Releasekatalog: MANDATORN_RELEASE_DIR (standard ../dist-data, skapad av
 * `python -m mandatorn_model.publish --out dist-data`).
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Manifest } from "@contracts/contracts";
import { SCHEMA_VERSION } from "@contracts/contracts";

export const RELEASE_DIR = path.resolve(process.env.MANDATORN_RELEASE_DIR ?? path.join(process.cwd(), "..", "dist-data"));

let cached: Manifest | null = null;
const fileCache = new Map<string, unknown>();

export function manifest(): Manifest {
  if (cached) return cached;
  const p = path.join(RELEASE_DIR, "manifest.json");
  if (!fs.existsSync(p)) {
    throw new Error(`Ingen release i ${RELEASE_DIR}. Kör: python -m mandatorn_model.publish --out dist-data`);
  }
  const m = JSON.parse(fs.readFileSync(p, "utf-8")) as Manifest;
  if (m.schemaVersion !== SCHEMA_VERSION) {
    throw new Error(`Okänd schemaversion ${m.schemaVersion} (sajten stöder ${SCHEMA_VERSION})`);
  }
  cached = m;
  return m;
}

export function entry(logicalPath: string) {
  const e = manifest().files.find((f) => f.path === logicalPath);
  if (!e) throw new Error(`Filen ${logicalPath} saknas i release ${manifest().release}`);
  return e;
}

export function hasFile(logicalPath: string): boolean {
  return manifest().files.some((f) => f.path === logicalPath);
}

export function paths(prefix: string): string[] {
  return manifest().files.map((f) => f.path).filter((p) => p.startsWith(prefix));
}

export function readBytes(logicalPath: string): Buffer {
  const e = entry(logicalPath);
  const data = fs.readFileSync(path.join(RELEASE_DIR, e.object));
  if (data.length !== e.size) throw new Error(`${logicalPath}: storlek ${data.length} ≠ ${e.size}`);
  const digest = createHash("sha256").update(data).digest("hex");
  if (digest !== e.sha256) throw new Error(`${logicalPath}: SHA-256 stämmer inte med manifestet`);
  return data;
}

export function readJSON<T>(logicalPath: string): T {
  if (!fileCache.has(logicalPath)) {
    const value = JSON.parse(readBytes(logicalPath).toString("utf-8")) as { schemaVersion?: number };
    if (value.schemaVersion !== undefined && value.schemaVersion !== SCHEMA_VERSION) {
      throw new Error(`${logicalPath}: okänd schemaversion ${value.schemaVersion}`);
    }
    fileCache.set(logicalPath, value);
  }
  return fileCache.get(logicalPath) as T;
}

/** Datafilens publika URL (för nedladdningslänkar och klienten). */
export function dataUrl(): string {
  return (process.env.PUBLIC_DATA_URL ?? "/_data").replace(/\/$/, "");
}
