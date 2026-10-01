/** Hämta en binär releasefil (t.ex. draws.parquet) verifierad mot manifestet (storlek + SHA-256). */
import type { Manifest } from "@contracts/contracts";
import { dataBase, ReleaseError } from "../client/release";

export async function fetchVerifiedBytes(m: Manifest, logicalPath: string): Promise<ArrayBuffer> {
  const e = m.files.find((f) => f.path === logicalPath);
  if (!e) throw new ReleaseError(`${logicalPath} saknas i release ${m.release.slice(0, 12)}`);
  const res = await fetch(`${dataBase()}/${e.object}`);
  if (!res.ok) throw new ReleaseError(`Kunde inte hämta ${logicalPath} (${res.status})`);
  const buf = await res.arrayBuffer();
  if (buf.byteLength !== e.size) throw new ReleaseError(`${logicalPath}: fel storlek — datan kan vara skadad`);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  if (hex !== e.sha256) throw new ReleaseError(`${logicalPath}: kontrollsumman stämmer inte`);
  return buf;
}
