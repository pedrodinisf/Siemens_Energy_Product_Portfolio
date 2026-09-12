#!/usr/bin/env node
/**
 * Merge everything known about each document into `src/data/document-metadata.json`
 * and enrich the file records in `src/data/catalog.json`.
 *
 * Title priority:
 *   page card/anchor title -> policy table row -> PDF /Title -> publication
 *   item title -> PDF first page -> humanised filename -> "{item title} — {type}"
 *
 * Also derives document type, language (explicit markers only), publication /
 * policy dates and page counts. Run after `scripts/refetch-documents.py` and
 * `scripts/fetch-document-metadata.py`; finishes with `catalog:split`.
 *
 *   node scripts/build-document-metadata.mjs [--no-split]
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CATALOG = join(ROOT, "src", "data", "catalog.json");
const SIDECAR = join(ROOT, "src", "data", "document-metadata.json");
const DATA_DIR = join(ROOT, "data", "siemens-energy");

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const GENERIC_TITLE =
  /^(download|downloads|read more|read our|view|view more|open|click here|learn more|learn more about|find out more|find out more about|explore|explore more|discover|discover more|more info|more information|request|see more|all downloads|downloads?|pdf|en|de)(\s+(our|the|a|an|this)\b.*)?$/i;
const DOC_TYPE_ONLY =
  /^(whitepaper|white paper|brochure|flyer|datasheet|data sheet|factsheet|fact sheet|poster|manual|presentation|document|pdf|interactive pdf)$/i;
const FREE_PAPER_CTA =
  /^your free (?:white|technical) paper(?:\s+on)?\s*(.*)$/i;
const QUOTED_TITLE = /[“"'](.+?)[”"']\s*:?\s*$/;
const CTA_PREFIX =
  /^(download|read|view|open|get|see|request)\s+(our|the|a|an)?\s*/i;
const CTA_LEARN = /^(learn more about|find out more about|explore|discover)\s+/i;
const JUNK_PDF_TITLE =
  /^(untitled|powerpoint presentation|presentation|microsoft word|microsoft powerpoint|product manual template|technical documentation|technical document|documentation|layout\s*\d*|slide\s*\d*|title chart.*|document\d*|pdf|screenshot.*|page\s*\d+)$/i;
const TEMPLATE_MARKERS = /technical document\s*·|– template|— template|\btemplate\b/i;
const FILE_EXT_RE = /\.(pdf|pptx|ppt|xlsx|xls|docx|doc|zip)$/i;
const LANGUAGE_TOKENS =
  /(?:^|[^A-Za-z0-9])(EN|DE|PT|ES|FR|IT|NL|PL|RU|ZH|JA|KO|TR|AR|NO|SV|DA|FI|CS|HU|RO|BG|EL)(?=[^A-Za-z0-9]|$)/;
const LANGUAGE_WORDS = [
  [/\b(german|deutsch)\b/i, "DE"],
  [/\b(english|englisch)\b/i, "EN"],
  [/\b(french|français|francais)\b/i, "FR"],
  [/\b(spanish|español|espanol)\b/i, "ES"],
  [/\b(portuguese|português|portugues)\b/i, "PT"],
  [/\b(italian|italiano)\b/i, "IT"],
  [/\b(dutch|nederlands)\b/i, "NL"],
  [/\b(chinese|mandarin)\b/i, "ZH"],
  [/\b(japanese)\b/i, "JA"],
  [/\b(korean)\b/i, "KO"],
  [/\b(polish|polski)\b/i, "PL"],
  [/\b(russian)\b/i, "RU"],
  [/\b(turkish|türkçe)\b/i, "TR"],
  [/\b(arabic)\b/i, "AR"],
  [/\b(norwegian|norsk)\b/i, "NO"],
  [/\b(swedish|svenska)\b/i, "SV"],
  [/\b(danish|dansk)\b/i, "DA"],
  [/\b(finnish|suomi)\b/i, "FI"],
];
const MONTHS = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4,
  may: 5, jun: 6, june: 6, jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9,
  september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
};

export function normalizeCandidateTitle(value) {
  const original = (value || "")
    .replace(/\s+/g, " ")
    .replace(/^[\s·•\-–—:]+|[\s·•\-–—:]+$/g, "")
    .trim();
  if (!original) return "";
  if (GENERIC_TITLE.test(original) || DOC_TYPE_ONLY.test(original)) return "";
  let title = original.replace(CTA_PREFIX, "").replace(CTA_LEARN, "").trim();
  title = title.replace(/\s*\((?:pdf|pptx|docx|xlsx)\)\s*$/i, "").trim();
  const freePaper = title.match(FREE_PAPER_CTA);
  if (freePaper) {
    const quoted = freePaper[1].match(QUOTED_TITLE);
    if (!quoted) return "";
    title = quoted[1].replace(/[”"':\s]+$/g, "").trim();
  }
  title = title.replace(/[:\s]+$/g, "").trim();
  if (title.length < 3 || GENERIC_TITLE.test(title) || DOC_TYPE_ONLY.test(title)) return "";
  return title;
}

export function isJunkPdfTitle(value) {
  let title = (value || "").replace(/\s+/g, " ").trim();
  if (!title) return true;
  title = title
    .replace(/^microsoft word\s*[-–]\s*/i, "")
    .replace(/^microsoft powerpoint\s*[-–]\s*/i, "")
    .trim();
  if (JUNK_PDF_TITLE.test(title)) return true;
  if (TEMPLATE_MARKERS.test(title)) return true;
  if (FILE_EXT_RE.test(title)) return true;
  if (/\.indd$/i.test(title)) return true;
  if (title.length > 160) return true;
  return false;
}

export function cleanPdfTitle(value) {
  let title = (value || "").replace(/\s+/g, " ").trim();
  title = title
    .replace(/^microsoft word\s*[-–]\s*/i, "")
    .replace(/^microsoft powerpoint\s*[-–]\s*/i, "")
    .trim();
  title = title.replace(/\.(indd|docx|pptx|pdf)$/i, "").trim();
  return title;
}

export function humanizeFilename(filename) {
  let name = (filename || "").replace(/\.[a-z0-9]{2,5}$/i, "");
  name = name.replace(/[_ ]original[_ ]file/gi, "");
  name = name.replace(/[-_]+/g, " ");
  name = name.replace(/\s*\bpdf\b\s*$/i, "");
  name = name.replace(/\s*\biPDF\b/gi, "");
  name = name.replace(/\s{2,}/g, " ").trim();
  name = name.replace(/^[\s\-_.]+|[\s\-_.]+$/g, "");
  if (/[a-z][A-Z]/.test(name) && !/\s/.test(name)) {
    name = name.replace(/([a-z])([A-Z])/g, "$1 $2");
  }
  return name;
}

export function classifyDocType(title, filename, format, tableCells = []) {
  if (tableCells.some((cell) => /^GFP[-\s]?\d+/i.test(cell)) || /\bpolicy\b/i.test(title)) {
    return "policy";
  }
  const hay = `${title} ${filename}`;
  const rules = [
    ["white-paper", /white[\s-]?paper/i],
    ["technical-paper", /technical[\s-]?paper|tech[\s-]?paper/i],
    ["datasheet", /data[\s-]?sheet|fact[\s-]?sheet|one[\s-]?pager|techn(?:ical)?[-\s]?data/i],
    ["brochure", /brochure|broschure|broschüre|portfolio presentation|portfolio/i],
    ["flyer", /flyer|leaflet/i],
    ["manual", /manual|operating instructions|installations|installation|bedienung|handbook/i],
    ["poster", /poster/i],
    ["certificate", /certificate|certificat|tüv|tuev/i],
    ["case-study", /case[\s-]?study|success story|\breference\b/i],
    ["article", /article|magazine|interview|column|journal|review/i],
    ["press-release", /press[\s-]?release|press information|news release/i],
    ["catalog", /catalog|catalogue/i],
    ["presentation", /presentation|slides|slide deck/i],
  ];
  for (const [type, pattern] of rules) {
    if (pattern.test(hay)) return type;
  }
  if (format === "xlsx" || format === "xls") return "spreadsheet";
  if (format === "docx" || format === "doc") return "document";
  return "other";
}

export function detectLanguage(title, filename) {
  for (const [pattern, code] of LANGUAGE_WORDS) {
    if (title && pattern.test(title)) return code;
  }
  const fileToken = (filename || "").match(LANGUAGE_TOKENS);
  if (fileToken) return fileToken[1].toUpperCase();
  return "EN";
}

/** Drop a trailing language code that duplicates the language column. */
export function stripLanguageSuffix(title, lang) {
  if (!title || lang === "EN") return title;
  const stripped = title
    .replace(new RegExp(`\\s*[-–(]?\\s*${lang}\\)?\\s*$`, "i"), "")
    .trim();
  return stripped.length >= 3 ? stripped : title;
}

export function normalizeDate(value) {
  const text = (value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  let match = text.match(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/);
  if (match) {
    return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
  }
  match = text.match(/\b(\d{4})-(\d{1,2})\b/);
  if (match) return `${match[1]}-${match[2].padStart(2, "0")}`;
  match = text.match(/\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b/);
  if (match && MONTHS[match[1].toLowerCase()]) {
    return `${match[3]}-${String(MONTHS[match[1].toLowerCase()]).padStart(2, "0")}-${match[2].padStart(2, "0")}`;
  }
  match = text.match(/\b([A-Za-z]{3,9})\s+(\d{4})\b/);
  if (match && MONTHS[match[1].toLowerCase()]) {
    return `${match[2]}-${String(MONTHS[match[1].toLowerCase()]).padStart(2, "0")}`;
  }
  match = text.match(/D:(\d{4})(\d{2})(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  return "";
}

function firstPageTitle(lines, filename) {
  const skip = /^(siemens energy|www\.|page\s*\d|figure|table|\d+$)/i;
  for (const line of lines || []) {
    const text = cleanPdfTitle(line);
    if (text.length < 4 || text.length > 120) continue;
    if (skip.test(text)) continue;
    if (text.split(/\s+/).length > 14) continue;
    if (isJunkPdfTitle(text)) continue;
    if (filename && text.toLowerCase() === filename.toLowerCase()) continue;
    return text;
  }
  return "";
}

function policyFromTable(cells) {
  const values = cells || [];
  const numberIndex = values.findIndex((cell) => /^GFP[-\s]?\d+/i.test(cell));
  if (numberIndex < 0) return { title: "", date: "" };
  const number = values[numberIndex].replace(/\s+/g, "").toUpperCase();
  const description = values.find(
    (cell, index) => index !== numberIndex && cell.trim().length > 2 && !/^\d+$/.test(cell),
  );
  const date = values.map(normalizeDate).find(Boolean) || "";
  const title = description ? `${number} · ${description}` : number;
  return { title, date };
}

export function buildMetadata({ catalog, candidates, fileMetadata }) {
  const byAsset = new Map();
  for (const item of catalog.items) {
    for (const file of item.files) {
      const key = (file.url.match(UUID_RE)?.[0] || file.url).toLowerCase();
      if (!byAsset.has(key)) {
        byAsset.set(key, { key, item, file, owners: [], candidateDocs: [], rows: [] });
      }
      const entry = byAsset.get(key);
      if (!entry.owners.includes(item)) entry.owners.push(item);
      entry.rows.push(file);
    }
  }

  for (const [itemId, page] of Object.entries(candidates?.items || {})) {
    for (const doc of page.documents || []) {
      const key = (doc.uuid || doc.href.split("?")[0]).toLowerCase();
      const entry = byAsset.get(key);
      if (entry) entry.candidateDocs.push({ ...doc, itemId });
    }
  }

  const metadata = {};
  const report = { titleSource: {}, docType: {}, lang: {}, unresolved: [], duplicates: new Map() };

  for (const entry of byAsset.values()) {
    const { file } = entry;
    const key = entry.key;
    const format = (file.filename.match(/\.([a-z0-9]+)$/i)?.[1] || "file").toLowerCase();
    const pdf = fileMetadata?.assets?.[key] || {};
    const rawPageTitles = entry.candidateDocs
      .map((doc) => doc.cardTitle)
      .filter(Boolean)
      .join(" | ");
    const lang = detectLanguage(rawPageTitles, file.filename);

    // 1) policy table row
    let title = "";
    let date = "";
    let titleSource = "";
    for (const doc of entry.candidateDocs) {
      const policy = policyFromTable(doc.tableCells);
      if (policy.title) {
        title = policy.title;
        date = policy.date;
        titleSource = "table";
        break;
      }
    }

    // 2) card / anchor titles from the source pages
    if (!title) {
      const counted = new Map();
      for (const doc of entry.candidateDocs) {
        for (const value of [doc.cardTitle, doc.ariaLabel, doc.anchorText]) {
          const normalized = normalizeCandidateTitle(value);
          if (!normalized) continue;
          counted.set(normalized, (counted.get(normalized) || 0) + 1);
        }
      }
      const ranked = [...counted.entries()].sort(
        (a, b) => b[1] - a[1] || b[0].length - a[0].length || a[0].localeCompare(b[0]),
      );
      if (ranked.length) {
        title = ranked[0][0];
        titleSource = "page";
      }
    }

    // 3) PDF /Title
    if (!title && pdf.ok && pdf.title && !isJunkPdfTitle(pdf.title)) {
      title = cleanPdfTitle(pdf.title);
      titleSource = "pdf-title";
    }

    // 4) first page
    if (!title && pdf.ok) {
      title = firstPageTitle(pdf.firstLines, file.filename);
      if (title) titleSource = "pdf-first-page";
    }

    // 5) filename
    if (!title) {
      title = humanizeFilename(file.filename);
      titleSource = "filename";
    }

    // Publication pages are titled by the site; keep the page title only when
    // it extends that title ("Grid stabilization" -> "Grid stabilization
    // brochure"), otherwise the curated item title wins ("Prevent detect
    // react" -> "Pretact EcoSafeT").
    const publication = entry.owners.find((owner) => owner.bucket === "publications");
    if (publication) {
      const itemTitle = publication.title
        .replace(/^(?:white|technical)\s+paper:\s*/i, "")
        .trim();
      if (
        itemTitle.length > 4 &&
        !title.toLowerCase().startsWith(itemTitle.toLowerCase())
      ) {
        title = itemTitle;
        titleSource = "item-title";
      }
    }

    // A bare document number ("HHHO1471") is weaker than the descriptive
    // filename it prefixes ("HHHO1471 14 00 DDV Cylinder Outline").
    const filenameTitle = humanizeFilename(file.filename);
    if (
      title.split(/\s+/).length <= 2 &&
      filenameTitle.toLowerCase().startsWith(title.toLowerCase()) &&
      filenameTitle.length > title.length + 6
    ) {
      title = filenameTitle;
      titleSource = "filename-detail";
    }

    // doc type / language / date
    title = stripLanguageSuffix(title, lang);
    const tableCells = entry.candidateDocs.find((doc) => policyFromTable(doc.tableCells).title)?.tableCells || [];
    const typeHaystack = `${file.filename} ${
      publication ? publication.title : ""
    }`;
    const docType = classifyDocType(title, typeHaystack, format, tableCells);
    if (!date) {
      const pageDate = entry.candidateDocs
        .flatMap((doc) => candidates?.items?.[doc.itemId]?.dates || [])
        .map(normalizeDate)
        .find(Boolean);
      if (pageDate && entry.item.bucket === "publications") date = pageDate;
    }
    if (!date && pdf.ok && pdf.created && ["white-paper", "technical-paper"].includes(docType)) {
      date = normalizeDate(pdf.created);
    }
    const pages = pdf.ok && typeof pdf.pages === "number" ? pdf.pages : null;

    if (!entry.candidateDocs.length && titleSource === "filename") {
      report.unresolved.push(`${key} ${file.filename}`);
    }
    if (title) {
      const owners = report.duplicates.get(title) || 0;
      report.duplicates.set(title, owners + 1);
    }
    report.titleSource[titleSource] = (report.titleSource[titleSource] || 0) + 1;
    report.docType[docType] = (report.docType[docType] || 0) + 1;
    report.lang[lang] = (report.lang[lang] || 0) + 1;

    metadata[key] = {
      title,
      docType,
      lang,
      date: date || undefined,
      pages: pages || undefined,
      format,
      titleSource,
    };
  }

  return { metadata, report };
}

function main() {
  const noSplit = process.argv.includes("--no-split");
  const catalog = JSON.parse(readFileSync(CATALOG, "utf8"));
  const candidates = existsSync(join(DATA_DIR, "document-candidates.json"))
    ? JSON.parse(readFileSync(join(DATA_DIR, "document-candidates.json"), "utf8"))
    : { items: {} };
  const fileMetadata = existsSync(join(DATA_DIR, "document-file-metadata.json"))
    ? JSON.parse(readFileSync(join(DATA_DIR, "document-file-metadata.json"), "utf8"))
    : { assets: {} };

  const { metadata, report } = buildMetadata({ catalog, candidates, fileMetadata });
  writeFileSync(
    SIDECAR,
    JSON.stringify({ generatedAt: new Date().toISOString(), assets: metadata }),
  );

  let enriched = 0;
  for (const item of catalog.items) {
    for (const file of item.files) {
      const key = (file.url.match(UUID_RE)?.[0] || file.url).toLowerCase();
      const meta = metadata[key];
      if (!meta) continue;
      file.title = meta.title;
      file.docType = meta.docType;
      file.lang = meta.lang;
      file.format = meta.format;
      file.titleSource = meta.titleSource;
      if (meta.date) file.date = meta.date;
      else delete file.date;
      if (meta.pages) file.pages = meta.pages;
      else delete file.pages;
      enriched += 1;
    }
  }

  // The summary reports unique assets now that duplicates are collapsed.
  const assetKeys = new Set();
  const localPaths = new Set();
  for (const item of catalog.items) {
    for (const file of item.files) {
      assetKeys.add((file.url.match(UUID_RE)?.[0] || file.url).toLowerCase());
      if (file.downloaded && file.publicPath) localPaths.add(file.publicPath);
    }
  }
  catalog.summary.filesDiscovered = assetKeys.size;
  catalog.summary.filesDownloaded = localPaths.size;

  writeFileSync(CATALOG, JSON.stringify(catalog));

  if (!noSplit) {
    execFileSync("node", [join(ROOT, "scripts", "split-catalog.mjs")], {
      stdio: "inherit",
    });
  }

  const duplicateTitles = [...report.duplicates.values()].filter((n) => n > 1).length;
  console.log(`[doc-meta] ${enriched} rows enriched, ${Object.keys(metadata).length} assets catalogued`);
  console.log(`[doc-meta] title sources: ${JSON.stringify(report.titleSource)}`);
  console.log(`[doc-meta] types: ${JSON.stringify(report.docType)}`);
  console.log(`[doc-meta] languages: ${JSON.stringify(report.lang)}`);
  console.log(`[doc-meta] filename-only titles: ${report.unresolved.length}, duplicate titles: ${duplicateTitles}`);
  console.log("[doc-meta] wrote src/data/document-metadata.json");
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isCli) main();
