#!/usr/bin/env node
/**
 * Split `src/data/catalog.json` into the files the app loads:
 *
 *   catalog-index.json  everything except `body`/`faqs` (bundled app index)
 *   catalog-body.json   id -> body  (lazy chunk: item/family pages + search)
 *   catalog-faqs.json   id -> faqs  (lazy chunk: item pages only)
 *
 * Keeping FAQ text out of the search corpus roughly halves what the first
 * search has to download. The full file stays the source of truth (and mirrors
 * the local scrape archive); run this after re-scraping:
 *
 *   npm run catalog:split
 */
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "data");
const catalog = JSON.parse(readFileSync(join(DATA_DIR, "catalog.json"), "utf8"));

const index = {
  ...catalog,
  items: catalog.items.map(({ body: _body, faqs: _faqs, ...rest }) => rest),
};

const bodies = {};
const faqs = {};
for (const item of catalog.items) {
  if (item.body) bodies[item.id] = item.body;
  if (item.faqs?.length) faqs[item.id] = item.faqs;
}

writeFileSync(join(DATA_DIR, "catalog-index.json"), JSON.stringify(index));
writeFileSync(join(DATA_DIR, "catalog-body.json"), JSON.stringify(bodies));
writeFileSync(join(DATA_DIR, "catalog-faqs.json"), JSON.stringify(faqs));

// The previous combined chunk is superseded by body/faqs.
const legacy = join(DATA_DIR, "catalog-detail.json");
if (existsSync(legacy)) rmSync(legacy);

const kb = (value) => `${(JSON.stringify(value).length / 1024).toFixed(0)} KB`;
console.log(
  `[catalog:split] index ${kb(index)}, body ${kb(bodies)} (${Object.keys(bodies).length}), ` +
    `faqs ${kb(faqs)} (${Object.keys(faqs).length})`,
);
