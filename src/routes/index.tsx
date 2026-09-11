import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { ProductCard } from "@/components/product-card";
import { CatalogImage } from "@/components/catalog-image";
import {
  prettyFamily,
  searchItems,
  SECTOR_ORDER,
  type BodyBlock,
  type CatalogFamily,
} from "@/lib/catalog";
import {
  loadAllBodies,
  useCatalog,
} from "@/lib/catalog-store";
import { cn } from "@/lib/utils";

type Search = { q?: string; sector?: string };

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): Search => ({
    q: typeof search.q === "string" ? search.q : undefined,
    sector: typeof search.sector === "string" ? search.sector : undefined,
  }),
  component: Home,
});

function Home() {
  const { q, sector } = Route.useSearch();
  const { catalog, ready } = useCatalog();
  const [bodies, setBodies] = useState<Record<string, BodyBlock[]> | null>(null);

  // Body text lives in its own chunk: metadata results show instantly, then
  // full-text matches appear once the chunk arrives.
  useEffect(() => {
    if (!q || bodies) return;
    let active = true;
    void loadAllBodies().then((loaded) => {
      if (active) setBodies(loaded);
    });
    return () => {
      active = false;
    };
  }, [q, bodies]);

  const items = searchItems(catalog.items, q ?? "", bodies ?? undefined);
  const filtered = sector ? items.filter((i) => i.sector === sector) : items;
  const products = filtered.filter((i) => i.bucket === "products");
  const families = catalog.families.filter((f) =>
    sector ? f.sector === sector : true,
  );

  const sectors = SECTOR_ORDER.filter((s) =>
    catalog.items.some((i) => i.sector === s),
  );

  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
          Product library
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight sm:text-5xl">
          {q ? `Results for “${q}”` : "The Siemens Energy portfolio, filed."}
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted">
          {ready
            ? `${catalog.summary.counts.products} products, ${catalog.summary.counts.services} services, ${catalog.summary.counts.solutions} solutions, and ${catalog.summary.filesDiscovered} documents pulled from the public catalog — brochures, datasheets, and papers included.`
            : "Catalog data is missing."}
        </p>
        {ready ? (
          <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat n={catalog.summary.pages} label="pages" />
            <Stat n={catalog.summary.families} label="families" />
            <Stat n={catalog.summary.filesDownloaded} label="files saved" />
            <Stat n={catalog.summary.filesDiscovered} label="files found" />
          </dl>
        ) : null}
      </section>

      {sectors.length ? (
        <div className="flex gap-2 overflow-x-auto pb-1">
          <SectorChip to="/" active={!sector} label="All" />
          {sectors.map((s) => (
            <SectorChip
              key={s}
              to="/"
              search={{ sector: s, q }}
              active={sector === s}
              label={s}
            />
          ))}
        </div>
      ) : null}

      {!q && families.length ? (
        <section className="space-y-4">
          <div className="flex items-end justify-between">
            <h2 className="font-display text-2xl font-semibold">Families</h2>
            <p className="text-xs uppercase tracking-[0.14em] text-subtle">
              {families.length} groups
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {families.slice(0, 12).map((f) => (
              <FamilyRow key={f.id} family={f} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        <div className="flex items-end justify-between">
          <h2 className="font-display text-2xl font-semibold">
            {q ? "Matching entries" : "Products"}
          </h2>
          <p className="text-xs tabular-nums text-subtle">{filtered.length}</p>
        </div>
        {filtered.length === 0 ? (
          <p className="rounded-xl bg-surface px-4 py-10 text-center text-muted">
            Nothing matched that search.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(q ? filtered : products).slice(0, q ? 60 : 24).map((item) => (
              <ProductCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex flex-col-reverse rounded-lg bg-surface px-3 py-3 shadow-card">
      <dt className="text-[11px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="font-display text-2xl font-semibold tabular-nums">{n}</dd>
    </div>
  );
}

function SectorChip({
  to,
  search,
  active,
  label,
}: {
  to: string;
  search?: Search;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      to={to}
      search={search}
      className={cn(
        "shrink-0 rounded-full px-3 py-2 text-sm transition-colors",
        active ? "bg-accent text-accent-fg" : "bg-surface text-muted hover:text-fg",
      )}
    >
      {label}
    </Link>
  );
}

function FamilyRow({ family }: { family: CatalogFamily }) {
  return (
    <Link
      to="/family/$familyId"
      params={{ familyId: family.id }}
      className="flex items-center gap-3 rounded-xl bg-surface p-3 shadow-card transition-[box-shadow] duration-150 hover:shadow-card-hover"
    >
      <div className="size-14 shrink-0 overflow-hidden rounded-md bg-surface-2">
        <CatalogImage
          src={family.hero}
          alt={prettyFamily(family)}
          fit={family.heroFit === "contain" ? "contain" : "cover"}
          imgClassName={family.heroFit === "contain" ? "p-1" : undefined}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-display text-lg font-semibold leading-tight">
          {prettyFamily(family)}
        </div>
        <div className="text-xs text-muted">
          {family.count} entries · {family.sector || family.bucket}
        </div>
      </div>
      <ArrowRight className="size-4 text-subtle" />
    </Link>
  );
}
