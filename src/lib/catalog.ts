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
};

export type RelatedProduct = {
  title: string;
  href?: string;
  image?: string;
  description?: string;
};

export type SpecRow =
  | { name: string; value: string }
  | Record<string, string>;

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
  specs: SpecRow[];
  faqs: { q: string; a: string }[];
  body: string;
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
  if (file.downloaded && file.publicPath) return file.publicPath;
  return file.url;
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

export function isNamedSpec(row: SpecRow): row is { name: string; value: string } {
  return "name" in row && "value" in row && Object.keys(row).length <= 4;
}

export function searchItems(items: CatalogItem[], q: string) {
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
      item.body,
      item.highlights.join(" "),
      item.files.map((f) => f.label).join(" "),
    ]
      .join(" ")
      .toLowerCase();
    return parts.every((p) => hay.includes(p));
  });
}
