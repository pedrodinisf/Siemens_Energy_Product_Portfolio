import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { FileText, Search, Zap } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useCatalog } from "@/lib/catalog-store";

export function Shell({ children }: { children: ReactNode }) {
  const { catalog, ready } = useCatalog();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(
      typeof window === "undefined" ? "" : window.location.search,
    );
    setQ(params.get("q") ?? "");
  }, [pathname]);

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const query = q.trim();
    void navigate({
      to: "/",
      search: query ? { q: query } : {},
    });
  }

  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-sm bg-accent text-accent-fg">
              <Zap className="size-4" strokeWidth={2.4} />
            </span>
            <span className="leading-tight">
              <span className="block font-display text-lg font-semibold tracking-wide">
                Fieldbook
              </span>
              <span className="hidden text-[11px] uppercase tracking-[0.16em] text-muted sm:block">
                Siemens Energy library
              </span>
            </span>
          </Link>
          <form onSubmit={onSearch} className="relative min-w-0 w-full sm:w-auto sm:max-w-xl sm:flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search products, specs, papers…"
              className="h-11 w-full rounded-md border border-border bg-surface pl-10 pr-3 text-sm text-fg outline-none placeholder:text-subtle focus:border-accent"
              aria-label="Search catalog"
            />
          </form>
          <nav className="hidden shrink-0 items-center gap-1 sm:flex">
            <NavLink to="/" active={pathname === "/"}>
              Catalog
            </NavLink>
            <NavLink to="/downloads" active={pathname.startsWith("/downloads")}>
              Files
            </NavLink>
            <NavLink to="/papers" active={pathname.startsWith("/papers")}>
              Papers
            </NavLink>
          </nav>
        </div>
        <div className="flex gap-1 border-t border-border px-4 py-2 sm:hidden">
          <NavLink to="/" active={pathname === "/"} className="flex-1 justify-center">
            Catalog
          </NavLink>
          <NavLink
            to="/downloads"
            active={pathname.startsWith("/downloads")}
            className="flex-1 justify-center"
          >
            Files
          </NavLink>
          <NavLink
            to="/papers"
            active={pathname.startsWith("/papers")}
            className="flex-1 justify-center"
          >
            Papers
          </NavLink>
        </div>
      </header>

      {!ready ? (
        <div className="border-b border-border bg-accent-dim/40 px-4 py-2 text-center text-xs text-accent">
          Catalog is empty.
        </div>
      ) : null}

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>

      <footer className="border-t border-border px-4 py-8 text-center text-xs text-subtle">
        {ready ? (
          <p>
            {catalog.summary.pages} pages · {catalog.summary.filesDownloaded} files
            saved · scraped {catalog.summary.scrapedAt?.slice(0, 10)} from public
            Siemens Energy pages. Trademarks belong to Siemens Energy AG.
          </p>
        ) : (
          <p>Reference library of publicly published Siemens Energy materials.</p>
        )}
        <p className="mt-2 inline-flex items-center gap-1.5">
          <FileText className="size-3.5" />
          Not affiliated with Siemens Energy.
        </p>
      </footer>
    </div>
  );
}

function NavLink({
  to,
  active,
  children,
  className,
}: {
  to: string;
  active: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "inline-flex h-10 items-center rounded-md px-3 text-sm font-medium transition-colors",
        active ? "bg-surface text-fg" : "text-muted hover:text-fg",
        className,
      )}
    >
      {children}
    </Link>
  );
}
