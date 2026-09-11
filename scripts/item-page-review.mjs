#!/usr/bin/env node
/**
 * Phase 4 review pass: audit every item page of the built Pages output.
 *
 * Serves `.pages/output/static` at the Pages base path, visits all 244 item
 * pages at a 1280x900 viewport and, per item, saves three cropped screenshot
 * regions under `data/siemens-energy/review/pages/` (`--top`, `--specs`,
 * `--body`) plus a JSON audit report with hero, specs, body, console and
 * overflow findings. `scripts/item-page-sheets.py` composes the crops into
 * per-sector contact sheets.
 *
 *   node scripts/item-page-review.mjs                 # uses .pages/output/static
 *   node scripts/item-page-review.mjs --origin http://127.0.0.1:8080
 *   node scripts/item-page-review.mjs --workers 4
 */
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const STATIC = join(ROOT, ".pages", "output", "static");
const OUT_DIR = join(ROOT, "data", "siemens-energy", "review");
const SHOT_DIR = join(OUT_DIR, "pages");
const REPORT = join(OUT_DIR, "page-audit.json");
const BASE = "/Siemens_Energy_Product_Portfolio";
const PORT = 8090;
const VIEWPORT = { width: 1280, height: 900 };

const require = createRequire(join(ROOT, "package.json"));
const { chromium } = require("playwright");

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

function parseArgs(argv) {
  const args = { origin: "", workers: 4, limit: 0 };
  for (let i = 0; i < argv.length; i++) {
    const [key, inline] = argv[i].split("=");
    if (key === "--origin") args.origin = inline ?? argv[++i];
    else if (key === "--workers") args.workers = Number(inline ?? argv[++i]);
    else if (key === "--limit") args.limit = Number(inline ?? argv[++i]);
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  return args;
}

function chromiumExe() {
  const pw = join(process.env.LOCALAPPDATA || "", "ms-playwright");
  if (!existsSync(pw)) return undefined;
  for (const dir of readdirSync(pw)) {
    const exe = join(pw, dir, "chrome-win64", "chrome.exe");
    if (dir.startsWith("chromium-") && existsSync(exe)) return exe;
  }
  return undefined;
}

function startStaticServer() {
  const server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (!path.startsWith(BASE)) {
      res.writeHead(404, { "content-type": "text/plain" });
      res.end("not found");
      return;
    }
    path = path.slice(BASE.length);
    if (path === "" || path.endsWith("/")) path += "index.html";
    let file = resolve(STATIC, "." + path);
    if (!file.startsWith(resolve(STATIC))) {
      res.writeHead(403);
      res.end();
      return;
    }
    if (!existsSync(file) || statSync(file).isDirectory()) {
      const asDir = file + "/index.html";
      if (existsSync(asDir)) file = asDir;
      else {
        const fallback = join(STATIC, "404.html");
        res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
        res.end(existsSync(fallback) ? readFileSync(fallback) : "not found");
        return;
      }
    }
    res.writeHead(200, { "content-type": MIME[extname(file).toLowerCase()] || "application/octet-stream" });
    res.end(readFileSync(file));
  });
  return new Promise((done) => server.listen(PORT, "127.0.0.1", () => done(server)));
}

async function auditItem(context, origin, item) {
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text().slice(0, 300)));
  page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 300)));
  page.on("requestfailed", (r) => {
    const url = r.url();
    if (!url.includes("grok.com")) failedRequests.push(`${url.slice(0, 160)} :: ${r.failure()?.errorText}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !r.url().includes("grok.com")) {
      failedRequests.push(`${r.status()} ${r.url().slice(0, 160)}`);
    }
  });

  const result = { id: item.id, family: item.family, slug: item.slug, status: 0 };
  try {
    const response = await page.goto(origin + `/item/${item.family}/${item.slug}/`, {
      waitUntil: "load",
      timeout: 60000,
    });
    result.status = response?.status() ?? 0;
    await page.waitForTimeout(1800);
    result.page = await page.evaluate(() => {
      const hero = document.querySelector("header img");
      const specs = [...document.querySelectorAll("section")].find(
        (s) => s.querySelector("h2")?.textContent === "Technical data",
      );
      const body = [...document.querySelectorAll("section")].find(
        (s) => s.querySelector("h2")?.textContent === "Overview",
      );
      return {
        h1: document.querySelector("h1")?.textContent?.trim() || null,
        textLength: (document.body.innerText || "").trim().length,
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        hero: hero
          ? { src: hero.currentSrc || hero.src, ok: hero.complete && hero.naturalWidth > 0 }
          : null,
        specsTables: specs ? specs.querySelectorAll("table").length : 0,
        specsBlanks: specs
          ? [...specs.querySelectorAll("td, th")].filter((c) => c.textContent?.trim() === "—").length
          : 0,
        bodyBlocks: body ? body.childElementCount : 0,
        leftovers: (() => {
          const text = (body?.innerText || "").toLowerCase();
          const needles = ["marketing information", "cookie", "read more", "learn more", "subscribe"];
          return needles.filter((needle) => text.includes(needle));
        })(),
      };
    });

    const shot = async (name, locator) => {
      if (locator) {
        const target = locator.first();
        if ((await target.count()) === 0) return;
        await target.scrollIntoViewIfNeeded();
      } else {
        await page.evaluate(() => window.scrollTo(0, 0));
      }
      await page.waitForTimeout(250);
      await page.screenshot({
        path: join(SHOT_DIR, `${item.family}__${item.slug}--${name}.jpg`),
        type: "jpeg",
        quality: 55,
      });
    };

    await shot("top");
    const specsSection = page.locator("section", {
      has: page.getByRole("heading", { name: "Technical data" }),
    });
    await shot("specs", specsSection);
    const bodySection = page.locator("section", {
      has: page.getByRole("heading", { name: "Overview" }),
    });
    await shot("body", bodySection);
  } catch (error) {
    result.error = String(error).slice(0, 300);
  }
  result.consoleErrors = consoleErrors;
  result.pageErrors = pageErrors;
  result.failedRequests = failedRequests;
  await page.close();
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  mkdirSync(SHOT_DIR, { recursive: true });

  let server = null;
  let origin = args.origin;
  if (!origin) {
    if (!existsSync(STATIC)) {
      throw new Error(`missing build output at ${STATIC} — run \`npm run build:pages\` first`);
    }
    server = await startStaticServer();
    origin = `http://127.0.0.1:${PORT}${BASE}`;
  }

  const catalog = JSON.parse(readFileSync(join(ROOT, "src", "data", "catalog.json"), "utf8"));
  const items = args.limit ? catalog.items.slice(0, args.limit) : catalog.items;
  console.log(`[review] ${items.length} items, ${args.workers} workers, origin ${origin}`);

  const browser = await chromium.launch({ headless: true, executablePath: chromiumExe() });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const results = [];
  let index = 0;
  await Promise.all(
    Array.from({ length: args.workers }, async () => {
      while (index < items.length) {
        const item = items[index++];
        const result = await auditItem(context, origin, item);
        results.push(result);
        if (results.length % 20 === 0) console.log(`[review]   ${results.length}/${items.length}`);
      }
    }),
  );
  await context.close();
  await browser.close();
  if (server) server.close();

  results.sort((a, b) => a.id.localeCompare(b.id));
  const summary = {
    generatedAt: new Date().toISOString(),
    items: results.length,
    statusOk: results.filter((r) => r.status === 200).length,
    missingHero: results.filter((r) => !r.page?.hero?.ok).map((r) => r.id),
    broken: results.filter((r) => r.error || r.consoleErrors.length || r.pageErrors.length).map((r) => r.id),
    overflow: results.filter((r) => (r.page?.overflow ?? 0) > 0).map((r) => r.id),
    leftovers: results.filter((r) => r.page?.leftovers?.length).map((r) => r.id),
    withoutSpecs: results.filter((r) => (r.page?.specsTables ?? 0) === 0).length,
    withoutBody: results.filter((r) => (r.page?.bodyBlocks ?? 0) === 0).map((r) => r.id),
  };
  writeFileSync(REPORT, JSON.stringify({ summary, results }, null, 1));
  console.log(`[review] wrote ${REPORT}`);
  console.log(`[review] summary: ${JSON.stringify(summary)}`);
}

main().catch((error) => {
  console.error(`[review] ${error}`);
  process.exit(1);
});
