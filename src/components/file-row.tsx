import { Download, ExternalLink } from "lucide-react";
import type { CatalogFile } from "@/lib/catalog";
import { fileHref, formatBytes, kindLabel } from "@/lib/catalog";

export function FileRow({ file }: { file: CatalogFile }) {
  const href = fileHref(file);
  const local = Boolean(file.downloaded && file.publicPath);
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-3 rounded-lg bg-surface px-3 py-3 shadow-card transition-[box-shadow] duration-150 hover:shadow-card-hover"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-accent-dim text-accent">
        <Download className="size-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-fg">
          {file.label || file.filename}
        </span>
        <span className="mt-0.5 block text-xs capitalize text-muted">
          {kindLabel(file.kind)}
          {file.bytes ? ` · ${formatBytes(file.bytes)}` : ""}
          {local ? " · saved locally" : " · source file"}
        </span>
      </span>
      <ExternalLink className="size-4 shrink-0 text-subtle" />
    </a>
  );
}
