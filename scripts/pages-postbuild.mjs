#!/usr/bin/env node
/**
 * Turn the `--mode pages` Nitro build into a GitHub Pages artifact.
 *
 * Every route is prerendered to real HTML at its own URL; this script makes
 * the output Pages-ready:
 *
 *   1. re-bases any root-absolute URLs the platform head injector added
 *      (e.g. /__grok/manifest.webmanifest) under the Pages project path
 *   2. reconciles each page's CSS link with the asset Vite actually emitted
 *   3. injects per-page Open Graph / Twitter share meta (title and description
 *      are read back from the prerendered document)
 *   4. writes `404.html` as a copy of the home page so unknown URLs still boot
 *      the client router, plus the static PWA manifest and `.nojekyll`
 *
 * Runs after `vite build --mode pages`; see .github/workflows/deploy-pages.yml.
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC_DIR = join(ROOT, ".pages", "output", "static");
const BASE = "/Siemens_Energy_Product_Portfolio/";
const SITE_URL = `https://pedrodinisf.github.io${BASE}`;
const APP_NAME = "Fieldbook";
const THEME = "#081018";
const DEFAULT_DESCRIPTION =
  "Searchable library of Siemens Energy products, specifications, brochures, and white papers.";

function fail(message) {
  console.error(`[pages-postbuild] ${message}`);
  process.exit(1);
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, out);
    else if (entry.name.endsWith(".html")) out.push(path);
  }
  return out;
}

/** URL path a built file will be served at, for og:url. */
export function urlPathFor(relPath) {
  const rel = relPath.replaceAll("\\", "/");
  if (rel === "index.html") return "/";
  if (rel.endsWith("/index.html")) return `/${rel.slice(0, -"index.html".length)}`;
  return `/${rel}`;
}

/** Prefix bare root-absolute URLs with BASE; leave external/based ones alone. */
export function rebaseRootUrls(html) {
  return html.replace(/(href|src|content)="(\/[^"]*)"/g, (match, attr, url) => {
    if (url.startsWith("//") || url.startsWith(BASE)) return match;
    return `${attr}="${BASE}${url.slice(1)}"`;
  });
}

/** Add canonical, Open Graph and Twitter tags derived from the prerendered document. */
export function injectShareMeta(html, urlPath) {
  if (html.includes('property="og:title"')) return html;
  const title = html.match(/<title>([^<]*)<\/title>/)?.[1] || APP_NAME;
  const description =
    html.match(/<meta name="description" content="([^"]*)"/)?.[1] ||
    DEFAULT_DESCRIPTION;
  const url = `${SITE_URL}${urlPath.replace(/^\/+/, "")}`;
  const tags = [
    `<link rel="canonical" href="${url}">`,
    '<meta property="og:type" content="website">',
    `<meta property="og:site_name" content="${APP_NAME}">`,
    `<meta property="og:title" content="${title}">`,
    `<meta property="og:description" content="${description}">`,
    `<meta property="og:url" content="${url}">`,
    `<meta property="og:image" content="${SITE_URL}og.jpg">`,
    '<meta name="twitter:card" content="summary_large_image">',
    `<meta name="twitter:title" content="${title}">`,
    `<meta name="twitter:description" content="${description}">`,
    `<meta name="twitter:image" content="${SITE_URL}og.jpg">`,
  ].join("");
  return html.replace("</head>", `${tags}</head>`);
}

/** XML sitemap for every prerendered page. */
export function renderSitemap(urlPaths) {
  const entries = [...urlPaths]
    .sort()
    .map((path) => `  <url><loc>${SITE_URL}${path.replace(/^\/+/, "")}</loc></url>`)
    .join("\n");
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    `${entries}\n` +
    "</urlset>\n"
  );
}

export function renderRobots() {
  return `User-agent: *\nAllow: /\nSitemap: ${SITE_URL}sitemap.xml\n`;
}

function main() {
  if (!existsSync(PUBLIC_DIR)) {
    fail(`missing build output at ${PUBLIC_DIR} — run \`vite build --mode pages\` first.`);
  }

  const indexPath = join(PUBLIC_DIR, "index.html");
  if (!existsSync(indexPath)) {
    fail(`no index.html in ${PUBLIC_DIR} — prerendering did not produce the home route.`);
  }

  const assetsDir = join(PUBLIC_DIR, "assets");
  const styleFiles = existsSync(assetsDir)
    ? readdirSync(assetsDir).filter((name) => /^styles-.*\.css$/.test(name))
    : [];
  if (styleFiles.length !== 1) {
    fail(`expected exactly one assets/styles-*.css, found ${styleFiles.length}.`);
  }
  const stylesheet = `${BASE}assets/${styleFiles[0]}`;

  let processed = 0;
  const urlPaths = [];
  for (const file of walk(PUBLIC_DIR)) {
    const html = readFileSync(file, "utf8");
    const updated = injectShareMeta(
      rebaseRootUrls(html).replace(
        /href="[^"]*?\/assets\/styles-[^"]*?\.css"/g,
        `href="${stylesheet}"`,
      ),
      urlPathFor(relative(PUBLIC_DIR, file)),
    );
    urlPaths.push(urlPathFor(relative(PUBLIC_DIR, file)));
    if (updated !== html) {
      writeFileSync(file, updated);
      processed += 1;
    }
  }

  writeFileSync(join(PUBLIC_DIR, "404.html"), readFileSync(indexPath, "utf8"));
  writeFileSync(join(PUBLIC_DIR, "sitemap.xml"), renderSitemap(urlPaths));
  writeFileSync(join(PUBLIC_DIR, "robots.txt"), renderRobots());

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
    `[pages-postbuild] patched ${processed} html file(s); wrote 404.html + sitemap.xml (${urlPaths.length} urls) + robots.txt + PWA manifest + .nojekyll into ${PUBLIC_DIR}`,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
