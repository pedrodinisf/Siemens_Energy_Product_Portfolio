#!/usr/bin/env node
/**
 * Apply Phase 0 integrity fixes to `src/data/catalog.json` using the probe
 * results from `scripts/probe-assets.mjs`:
 *
 *   - repair URLs that were scraped as truncated JSON fragments
 *   - adopt the probe's authoritative size + live/dead status per asset
 *   - canonicalise the local copy per asset (48 assets had conflicting
 *     `downloaded`/`publicPath` across rows)
 *   - verify magic bytes, drop HTML pages saved as `.pdf`, delete redundant
 *     content duplicates (same bytes under different asset URLs)
 *
 * Run `npm run catalog:split` afterwards.
 *
 *   node scripts/apply-asset-fixes.mjs
 */
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { assetKey, repairAssetUrl } from "./probe-assets.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CATALOG = join(ROOT, "src", "data", "catalog.json");
const PROBE = join(ROOT, "data", "siemens-energy", "asset-probe.json");

/** Rebuild a clean filename from a DAM URL (`_Original file` artifacts removed). */
export function filenameFromUrl(url) {
  let name = decodeURIComponent(url.split("?")[0].split("/").pop() || "");
  name = name.replace(/[_ ]Original[_ ]file/gi, "");
  name = name.replace(/[^\w.\-()+]+/g, "_");
  name = name.replace(/_+\./g, ".");
  return name.slice(0, 160) || "document";
}

export function looksLikeHtml(buffer) {
  const head = buffer.subarray(0, 512).toString("latin1").trimStart();
  return /^<!doctype|^<html|^<\?xml/i.test(head);
}

/** "pdf" | "zip" (docx/xlsx/pptx) | "html" | "other". */
export function classifyLocalFile(path) {
  if (!existsSync(path)) return "missing";
  const fd = openSync(path, "r");
  const head = Buffer.alloc(16);
  try {
    readSync(fd, head, 0, 16, 0);
  } finally {
    closeSync(fd);
  }
  if (head.subarray(0, 5).toString("latin1") === "%PDF-") return "pdf";
  if (head[0] === 0x50 && head[1] === 0x4b) return "zip";
  if (looksLikeHtml(head)) return "html";
  return "other";
}

const BAD_FILENAME = /^(text_|document$|file$)/i;

/** One keeper per identical-content group; duplicate paths get removed. */
export function planContentDedupe(groups) {
  const deletions = [];
  for (const paths of groups) {
    const sorted = [...new Set(paths)].sort();
    const keep = sorted[0];
    for (const removed of sorted.slice(1)) deletions.push({ removed, keep });
  }
  return { deletions };
}

function main() {
  const catalog = JSON.parse(readFileSync(CATALOG, "utf8"));
  const probe = JSON.parse(readFileSync(PROBE, "utf8")).assets;

  const assets = new Map();
  for (const item of catalog.items) {
    for (const file of item.files) {
      const url = repairAssetUrl(file.url);
      const key = assetKey(url);
      if (!assets.has(key)) {
        assets.set(key, { url, rows: [] });
      }
      assets.get(key).rows.push({ item, file, url });
    }
  }
  console.log(`[fixes] ${assets.size} unique assets, ${catalog.items.flatMap((i) => i.files).length} rows`);

  let repairedUrls = 0;
  let renamed = 0;
  let dead = 0;
  let localInvalid = 0;
  let localCanonical = 0;

  for (const [key, asset] of assets) {
    const result = probe[key] || {};
    const live = result.live === true;
    const info = probe[key];
    for (const row of asset.rows) {
      const { file } = row;
      if (file.url !== row.url) repairedUrls += 1;
      file.url = row.url;
      if (BAD_FILENAME.test(file.filename) || !/\.[a-z0-9]{2,5}$/i.test(file.filename)) {
        file.filename = filenameFromUrl(row.url);
        renamed += 1;
      }
      if (info && typeof info.bytes === "number" && info.bytes > 0) {
        file.bytes = info.bytes;
      }
      file.status = live ? "live" : "dead";
      if (!live) dead += 1;
    }
  }

  // Canonical local copy per asset: must exist on disk and have the right magic.
  for (const asset of assets.values()) {
    const candidates = new Set();
    for (const { file } of asset.rows) {
      if (file.publicPath) candidates.add(file.publicPath);
    }
    let canonical = "";
    for (const publicPath of [...candidates].sort()) {
      const disk = join(ROOT, "public", decodeURIComponent(publicPath));
      const kind = classifyLocalFile(disk);
      if (kind === "html") {
        rmSync(disk, { force: true });
        localInvalid += 1;
        continue;
      }
      if ((kind === "pdf" || kind === "zip") && !canonical) canonical = publicPath;
    }
    if (canonical && !asset.rows.some((r) => r.file.publicPath === canonical && r.file.downloaded)) {
      localCanonical += 1;
    }
    for (const { file } of asset.rows) {
      if (canonical) {
        file.publicPath = canonical;
        file.downloaded = true;
      } else if (file.publicPath) {
        file.downloaded = false;
      }
    }
  }

  // Content dedupe across unique on-disk paths: keep one file per hash and
  // repoint every asset that used a removed path. Several assets may share the
  // same path, so only paths (never assets) drive deletion.
  const pathToAssets = new Map();
  for (const asset of assets.values()) {
    const file = asset.rows[0]?.file;
    if (!file?.downloaded || !file.publicPath) continue;
    const disk = join(ROOT, "public", decodeURIComponent(file.publicPath));
    if (!existsSync(disk) || statSync(disk).size === 0) continue;
    if (!pathToAssets.has(file.publicPath)) {
      pathToAssets.set(file.publicPath, { disk, assets: [] });
    }
    pathToAssets.get(file.publicPath).assets.push(asset);
  }
  const hashToPaths = new Map();
  for (const [publicPath, info] of pathToAssets) {
    const hash = createHash("md5")
      .update(readFileSync(info.disk))
      .digest("hex");
    if (!hashToPaths.has(hash)) hashToPaths.set(hash, []);
    hashToPaths.get(hash).push(publicPath);
  }
  const plan = planContentDedupe(
    [...hashToPaths.values()].filter((paths) => paths.length > 1),
  );
  for (const { removed, keep } of plan.deletions) {
    rmSync(pathToAssets.get(removed).disk, { force: true });
    for (const asset of pathToAssets.get(removed).assets) {
      for (const { file } of asset.rows) {
        file.publicPath = keep;
        file.downloaded = true;
      }
    }
  }
  const deduped = plan.deletions.length;

  mkdirSync(join(ROOT, "data", "siemens-energy"), { recursive: true });
  writeFileSync(CATALOG, JSON.stringify(catalog));
  console.log(
    `[fixes] repaired urls ${repairedUrls}, renamed ${renamed}, dead rows ${dead}, ` +
      `html impostors removed ${localInvalid}, assets canonicalised ${localCanonical}, ` +
      `content duplicates removed ${deduped}`,
  );
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isCli) main();
