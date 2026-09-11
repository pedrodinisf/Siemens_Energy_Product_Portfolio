import { useState } from "react";
import type { SpecMatrixRow, SpecPair, SpecTable as SpecTableData } from "@/lib/catalog";

const COLLAPSED_ROWS = 12;

const captionClass =
  "caption-top px-4 pt-3 text-left text-xs font-medium uppercase tracking-[0.12em] text-muted";

function useVisibleRows(rows: unknown[]) {
  const [expanded, setExpanded] = useState(false);
  const capped = rows.length > COLLAPSED_ROWS;
  return {
    expanded: capped && expanded,
    visible: capped && !expanded ? rows.slice(0, COLLAPSED_ROWS) : rows,
    toggle: (
      <div className="border-t border-border px-4 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs font-medium text-accent hover:text-fg"
        >
          {expanded ? "Show fewer" : `Show all ${rows.length} rows`}
        </button>
      </div>
    ),
    capped,
  };
}

function PairsTable({ table }: { table: Extract<SpecTableData, { kind: "pairs" }> }) {
  const { visible, toggle, capped } = useVisibleRows(table.rows);
  return (
    <div className="overflow-hidden rounded-xl bg-surface shadow-card">
      <table className="w-full text-sm">
        {table.caption ? <caption className={captionClass}>{table.caption}</caption> : null}
        <tbody>
          {(visible as SpecPair[]).map((row, i) => (
            <tr
              key={`${row.name}-${i}`}
              className="border-b border-border bg-surface last:border-0 even:bg-surface-2"
            >
              <th
                scope="row"
                className="w-[40%] px-4 py-3 text-left font-medium text-muted"
              >
                {row.name || "—"}
              </th>
              <td className="px-4 py-3 text-fg">{row.value || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {capped ? toggle : null}
    </div>
  );
}

function MatrixTable({ table }: { table: Extract<SpecTableData, { kind: "matrix" }> }) {
  const { visible, toggle, capped } = useVisibleRows(table.rows);
  const columnLabel = (column: string, index: number) =>
    column || (table.columns.length === 1 ? "Value" : `Value ${index + 1}`);
  return (
    <div
      tabIndex={0}
      className="overflow-x-auto rounded-xl bg-surface shadow-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <table className="min-w-full text-sm">
        {table.caption ? <caption className={captionClass}>{table.caption}</caption> : null}
        <thead>
          <tr className="border-b border-border bg-surface text-left text-xs uppercase tracking-[0.12em] text-muted">
            <th scope="col" className="sticky left-0 z-10 bg-surface px-4 py-3 font-medium">
              {table.labelHeader || "Parameter"}
            </th>
            {table.columns.map((column, i) => (
              <th key={`${column}-${i}`} scope="col" className="px-4 py-3 font-medium">
                {columnLabel(column, i)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(visible as SpecMatrixRow[]).map((row, i) => (
            <tr
              key={`${row.label}-${i}`}
              className="border-b border-border bg-surface last:border-0 even:bg-surface-2"
            >
              <th
                scope="row"
                className="sticky left-0 z-10 bg-inherit px-4 py-3 text-left font-medium text-fg"
              >
                {row.label || "—"}
              </th>
              {table.columns.map((_, j) => (
                <td key={j} className="px-4 py-3 text-muted">
                  {row.values[j] || "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {capped ? toggle : null}
    </div>
  );
}

export function SpecTable({ tables }: { tables: SpecTableData[] }) {
  if (!tables.length) return null;
  return (
    <div className="space-y-3">
      {tables.map((table, i) =>
        table.kind === "pairs" ? (
          <PairsTable key={i} table={table} />
        ) : (
          <MatrixTable key={i} table={table} />
        ),
      )}
    </div>
  );
}
