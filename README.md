# Fieldbook — Siemens Energy Product Portfolio

A searchable static library of publicly published Siemens Energy product
material: 244 catalog pages, 67 families, and 850 brochures, datasheets, and
papers, with local copies of the smaller documents.

**Live site:** https://pedrodinisf.github.io/Siemens_Energy_Product_Portfolio/

![Fieldbook catalog home](screenshots/catalog-home.png)

## What it does

- **Search** everything — titles, descriptions, specs, FAQs, and file names.
- **Browse** by sector, family, or the global file index.
- **Product dossiers** with technical data tables, FAQs, related entries, and
  direct download links (local copies where available, source URLs otherwise).
- **Papers** view for white papers and technical papers.

## Data

Scraped on 2026-09-10 from the public
[product offerings catalog](https://www.siemens-energy.com/global/en/home/products-services/product-offerings.html).

| Bucket | Pages |
| --- | --- |
| Products | 137 |
| Services | 14 |
| Solutions | 30 |
| Publications | 61 |

- 850 files discovered; 637 archived. Small files are served from this repo,
  larger ones link to the Siemens Energy asset CDN.
- The scrape is preserved in [`data/siemens-energy/`](data/siemens-energy/) —
  one folder per page with a `README.md`, `product.json`, hero image, and
  `files/`. The app reads the bundled
  [`src/data/catalog.json`](src/data/catalog.json) index.
- Scraper: [`scripts/crawl-siemens-energy.py`](scripts/crawl-siemens-energy.py)
  plus [`scripts/catalog_images.py`](scripts/catalog_images.py). Kept for
  transparency; not required to run the app.

All content is © Siemens Energy AG, collected from public pages for research
and reference. This project is not affiliated with or endorsed by Siemens
Energy. Trademarks belong to their owners.

## Stack

- [TanStack Start](https://tanstack.com/start) + [TanStack Router](https://tanstack.com/router) (React 19, SSR)
- Vite 8, TypeScript (strict), Tailwind CSS v4
- Nitro (Vercel preset for the default deploy, static output for GitHub Pages)
- Node 22+, npm

## Repository layout

```
src/                  app code (routes, components, catalog store)
src/data/catalog.json bundled catalog index
public/catalog/       locally served images and documents
data/siemens-energy/  full scrape archive (dossiers + files)
scripts/              scraper, build helpers, QA scripts
.github/workflows/    GitHub Pages deployment
screenshots/          UI reference shots
server/, migrations/  platform plumbing from the original app-builder template
.grok/                app-builder workspace tooling
```

## Local development

Requires Node 22 or newer.

```sh
npm ci
npm run dev        # http://localhost:8080
```

Checks:

```sh
npm run typecheck
npm run lint
npm test
```

## Builds

```sh
npm run build          # default: Nitro Vercel output (SSR)
npm run build:pages    # static GitHub Pages build -> .pages/output/static
npm run preview        # serve the default build on 127.0.0.1:8081
```

The Pages build runs in SPA mode with the `/Siemens_Energy_Product_Portfolio/`
base path. `scripts/pages-postbuild.mjs` turns the generated shell into
`index.html` and `404.html` so deep links work on Pages (which has no rewrite
rules), reconciles the stylesheet link, and writes a static PWA manifest.

Deployment happens automatically: pushing to `main` runs
[`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml)
(typecheck → build → deploy). The repository's Pages source is set to
**GitHub Actions**.

## Notes

- The default build targets Vercel via the Nitro preset; GitHub Pages is an
  additional static target selected only by `--mode pages`.
- On-host PWA/branding chrome served by the original platform runtime (install
  page, extension script) is not part of the static Pages build.
