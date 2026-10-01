import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import fs from "node:fs";
import path from "node:path";

// Statisk förrendering. Datan läses vid bygget från en release (MANDATORN_RELEASE_DIR)
// och uppdateras i klienten från PUBLIC_DATA_URL om en nyare release finns.
// Utan PUBLIC_DATA_URL (lokalt) serveras releasen under /_data/.
const releaseDir = path.resolve(process.env.MANDATORN_RELEASE_DIR || path.join(process.cwd(), "..", "dist-data"));
const localData = !process.env.PUBLIC_DATA_URL;

function serveLocalRelease() {
  return {
    name: "mandatorn-local-release",
    hooks: {
      "astro:server:setup": ({ server }) => {
        server.middlewares.use("/_data", (req, res, next) => {
          const file = path.join(releaseDir, decodeURIComponent((req.url ?? "/").split("?")[0]));
          if (!file.startsWith(releaseDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return next();
          res.setHeader("Cache-Control", "no-cache");
          res.setHeader("Content-Type", file.endsWith(".json") ? "application/json" : "application/octet-stream");
          fs.createReadStream(file).pipe(res);
        });
      },
      "astro:build:done": ({ dir }) => {
        if (!localData) return;
        const out = path.join(new URL(dir).pathname.replace(/^\/([A-Za-z]:)/, "$1"), "_data");
        fs.cpSync(releaseDir, out, { recursive: true, filter: (src) => !src.endsWith(".meta.json") });
      },
    },
  };
}

export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || "https://mandatorn.se",
  output: "static",
  outDir: process.env.ASTRO_OUT_DIR || "./dist",
  trailingSlash: "always",
  build: { format: "directory", inlineStylesheets: "auto" },
  integrations: [react(), serveLocalRelease()],
  vite: { build: { target: "es2022" } },
});
