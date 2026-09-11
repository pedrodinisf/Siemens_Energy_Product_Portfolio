#!/usr/bin/env python3
"""Re-pick a real product photo for every catalog entry.

Hero files from the first crawl were often HTML error pages, dark placeholders,
or uncorrelated web headers. This pass scores family teaser photos, on-page
DAM images, and (if needed) images embedded in the product's own PDFs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_images import (
    download_valid_image,
    extract_pdf_photos,
    inspect_image_bytes,
    model_tokens,
    score_image_url,
)

ROOT = Path("/workspace/data/siemens-energy")
PUBLIC = Path("/workspace/public/catalog")
SRC_DATA = Path("/workspace/src/data")
PUBLIC_IMG = PUBLIC / "images"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slug_from_href(href: str) -> str:
    path = urllib.parse.urlparse(href or "").path.rstrip("/")
    name = path.rsplit("/", 1)[-1]
    return name.replace(".html", "").strip() or ""


def load_products() -> list[dict]:
    items = []
    for path in ROOT.rglob("product.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id"):
            data["_path"] = str(path)
            items.append(data)
    return items


def local_pdf_path(rec: dict) -> Path | None:
    lp = rec.get("localPath")
    if lp:
        p = ROOT / lp
        if p.exists():
            return p
    pub = rec.get("publicPath") or ""
    if pub.startswith("/"):
        p = Path("/workspace/public") / pub.lstrip("/")
        if p.exists():
            return p
    return None


def teaser_index(products: list[dict]) -> dict[str, list[dict]]:
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for prod in products:
        for rel in prod.get("related") or []:
            img = (rel or {}).get("image") or ""
            href = (rel or {}).get("href") or ""
            if not img:
                continue
            slug = slug_from_href(href)
            title = rel.get("title") or ""
            entry = {
                "image": img,
                "title": title,
                "href": href,
                "from": prod.get("id"),
                "family": prod.get("family"),
            }
            if slug:
                by_slug[slug].append(entry)
            # also index compact model tokens from the teaser title
            for tok in model_tokens(slug, title):
                by_slug[tok].append(entry)
    return by_slug


def candidate_urls(item: dict, teasers: dict[str, list[dict]]) -> list[tuple[int, str, str]]:
    """Return (score, url, reason) highest first."""
    slug = item.get("slug") or ""
    title = item.get("title") or item.get("h1") or ""
    family = item.get("family") or ""
    found: dict[str, tuple[int, str]] = {}

    def add(url: str, extra: int, reason: str) -> None:
        url = (url or "").strip()
        if not url:
            return
        base = url.split("?")[0]
        score = score_image_url(url, slug, title) + extra
        prev = found.get(base)
        if not prev or score > prev[0]:
            found[base] = (score, reason)

    add(item.get("hero") or "", 0, "hero")
    for img in item.get("images") or []:
        add(img, 4, "page")
    for rel in item.get("related") or []:
        add((rel or {}).get("image") or "", 12, "related")

    keys = {slug, slug.replace("-", "")}
    keys |= model_tokens(slug, title, item.get("h1") or "")
    exact = {slug, slug.replace("-", "")}
    for key in keys:
        for entry in teasers.get(key) or []:
            extra = 50 if key in exact or slug_from_href(entry.get("href") or "") == slug else 6
            if entry.get("family") and entry["family"] != family:
                extra = min(extra, 8)
            add(entry["image"], extra, "teaser")

    ranked = [(score, url, reason) for url, (score, reason) in found.items()]
    ranked.sort(key=lambda r: r[0], reverse=True)
    return ranked


def existing_hero(item: dict) -> dict | None:
    hl = item.get("heroLocal") or ""
    if not hl:
        return None
    rel = hl.replace("/catalog/images/", "")
    path = PUBLIC_IMG / rel
    if not path.exists():
        folder = Path(item.get("_path") or "").parent
        for cand in folder.glob("hero.*"):
            path = cand
            break
        else:
            return None
    try:
        data = path.read_bytes()
    except Exception:
        return None
    info = inspect_image_bytes(data)
    if not info:
        return None
    score = score_image_url(item.get("hero") or path.name, item.get("slug") or "", item.get("title") or "")
    if score < 0:
        return None
    return {
        "path": path,
        "score": score,
        "fit": info["fit"],
        "ext": path.suffix.lower() or ".jpg",
    }


def write_hero_files(item: dict, payload: dict) -> str:
    family = item["family"]
    slug = item["slug"]
    ext = payload["ext"]
    data: bytes = payload["bytes"]
    pub_dir = PUBLIC_IMG / family
    pub_dir.mkdir(parents=True, exist_ok=True)
    # drop stale companions (html saved as .png, old ext)
    for stale in pub_dir.glob(f"{slug}.*"):
        if stale.suffix.lower() != ext:
            stale.unlink(missing_ok=True)
    dest = pub_dir / f"{slug}{ext}"
    dest.write_bytes(data)

    folder = Path(item["_path"]).parent
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob("hero.*"):
        stale.unlink(missing_ok=True)
    (folder / f"hero{ext}").write_bytes(data)
    return f"/catalog/images/{family}/{slug}{ext}"


def pdf_fallback(item: dict) -> dict | None:
    ranked: list[dict] = []
    for rec in item.get("files") or []:
        path = local_pdf_path(rec)
        if not path or path.suffix.lower() != ".pdf":
            continue
        ranked.extend(
            extract_pdf_photos(path, item.get("slug") or "", item.get("title") or "")
        )
    if not ranked:
        return None
    ranked.sort(key=lambda r: r.get("score", 0), reverse=True)
    return ranked[0]


def patch_catalog(updates: dict[str, dict]) -> None:
    paths = [
        (ROOT / "catalog.json", True),
        (PUBLIC / "catalog.json", False),
        (SRC_DATA / "catalog.json", False),
    ]
    for path, pretty in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for item in data.get("items") or []:
            rec = updates.get(item.get("id") or "")
            if not rec:
                continue
            item["hero"] = rec.get("hero", item.get("hero"))
            item["heroLocal"] = rec["heroLocal"]
            item["heroFit"] = rec.get("heroFit") or "cover"
        for fam in data.get("families") or []:
            overview_id = fam.get("overview") or f"{fam.get('id')}/_overview"
            rec = updates.get(overview_id)
            if rec:
                fam["hero"] = rec["heroLocal"]
                fam["heroFit"] = rec.get("heroFit") or "cover"
            elif fam.get("id") in {u.split("/")[0] for u in updates}:
                # fall back to first updated member of this family
                for iid, rec in updates.items():
                    if iid.startswith(fam["id"] + "/") and rec.get("heroLocal"):
                        if not fam.get("hero") or "placeholder" in (fam.get("hero") or "").lower():
                            fam["hero"] = rec["heroLocal"]
                            fam["heroFit"] = rec.get("heroFit") or "cover"
                        break
        if pretty:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        else:
            path.write_text(json.dumps(data, ensure_ascii=False))
        log(f"wrote {path}")


def repair(family_filter: str | None = None, limit: int = 0) -> None:
    products = load_products()
    teasers = teaser_index(products)
    cache: dict = {}
    updates: dict[str, dict] = {}
    stats = defaultdict(int)

    work = products
    if family_filter:
        work = [p for p in products if p.get("family") == family_filter]
    work.sort(key=lambda p: (p.get("bucket") or "", p.get("family") or "", p.get("slug") or ""))
    if limit:
        work = work[:limit]

    log(f"repairing {len(work)} items")
    for i, item in enumerate(work, 1):
        iid = item["id"]
        ranked = candidate_urls(item, teasers)
        chosen = None
        reason = ""
        for score, url, why in ranked[:12]:
            if score < -80 and why != "teaser":
                continue
            payload = download_valid_image(url, cache)
            if payload:
                chosen = payload
                reason = f"{why} score={score}"
                break
        if not chosen:
            pdf = pdf_fallback(item)
            if pdf:
                chosen = pdf
                reason = f"pdf {pdf.get('source')}"
        if not chosen:
            keep = existing_hero(item)
            if keep:
                stats["kept"] += 1
                log(f"  keep {iid}")
                continue
            stats["failed"] += 1
            log(f"  FAIL {iid}")
            continue

        hero_local = write_hero_files(item, chosen)
        item["hero"] = chosen.get("source") or item.get("hero")
        item["heroLocal"] = hero_local
        item["heroFit"] = chosen.get("fit") or "cover"
        Path(item["_path"]).write_text(json.dumps({k: v for k, v in item.items() if k != "_path"}, indent=2, ensure_ascii=False) + "\n")
        updates[iid] = {
            "hero": item["hero"],
            "heroLocal": hero_local,
            "heroFit": item["heroFit"],
        }
        stats["updated"] += 1
        if i % 8 == 0 or i == len(work):
            log(f"  {i}/{len(work)} {iid} ← {reason} {chosen.get('ext')} {chosen.get('width')}x{chosen.get('height')}")

    if updates:
        patch_catalog(updates)
    log(f"done updated={stats['updated']} kept={stats['kept']} failed={stats['failed']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    repair(args.family or None, args.limit)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
