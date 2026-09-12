#!/usr/bin/env node
/**
 * Probe every unique document asset in `src/data/catalog.json`.
 *
 * One `Range: bytes=0-0` request per asset (the CDN answers 206 with a
 * `content-range: bytes 0-0/<total>` header, which is more reliable than HEAD)
 * records whether the asset is still live, its authoritative size and its
 * content type. Results land in `data/siemens-energy/asset-probe.json`
 * (untracked) keyed by DAM UUID, or the full URL when there is no UUID.
 *
 * Also repairs the handful of catalog URLs that were scraped as truncated
 * JSON fragments (`...pdf\",\"role\":null...` -> `...pdf`).
 *
 * The probe is resumable: already-probed assets are skipped unless --force.
 *
 *   node scripts/probe-assets.mjs [--limit N] [--workers 6] [--force]
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CATALOG = join(ROOT, "src", "data", "catalog.json");
const OUT_DIR = join(ROOT, "data", "siemens-energy");
const OUT = join(OUT_DIR, "asset-probe.json");

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const URL_RE = /^(https?:\/\/[^"'\s\\]+?\.(?:pdf|pptx|ppt|xlsx|xls|docx|doc|zip))/i;

/** Repair URLs that captured trailing JSON (seen as `text_ul`/`text_p` files). */
export function repairAssetUrl(url) {
  if (!url || !/["'\\]|richtextProperties/i.test(url)) return url;
  const match = url.match(URL_RE);
  return match ? match[1] : url;
}

export function assetKey(url) {
  const uuid = url.match(UUID_RE);
  return uuid ? uuid[0].toLowerCase() : url;
}

export function isDocumentUrl(url) {
  return URL_RE.test(url);
}

function expectedFormat(url) {
  const match = url.match(/\.([a-z0-9]+)(?:\?|$)/i);
  return match ? match[1].toLowerCase() : "file";
}

async function probe(url, timeoutMs = 30000) {
  const started = Date.now();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        headers: { "user-agent": UA, range: "bytes=0-0" },
        redirect: "follow",
        signal: controller.signal,
      });
      const headers = response.headers;
      const contentType = (headers.get("content-type") || "").toLowerCase();
      const contentRange = headers.get("content-range") || "";
      const total = Number(
        contentRange.includes("/") ? contentRange.split("/").pop() : NaN,
      );
      const bytes = Number.isFinite(total)
        ? total
        : Number(headers.get("content-length")) || null;
      // A range request must not stream the whole file; cancel promptly.
      if (response.body) await response.body.cancel().catch(() => {});
      const alive =
        response.ok &&
        !contentType.includes("text/html") &&
        !/\/global\/en\/home\.html$|\/$/.test(new URL(response.url).pathname);
      return {
        live: alive,
        httpStatus: response.status,
        contentType,
        bytes,
        finalUrl: response.url,
        ms: Date.now() - started,
      };
    } catch (error) {
      if (attempt === 2) {
        return {
          live: false,
          httpStatus: 0,
          contentType: "",
          bytes: null,
          finalUrl: "",
          error: `${error.name}: ${error.message}`,
          ms: Date.now() - started,
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 800 * (attempt + 1)));
    } finally {
      clearTimeout(timer);
    }
  }
}

async function main() {
  const args = process.argv.slice(2);
  const limit = Number(args[args.indexOf("--limit") + 1]) || 0;
  const workers = Number(args[args.indexOf("--workers") + 1]) || 6;
  const force = args.includes("--force");

  const catalog = JSON.parse(readFileSync(CATALOG, "utf8"));
  const assets = new Map();
  for (const item of catalog.items) {
    for (const file of item.files) {
      const url = repairAssetUrl(file.url);
      const key = assetKey(url);
      if (!assets.has(key)) assets.set(key, { url, format: expectedFormat(url) });
      else if (assets.get(key).url !== url) assets.get(key).url = url;
    }
  }

  mkdirSync(OUT_DIR, { recursive: true });
  const existing = existsSync(OUT)
    ? JSON.parse(readFileSync(OUT, "utf8"))
    : { generatedAt: null, assets: {} };
  const results = existing.assets || {};

  let keys = [...assets.keys()].filter((key) => force || !results[key]);
  if (limit) keys = keys.slice(0, limit);
  console.log(
    `[probe] ${keys.length} to probe (${Object.keys(results).length} already done), ${workers} workers`,
  );

  let index = 0;
  let done = 0;
  const failures = [];
  async function worker() {
    while (index < keys.length) {
      const key = keys[index++];
      const { url, format } = assets.get(key);
      const result = await probe(url);
      results[key] = { url, format, ...result };
      done += 1;
      if (!result.live) failures.push(`${key} ${result.httpStatus || "ERR"}`);
      if (done % 25 === 0) {
        writeFileSync(
          OUT,
          JSON.stringify(
            { generatedAt: existing.generatedAt, assets: results },
            null,
            0,
          ),
        );
        console.log(`[probe] ${done}/${keys.length}`);
      }
    }
  }
  await Promise.all(Array.from({ length: workers }, () => worker()));

  const payload = {
    generatedAt: new Date().toISOString(),
    assets: results,
  };
  writeFileSync(OUT, JSON.stringify(payload));
  const all = Object.values(results);
  const live = all.filter((entry) => entry.live).length;
  console.log(
    `[probe] wrote ${OUT.replace(ROOT + "/", "")} — ${all.length} assets, ${live} live, ${all.length - live} dead`,
  );
  if (failures.length) {
    console.log("[probe] not live (first 20):");
    for (const failure of failures.slice(0, 20)) console.log("  " + failure);
  }
}

const isCli =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isCli) await main();
