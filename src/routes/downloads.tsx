import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { FileRow } from "@/components/file-row";
import { kindLabel, type CatalogFile } from "@/lib/catalog";
import { useCatalog } from "@/lib/catalog-store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/downloads")({
  component: DownloadsPage,
});

type Row = CatalogFile & { product: string; family: string };

function DownloadsPage() {
  const { catalog } = useCatalog();
  const [kind, setKind] = useState("all");
  const [q, setQ] = useState("");

  const rows: Row[] = useMemo(() => {
    const out: Row[] = [];
    const seen = new Set<string>();
    for (const item of catalog.items) {
      for (const f of item.files) {
        const key = f.url || f.filename;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ ...f, product: item.title, family: item.familyLabel });
      }
    }
    return out;
  }, [catalog.items]);

  const kinds = useMemo(() => {
    const s = new Set(rows.map((r) => r.kind));
    return ["all", ...Array.from(s).sort()];
  }, [rows]);

  const filtered = rows.filter((r) => {
    if (kind !== "all" && r.kind !== kind) return false;
    if (!q.trim()) return true;
    const hay = `${r.label} ${r.filename} ${r.product} ${r.family}`.toLowerCase();
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
          {rows.length} unique files discovered on public Siemens Energy pages.
          Smaller files are stored in this library; larger ones open from the
          source.
        </p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter files…"
          className="h-11 flex-1 rounded-md border border-border bg-surface px-3 text-sm outline-none placeholder:text-subtle focus:border-accent"
        />
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {kinds.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(k)}
            className={cn(
              "shrink-0 rounded-full px-3 py-2 text-sm capitalize",
              kind === k ? "bg-accent text-accent-fg" : "bg-surface text-muted",
            )}
          >
            {k === "all" ? "All" : kindLabel(k)}
          </button>
        ))}
      </div>

      <p className="text-xs tabular-nums text-subtle">{filtered.length} files</p>
      <div className="grid gap-2 md:grid-cols-2">
        {filtered.slice(0, 200).map((f) => (
          <FileRow key={f.url + f.filename} file={f} />
        ))}
      </div>
    </div>
  );
}
