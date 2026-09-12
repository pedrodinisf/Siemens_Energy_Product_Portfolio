export type CatalogFile = {
  url: string;
  label: string;
  kind: string;
  filename: string;
  localPath?: string;
  publicPath?: string;
  downloaded?: boolean;
  bytes?: number;
  archiveOnly?: boolean;
  /** Enriched display metadata (see `scripts/build-document-metadata.mjs`). */
  title?: string;
  docType?: string;
  lang?: string;
  format?: string;
  titleSource?: string;
  status?: "live" | "dead";
  date?: string;
  pages?: number;
};

export type RelatedProduct = {
  title: string;
  href?: string;
  image?: string;
  description?: string;
};

export type CatalogFaq = { q: string; a: string };

/** Structured item body, cleaned by `scripts/clean-bodies.py`. */
export type BodyBlock =
  | { type: "heading"; level: 2 | 3 | 4; text: string }
  | { type: "paragraph"; text: string; bold?: string[] }
  | { type: "list"; ordered: boolean; items: string[] };

export type SpecPair = { name: string; value: string };

export type SpecMatrixRow = { label: string; values: string[] };

/** One page table, normalized by `scripts/normalize-spec-tables.py`. */
export type SpecTable =
  | { kind: "pairs"; caption?: string; rows: SpecPair[] }
  | {
      kind: "matrix";
      caption?: string;
      labelHeader: string;
      columns: string[];
      rows: SpecMatrixRow[];
    };

export type CatalogItem = {
  id: string;
  url: string;
  title: string;
  h1?: string;
  description: string;
  kind: string;
  bucket: string;
  family: string;
  familyLabel: string;
  slug: string;
  sector?: string;
  tags?: string;
  modified?: string;
  hero?: string;
  heroLocal?: string;
  heroFit?: "cover" | "contain";
  highlights: string[];
  specs: SpecTable[];
  /** Loaded lazily from `catalog-faqs.json` on item pages. */
  faqs?: CatalogFaq[];
  /** Loaded lazily from `catalog-body.json` on item/family pages and search. */
  body?: BodyBlock[];
  headings: string[];
  related: RelatedProduct[];
  files: CatalogFile[];
};

export type CatalogFamily = {
  id: string;
  label: string;
  bucket: string;
  sector?: string;
  count: number;
  products: string[];
  overview?: string;
  description?: string;
  hero?: string;
  heroFit?: "cover" | "contain";
};

export type Catalog = {
  summary: {
    source: string;
    scrapedAt: string;
    pages: number;
    families: number;
    filesDiscovered: number;
    filesDownloaded: number;
    counts: {
      products: number;
      services: number;
      solutions: number;
      publications: number;
    };
  };
  families: CatalogFamily[];
  items: CatalogItem[];
};

export const EMPTY_CATALOG: Catalog = {
  summary: {
    source: "",
    scrapedAt: "",
    pages: 0,
    families: 0,
    filesDiscovered: 0,
    filesDownloaded: 0,
    counts: { products: 0, services: 0, solutions: 0, publications: 0 },
  },
  families: [],
  items: [],
};

export function itemPath(item: Pick<CatalogItem, "family" | "slug">) {
  return `/item/${item.family}/${item.slug}`;
}

export function familyPath(id: string) {
  return `/family/${id}`;
}

export function fileHref(file: CatalogFile) {
  if (file.downloaded && file.publicPath) return assetHref(file.publicPath);
  return file.url;
}

/**
 * Resolve a root-relative asset path (e.g. `/catalog/files/x.pdf`) against the
 * Vite base. `/` on dev/Vercel, `/Siemens_Energy_Product_Portfolio/` on the
 * GitHub Pages build. Remote and protocol-relative URLs pass through untouched.
 */
export function assetHref(path?: string) {
  if (!path || !path.startsWith("/") || path.startsWith("//")) return path;
  // `?.` keeps the helper callable from plain Node (tests), where import.meta.env
  // does not exist; Vite always defines it in app builds.
  const base = import.meta.env?.BASE_URL ?? "/";
  return base.replace(/\/$/, "") + path;
}

export function prettyFamily(family: CatalogFamily | { id: string; label: string }) {
  let label = family.label || family.id;
  label = label.replace(/^Industry\s+/i, "").replace(/^Usecase\s+/i, "");
  label = label.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  return label;
}

export const SECTOR_ORDER = [
  "Generation",
  "Grid",
  "Compression",
  "Hydrogen & storage",
  "Digital",
  "Marine & subsea",
  "Services",
  "Industry solutions",
  "Use cases",
  "Publications",
  "Other products",
];

export function formatBytes(n?: number) {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function kindLabel(kind: string) {
  return kind.replace(/-/g, " ");
}

const DOC_TYPE_LABELS: Record<string, string> = {
  brochure: "Brochure",
  flyer: "Flyer",
  datasheet: "Datasheet",
  "white-paper": "White paper",
  "technical-paper": "Technical paper",
  manual: "Manual",
  poster: "Poster",
  certificate: "Certificate",
  policy: "Policy",
  article: "Article",
  "press-release": "Press release",
  "case-study": "Case study",
  catalog: "Catalog",
  presentation: "Presentation",
  spreadsheet: "Spreadsheet",
  document: "Document",
  other: "Document",
};

export function docTypeLabel(docType?: string) {
  if (!docType) return DOC_TYPE_LABELS.other;
  return DOC_TYPE_LABELS[docType] ?? docType.replace(/-/g, " ");
}

/** Flatten every spec cell into one searchable string. */
export function specText(specs: SpecTable[]) {
  return specs
    .flatMap((table) =>
      table.kind === "pairs"
        ? table.rows.flatMap((row) => [row.name, row.value])
        : [
            table.labelHeader,
            ...table.columns,
            ...table.rows.flatMap((row) => [row.label, ...row.values]),
          ],
    )
    .join(" ");
}

/** Lazily loaded per-item payload assembled from the body and FAQ chunks. */
export type ItemDetail = {
  body?: BodyBlock[];
  faqs?: CatalogFaq[];
};

/** Flatten structured body blocks into one searchable string. */
export function bodyText(blocks?: BodyBlock[]) {
  if (!blocks?.length) return "";
  return blocks
    .flatMap((block) => (block.type === "list" ? block.items : [block.text]))
    .join(" ");
}

/**
 * Search all metadata plus the lazily loaded body text when it is available;
 * callers without bodies get the fast metadata-only match set.
 */
export function searchItems(
  items: CatalogItem[],
  q: string,
  bodies?: Record<string, BodyBlock[]>,
) {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  const parts = needle.split(/\s+/).filter(Boolean);
  return items.filter((item) => {
    const hay = [
      item.title,
      item.h1,
      item.description,
      item.familyLabel,
      item.kind,
      item.slug,
      item.highlights.join(" "),
      specText(item.specs),
      item.files
        .map((f) => [f.title, f.filename, f.docType, f.lang].filter(Boolean).join(" "))
        .join(" "),
      bodyText(bodies?.[item.id]),
    ]
      .join(" ")
      .toLowerCase();
    return parts.every((p) => hay.includes(p));
  });
}
