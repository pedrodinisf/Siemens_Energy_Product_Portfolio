import { createFileRoute } from "@tanstack/react-router";
import { ProductCard } from "@/components/product-card";
import { DocumentTable } from "@/components/document-table";
import { uniqueDocuments } from "@/lib/documents";
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
  const documents = uniqueDocuments(papers);

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
          {papers.length} publication pages from the Siemens Energy library,{" "}
          {documents.length} of them with direct file links.
        </p>
      </header>

      {documents.length ? (
        <section className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">Documents</h2>
          <DocumentTable
            rows={documents}
            showProduct
            caption="White papers and technical notes"
          />
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
