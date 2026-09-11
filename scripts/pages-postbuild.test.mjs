import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";
import {
  injectShareMeta,
  rebaseRootUrls,
  renderRobots,
  renderSitemap,
  urlPathFor,
} from "./pages-postbuild.mjs";

const readJson = (name) =>
  JSON.parse(readFileSync(new URL(`../src/data/${name}`, import.meta.url), "utf8"));

const full = readJson("catalog.json");
const index = readJson("catalog-index.json");
const bodies = readJson("catalog-body.json");
const faqs = readJson("catalog-faqs.json");

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

test("catalog-body and catalog-faqs hold exactly the body/faqs of every item", () => {
  assert.equal(Object.keys(bodies).length, full.items.filter((i) => i.body).length);
  assert.equal(
    Object.keys(faqs).length,
    full.items.filter((i) => i.faqs?.length).length,
  );
  for (const entry of full.items) {
    assert.deepEqual(bodies[entry.id], entry.body || undefined, entry.id);
    assert.deepEqual(faqs[entry.id], entry.faqs?.length ? entry.faqs : undefined, entry.id);
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

test("every local hero image referenced by the catalog exists in public/", () => {
  const missing = [];
  const check = (value, owner) => {
    if (!value || !value.startsWith("/catalog/images/")) return;
    if (!existsSync(new URL(`../public${value}`, import.meta.url))) {
      missing.push(`${owner}: ${value}`);
    }
  };
  for (const entry of full.items) check(entry.heroLocal, entry.id);
  for (const family of full.families) check(family.hero, `family ${family.id}`);
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
  assert.match(
    out,
    /<link rel="canonical" href="https:\/\/pedrodinisf\.github\.io\/Siemens_Energy_Product_Portfolio\/item\/a\/b\/">/,
  );
  assert.match(out, /name="twitter:card" content="summary_large_image"/);
  assert.equal(injectShareMeta(out, "/item/a/b/"), out);
});

test("renderSitemap lists every URL under the site root", () => {
  const xml = renderSitemap(["/item/a/b/", "/", "/downloads/"]);
  assert.match(xml, /^<\?xml version="1\.0" encoding="UTF-8"\?>/);
  assert.match(xml, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/);
  assert.match(
    xml,
    /<url><loc>https:\/\/pedrodinisf\.github\.io\/Siemens_Energy_Product_Portfolio\/item\/a\/b\/<\/loc><\/url>/,
  );
  assert.match(
    xml,
    /<url><loc>https:\/\/pedrodinisf\.github\.io\/Siemens_Energy_Product_Portfolio\/<\/loc><\/url>/,
  );
  assert.ok(xml.trimEnd().endsWith("</urlset>"));
});

test("renderRobots allows crawling and points at the sitemap", () => {
  const robots = renderRobots();
  assert.match(robots, /User-agent: \*/);
  assert.match(robots, /Allow: \//);
  assert.match(
    robots,
    /Sitemap: https:\/\/pedrodinisf\.github\.io\/Siemens_Energy_Product_Portfolio\/sitemap\.xml/,
  );
});

test("urlPathFor maps built files to their served URLs", () => {
  assert.equal(urlPathFor("index.html"), "/");
  assert.equal(urlPathFor("downloads/index.html"), "/downloads/");
  assert.equal(urlPathFor("404.html"), "/404.html");
});
