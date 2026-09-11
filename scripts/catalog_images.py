"""Shared helpers for picking and validating Siemens Energy catalog photos."""

from __future__ import annotations

import io
import re
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BAD_HINTS = [
    (r"webheader|web-header|web_header", -95),
    (r"placeholder", -90),
    (r"icon|favicon|sprite|logo[-_]", -100),
    (r"rendition170", -40),
    (r"\.gif(?:$|\?)", -55),
    (r"classroom|power-academy|academy", -45),
    (r"track-record|grafik|graphic|stats-", -40),
    (r"social-media|linkedin|facebook|twitter", -80),
    (r"cookie|fallback|arrow-", -80),
    (r"key-visual-pps|energy.?system.?design", -35),
    (r"buttons---links", -80),
]

GOOD_HINTS = [
    (r"sidecut|side[-_]?cut", 60),
    (r"side[-_]?view|seitenansicht|sideview", 55),
    (r"on[-_]?white|onwhite", 28),
    (r"on[-_]?transparent|transparent", 22),
    (r"fullmodel|full-model|coreengine", 18),
    (r"rendition(?:960|1280)", 8),
    (r"keyvisual|key-visual|key_visual", 6),
    (r"product", 8),
]

MAX_EDGE = 1600
MIN_W = 360
MIN_H = 180


def filename_of(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url or "").path)
    return path.rsplit("/", 1)[-1].lower()


def model_tokens(*parts: str) -> set[str]:
    blob = " ".join(p or "" for p in parts).lower()
    toks: set[str] = set()
    for m in re.findall(r"sgt-?[0-9]+[a-z0-9-]*", blob):
        compact = m.replace("-", "")
        toks.add(compact)
        toks.add(m)
    for m in re.findall(r"[0-9]{3,4}[a-z]{1,3}", blob):
        toks.add(m)
    for m in re.findall(r"[a-z]{2,}[0-9]{2,}[a-z0-9-]*", blob):
        toks.add(m.replace("-", ""))
    for raw in parts:
        s = re.sub(r"[^a-z0-9]+", "-", (raw or "").lower()).strip("-")
        if s and s not in {"_overview", "overview", "index"}:
            toks.add(s.replace("-", ""))
            if len(s) > 4:
                toks.add(s)
    return {t for t in toks if len(t) >= 4}


def score_image_url(url: str, slug: str = "", title: str = "") -> int:
    if not url:
        return -1000
    name = filename_of(url)
    blob = name + " " + url.lower()
    score = 0
    for pat, w in BAD_HINTS:
        if re.search(pat, blob):
            score += w
    for pat, w in GOOD_HINTS:
        if re.search(pat, blob):
            score += w
    tokens = model_tokens(slug, title)
    compact_name = re.sub(r"[^a-z0-9]+", "", name)
    for tok in tokens:
        compact_tok = re.sub(r"[^a-z0-9]+", "", tok)
        if compact_tok and compact_tok in compact_name:
            score += 70
            break
        if tok in name:
            score += 55
            break
    file_models = [
        re.sub(r"[^a-z0-9]+", "", m)
        for m in re.findall(r"sgt-?[0-9]+[a-z0-9-]*", name)
    ]
    item_models = [
        re.sub(r"[^a-z0-9]+", "", t)
        for t in tokens
        if t.startswith("sgt") and any(c.isdigit() for c in t)
    ]
    if file_models and item_models:
        if not any(
            fm == im or fm.startswith(im) or im.startswith(fm)
            for fm in file_models
            for im in item_models
        ):
            score -= 70
    if "assets.siemens-energy.com/dam/" in url:
        score += 8
    if name.endswith(".gif"):
        score -= 40
    if "rendition170" in blob:
        score -= 25
    return score


def dam_variants(url: str) -> list[str]:
    if not url:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(u: str) -> None:
        u = (u or "").strip()
        if not u or " " in u or u in seen:
            return
        seen.add(u)
        out.append(u)

    add(url)
    base = url.split("?")[0]
    # DAM rejects unencoded spaces in "Original file"
    add(base.replace(" ", "%20"))
    add(base + "?apr_optimization=false")
    add(base.replace(" ", "%20") + "?apr_optimization=false")

    replacements = [
        "Rendition1280",
        "Rendition960",
        "Rendition480",
        "Original file",
        "Original%20file",
    ]
    for label in replacements:
        v = re.sub(r"(Original(?:%20| )file|Rendition\d+)", label, base, flags=re.I)
        add(v)
        add(v + "?apr_optimization=false")

    # PNG originals from this DAM often 404 as HTML; try jpeg siblings and case variants.
    for u in list(out):
        if re.search(r"\.png(?:$|\?)", u, re.I):
            add(re.sub(r"\.png", ".jpg", u, flags=re.I))
            add(re.sub(r"\.png", ".jpeg", u, flags=re.I))
            add(re.sub(r"-png_", "-jpg_", u, flags=re.I))
            add(re.sub(r"_png_", "_jpg_", u, flags=re.I))
        if re.search(r"\.JPG(?:$|\?)", u):
            add(u.replace(".JPG", ".jpg").replace(".JPG?", ".jpg?"))
        if re.search(r"\.JPEG(?:$|\?)", u):
            add(re.sub(r"\.JPEG", ".jpeg", u))
        if re.search(r"\.PNG(?:$|\?)", u):
            add(u.replace(".PNG", ".png").replace(".PNG?", ".png?"))

    def rank(u: str) -> int:
        n = u.lower()
        if "rendition1280" in n:
            return 0
        if "rendition960" in n:
            return 1
        if "original" in n:
            return 2
        if "rendition480" in n:
            return 4
        if "rendition170" in n:
            return 9
        return 3

    out.sort(key=rank)
    return out


def fetch_bytes(url: str, timeout: int = 25) -> tuple[bytes, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.siemens-energy.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = resp.read(12 * 1024 * 1024)
        return data, ctype


def inspect_image_bytes(data: bytes) -> dict | None:
    if not data or len(data) < 800:
        return None
    head = data[:32].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html") or head.startswith(b"<?xml"):
        return None
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im) or im
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w < MIN_W or h < MIN_H:
        return None
    sample = im.convert("RGB")
    sample.thumbnail((48, 48))
    pixels = list(sample.getdata())
    n = len(pixels) or 1
    avg = sum((p[0] + p[1] + p[2]) / 3 for p in pixels) / n
    uniq = len(set(pixels))
    var = sum(((p[0] + p[1] + p[2]) / 3 - avg) ** 2 for p in pixels) / n
    if uniq < 16 and var < 140:
        return None
    if avg < 20 and var < 220:
        return None
    has_alpha = im.mode in {"RGBA", "LA"} or (im.mode == "P" and "transparency" in im.info)
    light = 0
    if has_alpha:
        rgba = im.convert("RGBA")
        tiny = rgba.copy()
        tiny.thumbnail((48, 48))
        apx = list(tiny.getdata())
        avg_a = sum(p[3] for p in apx) / (len(apx) or 1)
        has_alpha = avg_a < 248
        light = sum(1 for p in apx if p[3] < 40 or (p[0] + p[1] + p[2]) / 3 > 230)
    else:
        light = sum(1 for p in pixels if (p[0] + p[1] + p[2]) / 3 > 230)
    light_ratio = light / n
    fit = "contain" if has_alpha or light_ratio > 0.38 else "cover"
    return {
        "image": im,
        "width": w,
        "height": h,
        "avg": avg,
        "uniq": uniq,
        "var": var,
        "has_alpha": has_alpha,
        "fit": fit,
        "bytes": len(data),
    }


def encode_hero(info: dict) -> tuple[bytes, str, str]:
    im: Image.Image = info["image"]
    w, h = im.size
    if max(w, h) > MAX_EDGE:
        im = im.copy()
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    fit = info["fit"]
    if info.get("has_alpha"):
        buf = io.BytesIO()
        im.convert("RGBA").save(buf, format="PNG", optimize=True)
        return buf.getvalue(), ".png", fit
    rgb = im.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=86, optimize=True)
    return buf.getvalue(), ".jpg", fit


def download_valid_image(url: str, cache: dict | None = None) -> dict | None:
    """Try a URL and its DAM variants; return encoded hero payload or None."""
    cache = cache if cache is not None else {}
    for variant in dam_variants(url):
        if variant in cache:
            result = cache[variant]
            if result:
                return result
            continue
        try:
            data, ctype = fetch_bytes(variant)
        except Exception:
            cache[variant] = None
            continue
        if ctype.startswith("text/"):
            cache[variant] = None
            continue
        info = inspect_image_bytes(data)
        if not info:
            cache[variant] = None
            continue
        payload, ext, fit = encode_hero(info)
        result = {
            "bytes": payload,
            "ext": ext,
            "fit": fit,
            "source": variant,
            "width": info["width"],
            "height": info["height"],
        }
        cache[variant] = result
        return result
    return None


def extract_pdf_photos(pdf_path: Path, slug: str = "", title: str = "") -> list[dict]:
    """Largest photographic embeds, plus a first-page render as last resort."""
    try:
        import pymupdf
    except Exception:
        return []
    if not pdf_path.exists() or pdf_path.stat().st_size < 8_000:
        return []
    name = pdf_path.name.lower()
    boost = 0
    if "poster" in name:
        boost += 25
    if any(t in name.replace("-", "") for t in model_tokens(slug, title)):
        boost += 35
    if "brochure" in name or "portfolio" in name:
        boost += 8
    if "factsheet" in name or "datasheet" in name:
        boost += 12
    out: list[dict] = []
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return []
    try:
        seen: set[int] = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    continue
                data = extracted.get("image") or b""
                info = inspect_image_bytes(data)
                if not info:
                    continue
                w, h = info["width"], info["height"]
                if w * h < 180_000:
                    continue
                payload, ext, fit = encode_hero(info)
                score = boost + min(40, (w * h) // 80_000)
                if info["fit"] == "contain":
                    score += 8
                out.append(
                    {
                        "bytes": payload,
                        "ext": ext,
                        "fit": fit,
                        "source": f"pdf:{pdf_path.name}",
                        "width": w,
                        "height": h,
                        "score": score,
                    }
                )
        # Document thumbnail — useful for papers, weak for product posters (lots of type).
        if not out and doc.page_count:
            page = doc[0]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False)
            data = pix.tobytes("jpeg")
            info = inspect_image_bytes(data)
            if info and info["uniq"] > 40:
                payload, ext, fit = encode_hero(info)
                out.append(
                    {
                        "bytes": payload,
                        "ext": ext,
                        "fit": "cover",
                        "source": f"pdf-page:{pdf_path.name}",
                        "width": info["width"],
                        "height": info["height"],
                        "score": boost - 15,
                    }
                )
    finally:
        doc.close()
    out.sort(key=lambda r: r.get("score", 0), reverse=True)
    return out[:3]
