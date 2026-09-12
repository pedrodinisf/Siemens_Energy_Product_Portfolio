import {
  fileHref,
  type CatalogFile,
  type CatalogItem,
} from "./catalog";

export type DocumentOwner = { title: string; family: string; slug: string };

export type DocumentRow = {
  key: string;
  id: string;
  title: string;
  docType: string;
  lang: string;
  date?: string;
  pages?: number;
  bytes?: number;
  format: string;
  status: "live" | "dead";
  local: boolean;
  href?: string;
  owner?: DocumentOwner;
};

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export function documentKey(file: CatalogFile) {
  return (file.url.match(UUID_RE)?.[0] ?? file.url).toLowerCase();
}

export function toDocumentRow(file: CatalogFile, owner?: DocumentOwner): DocumentRow {
  const key = documentKey(file);
  const live = file.status !== "dead";
  return {
    key,
    id: `${owner ? `${owner.family}/${owner.slug}/` : ""}${key}`,
    title: file.title || file.label || file.filename,
    docType: file.docType || "other",
    lang: file.lang || "EN",
    date: file.date,
    pages: file.pages,
    bytes: file.bytes,
    format: (file.format || "pdf").toUpperCase(),
    status: live ? "live" : "dead",
    local: Boolean(file.downloaded && file.publicPath),
    href: live ? fileHref(file) : undefined,
    owner,
  };
}

/** One row per asset within a single item, in page order. */
export function itemDocuments(item: CatalogItem): DocumentRow[] {
  const seen = new Set<string>();
  const rows: DocumentRow[] = [];
  for (const file of item.files) {
    const key = documentKey(file);
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(
      toDocumentRow(file, {
        title: item.title,
        family: item.family,
        slug: item.slug,
      }),
    );
  }
  return rows;
}

/** One row per asset across many items; the first owner wins. */
export function uniqueDocuments(items: CatalogItem[]): DocumentRow[] {
  const seen = new Map<string, DocumentRow>();
  for (const item of items) {
    for (const file of item.files) {
      const key = documentKey(file);
      if (seen.has(key)) continue;
      seen.set(
        key,
        toDocumentRow(file, {
          title: item.title,
          family: item.family,
          slug: item.slug,
        }),
      );
    }
  }
  return [...seen.values()];
}

export function documentSource(row: DocumentRow): "local" | "cdn" | "unavailable" {
  if (row.status === "dead") return "unavailable";
  return row.local ? "local" : "cdn";
}
