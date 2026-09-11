import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { nitro } from "nitro/vite";
// @ts-expect-error JS plugin alongside the TS vite config
import { grokPwaPlugin } from "./scripts/grok-pwa-plugin.mjs";

/**
 * Every route of the static GitHub Pages build, enumerated from the bundled
 * catalog. Prerendering them produces real HTML per URL — deep links get a 200
 * and readable content without JavaScript — instead of one SPA shell plus a
 * 404 fallback.
 */
function pagesPrerenderOptions() {
  const catalogPath = join(
    dirname(fileURLToPath(import.meta.url)),
    "src/data/catalog.json",
  );
  const catalog = JSON.parse(readFileSync(catalogPath, "utf8")) as {
    families: { id: string }[];
    items: { family: string; slug: string }[];
  };
  const paths = [
    "/",
    "/downloads",
    "/papers",
    ...catalog.families.map((family) => `/family/${family.id}`),
    ...catalog.items.map((item) => `/item/${item.family}/${item.slug}`),
  ];
  return {
    prerender: { enabled: true, crawlLinks: false, failOnError: true },
    pages: paths.map((path) => ({ path })),
  };
}

// `0.0.0.0:8080` is the live-preview contract — don't change host/port.
// The dev server starts once `src/router.tsx` and `src/routes/` exist.
export default defineConfig(({ command, isPreview, mode }) => {
  // `vite build --mode pages` targets a GitHub Pages project site, which lives
  // at /<repo>/ — every other target is root-served. Only this mode prerenders
  // every route, sets the base path and redirects the Nitro output to .pages/;
  // `npm run dev` / `npm run build` keep their platform contract.
  const pagesMode = mode === "pages";
  const base = pagesMode ? "/Siemens_Energy_Product_Portfolio/" : "/";

  return {
    base,
    server: {
      host: "0.0.0.0",
      port: 8080,
      strictPort: true,
    },
    preview: {
      host: "127.0.0.1",
      port: 8081,
      strictPort: true,
    },
    resolve: { tsconfigPaths: true },
    plugins: [
      // PWA head + ?install=1 tutorial page; runs before Start/Nitro.
      grokPwaPlugin(),
      tailwindcss(),
      tanstackStart(pagesMode ? pagesPrerenderOptions() : {}),
      ...(command === "build" || isPreview
        ? [
            nitro({
              preset: "vercel",
              // The static GitHub Pages artifact is the vercel build's static
              // dir; keep it out of the .vercel/ tree. (Nitro's static:true
              // presets don't survive the Vite plugin's final environment
              // build in this beta, so vercel + static output is the supported
              // path.)
              ...(pagesMode ? { output: { dir: ".pages/output" } } : {}),
              // Auto-registers server/middleware/* (the PWA install page +
              // manifest + head-tag middleware). Nitro v3 defaults serverDir to
              // false, so removing this silently unwires /?install=1 on deploys.
              // Static GitHub Pages output has no runtime, so the middleware is
              // skipped there (its ?install=1 page cannot exist on a static host).
              serverDir: pagesMode ? false : "./server",
            }),
          ]
        : []),
      viteReact(),
    ],
  };
});
