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
  const item = catalog.items.find((i) => i.family === family && i.slug === slug);
  const familyMeta = catalog.families.find((f) => f.id === family);
  return { item, familyMeta, catalog, ready, isLoading };
}
