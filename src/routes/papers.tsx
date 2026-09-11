import { createFileRoute } from "@tanstack/react-router";
import { ProductCard } from "@/components/product-card";
import { FileRow } from "@/components/file-row";
import { useCatalog } from "@/lib/catalog-store";

export const Route = createFileRoute("/papers")({
  component: PapersPage,
});

function PapersPage() {
  const { catalog } = useCatalog();
  const papers = catalog.items.filter(
    (i) =>
      i.bucket === "publications" ||
      i.kind === "white-paper" ||
      i.kind === "technical-paper",
  );
  const files = papers.flatMap((p) => p.files);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
          Research
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">
          White papers & technical notes
        </h1>
        <p className="mt-3 max-w-2xl text-muted">
          {papers.length} publication pages from the Siemens Energy library,
          with direct file links where the site published them.
        </p>
      </header>

      {files.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Files</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {files.slice(0, 40).map((f) => (
              <FileRow key={f.url} file={f} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        <h2 className="font-display text-2xl font-semibold">Pages</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {papers.map((item) => (
            <ProductCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </div>
  );
}
