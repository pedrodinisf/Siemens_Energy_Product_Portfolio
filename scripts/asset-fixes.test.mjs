import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  classifyLocalFile,
  filenameFromUrl,
  looksLikeHtml,
  planContentDedupe,
} from "./apply-asset-fixes.mjs";
import { assetKey, repairAssetUrl } from "./probe-assets.mjs";

test("repairAssetUrl trims truncated JSON fragments", () => {
  const broken =
    'https://assets.siemens-energy.com/dam/abc/Thing-pdf_Original%20file.pdf\\",\\"role\\":null';
  assert.equal(
    repairAssetUrl(broken),
    "https://assets.siemens-energy.com/dam/abc/Thing-pdf_Original%20file.pdf",
  );
  assert.equal(
    repairAssetUrl("https://assets.example.com/a.pdf"),
    "https://assets.example.com/a.pdf",
  );
});

test("assetKey prefers the DAM uuid, falls back to the URL", () => {
  const uuid = "55d5036f-2ea6-461b-b757-b05400002b9b";
  assert.equal(
    assetKey(`https://assets.siemens-energy.com/dam/${uuid}/x.pdf`),
    uuid,
  );
  assert.equal(assetKey("https://w3.example.com/x.pdf"), "https://w3.example.com/x.pdf");
});

test("filenameFromUrl strips Original-file artifacts and unsafe characters", () => {
  assert.equal(
    filenameFromUrl(
      "https://assets.siemens-energy.com/dam/x/3AV1-Blue-CB-flyer-EN-final-2021-03-pdf_Original%20file.pdf",
    ),
    "3AV1-Blue-CB-flyer-EN-final-2021-03-pdf.pdf",
  );
});

test("classifyLocalFile detects pdf, zip, html and missing files", () => {
  const dir = mkdtempSync(join(tmpdir(), "fieldbook-assets-"));
  const pdf = join(dir, "a.pdf");
  const zip = join(dir, "b.docx");
  const html = join(dir, "c.pdf");
  writeFileSync(pdf, Buffer.from("%PDF-1.7 content"));
  writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x03, 0x04, 0x00]));
  writeFileSync(html, Buffer.from("<!DOCTYPE html><html></html>"));
  assert.equal(classifyLocalFile(pdf), "pdf");
  assert.equal(classifyLocalFile(zip), "zip");
  assert.equal(classifyLocalFile(html), "html");
  assert.equal(classifyLocalFile(join(dir, "missing.pdf")), "missing");
  assert.equal(looksLikeHtml(Buffer.from("<?xml version=\"1.0\"?>")), true);
});

test("planContentDedupe never deletes a shared path and picks a stable keeper", () => {
  assert.deepEqual(planContentDedupe([["b.pdf", "a.pdf", "a.pdf"]]), {
    deletions: [{ removed: "b.pdf", keep: "a.pdf" }],
  });
  assert.deepEqual(planContentDedupe([["only.pdf"], ["x.pdf", "a.pdf"]]), {
    deletions: [{ removed: "x.pdf", keep: "a.pdf" }],
  });
});
