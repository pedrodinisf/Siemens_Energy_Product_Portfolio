import { createFileRoute, Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { FileRow } from "@/components/file-row";
import { ProductCard } from "@/components/product-card";
import { CatalogImage } from "@/components/catalog-image";
import { SpecTable } from "@/components/spec-table";
import { kindLabel } from "@/lib/catalog";
import { findItem, useItem } from "@/lib/catalog-store";

export const Route = createFileRoute("/item/$family/$slug")({
  head: ({ params }) => {
    const item = findItem(params.family, params.slug);
    return {
      meta: [
        { title: item ? `${item.title} · Fieldbook` : "Fieldbook" },
        ...(item?.description
          ? [{ name: "description", content: item.description }]
          : []),
      ],
    };
  },
  component: ItemPage,
});

function ItemPage() {
  const { family, slug } = Route.useParams();
  const { item, catalog, isLoading } = useItem(family, slug);

  if (!item) {
    return (
      <div className="py-16 text-center">
        <p className="text-muted">{isLoading ? "Loading…" : "Entry not found."}</p>
        <Link to="/" className="mt-3 inline-block text-accent">
          Back to catalog
        </Link>
      </div>
    );
  }

  const siblings = catalog.items
    .filter((i) => i.family === item.family && i.id !== item.id)
    .slice(0, 3);
  const img = item.heroLocal;

  return (
    <article className="space-y-10">
      <header className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted">
            <Link to="/" className="hover:text-fg">
              Catalog
            </Link>
            <span>/</span>
            <Link
              to="/family/$familyId"
              params={{ familyId: item.family }}
              className="hover:text-fg"
            >
              {item.familyLabel}
            </Link>
          </div>
          <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.18em] text-accent">
            {kindLabel(item.kind)} · {item.sector}
          </p>
          <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight sm:text-5xl">
            {item.title}
          </h1>
          {item.description ? (
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted">
              {item.description}
            </p>
          ) : null}
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="mt-5 inline-flex h-11 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-accent-fg"
          >
            View on Siemens Energy
            <ExternalLink className="size-4" />
          </a>
        </div>
        {img ? (
          <div className="overflow-hidden rounded-xl bg-surface shadow-card">
            <div className="aspect-[16/10]">
              <CatalogImage
                src={img}
                alt={item.title}
                fit={item.heroFit === "contain" ? "contain" : "cover"}
              />
            </div>
          </div>
        ) : null}
      </header>

      {item.specs.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Technical data</h2>
          <SpecTable specs={item.specs} />
        </section>
      ) : null}

      {item.files.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Downloads</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {item.files.map((f) => (
              <FileRow key={f.url + f.filename} file={f} />
            ))}
          </div>
        </section>
      ) : null}

      {item.body ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Overview</h2>
          <div className="max-w-3xl space-y-3 text-sm leading-relaxed text-muted">
            {item.body.split("\n\n").map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </section>
      ) : null}

      {item.faqs.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">FAQ</h2>
          <div className="space-y-2">
            {item.faqs.map((f) => (
              <details
                key={f.q}
                className="rounded-xl bg-surface px-4 py-3 shadow-card"
              >
                <summary className="cursor-pointer font-medium">{f.q}</summary>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      ) : null}

      {siblings.length ? (
        <section className="space-y-4">
          <h2 className="font-display text-2xl font-semibold">Same family</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {siblings.map((s) => (
              <ProductCard key={s.id} item={s} />
            ))}
          </div>
        </section>
      ) : null}
    </article>
  );
}
