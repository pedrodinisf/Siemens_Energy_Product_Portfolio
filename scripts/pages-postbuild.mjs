#!/usr/bin/env node
/**
 * Turn the `--mode pages` Nitro build into a GitHub Pages artifact.
 *
 * SPA mode only emits the router shell (`_shell.html`); Pages has no rewrite
 * rules, so the shell must also be served for `/` and for every 404 (deep
 * links like /item/gas-turbines/sgt-800). This script:
 *
 *   1. copies `_shell.html` to `index.html` and `404.html`
 *   2. re-bases any root-absolute URLs the platform head injector added
 *      (e.g. /__grok/manifest.webmanifest) under the Pages project path
 *   3. reconciles the shell's CSS link with the emitted asset and writes a
 *      static PWA manifest the shell links to
 *
 * Runs after `vite build --mode pages`; see .github/workflows/deploy-pages.yml.
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC_DIR = join(ROOT, ".pages", "output", "static");
const BASE = "/Siemens_Energy_Product_Portfolio/";
const APP_NAME = "Fieldbook";
const THEME = "#081018";

function fail(message) {
  console.error(`[pages-postbuild] ${message}`);
  process.exit(1);
}

if (!existsSync(PUBLIC_DIR)) {
  fail(`missing build output at ${PUBLIC_DIR} — run \`vite build --mode pages\` first.`);
}

const shellPath = ["_shell.html", "index.html"]
  .map((name) => join(PUBLIC_DIR, name))
  .find((p) => existsSync(p));
if (!shellPath) {
  fail(`neither _shell.html nor index.html found in ${PUBLIC_DIR}.`);
}

const shell = readFileSync(shellPath, "utf8");

// Root-absolute URLs the Grok head injector adds are host-relative to "/";
// under the Pages project path they must carry the base prefix. Vite-processed
// URLs already start with BASE, so skip them to avoid double-prefixing.
let rebased = shell.replace(/(href|src|content)="(\/[^"]*)"/g, (match, attr, url) => {
  if (url.startsWith("//") || url.startsWith(BASE)) return match;
  return `${attr}="${BASE}${url.slice(1)}"`;
});

// The prerendered shell can carry the SSR build's CSS filename
// (`assets/styles-<hash>.css`) while the emitted client CSS landed under a
// different hash — the client JS then loads the right one. Point the shell at
// the file that actually exists so the stale link doesn't 404 on first paint.
const assetsDir = join(PUBLIC_DIR, "assets");
const styleFiles = existsSync(assetsDir)
  ? readdirSync(assetsDir).filter((name) => /^styles-.*\.css$/.test(name))
  : [];
if (styleFiles.length === 1) {
  rebased = rebased.replace(
    /href="[^"]*?\/assets\/styles-[^"]*?\.css"/g,
    `href="${BASE}assets/${styleFiles[0]}"`,
  );
} else {
  console.warn(
    `[pages-postbuild] expected exactly one assets/styles-*.css, found ${styleFiles.length}; leaving CSS links untouched.`,
  );
}

for (const name of ["index.html", "404.html"]) {
  writeFileSync(join(PUBLIC_DIR, name), rebased);
}

const manifest = {
  name: APP_NAME,
  short_name: APP_NAME,
  id: BASE,
  start_url: BASE,
  scope: BASE,
  display: "standalone",
  background_color: THEME,
  theme_color: THEME,
  icons: [
    { src: `${BASE}__grok/icon-180.png`, sizes: "180x180", type: "image/png" },
    { src: `${BASE}favicon.svg`, sizes: "any", type: "image/svg+xml" },
  ],
};
const grokDir = join(PUBLIC_DIR, "__grok");
mkdirSync(grokDir, { recursive: true });
writeFileSync(join(grokDir, "manifest.webmanifest"), JSON.stringify(manifest, null, 2));

writeFileSync(join(PUBLIC_DIR, ".nojekyll"), "");

console.log(
  `[pages-postbuild] wrote index.html + 404.html from ${shellPath.endsWith("_shell.html") ? "_shell.html" : "index.html"}, ` +
    `PWA manifest and .nojekyll into ${PUBLIC_DIR}`,
);
