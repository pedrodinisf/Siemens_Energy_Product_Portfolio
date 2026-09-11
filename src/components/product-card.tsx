import { Link } from "@tanstack/react-router";
import { FileText } from "lucide-react";
import type { CatalogItem } from "@/lib/catalog";
import { kindLabel } from "@/lib/catalog";
import { CatalogImage } from "@/components/catalog-image";

export function ProductCard({ item }: { item: CatalogItem }) {
  const img = item.heroLocal;
  const files = item.files.length;
  return (
    <Link
      to="/item/$family/$slug"
      params={{ family: item.family, slug: item.slug }}
      className="group flex flex-col overflow-hidden rounded-xl bg-surface shadow-card transition-[box-shadow,transform] duration-200 hover:shadow-card-hover"
    >
      <div className="relative aspect-[16/9] overflow-hidden bg-surface-2">
        <CatalogImage
          src={img}
          alt={item.title}
          fit={item.heroFit === "contain" ? "contain" : "cover"}
          imgClassName={
            item.heroFit === "contain"
              ? "p-3 transition-transform duration-300 group-hover:scale-[1.03]"
              : "transition-transform duration-300 group-hover:scale-[1.03]"
          }
        />
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-muted">
          <span className="text-accent">{kindLabel(item.kind)}</span>
          <span className="text-subtle">/</span>
          <span className="truncate">{item.familyLabel}</span>
        </div>
        <h3 className="font-display text-xl font-semibold leading-snug tracking-tight text-fg">
          {item.title}
        </h3>
        {item.description ? (
          <p className="line-clamp-3 text-sm leading-relaxed text-muted">{item.description}</p>
        ) : null}
        <div className="mt-auto flex items-center gap-3 pt-2 text-xs text-subtle">
          {files ? (
            <span className="inline-flex items-center gap-1">
              <FileText className="size-3.5" />
              {files} file{files === 1 ? "" : "s"}
            </span>
          ) : (
            <span>Open dossier</span>
          )}
        </div>
      </div>
    </Link>
  );
}
