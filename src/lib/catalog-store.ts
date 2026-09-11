import bundled from "@/data/catalog-index.json";
import type { Catalog, CatalogFaq, ItemDetail } from "./catalog";

const catalog = bundled as Catalog;

export type { ItemDetail } from "./catalog";

/**
 * `body`/`faqs` are about half the catalog and live in their own chunks, loaded
 * on demand. Split in two so full-text search only downloads the body text;
 * item pages fetch both in parallel. The promises are memoized so every
 * consumer shares one fetch per chunk.
 */
let bodyPromise: Promise<Record<string, string>> | null = null;
let faqsPromise: Promise<Record<string, CatalogFaq[]>> | null = null;

export function loadAllBodies(): Promise<Record<string, string>> {
  bodyPromise ??= import("@/data/catalog-body.json").then(
    (module) => module.default as Record<string, string>,
  );
  return bodyPromise;
}

export function loadAllFaqs(): Promise<Record<string, CatalogFaq[]>> {
  faqsPromise ??= import("@/data/catalog-faqs.json").then(
    (module) => module.default as Record<string, CatalogFaq[]>,
  );
  return faqsPromise;
}

export async function loadItemBody(id: string): Promise<string | undefined> {
  return (await loadAllBodies())[id];
}

export async function loadItemDetail(id: string): Promise<ItemDetail | undefined> {
  const [bodies, faqs] = await Promise.all([loadAllBodies(), loadAllFaqs()]);
  if (!bodies[id] && !faqs[id]) return undefined;
  return { body: bodies[id], faqs: faqs[id] };
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
