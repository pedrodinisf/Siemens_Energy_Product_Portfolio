#!/usr/bin/env node
/**
 * Browser review for the document tables: serves the built Pages output at the
 * Pages base path and checks the catalog, family, item, downloads and papers
 * views on desktop and mobile. Verifies expected document titles render, that
 * the console stays clean and that pages do not overflow horizontally.
 *
 *   node scripts/document-ui-review.mjs
 *
 * Screenshots and a JSON verdict land in `data/siemens-energy/qa/`.
 */
import { createServer } from "node:http";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const STATIC = join(ROOT, ".pages", "output", "static");
const OUT_DIR = join(ROOT, "data", "siemens-energy", "qa");
const BASE = "/Siemens_Energy_Product_Portfolio";
const PORT = 8095;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".xml": "application/xml",
  ".txt": "text/plain",
};

const ROUTES = [
  { path: "/", expect: "The Siemens Energy portfolio, filed." },
  { path: "/downloads", expect: "Composite insulators flyer" },
  { path: "/papers", expect: "White papers & technical notes" },
  {
    path: "/family/grid-products",
    expect: "Synchronous condenser flyer",
  },
  {
    path: "/family/other-products",
    expect: "Packager and parts distributor support data",
  },
  {
    path: "/item/grid-products/voltage-regulators",
    expect: "JFR single-phase voltage regulator",
  },
  {
    path: "/item/other-products/packager-and-parts-distributor-support-data",
    expect: "GFP-1 · Order Entry Policy",
  },
  {
    path: "/item/gas-turbines/sgt5-2000e",
    expect: "Unavailable",
  },
];

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "mobile", width: 390, height: 844 },
];

function resolveFile(pathname) {
  const candidates = [join(STATIC, pathname)];
  if (pathname.endsWith("/")) {
    candidates.push(join(STATIC, pathname, "index.html"));
  } else {
    candidates.push(join(STATIC, `${pathname}.html`));
    candidates.push(join(STATIC, pathname, "index.html"));
  }
  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      /* unreadable */
    }
  }
  return null;
}

function serve() {
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    const pathname = decodeURIComponent(url.pathname);
    if (!pathname.startsWith(BASE)) {
      response.writeHead(404);
      response.end("not found");
      return;
    }
    const file = resolveFile(pathname.slice(BASE.length));
    if (!file) {
      const fallback = join(STATIC, "404.html");
      response.writeHead(404, { "content-type": "text/html; charset=utf-8" });
      response.end(existsSync(fallback) ? readFileSync(fallback) : "not found");
      return;
    }
    response.writeHead(200, {
      "content-type": MIME[extname(file)] || "application/octet-stream",
    });
    response.end(readFileSync(file));
  });
  return new Promise((resolve) => server.listen(PORT, "127.0.0.1", () => resolve(server)));
}

const require = createRequire(join(ROOT, "package.json"));
const { chromium } = require("playwright");

async function main() {
  if (!existsSync(STATIC)) {
    console.error("built output missing: run npm run build:pages first");
    process.exit(1);
  }
  mkdirSync(OUT_DIR, { recursive: true });
  const server = await serve();
  const browser = await chromium.launch({ channel: "chrome" });
  const findings = [];
  const results = [];

  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
    });
    for (const route of ROUTES) {
      const page = await context.newPage();
      const consoleErrors = [];
      const pageErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("pageerror", (error) => pageErrors.push(String(error)));
      const url = `http://127.0.0.1:${PORT}${BASE}${route.path}`;
      await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
      const body = await page.innerText("body");
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      const hasContent = body.includes(route.expect);
      const result = {
        route: route.path,
        viewport: viewport.name,
        hasContent,
        overflow,
        consoleErrors,
        pageErrors,
      };
      results.push(result);
      if (!hasContent) findings.push(`${route.path} [${viewport.name}] missing "${route.expect}"`);
      if (consoleErrors.length || pageErrors.length) {
        findings.push(
          `${route.path} [${viewport.name}] console: ${[...consoleErrors, ...pageErrors].join(" | ").slice(0, 200)}`,
        );
      }
      if (overflow > 2) findings.push(`${route.path} [${viewport.name}] overflows by ${overflow}px`);
      const documentsTable = page.locator('table:has(a[aria-label^="Open "])').first();
      const table =
        (await documentsTable.count()) > 0 ? documentsTable : page.locator("table").first();
      if ((await table.count()) > 0) {
        await table.scrollIntoViewIfNeeded();
        await page.waitForTimeout(150);
      }
      const name = `${route.path.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "home"}-${viewport.name}.png`;
      await page.screenshot({ path: join(OUT_DIR, name), fullPage: false });
      await page.close();
    }
    await context.close();
  }

  await browser.close();
  server.close();
  const verdict = { ok: findings.length === 0, findings, results };
  writeFileSync(join(OUT_DIR, "verdict.json"), JSON.stringify(verdict, null, 2));
  console.log(JSON.stringify(verdict, null, 2));
  process.exit(findings.length ? 1 : 0);
}

await main();
