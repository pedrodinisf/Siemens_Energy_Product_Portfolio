# Product Page Overhaul — Plan & Repo Context

Self-contained brief for a new session. Verified 2026-09-11. User decisions are locked in §5.

## 0. How to use this document

Paste this file into a new session (or point the session at it) and say:
"Execute Phase 1 of the plan in docs/product-page-overhaul-plan.md. Decisions are locked."

Phases are independent; the locked order is **1 (images) → 3 (tables) → 2 (typography) → 4 (review)**.
Do not start a later phase without being asked.

## 1. Project context

### 1.1 What it is
"Fieldbook" — a static, searchable catalog of Siemens Energy's publicly published product material.
244 catalog pages (137 products / 14 services / 30 solutions / 61 publications), 67 families,
850 discovered documents (637 archived), scraped 2026-09-10 from siemens-energy.com.

**Live:** https://pedrodinisf.github.io/Siemens_Energy_Product_Portfolio/

### 1.2 Stack & architecture
- TanStack Start + React 19 + Vite 8 + Tailwind v4 + Nitro; TypeScript strict.
- GitHub Pages build: `vite build --mode pages` → **314 prerendered routes** (244 item +
  67 family + `/`, `/downloads`, `/papers`) → `.pages/output/static`.
- `scripts/pages-postbuild.mjs`: `index.html`/`404.html`, sitemap.xml, robots.txt, canonical +
  OG/Twitter meta, PWA manifest, `.nojekyll`.
- Base path `/Siemens_Energy_Product_Portfolio/`; `assetHref()` in `src/lib/catalog.ts` resolves
  root-relative asset paths against the Vite base.
- Local dev: `npm run dev` → http://localhost:8080.

### 1.3 Deployment
Push to `main` → `.github/workflows/deploy-pages.yml` (node 22, `npm ci`, typecheck, lint, test,
`build:pages`, postbuild, upload, deploy). Fresh clone ≈ 104 MB (`data/` archive is untracked).

### 1.4 Verification workflow (run after every change)
```powershell
npm run typecheck
npm run lint
npm test
npm run build:pages
node scripts/pages-postbuild.mjs
# Browser QA: serve `.pages/output/static` at `/Siemens_Energy_Product_Portfolio/`
# with a 404-fallback; check desktop + 390x844 mobile: 0 console/page/network errors,
# 0 broken images, deep links 200, search works.
```
Then commit + push, confirm the Actions run succeeds, and spot-check the live site.

### 1.5 Conventions & constraints
- Windows/PowerShell 5.1, Node 22+, npm-10-compatible lockfile (`npx npm@10 install …` if deps
  change; validate with `npm ci`).
- Python tooling runs from a venv. Existing scripts need Pillow; PDF extraction needs PyMuPDF.
  There is no requirements file yet.
- `AGENTS.md` is stale Grok-sandbox documentation — ignore its platform workflow rules.
- `src/data/catalog.json` is the source of truth; regenerate split files with `npm run catalog:split`.
- Tests guard data integrity in `scripts/pages-postbuild.test.mjs` (split sync, files/heroes exist)
  and `src/lib/catalog.test.ts`.

### 1.6 Prerequisites for a fresh machine
```powershell
npm ci                      # restores node + Playwright package (browsers not downloaded)
# For Python passes: create a venv and install
python -m venv .venv-pages
.venv-pages\Scripts\pip install Pillow      # add pymupdf only if touching PDF extraction
```
Browser QA uses the installed Chrome (`channel: "chrome"`) via the `playwright` package.

## 2. Data pipeline & file map

### 2.1 Archive — `data/siemens-energy/` (untracked, local; ~1.1 GB, 1,407 files)
- 243 `product.json`: 240 have `images` (1,365 candidate URLs), 175 `related`, 242 `headings`,
  all have `hero` (original CDN URL), `body` (flattened, ≤12k chars), `specs`, `faqs`, `files`,
  `heroLocal`, `heroFit`. Each folder also has `README.md`, `hero.jpg`, `files/`.
- This is the working store for re-fetch output and the only local source of original CDN URLs.

### 2.2 Bundled app data — `src/data/` (tracked)
| File | Content | Loaded |
|---|---|---|
| `catalog.json` | full catalog (~2.2 MB; source of truth) | never at runtime |
| `catalog-index.json` | all except body/faqs (~1.0 MB, 180 KB gzip) | always |
| `catalog-body.json` | `id → body` (220 KB gzip) | item/family + search |
| `catalog-faqs.json` | `id → faqs` (105 KB gzip) | item pages |

### 2.3 Public assets — `public/catalog/` (tracked)
- `images/` — 289 WebP files (19.3 MB), produced by `scripts/optimize-catalog-images.py`.
- `files/` — ~358 local PDFs/docs (89 MB); larger files link to the Siemens CDN.

### 2.4 Scripts
- `scripts/crawl-siemens-energy.py` — original crawler (HTML parser ~line 179; `pick_hero` ~616);
  **hardcodes `/workspace` paths**.
- `scripts/catalog_images.py` — image scoring (`score_image_url` ~73), DAM download variants,
  PDF photo extraction (PyMuPDF).
- `scripts/repair-catalog-images.py` — earlier re-pick pass (also `/workspace`-hardcoded).
- `scripts/optimize-catalog-images.py` — WebP conversion + catalog repointing.
- `scripts/split-catalog.mjs`, `scripts/pages-postbuild.mjs`.

### 2.5 Rendering
- `src/routes/item.$family.$slug.tsx`: hero, `SpecTable`, downloads, flat `<p>` body, FAQ,
  "Same family". Does not render `highlights`/`related`/`images` — and must not gain new sections
  (see §5).
- `src/components/spec-table.tsx`: `{name,value}` or header-row shapes; empty cells blank;
  no row-label support.
- Design tokens in `src/styles.css` (Source Sans 3 body, Barlow Condensed display, a11y-audited
  colors: `--color-subtle #7c8b97`, `--color-muted #8b9aa6`).

## 3. Known problems (evidence)

### 3.1 Images
- Picker scores filenames only; `og:image`, JSON-LD images and `alt` text were never captured.
- Mismatch examples: `digital/fatigue-monitoring-system → CHP-KeyVisual`,
  `digital/power-intelligence → Solar-and-wind-power-plant`, `digital/icss → A__Large.jpg`,
  `compression/compressor-controls → ME-SGT-400-…`, `compression/hsrc-app → HOS_KeyVisual`,
  both SGT-9000HL items → "Siemens-Phoenix".
- A crude filename-token audit flags ~215/241 items — too noisy to act on; visual review is
  required to enumerate the real mismatches.

### 3.2 Text
- 243/244 items have `headings`, but only 72 have any heading inside `body`; bodies are flat
  paragraphs (3 items with bullet markers, 1 numbered). Leftovers: "Discover …" (30 items),
  "Read more / Learn more" (37), "Contact us" (5), plus duplicated H1/nav fragments.

### 3.3 Tables
- Only 39/244 items have `specs`: 24 header-row/transposed, 11 mixed, 4 named; 47 empty cells;
  one 80-row table. The transposed tables lost their metric label column — e.g. SGT-800's first
  record `{ "62 MW rating": "62.5 MW(e)", … }` with no "Power/Fuel/Frequency/…" labels.

### 3.4 Already fixed — do not redo
WebP + lazy images; sitemap/robots/canonical/OG; axe a11y 0 violations; unused deps removed;
history rewritten (clone 104 MB); fonts self-hosted.

## 4. Plan

### Phase 1 — Image audit + picker v2 (no paid vision API)
1. **Single re-fetch pass** over the 244 product URLs (polite concurrency 6–8, crawler UA),
   saving into `data/siemens-energy/`:
   - `image-candidates.json`: per item — `og:image`, JSON-LD `image`, all `<img>` with `alt`
     and nearest heading/link context.
   - `content-blocks.json`: main-article structure (`h2/h3`, paragraphs, lists, bold) for Phase 2.
   - `spec-tables.json`: raw spec `<table>` HTML (cells + headers) for Phase 3.
   Write a focused new `scripts/refetch-pages.py` (repo-relative paths, Windows-friendly) instead
   of editing the `/workspace`-hardcoded crawler.
2. **Picker v2**: priority = exact model/alt match → `og:image` → own poster/datasheet PDF with
   model in filename → scored page images → family image. Blacklist generic keys (`keyvisual`,
   `key-viz`, `webheader`, `solar-and-wind`, `CHP`, `A__Large`, people/office shots); dedupe
   heroes across items.
3. **Self-managed QC (no API)**: with Pillow, compose labeled contact sheets (item id + title +
   current hero, ~20–24/sheet); inspect them directly; for flagged items compose alternate sheets
   from the candidate pool; choose corrections.
4. **Overrides**: committed `src/data/image-overrides.json` (`item id → chosen URL/local path`),
   applied by the picker/apply step so corrections survive re-scrapes.
5. Apply: download picks → WebP (`optimize-catalog-images.py`) → catalogs → `catalog:split` → verify.

**Acceptance:** contact-sheet review completed for all 244; every flagged mismatch corrected;
overrides committed; typecheck/lint/tests/build/QA/live green; 0 broken images.

### Phase 3 — Spec tables
1. **Extractor fix** using `spec-tables.json`: preserve the label column; normalize to a matrix
   (`columns`, `rows: [{label, values}]`) or `{name,value}` pairs; drop empty rows/columns;
   merge duplicates; cap oversized tables (expand on demand).
2. **New renderer**: semantic `<th scope>`, label column, sticky label column + horizontal scroll
   on mobile, zebra rows, `—` for blanks.
3. Scope: **page tables only** by default; PDF mining for the ~200 items without tables is optional
   and only on request.

**Acceptance:** SGT-800-style tables show labeled rows; no unlabeled grids; empty cells handled;
tests updated; build/QA/live green.

### Phase 2 — Typography (restyle only, dark Fieldbook style kept)
1. **Body cleanup** (content of existing pages only): drop CTA/nav leftovers, duplicated H1,
   cookie text; dedupe paragraphs; normalize whitespace. Use `content-blocks.json` only to render
   each page's own content better — no new page sections, no galleries, no outlines.
2. **Legibility pass** on item (and family) pages, keeping the current aesthetic: ~16px body,
   line-height ~1.7, brighter body color (≥4.5:1), 65–70ch measure, paragraph and list styling,
   bold/strong emphasis, consistent spacing around hero/specs/downloads/FAQ.
3. The one allowed formatting addition: render source subheads/lists (already part of the page's
   own content) as formatted body elements — not as new page sections.

**Acceptance:** sampled pages across families read cleanly; no layout regressions; a11y stays
0 violations; tests/build/QA/live green.

### Phase 4 — Full-page review loop
Playwright snapshots of all 244 item pages → per-family contact sheets + audit report
(hero verdict, specs shape, body issues). Iterate until clean; final deploy.

## 5. Decisions (locked)
1. **Re-fetch:** approved (one polite pass over 244 pages).
2. **Vision model:** not used; no API spend. Image QC is done by the agent via self-inspected
   contact sheets.
3. **Style:** keep the dark "Fieldbook" look; improve legibility only.
4. **Scope:** restyle only — no new sections (no key benefits/related/gallery/outline).
5. **Order:** images → tables → typography → final review.
6. **Tables scope:** page tables only for now; PDF mining optional later.

## 6. Definition of done (whole project)
- No mismatched heroes on the curated list; overrides committed.
- Item pages: legible, cleaned body copy (same sections as today); specs (where available)
  correctly labeled.
- `npm run typecheck && npm run lint && npm test` pass; build + postbuild reproduce cleanly.
- Browser QA desktop + mobile: 0 errors, 0 broken images, deep links 200; a11y still 0 violations.
- Pushed to `main`, Actions green, live spot-check of ≥5 representative items.

## 7. Kickoff prompt
"Execute Phase 1 of the plan in docs/product-page-overhaul-plan.md. Decisions are locked (§5).
Re-fetch the 244 pages, build the candidate/content/spec extracts, run picker v2, do the
contact-sheet QC yourself, apply overrides, and verify with typecheck/lint/tests/build/QA before
pushing. Do not start Phases 2–4."
