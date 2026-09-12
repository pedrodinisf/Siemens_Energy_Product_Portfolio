import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { DocumentTable } from "@/components/document-table";
import { docTypeLabel } from "@/lib/catalog";
import { documentSource, uniqueDocuments } from "@/lib/documents";
import { useCatalog } from "@/lib/catalog-store";

export const Route = createFileRoute("/downloads")({
  component: DownloadsPage,
});

function DownloadsPage() {
  const { catalog } = useCatalog();
  const [q, setQ] = useState("");
  const [docType, setDocType] = useState("all");
  const [lang, setLang] = useState("all");
  const [source, setSource] = useState("all");

  const rows = useMemo(
    () =>
      uniqueDocuments(catalog.items).sort((a, b) => a.title.localeCompare(b.title)),
    [catalog.items],
  );
  const types = useMemo(
    () => [...new Set(rows.map((r) => r.docType))].sort(),
    [rows],
  );
  const langs = useMemo(() => [...new Set(rows.map((r) => r.lang))].sort(), [rows]);

  const filtered = rows.filter((row) => {
    if (docType !== "all" && row.docType !== docType) return false;
    if (lang !== "all" && row.lang !== lang) return false;
    if (source !== "all" && documentSource(row) !== source) return false;
    if (!q.trim()) return true;
    const hay =
      `${row.title} ${row.owner?.title ?? ""} ${row.format} ${row.docType}`.toLowerCase();
    return hay.includes(q.trim().toLowerCase());
  });

  return (
    <div className="space-y-6">
      <header>
        <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
          Documents
        </p>
        <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight">
          Brochures, papers, datasheets
        </h1>
        <p className="mt-3 max-w-2xl text-muted">
          {rows.length} unique documents discovered on public Siemens Energy
          pages. Smaller files are stored in this library; larger ones open from
          the source.
        </p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter documents…"
          aria-label="Filter documents"
          className="h-11 flex-1 rounded-md border border-border bg-surface px-3 text-sm outline-none placeholder:text-subtle focus:border-accent"
        />
        <select
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          aria-label="Filter by document type"
          className="h-11 rounded-md border border-border bg-surface px-3 text-sm text-muted outline-none focus:border-accent"
        >
          <option value="all">All types</option>
          {types.map((type) => (
            <option key={type} value={type}>
              {docTypeLabel(type)}
            </option>
          ))}
        </select>
        <select
          value={lang}
          onChange={(e) => setLang(e.target.value)}
          aria-label="Filter by language"
          className="h-11 rounded-md border border-border bg-surface px-3 text-sm text-muted outline-none focus:border-accent"
        >
          <option value="all">All languages</option>
          {langs.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          aria-label="Filter by source"
          className="h-11 rounded-md border border-border bg-surface px-3 text-sm text-muted outline-none focus:border-accent"
        >
          <option value="all">All sources</option>
          <option value="local">Saved locally</option>
          <option value="cdn">Siemens Energy</option>
          <option value="unavailable">Unavailable</option>
        </select>
      </div>

      <p className="text-xs tabular-nums text-subtle">
        {filtered.length} document{filtered.length === 1 ? "" : "s"}
      </p>

      {filtered.length ? (
        <DocumentTable rows={filtered} showProduct caption="All documents" />
      ) : (
        <p className="rounded-xl bg-surface px-4 py-10 text-center text-muted">
          Nothing matched those filters.
        </p>
      )}
    </div>
  );
}
