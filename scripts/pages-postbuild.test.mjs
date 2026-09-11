import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";
import {
  injectShareMeta,
  rebaseRootUrls,
  urlPathFor,
} from "./pages-postbuild.mjs";

const readJson = (name) =>
  JSON.parse(readFileSync(new URL(`../src/data/${name}`, import.meta.url), "utf8"));

const full = readJson("catalog.json");
const index = readJson("catalog-index.json");
const detail = readJson("catalog-detail.json");

test("catalog-index mirrors the full catalog minus body/faqs", () => {
  assert.equal(index.items.length, full.items.length);
  for (const entry of full.items) {
    const { body: _body, faqs: _faqs, ...expected } = entry;
    assert.deepEqual(
      index.items.find((i) => i.id === entry.id),
      expected,
      entry.id,
    );
  }
});

test("catalog-detail holds exactly the body/faqs of every item", () => {
  const expectedCount = full.items.filter((i) => i.body || i.faqs?.length).length;
  assert.equal(Object.keys(detail).length, expectedCount);
  for (const entry of full.items) {
    const got = detail[entry.id];
    if (!entry.body && !entry.faqs?.length) {
      assert.equal(got, undefined, entry.id);
      continue;
    }
    assert.equal(got.body, entry.body, entry.id);
    assert.deepEqual(got.faqs, entry.faqs?.length ? entry.faqs : undefined, entry.id);
  }
});

test("every downloaded catalog file exists in public/", () => {
  const missing = [];
  for (const entry of full.items) {
    for (const file of entry.files) {
      if (!file.downloaded || !file.publicPath) continue;
      if (!existsSync(new URL(`../public${file.publicPath}`, import.meta.url))) {
        missing.push(file.publicPath);
      }
    }
  }
  assert.deepEqual(missing, []);
});

test("rebaseRootUrls prefixes bare root paths, leaves based/external URLs", () => {
  const html =
    '<a href="/__grok/x">a</a>' +
    '<link href="/Siemens_Energy_Product_Portfolio/favicon.svg">' +
    '<img src="https://example.com/y">' +
    '<img src="//cdn.example.com/z">';
  const out = rebaseRootUrls(html);
  assert.match(out, /href="\/Siemens_Energy_Product_Portfolio\/__grok\/x"/);
  assert.match(out, /href="\/Siemens_Energy_Product_Portfolio\/favicon\.svg"/);
  assert.doesNotMatch(out, /Siemens_Energy_Product_Portfolio\/Siemens_Energy_Product_Portfolio/);
  assert.match(out, /src="https:\/\/example\.com\/y"/);
  assert.match(out, /src="\/\/cdn\.example\.com\/z"/);
});

test("injectShareMeta builds tags from the document and is idempotent", () => {
  const html =
    '<html><head><title>Hello &amp; World</title>' +
    '<meta name="description" content="A description"></head><body></body></html>';
  const out = injectShareMeta(html, "/item/a/b/");
  assert.match(out, /property="og:title" content="Hello &amp; World"/);
  assert.match(out, /property="og:description" content="A description"/);
  assert.match(
    out,
    /property="og:url" content="https:\/\/pedrodinisf\.github\.io\/Siemens_Energy_Product_Portfolio\/item\/a\/b\/"/,
  );
  assert.match(out, /name="twitter:card" content="summary_large_image"/);
  assert.equal(injectShareMeta(out, "/item/a/b/"), out);
});

test("urlPathFor maps built files to their served URLs", () => {
  assert.equal(urlPathFor("index.html"), "/");
  assert.equal(urlPathFor("downloads/index.html"), "/downloads/");
  assert.equal(urlPathFor("404.html"), "/404.html");
});
