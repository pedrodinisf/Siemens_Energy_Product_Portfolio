import { Link } from "@tanstack/react-router";
import { ExternalLink, FileText } from "lucide-react";
import { docTypeLabel, formatBytes } from "@/lib/catalog";
import { documentSource, type DocumentRow } from "@/lib/documents";
import { cn } from "@/lib/utils";

export function DocumentTable({
  rows,
  showProduct = false,
  caption,
}: {
  rows: DocumentRow[];
  showProduct?: boolean;
  caption: string;
}) {
  const withDate = rows.some((row) => row.date);
  return (
    <div className="overflow-x-auto rounded-xl bg-surface shadow-card">
      <table className="w-full min-w-[680px] border-separate border-spacing-0 text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-[11px] uppercase tracking-[0.14em] text-subtle">
            <th
              scope="col"
              className="sticky left-0 z-10 border-b border-border bg-surface px-4 py-3 font-medium"
            >
              Document
            </th>
            <th scope="col" className="border-b border-border px-3 py-3 font-medium">
              Type
            </th>
            <th scope="col" className="border-b border-border px-3 py-3 font-medium">
              Lang
            </th>
            {withDate ? (
              <th scope="col" className="border-b border-border px-3 py-3 font-medium">
                Date
              </th>
            ) : null}
            <th scope="col" className="border-b border-border px-3 py-3 font-medium">
              Size
            </th>
            <th scope="col" className="border-b border-border px-3 py-3 font-medium">
              Source
            </th>
            {showProduct ? (
              <th scope="col" className="border-b border-border px-3 py-3 font-medium">
                Product
              </th>
            ) : null}
            <th
              scope="col"
              className="border-b border-border px-4 py-3 text-right font-medium"
            >
              Open
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <DocumentTableRow
              key={row.id}
              row={row}
              withDate={withDate}
              showProduct={showProduct}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentTableRow({
  row,
  withDate,
  showProduct,
}: {
  row: DocumentRow;
  withDate: boolean;
  showProduct: boolean;
}) {
  const source = documentSource(row);
  return (
    <tr className={cn("align-top", row.status === "dead" && "text-muted")}>
      <td className="sticky left-0 z-10 border-b border-border/60 bg-surface px-4 py-3">
        <span className="flex items-start gap-2">
          <FileText
            aria-hidden
            className={cn(
              "mt-0.5 size-4 shrink-0",
              row.status === "dead" ? "text-subtle" : "text-accent",
            )}
          />
          <span className="min-w-0">
            <span className="block font-medium text-fg">{row.title}</span>
            <span className="mt-0.5 block text-xs text-subtle">
              {row.format}
              {row.pages ? ` · ${row.pages} pages` : ""}
            </span>
          </span>
        </span>
      </td>
      <td className="border-b border-border/60 px-3 py-3">
        <span className="inline-flex whitespace-nowrap rounded-full bg-surface-2 px-2 py-0.5 text-[11px] uppercase tracking-[0.08em] text-muted">
          {docTypeLabel(row.docType)}
        </span>
      </td>
      <td className="border-b border-border/60 px-3 py-3 text-muted">{row.lang}</td>
      {withDate ? (
        <td className="border-b border-border/60 whitespace-nowrap px-3 py-3 tabular-nums text-muted">
          {row.date ?? "—"}
        </td>
      ) : null}
      <td className="border-b border-border/60 whitespace-nowrap px-3 py-3 tabular-nums text-muted">
        {formatBytes(row.bytes) || "—"}
      </td>
      <td className="border-b border-border/60 whitespace-nowrap px-3 py-3 text-muted">
        {source === "unavailable"
          ? "Unavailable"
          : source === "local"
            ? "Saved locally"
            : "Siemens Energy"}
      </td>
      {showProduct ? (
        <td className="border-b border-border/60 px-3 py-3">
          {row.owner ? (
            <Link
              to="/item/$family/$slug"
              params={{ family: row.owner.family, slug: row.owner.slug }}
              className="text-muted hover:text-fg"
            >
              {row.owner.title}
            </Link>
          ) : (
            "—"
          )}
        </td>
      ) : null}
      <td className="border-b border-border/60 px-4 py-3 text-right">
        {row.href ? (
          <a
            href={row.href}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open ${row.title} (${row.format})`}
            className="inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
          >
            <ExternalLink aria-hidden className="size-4" />
          </a>
        ) : row.owner ? (
          <Link
            to="/item/$family/$slug"
            params={{ family: row.owner.family, slug: row.owner.slug }}
            aria-label={`View the source page for ${row.title}`}
            className="text-xs text-subtle hover:text-fg"
          >
            Product page
          </Link>
        ) : (
          <span className="text-xs text-subtle">—</span>
        )}
      </td>
    </tr>
  );
}
