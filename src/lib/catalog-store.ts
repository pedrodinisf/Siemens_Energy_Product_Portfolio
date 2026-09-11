import bundled from "@/data/catalog-index.json";
import type { Catalog, ItemDetail } from "./catalog";

const catalog = bundled as Catalog;

export type { ItemDetail } from "./catalog";

let detailPromise: Promise<Record<string, ItemDetail>> | null = null;

/**
 * `body`/`faqs` are about half the catalog and live in their own chunk, loaded
 * by item/family pages and by full-text search. The promise is memoized so
 * every consumer shares a single fetch.
 */
export async function loadAllDetails(): Promise<Record<string, ItemDetail>> {
  detailPromise ??= import("@/data/catalog-detail.json").then(
    (module) => module.default as Record<string, ItemDetail>,
  );
  return detailPromise;
}

export async function loadItemDetail(id: string): Promise<ItemDetail | undefined> {
  return (await loadAllDetails())[id];
}

export function useCatalog() {
  const ready = catalog.items.length > 0;
  return {
    catalog,
    isLoading: false,
    isError: false,
    ready,
  };
}

export function useItem(family: string, slug: string) {
  const { catalog, ready, isLoading } = useCatalog();
  const item = findItem(family, slug);
  const familyMeta = findFamily(family);
  return { item, familyMeta, catalog, ready, isLoading };
}

/** Non-hook lookups for route `head()` and loaders. */
export function findItem(family: string, slug: string) {
  return catalog.items.find((i) => i.family === family && i.slug === slug);
}

export function findFamily(id: string) {
  return catalog.families.find((f) => f.id === id);
}
