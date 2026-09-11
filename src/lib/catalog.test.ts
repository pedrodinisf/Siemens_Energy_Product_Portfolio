import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assetHref,
  fileHref,
  formatBytes,
  isNamedSpec,
  kindLabel,
  prettyFamily,
  searchItems,
  type CatalogFile,
  type CatalogItem,
} from "./catalog.ts";

function item(overrides: Partial<CatalogItem>): CatalogItem {
  return {
    id: "x",
    url: "https://example.com/x",
    title: "",
    description: "",
    kind: "product",
    bucket: "products",
    family: "f",
    familyLabel: "F",
    slug: "x",
    highlights: [],
    specs: [],
    headings: [],
    related: [],
    files: [],
    ...overrides,
  };
}

test("assetHref leaves absolute URLs, protocol-relative URLs and empty input alone", () => {
  assert.equal(assetHref("/catalog/files/a.pdf"), "/catalog/files/a.pdf");
  assert.equal(assetHref("https://assets.example.com/a.pdf"), "https://assets.example.com/a.pdf");
  assert.equal(assetHref("//cdn.example.com/a.pdf"), "//cdn.example.com/a.pdf");
  assert.equal(assetHref(undefined), undefined);
});

test("fileHref prefers the local copy only when it was downloaded", () => {
  const downloaded: CatalogFile = {
    url: "https://source/a.pdf",
    label: "a",
    kind: "pdf",
    filename: "a.pdf",
    downloaded: true,
    publicPath: "/catalog/files/a.pdf",
  };
  const remote: CatalogFile = { ...downloaded, downloaded: false };
  assert.equal(fileHref(downloaded), "/catalog/files/a.pdf");
  assert.equal(fileHref(remote), "https://source/a.pdf");
});

test("prettyFamily strips industry/usecase prefixes and separators", () => {
  assert.equal(prettyFamily({ id: "gas-turbines", label: "Gas Turbines" }), "Gas Turbines");
  assert.equal(prettyFamily({ id: "x", label: "Industry Oil Gas" }), "Oil Gas");
  assert.equal(prettyFamily({ id: "x", label: "Usecase  Hydrogen" }), "Hydrogen");
  assert.equal(prettyFamily({ id: "other_products", label: "" }), "other products");
});

test("formatBytes renders small, KB and MB sizes", () => {
  assert.equal(formatBytes(undefined), "");
  assert.equal(formatBytes(0), "");
  assert.equal(formatBytes(500), "500 B");
  assert.equal(formatBytes(2048), "2 KB");
  assert.equal(formatBytes(2.5 * 1024 * 1024), "2.5 MB");
});

test("kindLabel and isNamedSpec handle both spec shapes", () => {
  assert.equal(kindLabel("white-paper"), "white paper");
  assert.equal(isNamedSpec({ name: "Rating", value: "62 MW" }), true);
  assert.equal(isNamedSpec({ "62 MW": "62.5 MW(e)" }), false);
});

test("searchItems matches metadata, specs and file labels with AND semantics", () => {
  const items = [
    item({
      id: "gas-turbines/sgt-800",
      title: "SGT-800 gas turbine",
      familyLabel: "Gas Turbines",
      specs: [{ "62 MW RATING": "62.5 MW(e)" }],
      files: [{ url: "https://x", label: "Feature poster", kind: "poster", filename: "p.pdf" }],
    }),
    item({ id: "steam-turbines/sst-600", title: "SST-600 steam turbine" }),
  ];

  assert.equal(searchItems(items, "sgt-800").length, 1);
  assert.equal(searchItems(items, "turbine").length, 2);
  assert.equal(searchItems(items, "sgt steam").length, 0);
  assert.equal(searchItems(items, "62.5 mw").length, 1);
  assert.equal(searchItems(items, "feature poster").length, 1);
  assert.equal(searchItems(items, "").length, 2);
});

test("searchItems searches lazily loaded body text only when provided", () => {
  const items = [
    item({ id: "a", title: "SGT-800 gas turbine" }),
    item({ id: "b", title: "Something else" }),
  ];
  const bodies = { b: "With over 620 successful installations worldwide." };

  assert.equal(searchItems(items, "620 installations").length, 0);
  assert.equal(searchItems(items, "620 installations", bodies)[0]?.id, "b");
});
