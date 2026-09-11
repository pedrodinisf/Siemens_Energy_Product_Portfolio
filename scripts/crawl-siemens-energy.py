#!/usr/bin/env python3
"""Crawl Siemens Energy product portfolio, publications, and downloads."""

from __future__ import annotations

import concurrent.futures
import hashlib
import html as html_lib
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog_images import download_valid_image, score_image_url

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE = "https://www.siemens-energy.com"
SITEMAP = f"{BASE}/global/en.sitemap.xml"
ELASTIC = "https://prod-deployment-siemens-energy.ent.westeurope.azure.elastic-cloud.com"
ENGINE = "siemensenergy-global-en"
SEARCH_KEY = "search-9rka2u8qc75nq2wz6j3zh7p2"

ROOT = Path("/workspace/data/siemens-energy")
PUBLIC = Path("/workspace/public/catalog")
SRC_DATA = Path("/workspace/src/data")
MAX_PDF_BYTES = 55 * 1024 * 1024
PAGE_WORKERS = 8
FILE_WORKERS = 6
MAX_BODY_CHARS = 12000

DOC_EXT = (".pdf", ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".zip")
SKIP_IMG_HINTS = (
    "icon",
    "logo",
    "social-media",
    "buttons---links",
    "fallback",
    "arrow-",
    "facebook",
    "linkedin",
)

lock = threading.Lock()
progress = {"pages": 0, "files": 0, "errors": 0}


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def slugify(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:120] or "untitled"


def fetch(url: str, timeout: int = 35, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        final = resp.geturl()
        if binary:
            return data, ctype, final
        return data.decode("utf-8", "replace"), ctype, final


def abs_url(href: str, page_url: str) -> str:
    if not href:
        return ""
    href = html_lib.unescape(href).strip()
    if href.startswith("//"):
        return "https:" + href
    return urllib.parse.urljoin(page_url, href)


def normalize_url(url: str) -> str:
    url = (url or "").split("#")[0].split("?")[0].strip()
    if url.endswith("/"):
        url = url[:-1]
    if url and not url.endswith(".html") and "siemens-energy.com" in url:
        path = urllib.parse.urlparse(url).path
        last = path.rsplit("/", 1)[-1]
        if path and "." not in last:
            url = url + ".html"
    return url


def clean_text(s: str) -> str:
    s = html_lib.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def dam_id(url: str) -> str | None:
    m = re.search(r"/dam/([0-9a-f-]{36})/", url, re.I)
    return m.group(1) if m else None


def file_kind(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    name = urllib.parse.unquote(path).lower()
    if "white" in name and "paper" in name:
        return "white-paper"
    if "brochure" in name or "portfolio" in name:
        return "brochure"
    if "datasheet" in name or "data-sheet" in name or "factsheet" in name:
        return "datasheet"
    if "technical" in name or "tech-paper" in name:
        return "technical-paper"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith((".ppt", ".pptx")):
        return "presentation"
    if name.endswith((".doc", ".docx")):
        return "document"
    if name.endswith((".xls", ".xlsx")):
        return "spreadsheet"
    if name.endswith(".zip"):
        return "archive"
    return "file"


def nice_filename(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    name = path.rsplit("/", 1)[-1]
    name = re.sub(r"(_Original(?:%20| )file|_Rendition\d+)", "", name, flags=re.I)
    name = re.sub(r"[?#].*$", "", name)
    name = re.sub(r"[^\w.\-()+]+", "_", name)
    if not name or name in {".pdf", ".PDF"}:
        did = dam_id(url) or hashlib.md5(url.encode()).hexdigest()[:10]
        name = f"document-{did}.pdf"
    return name[:160]


class PageParser(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.title = ""
        self.metas: dict[str, str] = {}
        self.in_title = False
        self.in_heading = False
        self.heading_tag = ""
        self.heading_buf: list[str] = []
        self.headings: list[dict] = []
        self.in_p = False
        self.p_buf: list[str] = []
        self.paragraphs: list[str] = []
        self.in_li = False
        self.li_buf: list[str] = []
        self.bullets: list[str] = []
        self.skip_depth = 0
        self.skip_tags = {"script", "style", "noscript", "svg"}
        self.in_table = False
        self.in_tr = False
        self.in_cell = False
        self.cell_tag = ""
        self.cell_buf: list[str] = []
        self.row: list[str] = []
        self.tables: list[list[list[str]]] = []
        self.cur_table: list[list[str]] = []
        self.links: list[dict] = []
        self.images: list[dict] = []
        self.teasers: list[dict] = []
        self.cur_teaser: dict | None = None
        self.teaser_desc_buf: list[str] = []
        self.in_teaser_title = False
        self.downloads: list[dict] = []
        self.faqs: list[dict] = []
        self.cur_faq_q = ""
        self.in_accordion_title = False
        self.acc_buf: list[str] = []
        self.in_accordion_panel = False
        self.panel_buf: list[str] = []
        self.breadcrumbs: list[str] = []
        self.in_breadcrumb = False
        self.exclude_nav = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        name = a.get("data-g-name", "")
        if a.get("data-elastic-exclude") is not None and tag in {"div", "nav", "footer", "header"}:
            self.exclude_nav += 1
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if tag == "meta":
            key = a.get("name") or a.get("property") or a.get("itemprop")
            if key and a.get("content"):
                self.metas[key] = a["content"]
        if tag == "title":
            self.in_title = True

        if "aem-product-teaser-item" in cls and a.get("data-ste-teaser-title"):
            self.cur_teaser = {
                "title": a.get("data-ste-teaser-title", ""),
                "type": a.get("data-ste-teaser-type", "product"),
                "href": "",
                "image": "",
                "description": "",
            }
        if self.cur_teaser and tag == "a" and a.get("href"):
            if not self.cur_teaser["href"]:
                self.cur_teaser["href"] = abs_url(a["href"], self.page_url)
        if self.cur_teaser and tag == "img" and a.get("src"):
            if not self.cur_teaser["image"]:
                self.cur_teaser["image"] = abs_url(a["src"], self.page_url)
                self.cur_teaser["imageAlt"] = a.get("alt", "")

        if tag in {"h1", "h2", "h3"} and self.exclude_nav == 0:
            self.in_heading = True
            self.heading_tag = tag
            self.heading_buf = []
        if tag == "p" and self.exclude_nav == 0 and not self.cur_teaser:
            self.in_p = True
            self.p_buf = []
        if tag == "li" and self.exclude_nav == 0:
            self.in_li = True
            self.li_buf = []

        if tag == "table":
            self.in_table = True
            self.cur_table = []
        if self.in_table and tag == "tr":
            self.in_tr = True
            self.row = []
        if self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.cell_tag = tag
            self.cell_buf = []

        if tag == "a" and a.get("href"):
            href = abs_url(a["href"], self.page_url)
            label = a.get("aria-label") or a.get("title") or ""
            is_dl = (
                name == "TertiaryLinkDownload"
                or "download" in cls.lower()
                or href.lower().split("?")[0].endswith(DOC_EXT)
            )
            rec = {"href": href, "label": label, "download": is_dl}
            self.links.append(rec)
            if is_dl:
                self.downloads.append(rec)

        if tag == "img" and a.get("src") and self.exclude_nav == 0:
            src = abs_url(a["src"], self.page_url)
            if not any(h in src.lower() for h in SKIP_IMG_HINTS):
                self.images.append({"src": src, "alt": a.get("alt", "")})

        if "cmp-accordion__title" in cls:
            self.in_accordion_title = True
            self.acc_buf = []
        if "cmp-accordion__panel" in cls:
            self.in_accordion_panel = True
            self.panel_buf = []

        if "aem-product-teaser-item__title" in cls:
            self.in_teaser_title = True

    def handle_endtag(self, tag):
        if tag in {"div", "nav", "footer", "header"} and self.exclude_nav:
            self.exclude_nav -= 1
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
        if self.in_heading and tag == self.heading_tag:
            t = clean_text("".join(self.heading_buf))
            if t:
                self.headings.append({"level": tag, "text": t})
            self.in_heading = False
        if tag == "p" and self.in_p:
            t = clean_text("".join(self.p_buf))
            if t and len(t) > 40:
                self.paragraphs.append(t)
            self.in_p = False
        if tag == "li" and self.in_li:
            t = clean_text("".join(self.li_buf))
            if t and 12 < len(t) < 400:
                self.bullets.append(t)
            self.in_li = False
        if self.in_cell and tag in {"td", "th"}:
            self.row.append(clean_text("".join(self.cell_buf)))
            self.in_cell = False
        if self.in_tr and tag == "tr":
            if any(self.row):
                self.cur_table.append(self.row)
            self.in_tr = False
        if self.in_table and tag == "table":
            if self.cur_table:
                self.tables.append(self.cur_table)
            self.in_table = False
        if self.in_accordion_title and tag in {"span", "button", "h3", "h2", "div"}:
            if self.acc_buf:
                self.cur_faq_q = clean_text("".join(self.acc_buf))
                self.in_accordion_title = False
        if self.in_accordion_panel and tag == "div" and self.panel_buf:
            ans = clean_text("".join(self.panel_buf))
            if self.cur_faq_q and ans:
                self.faqs.append({"q": self.cur_faq_q, "a": ans[:2000]})
            self.in_accordion_panel = False
            self.panel_buf = []
        if tag == "div" and self.cur_teaser and not self.in_teaser_title:
            # closed later via finalize
            pass
        if tag == "div" and self.cur_teaser:
            # detect teaser item close by class not available here; handled in start of next
            pass

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title += data
        if self.in_heading:
            self.heading_buf.append(data)
        if self.in_p:
            self.p_buf.append(data)
        if self.in_li:
            self.li_buf.append(data)
        if self.in_cell:
            self.cell_buf.append(data)
        if self.in_accordion_title:
            self.acc_buf.append(data)
        if self.in_accordion_panel:
            self.panel_buf.append(data)
        if self.cur_teaser and not self.cur_teaser.get("description"):
            # capture nearby text as description later
            t = data.strip()
            if t and len(t) > 40:
                self.teaser_desc_buf.append(t)


def finalize_teasers(raw_html: str, page_url: str) -> list[dict]:
    teasers = []
    for m in re.finditer(
        r'<div class="aem-product-teaser-item"[^>]*data-ste-teaser-title="([^"]+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        raw_html,
        re.S,
    ):
        block = m.group(2)
        title = clean_text(m.group(1))
        hrefs = re.findall(r'href="([^"]+)"', block)
        href = ""
        for h in hrefs:
            au = abs_url(h, page_url)
            if "/product" in au and not au.lower().endswith(DOC_EXT):
                href = au
                break
        if not href and hrefs:
            href = abs_url(hrefs[0], page_url)
        img = ""
        im = re.search(r'<img[^>]+src="([^"]+)"', block)
        if im:
            img = abs_url(im.group(1), page_url)
        desc = ""
        ps = re.findall(r"<p[^>]*>(.*?)</p>", block, re.S)
        if ps:
            desc = clean_text(re.sub(r"<[^>]+>", " ", ps[0]))
        teasers.append(
            {"title": title, "href": href, "image": img, "description": desc[:500]}
        )
    if teasers:
        return teasers
    # fallback: data-ste-teaser-title only
    for m in re.finditer(r'data-ste-teaser-title="([^"]+)"', raw_html):
        teasers.append({"title": clean_text(m.group(1)), "href": "", "image": "", "description": ""})
    return teasers


def extract_pdfs(raw_html: str, page_url: str, extra_labels: dict) -> list[dict]:
    found = {}
    patterns = [
        r'href="([^"]+\.pdf(?:\?[^"]*)?)"',
        r"href='([^']+\.pdf(?:\?[^']*)?)'",
        r'(https://assets\.siemens-energy\.com/dam/[^"\'\s<>]+)',
    ]
    for pat in patterns:
        for href in re.findall(pat, raw_html, re.I):
            url = abs_url(href, page_url)
            path = urllib.parse.urlparse(url).path.lower()
            if not path.endswith(DOC_EXT) and ".pdf" not in path.lower():
                continue
            if "rendition" in path.lower():
                continue
            did = dam_id(url) or url
            if did in found:
                continue
            label = extra_labels.get(url) or extra_labels.get(did) or nice_filename(url)
            found[did] = {
                "url": url,
                "label": clean_text(re.sub(r"[_%20]+", " ", urllib.parse.unquote(label))),
                "kind": file_kind(url),
                "id": did,
            }
    # labels from nearby aria-label
    for m in re.finditer(
        r'<a[^>]+href="([^"]+)"[^>]*aria-label="([^"]+)"', raw_html, re.I
    ):
        url = abs_url(m.group(1), page_url)
        did = dam_id(url) or url
        if did in found and m.group(2).lower() not in {"download", "icon"}:
            found[did]["label"] = clean_text(m.group(2))
    return list(found.values())


def specs_from_tables(tables: list[list[list[str]]]) -> list[dict]:
    specs = []
    for table in tables:
        if not table:
            continue
        # 2-col key/value
        if all(len(r) == 2 for r in table):
            headerish = table[0][0].lower() in {"specification", "parameter", "item", "key"}
            rows = table[1:] if headerish else table
            for k, v in rows:
                if k and v and len(k) < 80:
                    specs.append({"name": k, "value": v})
            continue
        # header row + data
        if len(table) >= 2 and len(table[0]) >= 2:
            headers = table[0]
            for row in table[1:]:
                item = {}
                for i, h in enumerate(headers):
                    if i < len(row) and h:
                        item[h] = row[i]
                if item:
                    specs.append(item)
    # de-dup
    seen = set()
    out = []
    for s in specs:
        key = json.dumps(s, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out[:80]


def classify_url(url: str) -> tuple[str, str, str]:
    """Return (bucket, family, slug)."""
    path = urllib.parse.urlparse(url).path.replace(".html", "").strip("/")
    parts = path.split("/")
    # .../home/products-services/product-offerings/gas-turbines[/hl-class]
    # .../home/products-services/product/sgt-800
    try:
        i = parts.index("products-services")
        rest = parts[i + 1 :]
    except ValueError:
        if "publications" in parts:
            kind = "white-paper" if "white-paper" in path else "technical-paper" if "technical-paper" in path else "publication"
            slug = parts[-1] if parts else "pub"
            return "publications", kind, slug
        return "other", "site", parts[-1] if parts else "page"

    if not rest:
        return "hub", "products-services", "index"

    head = rest[0]
    if head == "product-offerings":
        if len(rest) == 1:
            return "hub", "product-offerings", "index"
        family = rest[1]
        slug = "-".join(rest[2:]) if len(rest) > 2 else "_overview"
        return "products", family, slug
    if head == "product":
        slug = rest[1] if len(rest) > 1 else "unknown"
        family = infer_family(slug)
        return "products", family, slug
    if head == "service-offerings":
        family = rest[1] if len(rest) > 1 else "_overview"
        slug = "-".join(rest[2:]) if len(rest) > 2 else "_overview"
        return "services", family, slug
    if head == "solutions-industry":
        family = rest[1] if len(rest) > 1 else "_overview"
        slug = "-".join(rest[2:]) if len(rest) > 2 else "_overview"
        return "solutions", f"industry-{family}", slug
    if head == "solutions-usecase":
        family = rest[1] if len(rest) > 1 else "_overview"
        slug = "-".join(rest[2:]) if len(rest) > 2 else "_overview"
        return "solutions", f"usecase-{family}", slug
    if head == "training":
        return "services", "training", "_overview"
    return "other", head, rest[-1]


FAMILY_HINTS = [
    (r"^sgt|^sgen-?a", "gas-turbines"),
    (r"^sgen", "generators"),
    (r"^sst|^d-r-steam|^utility-steam|^industrial-steam", "steam-turbines"),
    (r"transformer|geafol|carepole|reactor|traction|phase-shifting|hvdc-transformer", "transformers"),
    (r"arrester", "surge-arresters"),
    (r"gis|switchgear|circuit|disconnector|blue-high", "switchgear"),
    (r"compress|recip|dry-gas|pipeline|integrally|single-shaft|single-stage|hsrc|co2-comp|hydrogen-comp", "compression"),
    (r"hvdc|facts|svc|upfc|msc-|grid-forming|mvdc|medium-voltage-direct", "grid-transmission"),
    (r"subsea|podded|propulsion|life-ocean", "subsea-marine"),
    (r"hydrogen|electrolyzer|power-to-x", "hydrogen-solutions"),
    (r"omnivise|t3000|icss|plant-saas|power-intelligence|process-information|fatigue|emidate", "digital"),
    (r"power-plant|combined-cycle|peaker|hybrid-power|seafloat|benson|nuclear|industrial-power|heavy-duty-power|modular-onsite", "power-plants"),
    (r"battery|bluevault|caes|storage", "storage"),
    (r"e-house|prefabricated|voltage-regulator|composite-insulator|dc-gis|synchronous", "grid-products"),
    (r"sensor|connector", "subsea-solutions"),
]


def infer_family(slug: str) -> str:
    s = slug.lower()
    for pat, fam in FAMILY_HINTS:
        if re.search(pat, s):
            return fam
    return "other-products"


def is_catalog_url(url: str) -> bool:
    if "siemens-energy.com" not in url:
        return False
    if "/global/en/" not in url:
        return False
    path = urllib.parse.urlparse(url).path
    if any(
        x in path
        for x in (
            "/products-services/",
            "/publications/white-paper",
            "/publications/technical-paper",
            "/publications.html",
        )
    ):
        if "/search-results" in path:
            return False
        if "/products-services/service/" in path and "/service-offerings" not in path:
            return False
        return True
    return False


def harvest_sitemap() -> list[str]:
    xml, _, _ = fetch(SITEMAP)
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    urls = [u for u in locs if is_catalog_url(u)]
    log(f"sitemap catalog urls: {len(urls)}")
    return urls


def harvest_elastic() -> list[str]:
    urls = []
    queries = [
        {"query": "product", "filters": {"url_path_dir2": ["products-services"]}},
        {"query": "", "filters": {"all": [{"url_path_dir2": "products-services"}]}},
        {"query": "brochure OR datasheet OR white paper", "page": {"size": 100}},
    ]
    # paginate products-services
    for page in range(1, 12):
        payload = {
            "query": "siemens energy",
            "page": {"size": 100, "current": page},
            "filters": {"all": [{"url_path_dir2": "products-services"}]},
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{ELASTIC}/api/as/v1/engines/{ENGINE}/search",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {SEARCH_KEY}",
                "Content-Type": "application/json",
                "User-Agent": UA,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            log(f"elastic page {page} fail: {e}")
            break
        results = data.get("results") or []
        if not results:
            break
        for r in results:
            u = (r.get("url") or r.get("es_page_path") or {}).get("raw")
            if u and is_catalog_url(u):
                urls.append(u)
        total = data.get("meta", {}).get("page", {}).get("total_pages", 1)
        if page >= total:
            break
        time.sleep(0.05)
    urls = sorted(set(urls))
    log(f"elastic catalog urls: {len(urls)}")
    return urls


def pick_hero(images: list[dict], teasers: list[dict] | None = None, slug: str = "", title: str = "") -> str:
    candidates: list[tuple[int, str]] = []
    for im in images or []:
        src = im.get("src") if isinstance(im, dict) else str(im)
        if not src:
            continue
        if "assets.siemens-energy.com/dam/" not in src and not src.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            continue
        candidates.append((score_image_url(src, slug, title), src))
    for t in teasers or []:
        src = (t or {}).get("image") or ""
        if src:
            candidates.append((score_image_url(src, slug, title) + 20, src))
    candidates.sort(key=lambda r: r[0], reverse=True)
    for score, src in candidates:
        if score < -30:
            continue
        return src
    return candidates[0][1] if candidates else ""


def to_markdown(item: dict) -> str:
    lines = [
        f"# {item['title']}",
        "",
        f"- **Type:** {item.get('kind')}",
        f"- **Family:** {item.get('familyLabel') or item.get('family')}",
        f"- **Source:** {item['url']}",
        "",
    ]
    if item.get("description"):
        lines += [item["description"], ""]
    if item.get("highlights"):
        lines += ["## Highlights", ""]
        for h in item["highlights"][:20]:
            lines.append(f"- {h}")
        lines.append("")
    specs = item.get("specs") or []
    if specs:
        lines += ["## Technical data", ""]
        if all(isinstance(s, dict) and "name" in s and "value" in s for s in specs[:3]):
            lines += ["| Parameter | Value |", "| --- | --- |"]
            for s in specs:
                if isinstance(s, dict) and "name" in s:
                    lines.append(f"| {s['name']} | {s['value']} |")
        else:
            for s in specs:
                if isinstance(s, dict):
                    lines.append("- " + "; ".join(f"{k}: {v}" for k, v in s.items()))
        lines.append("")
    if item.get("body"):
        lines += ["## Overview", "", item["body"][:8000], ""]
    faqs = item.get("faqs") or []
    if faqs:
        lines += ["## FAQ", ""]
        for f in faqs:
            lines.append(f"**{f['q']}**")
            lines.append("")
            lines.append(f"{f['a']}")
            lines.append("")
    files = item.get("files") or []
    if files:
        lines += ["## Downloads", ""]
        for f in files:
            local = f.get("localPath") or f.get("url")
            lines.append(f"- [{f.get('label') or f.get('filename')}]({local}) ({f.get('kind')})")
        lines.append("")
    teasers = item.get("related") or []
    if teasers:
        lines += ["## Related products", ""]
        for t in teasers:
            lines.append(f"- [{t.get('title')}]({t.get('href') or ''}) — {t.get('description','')[:180]}")
        lines.append("")
    lines += [
        "---",
        f"_Scraped from Siemens Energy public website. All trademarks belong to Siemens Energy AG._",
        "",
    ]
    return "\n".join(lines)


def parse_page(url: str, html: str) -> dict:
    parser = PageParser(url)
    try:
        parser.feed(html)
    except Exception:
        pass
    title = clean_text(parser.title) or clean_text(parser.metas.get("og:title") or "")
    desc = clean_text(
        parser.metas.get("description")
        or parser.metas.get("og:description")
        or parser.metas.get("es_search_text")
        or ""
    )
    labels = {}
    for d in parser.downloads:
        labels[d["href"]] = d.get("label") or ""
    files = extract_pdfs(html, url, labels)
    teasers = finalize_teasers(html, url)
    # follow-on product links
    child_links = []
    for a in parser.links:
        href = a["href"]
        if is_catalog_url(href) and href.rstrip("/") != url.rstrip("/"):
            child_links.append(href)
    bucket, family, slug = classify_url(url)
    family_label = family.replace("-", " ").title()
    kind = {
        "products": "product" if slug != "_overview" else "product-family",
        "services": "service",
        "solutions": "solution",
        "publications": "publication",
        "hub": "hub",
    }.get(bucket, "page")
    if "white-paper" in url:
        kind = "white-paper"
    elif "technical-paper" in url:
        kind = "technical-paper"

    body = "\n\n".join(parser.paragraphs[:18])[:MAX_BODY_CHARS]
    highlights = []
    seen_b = set()
    for b in parser.bullets:
        k = b.lower()
        if k in seen_b:
            continue
        seen_b.add(k)
        if any(x in k for x in ("cookie", "privacy", "linkedin", "facebook", "subscribe")):
            continue
        highlights.append(b)
        if len(highlights) >= 16:
            break

    hero = pick_hero(parser.images, teasers, slug, title)
    tags = parser.metas.get("es_localized_page_tags") or parser.metas.get("es_page_tags") or ""
    h1 = next((h["text"] for h in parser.headings if h["level"] == "h1"), title)

    return {
        "id": f"{family}/{slug}",
        "url": url,
        "title": title or h1,
        "h1": h1,
        "description": desc,
        "kind": kind,
        "bucket": bucket,
        "family": family,
        "familyLabel": family_label,
        "slug": slug,
        "tags": tags,
        "searchTitle": parser.metas.get("es_search_title") or title,
        "modified": parser.metas.get("es_page_date") or "",
        "hero": hero,
        "images": [im["src"] for im in parser.images[:8]],
        "highlights": highlights,
        "specs": specs_from_tables(parser.tables),
        "faqs": parser.faqs[:12],
        "body": body,
        "headings": [h["text"] for h in parser.headings[:20]],
        "files": files,
        "related": teasers,
        "discovered": sorted(set(child_links)),
    }


def folder_for(item: dict) -> Path:
    bucket = item["bucket"]
    family = item["family"]
    slug = item["slug"]
    if bucket == "publications":
        return ROOT / "publications" / family / slug
    if bucket == "hub":
        return ROOT / "hub" / slug
    if slug == "_overview":
        return ROOT / bucket / family
    return ROOT / bucket / family / slug


def safe_write(path: Path, content: str | bytes, binary=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def download_file(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > MAX_PDF_BYTES:
                return {"ok": False, "reason": f"too large ({cl} bytes)", "url": url}
            size = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        f.close()
                        tmp.unlink(missing_ok=True)
                        return {"ok": False, "reason": "too large mid-stream", "url": url}
                    f.write(chunk)
            tmp.replace(dest)
            with lock:
                progress["files"] += 1
            return {"ok": True, "bytes": size, "path": str(dest)}
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "reason": str(e), "url": url}


def download_image(url: str, dest: Path) -> str | None:
    if dest.exists() and dest.stat().st_size > 1000:
        existing = inspect_if_possible(dest)
        if existing:
            return str(dest)
    try:
        payload = download_valid_image(url)
        if not payload:
            return None
        dest = dest.with_suffix(payload["ext"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload["bytes"])
        return str(dest)
    except Exception:
        return None


def inspect_if_possible(path: Path) -> bool:
    try:
        from catalog_images import inspect_image_bytes

        return inspect_image_bytes(path.read_bytes()) is not None
    except Exception:
        return False


def crawl():
    ROOT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    SRC_DATA.mkdir(parents=True, exist_ok=True)

    urls = set(harvest_sitemap())
    try:
        urls.update(harvest_elastic())
    except Exception as e:
        log(f"elastic harvest skipped: {e}")

    # always include the offerings hub
    urls.add(f"{BASE}/global/en/home/products-services/product-offerings.html")
    urls.add(f"{BASE}/global/en/home/products-services.html")
    urls.add(f"{BASE}/global/en/home/publications.html")
    urls.add(f"{BASE}/global/en/home/publications/white-paper.html")
    urls.add(f"{BASE}/global/en/home/publications/technical-paper.html")

    queue = sorted(normalize_url(u) for u in urls)
    seen = set()
    items: dict[str, dict] = {}
    file_jobs = []  # (url, dest, pub, rec)

    log(f"starting crawl of {len(queue)} seed urls")

    def handle_url(url: str) -> dict | None:
        url = normalize_url(url)
        if url in seen:
            return None
        with lock:
            if url in seen:
                return None
            seen.add(url)
        try:
            html, ctype, final = fetch(url)
        except Exception as e:
            with lock:
                progress["errors"] += 1
            log(f"FAIL {url} :: {e}")
            return None
        final = normalize_url(final or url)
        item = parse_page(final or url, html)
        with lock:
            seen.add(final)
            items[item["id"]] = item
            progress["pages"] += 1
            if progress["pages"] % 15 == 0:
                log(f"pages={progress['pages']} errors={progress['errors']}")
        return item

    # BFS-ish: first pass seeds, then discovered
    round_n = 0
    pending = list(queue)
    while pending and round_n < 3:
        round_n += 1
        batch = [u for u in pending if u not in seen]
        pending = []
        log(f"round {round_n}: {len(batch)} urls")
        with concurrent.futures.ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
            futs = [ex.submit(handle_url, u) for u in batch]
            for fut in concurrent.futures.as_completed(futs):
                item = fut.result()
                if not item:
                    continue
                # discover more product pages
                if round_n < 3:
                    for d in item.get("discovered") or []:
                        d = normalize_url(d)
                        if is_catalog_url(d) and d not in seen:
                            pending.append(d)
                time.sleep(0.01)

    log(f"parsed {len(items)} pages; preparing downloads")

    def hero_job(item: dict):
        if not item.get("hero"):
            return
        folder = folder_for(item)
        dest = folder / "hero.jpg"
        local = download_image(item["hero"], dest)
        if not local:
            return
        ext = Path(local).suffix or ".jpg"
        pub = PUBLIC / "images" / item["family"] / f"{item['slug']}{ext}"
        try:
            pub.parent.mkdir(parents=True, exist_ok=True)
            pub.write_bytes(Path(local).read_bytes())
            item["heroLocal"] = f"/catalog/images/{item['family']}/{item['slug']}{ext}"
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(hero_job, list(items.values())))
    log("hero images done")

    # write pages + queue files
    seen_dams = {}
    for item in items.values():
        folder = folder_for(item)
        folder.mkdir(parents=True, exist_ok=True)
        new_files = []
        for f in item.get("files") or []:
            did = f.get("id") or dam_id(f["url"]) or hashlib.md5(f["url"].encode()).hexdigest()
            fname = nice_filename(f["url"])
            dest = folder / "files" / fname
            pub = PUBLIC / "files" / item["family"] / fname
            rec = {
                **f,
                "filename": fname,
                "localPath": str(dest.relative_to(ROOT)),
                "publicPath": f"/catalog/files/{item['family']}/{fname}",
            }
            if did in seen_dams:
                rec["localPath"] = seen_dams[did]
                rec["duplicate"] = True
                new_files.append(rec)
                continue
            seen_dams[did] = rec["localPath"]
            file_jobs.append((f["url"], dest, pub, rec))
            new_files.append(rec)
        item["files"] = new_files

    log(f"downloading {len(file_jobs)} unique documents")

    def do_file(job):
        url, dest, pub, rec = job
        res = download_file(url, dest)
        rec["download"] = res
        if res.get("ok"):
            try:
                pub.parent.mkdir(parents=True, exist_ok=True)
                if not pub.exists():
                    pub.write_bytes(dest.read_bytes())
            except Exception as e:
                rec["publicCopyError"] = str(e)
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=FILE_WORKERS) as ex:
        list(ex.map(do_file, file_jobs))

    # write per-item markdown + json
    catalog = []
    for item in sorted(items.values(), key=lambda x: (x["bucket"], x["family"], x["slug"])):
        folder = folder_for(item)
        safe_write(folder / "product.json", json.dumps(item, indent=2, ensure_ascii=False))
        safe_write(folder / "README.md", to_markdown(item))
        catalog.append(
            {
                "id": item["id"],
                "url": item["url"],
                "title": item["title"],
                "h1": item.get("h1"),
                "description": item.get("description"),
                "kind": item["kind"],
                "bucket": item["bucket"],
                "family": item["family"],
                "familyLabel": item.get("familyLabel"),
                "slug": item["slug"],
                "tags": item.get("tags"),
                "modified": item.get("modified"),
                "hero": item.get("hero"),
                "heroLocal": item.get("heroLocal"),
                "heroFit": item.get("heroFit") or "cover",
                "highlights": item.get("highlights") or [],
                "specs": item.get("specs") or [],
                "faqs": item.get("faqs") or [],
                "body": item.get("body") or "",
                "headings": item.get("headings") or [],
                "related": item.get("related") or [],
                "files": [
                    {
                        "url": f.get("url"),
                        "label": f.get("label"),
                        "kind": f.get("kind"),
                        "filename": f.get("filename"),
                        "localPath": f.get("localPath"),
                        "publicPath": f.get("publicPath"),
                        "downloaded": bool((f.get("download") or {}).get("ok")),
                        "bytes": (f.get("download") or {}).get("bytes"),
                    }
                    for f in item.get("files") or []
                ],
            }
        )

    families = defaultdict(lambda: {"id": "", "label": "", "bucket": "", "count": 0, "products": []})
    for it in catalog:
        if it["bucket"] not in {"products", "services", "solutions"}:
            continue
        fam = families[it["family"]]
        fam["id"] = it["family"]
        fam["label"] = it["familyLabel"]
        fam["bucket"] = it["bucket"]
        fam["count"] += 1
        fam["products"].append(it["id"])
        if it["slug"] == "_overview":
            fam["overview"] = it["id"]
            fam["description"] = it.get("description")
            fam["hero"] = it.get("heroLocal") or it.get("hero")
            if it.get("heroFit"):
                fam["heroFit"] = it["heroFit"]

    downloaded = sum(1 for it in catalog for f in it["files"] if f.get("downloaded"))
    total_files = sum(len(it["files"]) for it in catalog)
    summary = {
        "source": f"{BASE}/global/en/home/products-services/product-offerings.html",
        "scrapedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pages": len(catalog),
        "families": len(families),
        "filesDiscovered": total_files,
        "filesDownloaded": downloaded,
        "counts": {
            "products": sum(1 for i in catalog if i["bucket"] == "products"),
            "services": sum(1 for i in catalog if i["bucket"] == "services"),
            "solutions": sum(1 for i in catalog if i["bucket"] == "solutions"),
            "publications": sum(1 for i in catalog if i["bucket"] == "publications"),
        },
    }
    payload = {
        "summary": summary,
        "families": sorted(families.values(), key=lambda x: (-x["count"], x["label"])),
        "items": catalog,
    }
    out_json = json.dumps(payload, ensure_ascii=False)
    safe_write(ROOT / "catalog.json", json.dumps(payload, indent=2, ensure_ascii=False))
    safe_write(PUBLIC / "catalog.json", out_json)
    safe_write(SRC_DATA / "catalog.json", out_json)

    readme = f"""# Siemens Energy product portfolio

Scraped {summary['scrapedAt']} from the public Siemens Energy website.

- Pages: {summary['pages']}
- Families: {summary['families']}
- Files discovered: {summary['filesDiscovered']}
- Files downloaded: {summary['filesDownloaded']}

## Counts

- Products: {summary['counts']['products']}
- Services: {summary['counts']['services']}
- Solutions: {summary['counts']['solutions']}
- Publications: {summary['counts']['publications']}

## Layout

- `products/` — product families and individual products
- `services/` — service offerings
- `solutions/` — industry and use-case solutions
- `publications/` — white papers and technical papers
- Each product folder has `README.md`, `product.json`, optional `hero` image, and `files/`

All content is © Siemens Energy AG. Collected from publicly available pages for research/reference.
"""
    safe_write(ROOT / "README.md", readme)
    log(f"DONE pages={len(catalog)} files={downloaded}/{total_files} errors={progress['errors']}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        crawl()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
