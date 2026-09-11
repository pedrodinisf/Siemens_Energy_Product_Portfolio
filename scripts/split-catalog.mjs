#!/usr/bin/env node
/**
 * Split `src/data/catalog.json` into the two files the app loads:
 *
 *   catalog-index.json   everything except `body`/`faqs` (bundled app index)
 *   catalog-detail.json  id -> { body, faqs } (lazy chunk, item/family pages)
 *
 * The full file stays the source of truth (and mirrors
 * `data/siemens-energy/catalog.json`); run this after re-scraping:
 *
 *   npm run catalog:split
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "data");
const catalog = JSON.parse(readFileSync(join(DATA_DIR, "catalog.json"), "utf8"));

const index = {
  ...catalog,
  items: catalog.items.map(({ body: _body, faqs: _faqs, ...rest }) => rest),
};

const detail = {};
for (const item of catalog.items) {
  if (item.body || item.faqs?.length) {
    detail[item.id] = {
      ...(item.body ? { body: item.body } : {}),
      ...(item.faqs?.length ? { faqs: item.faqs } : {}),
    };
  }
}

writeFileSync(join(DATA_DIR, "catalog-index.json"), JSON.stringify(index));
writeFileSync(join(DATA_DIR, "catalog-detail.json"), JSON.stringify(detail));

const kb = (value) => `${(JSON.stringify(value).length / 1024).toFixed(0)} KB`;
console.log(
  `[catalog:split] index ${kb(index)} (${index.items.length} items), detail ${kb(detail)} (${Object.keys(detail).length} entries)`,
);
