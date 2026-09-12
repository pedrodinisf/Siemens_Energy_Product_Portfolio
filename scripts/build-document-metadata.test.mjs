import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildMetadata,
  classifyDocType,
  cleanPdfTitle,
  detectLanguage,
  humanizeFilename,
  isJunkPdfTitle,
  normalizeCandidateTitle,
  normalizeDate,
} from "./build-document-metadata.mjs";

test("normalizeCandidateTitle strips CTA phrasing and rejects generic labels", () => {
  assert.equal(
    normalizeCandidateTitle("Download connector and sensor brochure"),
    "connector and sensor brochure",
  );
  assert.equal(
    normalizeCandidateTitle("Read our Omnivise T3000 SCADA whitepaper"),
    "Omnivise T3000 SCADA whitepaper",
  );
  assert.equal(
    normalizeCandidateTitle('Download your free white paper on "The internet of energy": '),
    "The internet of energy",
  );
  assert.equal(normalizeCandidateTitle("Download your free technical paper (PDF)"), "");
  assert.equal(normalizeCandidateTitle("Download"), "");
  assert.equal(normalizeCandidateTitle("Read more"), "");
  assert.equal(normalizeCandidateTitle(""), "");
});

test("PDF title junk detection and cleaning", () => {
  assert.equal(
    isJunkPdfTitle("Siemens Energy · Technical document · Letter format portrait – Template"),
    true,
  );
  assert.equal(isJunkPdfTitle("PowerPoint Presentation"), true);
  assert.equal(isJunkPdfTitle("Product Manual Template"), true);
  assert.equal(isJunkPdfTitle("Poster SGT5-4000F_210917.indd"), true);
  assert.equal(isJunkPdfTitle("Hydrogen and Power-to-X solutions"), false);
  assert.equal(
    cleanPdfTitle("Microsoft Word - Authorized Parts Resellers April 2025.docx"),
    "Authorized Parts Resellers April 2025",
  );
});

test("humanizeFilename removes scraper artifacts", () => {
  assert.equal(humanizeFilename("2023-Seal-Protect-Flyer-pdf.pdf"), "2023 Seal Protect Flyer");
  assert.equal(humanizeFilename("Flyer_3FT-pdf.pdf"), "Flyer 3FT");
  assert.equal(
    humanizeFilename("2026_05_29_DataCenter-ReferenceMap-iPDF-pdf.pdf"),
    "2026 05 29 DataCenter ReferenceMap",
  );
});

test("classifyDocType covers policies, papers, flyers and office formats", () => {
  assert.equal(classifyDocType("GFP-1 · Order Entry Policy", "a.pdf", "pdf", ["", "GFP-1", ""]), "policy");
  assert.equal(classifyDocType("Hydrogen and Power-to-X solutions", "Electrolyzer_Brochure-pdf.pdf", "pdf"), "brochure");
  assert.equal(classifyDocType("Cybersecurity whitepaper", "x.pdf", "pdf"), "white-paper");
  assert.equal(classifyDocType("Poster SGT-800", "Poster-SGT800-pdf.pdf", "pdf"), "poster");
  assert.equal(classifyDocType("Worksheet", "cylinder-heat-duty.xlsx", "xlsx"), "spreadsheet");
  assert.equal(classifyDocType("Something", "a.pdf", "pdf"), "other");
});

test("detectLanguage reads explicit markers and defaults to EN", () => {
  assert.equal(detectLanguage("Flyer", "Produktflyer-DE-pdf.pdf"), "DE");
  assert.equal(detectLanguage("Manual", "manual_EN.pdf"), "EN");
  assert.equal(detectLanguage("Flyer", "Flyer-pdf.pdf"), "EN");
});

test("normalizeDate handles table, publication and PDF date formats", () => {
  assert.equal(normalizeDate("Oct 2020"), "2020-10");
  assert.equal(normalizeDate("April 11, 2025"), "2025-04-11");
  assert.equal(normalizeDate("D:20240102093000Z"), "2024-01-02");
  assert.equal(normalizeDate("not a date"), "");
});

test("buildMetadata prefers page titles over PDF metadata and falls back sensibly", () => {
  const catalog = {
    items: [
      {
        id: "grid-products/voltage-regulators",
        bucket: "products",
        files: [
          {
            url: "https://assets.example.com/dam/28e77a7c-9ef6-496c-83c2-b05a008b7bab/JFR-pdf_Original%20file.pdf",
            filename: "JFRsingle-phaseVoltageRegulator-pdf.pdf",
            status: "live",
          },
          {
            url: "https://assets.example.com/dam/aaaaaaaa-0000-0000-0000-000000000001/Blank-pdf_Original%20file.pdf",
            filename: "2023-Seal-Protect-Flyer-pdf.pdf",
            status: "live",
          },
        ],
      },
    ],
  };
  const candidates = {
    items: {
      "grid-products/voltage-regulators": {
        dates: [],
        documents: [
          {
            uuid: "28e77a7c-9ef6-496c-83c2-b05a008b7bab",
            href: "https://assets.example.com/dam/28e77a7c/JFR-pdf_Original%20file.pdf",
            cardTitle: "JFR single-phase voltage regulator",
            anchorText: "Download",
            ariaLabel: "Download",
            tableCells: [],
          },
        ],
      },
    },
  };
  const fileMetadata = {
    assets: {
      "aaaaaaaa-0000-0000-0000-000000000001": {
        ok: true,
        pages: 3,
        title: "Seal Protect",
        firstLines: ["Seal Protect"],
        created: "",
      },
    },
  };
  const { metadata } = buildMetadata({ catalog, candidates, fileMetadata });
  assert.equal(metadata["28e77a7c-9ef6-496c-83c2-b05a008b7bab"].title, "JFR single-phase voltage regulator");
  assert.equal(metadata["28e77a7c-9ef6-496c-83c2-b05a008b7bab"].titleSource, "page");
  assert.equal(metadata["aaaaaaaa-0000-0000-0000-000000000001"].title, "Seal Protect");
  assert.equal(metadata["aaaaaaaa-0000-0000-0000-000000000001"].titleSource, "pdf-title");
  assert.equal(metadata["aaaaaaaa-0000-0000-0000-000000000001"].pages, 3);
});
