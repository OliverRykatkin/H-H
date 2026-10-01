/**
 * Klientens dataåtkomst: hämtar senaste manifest (no-cache), verifierar storlek och
 * SHA-256 för varje fil med crypto.subtle och avvisar okända schemaversioner.
 * Vid fel kastas ReleaseError — anroparen visar ett tydligt fel i stället för siffror.
 */
import type { FileEntry, Manifest } from "@contracts/contracts";
import { SCHEMA_VERSION } from "@contracts/contracts";

export class ReleaseError extends Error {}

export function dataBase(): string {
  const el = document.querySelector<HTMLMetaElement>('meta[name="mandatorn:data"]');
  return (el?.content || "/_data").replace(/\/$/, "");
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function checkSchema(value: unknown, where: string) {
  const v = (value as { schemaVersion?: number })?.schemaVersion;
  if (v !== undefined && v !== SCHEMA_VERSION) {
    throw new ReleaseError(`${where}: datan har schemaversion ${v}, sajten stöder ${SCHEMA_VERSION}. Ladda om sidan.`);
  }
}

export async function fetchManifest(path = "manifest.json"): Promise<Manifest> {
  const res = await fetch(`${dataBase()}/${path}`, { cache: "no-cache" });
  if (!res.ok) throw new ReleaseError(`Kunde inte hämta ${path} (${res.status})`);
  const m = (await res.json()) as Manifest;
  checkSchema(m, path);
  return m;
}

export async function fetchVerified<T>(m: Manifest, logicalPath: string): Promise<T> {
  const e: FileEntry | undefined = m.files.find((f) => f.path === logicalPath);
  if (!e) throw new ReleaseError(`${logicalPath} saknas i release ${m.release.slice(0, 12)}`);
  const res = await fetch(`${dataBase()}/${e.object}`);
  if (!res.ok) throw new ReleaseError(`Kunde inte hämta ${logicalPath} (${res.status})`);
  const buf = await res.arrayBuffer();
  if (buf.byteLength !== e.size) throw new ReleaseError(`${logicalPath}: fel storlek — datan kan vara skadad`);
  if ((await sha256Hex(buf)) !== e.sha256) throw new ReleaseError(`${logicalPath}: kontrollsumman stämmer inte`);
  const value = JSON.parse(new TextDecoder().decode(buf)) as T;
  checkSchema(value, logicalPath);
  return value;
}

export interface ReleaseStatus {
  latest: Manifest;
  builtRelease: string;
  isNewer: boolean;
  /** Releasen sidan byggdes med har rättats (supersededBy satt). */
  supersededBy: string | null;
}

/** Jämför sidans release (meta mandatorn:release) med senaste manifestet. */
export async function releaseStatus(): Promise<ReleaseStatus> {
  const built = document.querySelector<HTMLMetaElement>('meta[name="mandatorn:release"]')?.content ?? "";
  const latest = await fetchManifest();
  let supersededBy: string | null = null;
  if (built && built !== latest.release) {
    try {
      supersededBy = (await fetchManifest(`releases/${built}/manifest.json`)).supersededBy ?? null;
    } catch {
      supersededBy = null;
    }
  }
  return { latest, builtRelease: built, isNewer: !!built && built !== latest.release, supersededBy };
}
