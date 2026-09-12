import { createFileRoute, Link } from "@tanstack/react-router";
import { BodyBlocks } from "@/components/body-blocks";
import { ProductCard } from "@/components/product-card";
import { DocumentTable } from "@/components/document-table";
import { prettyFamily } from "@/lib/catalog";
import { itemDocuments } from "@/lib/documents";
import {
  findFamily,
  findItem,
  loadItemBody,
  useCatalog,
} from "@/lib/catalog-store";

export const Route = createFileRoute("/family/$familyId")({
  loader: async ({ params }) => {
    const overview = findItem(params.familyId, "_overview");
    return overview ? await loadItemBody(overview.id) : undefined;
  },
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
  const overviewBody = Route.useLoaderData();
  const { catalog, isLoading } = useCatalog();
  const family = catalog.families.find((f) => f.id === familyId);
  const items = catalog.items.filter((i) => i.family === familyId);
  const overview = items.find((i) => i.slug === "_overview");
  const rest = items.filter((i) => i.slug !== "_overview");
  const docGroups = [
    ...(overview && overview.files.length
      ? [{ owner: overview, label: "Family overview" }]
      : []),
    ...rest
      .filter((i) => i.files.length)
      .map((i) => ({ owner: i, label: i.title })),
  ];

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

      {overviewBody?.length ? <BodyBlocks blocks={overviewBody} max={6} /> : null}

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

      {docGroups.length ? (
        <section className="space-y-6">
          <h2 className="font-display text-2xl font-semibold">Documents</h2>
          {docGroups.map(({ owner, label }) => {
            const rows = itemDocuments(owner);
            return (
              <div key={owner.id} className="space-y-2">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="font-display text-lg font-semibold">
                    <Link
                      to="/item/$family/$slug"
                      params={{ family: owner.family, slug: owner.slug }}
                      className="hover:text-accent"
                    >
                      {label}
                    </Link>
                  </h3>
                  <span className="text-xs tabular-nums text-subtle">
                    {rows.length} document{rows.length === 1 ? "" : "s"}
                  </span>
                </div>
                <DocumentTable
                  rows={rows}
                  caption={`Documents for ${label}`}
                />
              </div>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}
