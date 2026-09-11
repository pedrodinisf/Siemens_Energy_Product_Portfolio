import type { SpecRow } from "@/lib/catalog";
import { isNamedSpec } from "@/lib/catalog";

export function SpecTable({ specs }: { specs: SpecRow[] }) {
  if (!specs.length) return null;
  const named = specs.filter(isNamedSpec);
  if (named.length === specs.length) {
    return (
      <div className="overflow-hidden rounded-xl bg-surface shadow-card">
        <table className="w-full text-sm">
          <tbody>
            {named.map((row) => (
              <tr key={row.name} className="border-b border-border last:border-0">
                <th className="w-[40%] px-4 py-3 text-left font-medium text-muted">{row.name}</th>
                <td className="px-4 py-3 text-fg">{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  const headers = Array.from(
    new Set(specs.flatMap((s) => Object.keys(s))),
  );
  return (
    <div className="overflow-x-auto rounded-xl bg-surface shadow-card">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-[0.12em] text-muted">
            {headers.map((h) => (
              <th key={h} className="px-4 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {specs.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              {headers.map((h) => (
                <td key={h} className="px-4 py-3 text-fg">
                  {(row as Record<string, string>)[h] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
