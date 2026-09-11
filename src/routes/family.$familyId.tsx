import { createFileRoute, Link } from "@tanstack/react-router";
import { ProductCard } from "@/components/product-card";
import { FileRow } from "@/components/file-row";
import { prettyFamily } from "@/lib/catalog";
import { findFamily, findItem, useCatalog } from "@/lib/catalog-store";

export const Route = createFileRoute("/family/$familyId")({
  head: ({ params }) => {
    const family = findFamily(params.familyId);
    const overview = findItem(params.familyId, "_overview");
    const label = family
      ? prettyFamily(family)
      : params.familyId.replace(/-/g, " ");
    const description = overview?.description || family?.description;
    return {
      meta: [
        { title: `${label} · Fieldbook` },
        ...(description ? [{ name: "description", content: description }] : []),
      ],
    };
  },
  component: FamilyPage,
});

function FamilyPage() {
  const { familyId } = Route.useParams();
  const { catalog, isLoading } = useCatalog();
  const family = catalog.families.find((f) => f.id === familyId);
  const items = catalog.items.filter((i) => i.family === familyId);
  const overview = items.find((i) => i.slug === "_overview");
  const rest = items.filter((i) => i.slug !== "_overview");
  const files = items.flatMap((i) => i.files);

  if (!isLoading && items.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-muted">Family not found.</p>
        <Link to="/" className="mt-3 inline-block text-accent">
          Back to catalog
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <Link to="/" className="text-xs uppercase tracking-[0.16em] text-muted">
          Catalog
        </Link>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">
          {family ? prettyFamily(family) : familyId.replace(/-/g, " ")}
        </h1>
        {overview?.description || family?.description ? (
          <p className="mt-3 max-w-3xl text-base leading-relaxed text-muted">
            {overview?.description || family?.description}
          </p>
        ) : null}
      </div>

      {overview?.body ? (
        <article className="max-w-3xl space-y-3 text-sm leading-relaxed text-muted">
          {overview.body.split("\n\n").slice(0, 6).map((p) => (
            <p key={p.slice(0, 40)}>{p}</p>
          ))}
        </article>
      ) : null}

      {rest.length ? (
        <section className="space-y-4">
          <h2 className="font-display text-2xl font-semibold">In this family</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rest.map((item) => (
              <ProductCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ) : items.length === 1 && overview ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ProductCard item={overview} />
        </div>
      ) : null}

      {files.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Documents</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {files.slice(0, 24).map((f) => (
              <FileRow key={f.url} file={f} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
