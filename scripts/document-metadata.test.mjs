import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const catalog = JSON.parse(
  readFileSync(new URL("../src/data/catalog.json", import.meta.url), "utf8"),
);
const sidecar = JSON.parse(
  readFileSync(new URL("../src/data/document-metadata.json", import.meta.url), "utf8"),
);

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const GENERIC = /^(download|read more|view|open|click here|pdf|interactive pdf)$/i;

test("every catalog file carries display metadata", () => {
  for (const item of catalog.items) {
    for (const file of item.files) {
      assert.ok(file.title && file.title.length >= 2, `${item.id} title`);
      assert.ok(!GENERIC.test(file.title), `${item.id} generic title: ${file.title}`);
      assert.ok(file.docType, `${item.id} docType`);
      assert.match(file.lang, /^[A-Z]{2}$/, `${item.id} lang`);
      assert.ok(file.format, `${item.id} format`);
      assert.ok(file.titleSource, `${item.id} titleSource`);
      assert.ok(["live", "dead"].includes(file.status), `${item.id} status`);
      if (file.date) {
        assert.match(file.date, /^\d{4}-\d{2}(-\d{2})?$/, `${item.id} date ${file.date}`);
      }
    }
  }
});

test("document metadata sidecar covers every catalog asset with the same values", () => {
  const assets = new Map();
  for (const item of catalog.items) {
    for (const file of item.files) {
      const key = (file.url.match(UUID_RE)?.[0] || file.url).toLowerCase();
      assets.set(key, file);
    }
  }
  assert.equal(Object.keys(sidecar.assets).length, assets.size);
  for (const [key, meta] of Object.entries(sidecar.assets)) {
    const file = assets.get(key);
    assert.ok(file, `sidecar has unknown asset ${key}`);
    assert.equal(file.title, meta.title, key);
    assert.equal(file.docType, meta.docType, key);
    assert.equal(file.lang, meta.lang, key);
  }
});

test("no document is left with a filename-only or empty title", () => {
  const weak = [];
  for (const item of catalog.items) {
    for (const file of item.files) {
      if (file.titleSource === "filename" && /^[\d\s._-]+$/.test(file.title)) {
        weak.push(`${item.id} ${file.title}`);
      }
    }
  }
  assert.deepEqual(weak, []);
});
