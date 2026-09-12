# Fieldbook — Siemens Energy Product Portfolio

A searchable static library of publicly published Siemens Energy product
material: 244 catalog pages, 67 families, and 646 brochures, datasheets, and
papers, with local copies of the smaller documents.

**Live site:** https://pedrodinisf.github.io/Siemens_Energy_Product_Portfolio/

![Fieldbook catalog home](screenshots/catalog-home.png)

## What it does

- **Search** everything — titles, descriptions, specs, FAQs, document titles,
  and file names.
- **Browse** by sector, family, or the global file index.
- **Product dossiers** with technical data tables, FAQs, related entries, and a
  document table (title, type, language, size, source) with direct download
  links — local copies where available, source URLs otherwise.
- **Documents view** with filters for type, language and source across every
  document in the library.
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

- 646 unique documents discovered; 345 saved locally. Small files are served
  from this repo, larger ones link to the Siemens Energy asset CDN. Ten source
  files have been removed upstream and are listed as unavailable.
- Document rows carry a real title, type, language, size, source and — where
  the source page publishes one — a date. Titles and context come from the
  source pages (`scripts/refetch-documents.py`), the files themselves
  (`scripts/fetch-document-metadata.py`, PyMuPDF + Office core properties) and
  the merge pass (`scripts/build-document-metadata.mjs`), which writes
  `src/data/document-metadata.json` and enriches `catalog.json`. Asset health,
  sizes and local-copy integrity come from `scripts/probe-assets.mjs` and
  `scripts/apply-asset-fixes.mjs`.
- The full scrape is kept locally in `data/siemens-energy/` — one folder per
  page with a `README.md`, `product.json`, hero image, and `files/`. It is not
  tracked in git (the repo stays lean); regenerate it with the scraper. The app
  reads three generated files: `src/data/catalog-index.json` (metadata, bundled
  with the app), `src/data/catalog-body.json` (body text, loaded on demand by
  item/family pages and full-text search) and `src/data/catalog-faqs.json`
  (FAQ answers, item pages only). Run `npm run catalog:split` after
  re-scraping to regenerate them from `src/data/catalog.json`.
- Hero images are served as WebP; `scripts/optimize-catalog-images.py`
  (requires Pillow) re-encodes them and repoints the catalogs after a scrape.
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
src/data/catalog.json full catalog (source of truth)
public/catalog/       locally served images and documents
data/siemens-energy/  full scrape archive (local only, not tracked in git)
scripts/              scraper, document-metadata pipeline, build helpers, QA scripts
.github/workflows/    GitHub Pages deployment
screenshots/          UI reference shots
server/               platform PWA middleware (install page, head tags)
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

Document pipeline (optional; only after a re-scrape): the Python passes need a
virtualenv with PyMuPDF and pypdf.

```sh
python3 -m venv .venv-pages
.venv-pages/bin/pip install pymupdf pypdf     # Windows: .venv-pages\Scripts\pip

node scripts/probe-assets.mjs                 # live/dead + sizes (data/…/asset-probe.json)
node scripts/apply-asset-fixes.mjs            # repair URLs, canonical local copies
python3 scripts/refetch-documents.py          # page titles/types/table data
.venv-pages/bin/python scripts/fetch-document-metadata.py   # PDF/Office metadata
node scripts/build-document-metadata.mjs      # merge + catalog:split
node scripts/document-ui-review.mjs           # browser QA on the built output
```

Browser QA for the document views runs against the built Pages output (build
with `npm run build:pages` first) and writes screenshots plus a verdict to
`data/siemens-energy/qa/`.

## Builds

```sh
npm run build          # default: Nitro Vercel output (SSR)
npm run build:pages    # static GitHub Pages build -> .pages/output/static
npm run preview        # serve the default build on 127.0.0.1:8081
```

The Pages build prerenders every route (244 items, 67 families, plus the
catalog, files, and papers views) into real HTML under
`/Siemens_Energy_Product_Portfolio/`, so deep links return 200 with readable
content and per-page titles. `scripts/pages-postbuild.mjs` then reconciles the
stylesheet links, adds Open Graph/Twitter share meta, writes a static PWA
manifest, and copies the home page to `404.html` so unknown URLs still boot the
client router.

Deployment happens automatically: pushing to `main` runs
[`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml)
(typecheck → build → deploy). The repository's Pages source is set to
**GitHub Actions**.

## Notes

- The default build targets Vercel via the Nitro preset; GitHub Pages is an
  additional static target selected only by `--mode pages`.
- The app is fully static. The original app-builder template's opt-in auth,
  database, connector, and multiplayer scaffolding has been removed along with
  its dependencies.
- On-host PWA/branding chrome served by the original platform runtime (install
  page, extension script) is not part of the static Pages build.
- Fonts (Barlow Condensed, Source Sans 3 — SIL Open Font License) are
  self-hosted from `src/assets/fonts/`, so the site makes no third-party font
  requests.
