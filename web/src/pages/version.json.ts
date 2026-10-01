import type { APIRoute } from "astro";
import { manifest } from "../lib/release";

export const GET: APIRoute = () => {
  const m = manifest();
  return new Response(JSON.stringify({
    build: { commit: import.meta.env.PUBLIC_BUILD_COMMIT ?? "lokal", builtAt: new Date().toISOString() },
    release: { id: m.release, generatedAt: m.generatedAt, mode: m.mode, modelVersion: m.modelVersion, seed: m.seed },
    polls: m.pollsIncluded,
  }, null, 2), { headers: { "Content-Type": "application/json" } });
};
