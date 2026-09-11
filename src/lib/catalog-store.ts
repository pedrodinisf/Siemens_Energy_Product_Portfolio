import bundled from "@/data/catalog.json";
import type { Catalog } from "./catalog";

const catalog = bundled as Catalog;

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
