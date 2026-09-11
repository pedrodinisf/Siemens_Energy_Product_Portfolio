import { useState } from "react";
import { cn } from "@/lib/utils";

export function CatalogImage({
  src,
  alt,
  fit = "cover",
  className,
  imgClassName,
}: {
  src?: string;
  alt: string;
  fit?: "cover" | "contain";
  className?: string;
  imgClassName?: string;
}) {
  const [failed, setFailed] = useState(false);
  const contain = fit === "contain";

  if (!src || failed) {
    const label = alt.replace(/[-_]/g, " ").slice(0, 22);
    return (
      <div
        className={cn(
          "flex h-full w-full items-end bg-surface-2 p-4",
          className,
        )}
      >
        <span className="font-display text-2xl font-semibold tracking-wide text-subtle/45">
          {label}
        </span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "h-full w-full overflow-hidden",
        contain ? "bg-photo" : "bg-surface-2",
        className,
      )}
    >
      <img
        src={src}
        alt={alt}
        onError={() => setFailed(true)}
        className={cn(
          "h-full w-full",
          contain
            ? "object-contain p-2"
            : "object-cover object-center",
          imgClassName,
        )}
      />
    </div>
  );
}
