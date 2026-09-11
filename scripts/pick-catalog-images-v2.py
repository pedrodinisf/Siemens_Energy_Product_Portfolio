#!/usr/bin/env python3
"""Picker v2: choose a product-correct hero for every catalog item.

Priority order (per the image-overhaul plan):
    exact model / alt match -> og:image -> own poster/datasheet PDF with the
    model in its filename -> scored page images -> family image

Generic marketing keys (keyvisual, key-viz, webheader, solar-and-wind, CHP,
A__Large, stock/people/office shots) are blacklisted: they can never be picked
automatically. Picks are deduped across items, and `src/data/image-overrides.json`
(item id -> URL or local path) always wins.

Without flags this only writes `data/siemens-energy/picks-v2.json` plus a
thumbnail cache under `data/siemens-energy/.image-cache/` for the contact-sheet
review. `--apply` downloads the final picks, updates the archive/catalogs and
prints the follow-up commands (optimize -> catalog:split).

    .venv-pages/Scripts/python scripts/pick-catalog-images-v2.py
    .venv-pages/Scripts/python scripts/pick-catalog-images-v2.py --apply
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_images import (  # noqa: E402
    download_valid_image,
    extract_pdf_photos,
    filename_of,
    inspect_image_bytes,
    model_tokens,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
CANDIDATES = DATA_DIR / "image-candidates.json"
CATALOG = ROOT / "src" / "data" / "catalog.json"
ARCHIVE_CATALOG = DATA_DIR / "catalog.json"
OVERRIDES = ROOT / "src" / "data" / "image-overrides.json"
PICKS = DATA_DIR / "picks-v2.json"
CACHE_DIR = DATA_DIR / ".image-cache"
THUMB_DIR = CACHE_DIR / "thumbs"

THUMB_EDGE = 480

GENERIC_RE = re.compile(
    r"key[\s_-]*visual|keyviz|key[\s_-]*viz|webheader|web[\s_-]*header|"
    r"web[\s_-]*guide|(?<![a-z])contact(?![a-z])|"
    r"solar[\s_-]*and[\s_-]*wind|solarandwind|"
    r"(?<![a-z])chp(?![a-z])|a_{1,2}large|a-large",
    re.I,
)
PEOPLE_RE = re.compile(
    r"(?<![a-z])(people|person|persons|employees?|colleagues?|team|staff|"
    r"workers?|working|engineers?|technicians?|operators?|managers?|owners?|"
    r"customers?|students?|trainees?|audience|portrait|headshot|selfie|"
    r"businessm[ae]n|businesswom[ae]n|handshake|meeting|conference|office|"
    r"classroom|academy|family|kids?|children|woman|women|men)(?![a-z])",
    re.I,
)
HARD_RE = re.compile(
    r"icon|logo|sprite|favicon|placeholder|spacer|pixel|thumb|"
    r"badge|app[\s_-]*store|google[\s_-]*play|"
    r"social|facebook|linkedin|twitter|youtube|instagram|"
    r"buttons?---links|arrow|\.svg(?:$|\?)|"
    r"adobe[\s_-]*stock|shutterstock|istock|getty|alamy|dreamstime|"
    r"\.gif(?:$|\?)",
    re.I,
)
PRESENTATION_RE = re.compile(r"on[\s_-]*transparent|on[\s_-]*white|sidecut|side[\s_-]*cut|sideview|side[\s_-]*view", re.I)

SOURCE_BASE = {"og": 200, "jsonld": 180, "pdf": 150, "page": 60, "current": 60, "family": 0}
GENERIC_PENALTY = -420
PEOPLE_PENALTY = -380
SOFT_KINDS = {"service", "solution", "product-family", "hub"}
SOFT_GENERIC_PENALTY = -150
SOFT_PEOPLE_PENALTY = -80
FOREIGN_PENALTY = -340
CURRENT_BONUS = 2
PAPER_KINDS = {"white-paper", "technical-paper", "publication"}
STOPWORDS = {
    "with", "from", "that", "this", "your", "their", "more", "than", "into",
    "energy", "siemens", "power", "systems", "system", "solutions", "solution",
    "products", "product", "services", "service", "support", "overview",
}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def dam_id(url: str) -> str | None:
    match = re.search(r"/dam/([0-9a-f-]{36})/", url or "", re.I)
    return match.group(1) if match else None


def base_url(url: str) -> str:
    return (url or "").split("?")[0].strip()


def candidate_key(url: str = "", local: str = "") -> str:
    if local:
        return "local:" + local
    did = dam_id(url)
    if did:
        return "dam:" + did
    return "url:" + base_url(url).lower()


def strong_filename_models(filename: str) -> set[str]:
    found: set[str] = set()
    for match in re.findall(r"(?:sgt|sgen|sst)-?\d[\w-]*", filename, re.I):
        found.add(compact(match))
    for match in re.findall(r"\bt\d{3,4}\b", filename, re.I):
        found.add(compact(match))
    return found


def rendition_bonus(url: str) -> tuple[int, str | None]:
    name = filename_of(url)
    if "rendition1920" in name:
        return 12, "r1920"
    if "rendition1280" in name:
        return 10, "r1280"
    if "rendition960" in name:
        return 6, "r960"
    if "original" in name:
        return 4, "original"
    if "rendition480" in name:
        return -6, "r480"
    if "rendition170" in name:
        return -40, "r170"
    return 0, None


def score_candidate(item: dict, cand: dict, item_tokens: set[str]) -> dict:
    url = cand.get("url") or ""
    local = cand.get("local") or ""
    alt = cand.get("alt") or ""
    link_text = (cand.get("link") or {}).get("text") or ""
    heading_text = (cand.get("heading") or {}).get("text") or ""
    filename = urllib.parse.unquote(filename_of(url)) or Path(local).name
    compact_filename = compact(filename)
    compact_alt = compact(alt)
    source = cand.get("source") or "page"

    score = SOURCE_BASE.get(source, 0)
    reasons: list[str] = [source]

    model_like = {t for t in item_tokens if any(c.isdigit() for c in t) and len(t) >= 4}
    file_model_match = sorted(t for t in model_like if t in compact_filename)
    alt_model_match = sorted(t for t in model_like if t in compact_alt)
    other_file_match = sorted(
        t for t in item_tokens if len(t) >= 6 and t in compact_filename and t not in model_like
    )
    other_alt_match = sorted(
        t for t in item_tokens if len(t) >= 6 and t in compact_alt and t not in model_like
    )

    if alt_model_match:
        score += 320
        reasons.append("alt-model:" + alt_model_match[0])
    elif other_alt_match:
        score += 110
        reasons.append("alt-token:" + other_alt_match[0])
    if file_model_match:
        score += 270
        reasons.append("file-model:" + file_model_match[0])
    elif other_file_match:
        score += 80
        reasons.append("file-token:" + other_file_match[0])

    foreign = {
        fm
        for fm in strong_filename_models(filename)
        if not any(fm in token or token in fm for token in item_tokens)
    }
    if foreign:
        score += FOREIGN_PENALTY
        reasons.append("foreign-model:" + sorted(foreign)[0])

    overlap = {
        token
        for token in item_tokens
        if len(token) >= 5 and token not in model_like and token not in STOPWORDS
    }
    text_blob = compact(alt) + " " + compact(link_text) + " " + compact(heading_text)
    matched_words = sorted(t for t in overlap if t in text_blob)
    if matched_words:
        score += min(60, 20 * len(matched_words))
        reasons.append("context:" + ",".join(matched_words[:3]))

    if PRESENTATION_RE.search(filename):
        score += 20
        reasons.append("presentation")

    delta, rendition = rendition_bonus(url)
    score += delta
    if rendition:
        reasons.append(rendition)
    if "assets.siemens-energy.com/dam/" in url:
        score += 8
    if cand.get("is_current"):
        score += CURRENT_BONUS
        reasons.append("current")

    soft = (item.get("kind") or "") in SOFT_KINDS
    generic = bool(GENERIC_RE.search(filename + " " + alt))
    people = bool(PEOPLE_RE.search(filename + " " + alt + " " + link_text))
    if generic:
        score += SOFT_GENERIC_PENALTY if soft else GENERIC_PENALTY
        reasons.append("generic")
    if people:
        score += SOFT_PEOPLE_PENALTY if soft else PEOPLE_PENALTY
        reasons.append("people")
    hard = bool(HARD_RE.search(filename) or HARD_RE.search(alt))
    if hard:
        reasons.append("hard-reject")

    return {
        "key": candidate_key(url, local),
        "url": url or None,
        "local": local or None,
        "source": source,
        "score": score,
        "reasons": reasons,
        "valid": None,
        "generic": generic,
        "people": people,
        "hard": hard,
        "width": None,
        "height": None,
        "fit": None,
        "thumb": None,
    }


class ImageCache:
    """URL/local/PDF validation + review thumbnails, persisted between runs."""

    def __init__(self, force: bool = False):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self.force = force
        self.lock = threading.Lock()
        self._pending = 0
        self.url_cache = self._load(CACHE_DIR / "url-cache.json")
        self.local_cache = self._load(CACHE_DIR / "local-cache.json")
        self.pdf_cache = self._load(CACHE_DIR / "pdf-cache.json")

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self) -> None:
        for name, data in (
            ("url-cache.json", self.url_cache),
            ("local-cache.json", self.local_cache),
            ("pdf-cache.json", self.pdf_cache),
        ):
            (CACHE_DIR / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def save(self) -> None:
        with self.lock:
            self._save()

    @staticmethod
    def _thumb_name(key: str) -> str:
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".jpg"

    def _make_thumb(self, payload: bytes, key: str) -> str | None:
        try:
            import io

            from PIL import Image, ImageOps

            image = Image.open(io.BytesIO(payload))
            image = ImageOps.exif_transpose(image) or image
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, (241, 245, 249))
                flattened.paste(rgba, mask=rgba.split()[-1])
                image = flattened
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail((THUMB_EDGE, THUMB_EDGE))
            name = self._thumb_name(key)
            image.save(THUMB_DIR / name, "JPEG", quality=80)
            return name
        except Exception:
            return None

    def inspect_url(self, url: str) -> dict:
        key = candidate_key(url)
        with self.lock:
            cached = self.url_cache.get(key)
        if cached is not None and not self.force and (not cached.get("ok") or cached.get("thumb")):
            return cached
        payload = download_valid_image(url)
        if not payload:
            meta = {"ok": False, "key": key}
        else:
            source = payload.get("source") or url
            thumb = self._make_thumb(payload["bytes"], source)
            meta = {
                "ok": True,
                "key": key,
                "source": source,
                "width": payload.get("width"),
                "height": payload.get("height"),
                "fit": payload.get("fit") or "cover",
                "thumb": thumb,
            }
        self._store(self.url_cache, key, meta)
        return meta

    def _store(self, store: dict, key: str, meta: dict) -> None:
        with self.lock:
            store[key] = meta
            self._pending += 1
            if self._pending >= 50:
                self._pending = 0
                self._save()

    def inspect_local(self, path: str) -> dict:
        key = candidate_key(local=path)
        with self.lock:
            cached = self.local_cache.get(key)
        if cached is not None and not self.force:
            return cached
        if path.startswith("/"):
            absolute = ROOT / "public" / path.lstrip("/")
        else:
            candidate = Path(path)
            absolute = candidate if candidate.is_absolute() else ROOT / candidate
        try:
            data = absolute.read_bytes()
            info = inspect_image_bytes(data)
            meta = (
                {
                    "ok": True,
                    "key": key,
                    "source": path,
                    "width": info["width"],
                    "height": info["height"],
                    "fit": info["fit"],
                    "thumb": self._make_thumb(data, key),
                }
                if info
                else {"ok": False, "key": key}
            )
        except Exception:
            meta = {"ok": False, "key": key}
        self._store(self.local_cache, key, meta)
        return meta

    def inspect_pdf(self, path: str, slug: str, title: str) -> dict:
        key = "pdf:" + path
        with self.lock:
            cached = self.pdf_cache.get(key)
        if cached is not None and not self.force:
            return cached
        photos = extract_pdf_photos(Path(path), slug, title)
        if not photos:
            meta = {"ok": False, "key": key}
        else:
            best = photos[0]
            thumb = self._make_thumb(best["bytes"], key)
            meta = {
                "ok": True,
                "key": key,
                "source": f"{best.get('source')}",
                "width": best.get("width"),
                "height": best.get("height"),
                "fit": best.get("fit") or "cover",
                "thumb": thumb,
            }
        self._store(self.pdf_cache, key, meta)
        return meta


def archive_items() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for path in DATA_DIR.rglob("product.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id"):
            data["_path"] = str(path)
            items[data["id"]] = data
    return items


def build_candidates(
    item: dict, page: dict, current_key: str | None, current_url: str = ""
) -> list[dict]:
    item_tokens = model_tokens(item.get("slug") or "", item.get("title") or "", item.get("h1") or "")
    entries: list[dict] = []
    seen: set[str] = set()

    og_key = candidate_key(page.get("ogImage") or "")
    jsonld_keys = {candidate_key(u) for u in page.get("jsonLdImages") or []}
    twitter_key = candidate_key(page.get("twitterImage") or "")

    def add(cand: dict) -> None:
        key = cand["key"]
        if not key or key == "dam:" or key == "url:":
            return
        if key in seen:
            existing = next(c for c in entries if c["key"] == key)
            if SOURCE_BASE.get(cand["source"], 0) > SOURCE_BASE.get(existing["source"], 0):
                existing["source"] = cand["source"]
            return
        seen.add(key)
        entries.append(cand)

    for img in page.get("images") or []:
        url = img.get("srcset_best") or img.get("src") or ""
        if not url:
            continue
        key = candidate_key(url)
        source = "page"
        if key == og_key:
            source = "og"
        elif key in jsonld_keys:
            source = "jsonld"
        elif key == twitter_key:
            source = "og"
        add(
            {
                "key": key,
                "url": url,
                "local": None,
                "source": source,
                "alt": img.get("alt") or "",
                "link": img.get("link"),
                "heading": img.get("heading"),
                "is_current": key == current_key,
            }
        )

    for url, source in ((page.get("ogImage"), "og"), (page.get("twitterImage"), "og")):
        if not url:
            continue
        add(
            {
                "key": candidate_key(url),
                "url": url,
                "local": None,
                "source": source,
                "alt": "",
                "link": None,
                "heading": None,
                "is_current": candidate_key(url) == current_key,
            }
        )
    for url in page.get("jsonLdImages") or []:
        add(
            {
                "key": candidate_key(url),
                "url": url,
                "local": None,
                "source": "jsonld",
                "alt": "",
                "link": None,
                "heading": None,
                "is_current": candidate_key(url) == current_key,
            }
        )

    if current_url and current_key not in seen:
        add(
            {
                "key": candidate_key(current_url),
                "url": current_url,
                "local": None,
                "source": "current",
                "alt": "",
                "link": None,
                "heading": None,
                "is_current": True,
            }
        )

    hero_local = item.get("heroLocal") or ""
    if hero_local:
        add(
            {
                "key": candidate_key(local=hero_local),
                "url": None,
                "local": hero_local,
                "source": "current",
                "alt": "",
                "link": None,
                "heading": None,
                "is_current": True,
                "fixed_score": 62,
            }
        )



    paper_item = (item.get("kind") or "") in PAPER_KINDS
    for file in item.get("files") or []:
        name = (file.get("filename") or filename_of(file.get("url") or "")).lower()
        if not name.endswith(".pdf"):
            continue
        tokens = [t for t in item_tokens if len(t) >= 5]
        if not paper_item and not any(t in compact(name) for t in tokens):
            continue
        local_path = file.get("localPath") or ""
        path = (DATA_DIR / local_path) if local_path else None
        if not path or not path.exists():
            public = file.get("publicPath") or ""
            alt_path = (ROOT / "public" / public.lstrip("/")) if public else None
            path = alt_path if alt_path and alt_path.exists() else None
        if not path:
            continue
        kind_bonus = 40 if "poster" in name else 30 if "datasheet" in name or "factsheet" in name else 0
        entries.append(
            {
                "key": "pdf:" + str(path),
                "url": None,
                "local": str(path),
                "source": "pdf",
                "pdf": str(path),
                "pdf_bonus": kind_bonus,
                "alt": "",
                "link": None,
                "heading": None,
                "is_current": False,
            }
        )

    scored = []
    for cand in entries:
        if cand.get("fixed_score") is not None:
            result = {
                "key": cand["key"],
                "url": None,
                "local": cand["local"],
                "source": cand["source"],
                "score": cand["fixed_score"],
                "reasons": ["current-local"],
                "valid": None,
                "generic": False,
                "people": False,
                "hard": False,
                "width": None,
                "height": None,
                "fit": None,
                "thumb": None,
            }
        else:
            result = score_candidate(item, cand, item_tokens)
            result["score"] += cand.get("pdf_bonus", 0)
        result["pdf"] = cand.get("pdf")
        scored.append(result)
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


def pick_for_item(
    item: dict,
    page: dict,
    cache: ImageCache,
    current_key: str | None,
    current_url: str,
    family: dict | None,
    slug: str,
    title: str,
    max_valid: int,
    max_generic: int,
) -> dict:
    candidates = build_candidates(item, page, current_key, current_url)
    validated: list[dict] = []
    generic_valid = 0
    for cand in candidates:
        if cand.get("hard"):
            continue
        if cand.get("generic") or cand.get("people"):
            if generic_valid >= max_generic:
                continue
        else:
            if len([c for c in validated if not (c.get("generic") or c.get("people"))]) >= max_valid:
                continue
        key = cand["key"]
        if cand.get("pdf"):
            meta = cache.inspect_pdf(cand["pdf"], slug, title)
        elif cand.get("url"):
            meta = cache.inspect_url(cand["url"])
        else:
            meta = cache.inspect_local(cand["local"])
        if not meta.get("ok"):
            cand["valid"] = False
            continue
        cand["valid"] = True
        cand["width"] = meta.get("width")
        cand["height"] = meta.get("height")
        cand["fit"] = meta.get("fit")
        cand["thumb"] = meta.get("thumb")
        validated.append(cand)
        if cand.get("generic") or cand.get("people"):
            generic_valid += 1

    if family and family.get("hero") and not HARD_RE.search(family["hero"]):
        hero = family["hero"]
        meta = cache.inspect_local(hero)
        family_cand = {
            "key": candidate_key(local=hero),
            "url": None,
            "local": hero,
            "source": "family",
            "score": 0,
            "reasons": ["family"],
            "valid": bool(meta.get("ok")),
            "generic": False,
            "people": False,
            "hard": False,
            "width": meta.get("width"),
            "height": meta.get("height"),
            "fit": meta.get("fit"),
            "thumb": meta.get("thumb"),
        }
        if family_cand["valid"]:
            validated.append(family_cand)

    validated.sort(key=lambda c: c["score"], reverse=True)
    return {"candidates": validated, "all": candidates}


def override_candidate(item: dict, value: str, cache: ImageCache) -> dict:
    local = value if value.startswith("/") or value.startswith("data/") else ""
    if local:
        meta = cache.inspect_local(local)
        return {
            "key": candidate_key(local=local),
            "url": None,
            "local": local,
            "source": "override",
            "score": 10**9,
            "reasons": ["override"],
            "valid": bool(meta.get("ok")),
            "generic": False,
            "people": False,
            "hard": False,
            "width": meta.get("width"),
            "height": meta.get("height"),
            "fit": meta.get("fit"),
            "thumb": meta.get("thumb"),
        }
    meta = cache.inspect_url(value)
    return {
        "key": candidate_key(value),
        "url": value,
        "local": None,
        "source": "override",
        "score": 10**9,
        "reasons": ["override"],
        "valid": bool(meta.get("ok")),
        "generic": False,
        "people": False,
        "hard": False,
        "width": meta.get("width"),
        "height": meta.get("height"),
        "fit": meta.get("fit"),
        "thumb": meta.get("thumb"),
    }


def folder_for(item: dict) -> Path:
    bucket = item["bucket"]
    family = item["family"]
    slug = item["slug"]
    if bucket == "publications":
        return DATA_DIR / "publications" / family / slug
    if bucket == "hub":
        return DATA_DIR / "hub" / slug
    if slug == "_overview":
        return DATA_DIR / bucket / family
    return DATA_DIR / bucket / family / slug


def write_json(path: Path, data, indent: int | None = None, newline: bool = False) -> None:
    path.write_text(
        json.dumps(data, indent=indent, ensure_ascii=False) + ("\n" if newline else ""),
        encoding="utf-8",
    )


def apply_picks(picks: dict, catalog: dict, archive: dict, cache: ImageCache) -> None:
    archive_catalog = None
    if ARCHIVE_CATALOG.exists():
        archive_catalog = json.loads(ARCHIVE_CATALOG.read_text(encoding="utf-8"))

    catalog_by_id = {entry["id"]: entry for entry in catalog["items"]}
    archive_catalog_by_id = (
        {entry["id"]: entry for entry in archive_catalog.get("items", [])} if archive_catalog else {}
    )

    updated = skipped = failed = 0
    for item_id, record in picks["items"].items():
        pick = record.get("pick")
        if not pick or not pick.get("valid"):
            failed += 1
            log(f"  FAIL {item_id}: no valid pick")
            continue
        entry = catalog_by_id.get(item_id)
        if not entry:
            failed += 1
            continue
        targets = [t for t in (entry, archive.get(item_id), archive_catalog_by_id.get(item_id)) if t]

        current_key = candidate_key(entry.get("hero") or "")
        if pick["key"] == current_key and entry.get("heroLocal"):
            skipped += 1
            continue

        if pick.get("local") and not pick.get("url") and not pick.get("pdf"):
            local = pick["local"]
            if local.startswith("/catalog/images/"):
                info = cache.inspect_local(local)
                if not info.get("ok"):
                    failed += 1
                    log(f"  FAIL {item_id}: local image unreadable {local}")
                    continue
                for target in targets:
                    target["heroLocal"] = local
                    target["heroFit"] = info.get("fit") or "cover"
                updated += 1
                continue
            pick = {**pick, "pdf": local}

        if pick.get("pdf"):
            photos = extract_pdf_photos(Path(pick["pdf"]), entry.get("slug") or "", entry.get("title") or "")
            if not photos:
                failed += 1
                log(f"  FAIL {item_id}: no photo in PDF {pick['pdf']}")
                continue
            payload = photos[0]
            source_url = payload.get("source") or entry.get("hero") or ""
        else:
            payload = download_valid_image(pick["url"])
            if not payload:
                failed += 1
                log(f"  FAIL {item_id}: download failed {pick['url']}")
                continue
            source_url = payload.get("source") or pick["url"]

        ext = payload["ext"]
        family = entry["family"]
        slug = entry["slug"]
        public_dir = ROOT / "public" / "catalog" / "images" / family
        public_dir.mkdir(parents=True, exist_ok=True)
        for stale in public_dir.glob(f"{slug}.*"):
            if stale.suffix.lower() != ext:
                stale.unlink(missing_ok=True)
        (public_dir / f"{slug}{ext}").write_bytes(payload["bytes"])

        folder = folder_for(entry)
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.glob("hero.*"):
            stale.unlink(missing_ok=True)
        (folder / f"hero{ext}").write_bytes(payload["bytes"])

        hero_local = f"/catalog/images/{family}/{slug}{ext}"
        for target in targets:
            target["hero"] = source_url
            target["heroLocal"] = hero_local
            target["heroFit"] = payload.get("fit") or "cover"
        updated += 1
        if updated % 25 == 0:
            log(f"  applied {updated}")

    write_json(CATALOG, catalog)
    if archive_catalog is not None:
        write_json(ARCHIVE_CATALOG, archive_catalog, indent=2)
    for entry in archive.values():
        path = entry.get("_path")
        if not path:
            continue
        clean = {k: v for k, v in entry.items() if k != "_path"}
        write_json(Path(path), clean, indent=2, newline=True)
    cache.save()
    log(f"apply: updated={updated} skipped={skipped} failed={failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true", help="ignore the validation cache")
    parser.add_argument("--max-valid", type=int, default=6)
    parser.add_argument("--max-generic", type=int, default=2)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["items"]
    archive = archive_items()
    overrides = {}
    if OVERRIDES.exists():
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    cache = ImageCache(force=args.force)
    families = {fam["id"]: fam for fam in catalog.get("families", [])}

    items = catalog["items"]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        items = [i for i in items if i["id"] in wanted]
    if args.limit:
        items = items[: args.limit]
    log(f"picking for {len(items)} items ({len(overrides)} overrides)")

    def work(item: dict) -> dict:
        item_id = item["id"]
        page = candidates.get(item_id) or {"images": [], "ogImage": "", "jsonLdImages": []}
        archive_entry = archive.get(item_id) or {}
        current_url = item.get("hero") or archive_entry.get("hero") or ""
        current_key = candidate_key(current_url) if current_url else None
        if overrides.get(item_id):
            pick = override_candidate(item, overrides[item_id], cache)
            pool = [pick]
        else:
            built = pick_for_item(
                item,
                page,
                cache,
                current_key,
                current_url,
                families.get(item.get("family")),
                item.get("slug") or "",
                item.get("title") or "",
                args.max_valid,
                args.max_generic,
            )
            pool = built["candidates"]
            pick = pool[0] if pool else None
        return {
            "id": item_id,
            "family": item.get("family"),
            "slug": item.get("slug"),
            "bucket": item.get("bucket"),
            "title": item.get("title"),
            "kind": item.get("kind"),
            "pick": pick,
            "candidates": pool[:12],
        }

    results: dict[str, dict] = {}
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for done, record in enumerate(executor.map(work, items), 1):
            results[record["id"]] = record
            if done % 20 == 0 or done == len(items):
                log(f"  {done}/{len(items)}")

    # Cross-item dedupe: overrides first, then strongest picks keep their image.
    claimed: dict[str, str] = {}
    override_ids = [i for i in results if overrides.get(i) and results[i]["pick"]]
    order = override_ids + sorted(
        (i for i in results if i not in override_ids and results[i]["pick"]),
        key=lambda i: (results[i]["pick"]["score"], results[i]["id"]),
        reverse=True,
    )
    for item_id in order:
        record = results[item_id]
        pick = record["pick"]
        if not pick.get("valid"):
            continue
        free = next(
            (c for c in record["candidates"] if c.get("valid") and c["key"] not in claimed),
            None,
        )
        if free is None and pick["key"] in claimed:
            pick["duplicate"] = True
            pick["reasons"] = list(pick.get("reasons", [])) + ["shared:" + claimed.get(pick["key"], "")]
        else:
            chosen = free or pick
            chosen.pop("duplicate", None)
            record["pick"] = chosen
        picked = record["pick"]
        pick["duplicate"] = picked.get("duplicate", False)
        claimed[picked["key"]] = item_id

    stats = defaultdict(int)
    no_pick = []
    duplicates = []
    for item_id, record in results.items():
        pick = record.get("pick")
        if not pick or not pick.get("valid"):
            stats["no-valid"] += 1
            no_pick.append(item_id)
        else:
            stats[pick["source"]] += 1
            if pick.get("duplicate"):
                duplicates.append(item_id)
    log(f"picks: {dict(stats)} duplicate-shared: {len(duplicates)}")
    if no_pick:
        log("no valid pick: " + ", ".join(no_pick))
    if duplicates:
        log("shared picks: " + ", ".join(duplicates))

    picks_payload = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stats": dict(stats),
        "duplicates": duplicates,
        "items": results,
    }
    PICKS.write_text(json.dumps(picks_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cache.save()
    log(f"wrote {PICKS.relative_to(ROOT)} in {time.time() - started:.0f}s")

    if args.apply:
        apply_picks(picks_payload, catalog, archive, cache)
        log("next: .venv-pages/Scripts/python scripts/optimize-catalog-images.py")
        log("next: npm run catalog:split")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
