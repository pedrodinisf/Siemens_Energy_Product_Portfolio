#!/usr/bin/env python3
"""Extract document metadata from the catalog's source pages.

One polite pass over every item URL in `src/data/catalog.json`, capturing for
each linked asset what the page itself says about it:

    document-candidates.json   per item: for every PDF/Office link, the card
                               title, anchor text, aria-label, nearest heading,
                               enclosing table row (Description / Policy number
                               / Date) and teaser type

The page markup carries the human-curated names ("Synchronous condenser
flyer"); the original scraper only kept `aria-label`, which is "Download" on
most cards. No document files are downloaded here.

Per-page results are cached under `data/siemens-energy/.doc-refetch-cache/` so
an interrupted run resumes without re-hitting the site.

    python3 scripts/refetch-documents.py [--workers 6] [--ids a,b]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html as html_lib
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
CACHE_DIR = DATA_DIR / ".doc-refetch-cache"
CATALOG = ROOT / "src" / "data" / "catalog.json"
OUT = DATA_DIR / "document-candidates.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
DOC_EXT_RE = re.compile(r"\.(?:pdf|pptx|ppt|xlsx|xls|docx|doc|zip)(?:\?|$)", re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
DATE_META = {
    "article:published_time", "date", "publication_date", "dc.date",
    "datepublished", "publishdate",
}
DATE_TEXT_RE = re.compile(
    r'(?:"dateStr"|"datePublished"|"publishDate")\s*:\s*"([^"]{4,40})"', re.I
)

_orig_getaddrinfo = socket.getaddrinfo


def prefer_ipv4() -> None:
    """CloudFront AAAA records blackhole here; Python tries them serially."""

    def ordered(host, port, family=0, type=0, proto=0, flags=0):
        results = _orig_getaddrinfo(host, port, family, type, proto, flags)
        return sorted(results, key=lambda r: 0 if r[0] == socket.AF_INET else 1)

    socket.getaddrinfo = ordered


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


def abs_url(href: str, page_url: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("data:", "javascript:", "mailto:", "#")):
        return ""
    return urllib.parse.urljoin(page_url, html_lib.unescape(href))


def is_doc_url(url: str) -> bool:
    if not url:
        return False
    path = urllib.parse.urlparse(url).path
    if DOC_EXT_RE.search(path):
        return True
    return bool(UUID_RE.search(path)) and "/dam/" in path


def uuid_of(url: str) -> str:
    match = UUID_RE.search(url or "")
    return match.group(0).lower() if match else ""


class DocumentExtractor(HTMLParser):
    """Anchors with their page context, plus escaped data-layer tables."""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.title = ""
        self.in_title = False
        self.skip_depth = 0
        self.metas: dict[str, str] = {}

        self.last_teaser_title = ""
        self.last_teaser_type = ""
        self.teaser = None
        self.depth = 0
        self.last_heading = ""
        self.current_heading = None

        self.anchors: list[dict] = []
        self.anchor_stack: list[dict] = []
        self.table_depth = 0
        self.row: dict | None = None
        self.cell: dict | None = None
        self.data_layers: list[str] = []

    def _excluded(self, tag: str, attrs: dict) -> bool:
        if tag in ("nav", "footer") or "data-elastic-exclude" in attrs:
            return True
        ident = (attrs.get("id") or "") + " " + (attrs.get("class") or "")
        return bool(
            re.search(r"onetrust|cookie[-_]?banner|consent[-_]banner", ident, re.I)
        )

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if self.skip_depth:
            if tag not in VOID_TAGS:
                self.skip_depth += 1
            return
        if tag in SKIP_TAGS:
            self.skip_depth = 1
            return
        if self._excluded(tag, a):
            self.skip_depth = 1
            return
        if tag not in VOID_TAGS:
            self.depth += 1
        if tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key in DATE_META and a.get("content"):
                self.metas.setdefault(key, a["content"])
            return
        if tag == "title":
            self.in_title = True
            return
        if "data-cmp-data-layer" in a:
            self.data_layers.append(a["data-cmp-data-layer"])
        if a.get("data-ste-teaser-title") or a.get("data-ste-teaser-type"):
            self.teaser = {
                "title": clean_text(a.get("data-ste-teaser-title") or ""),
                "type": a.get("data-ste-teaser-type") or "",
                "depth": self.depth,
            }
        if tag in HEADING_TAGS:
            self.current_heading = []
        if tag == "table":
            self.table_depth += 1
        elif tag == "tr" and self.table_depth:
            self.row = {"cells": []}
        elif tag in ("td", "th") and self.table_depth and self.row is not None:
            self.cell = {"text": [], "anchors": []}
            self.row["cells"].append(self.cell)
        if tag == "a":
            href = abs_url(a.get("href") or "", self.page_url)
            record = {
                "href": href,
                "anchorText": [],
                "ariaLabel": clean_text(a.get("aria-label") or ""),
                "cardTitle": self.teaser["title"] if self.teaser else "",
                "teaserType": self.teaser["type"] if self.teaser else "",
                "heading": self.last_heading,
                "row": self.row,
                "cell": self.cell,
                "gName": a.get("data-g-name", ""),
            }
            self.anchors.append(record)
            self.anchor_stack.append(record)
            if self.cell is not None:
                self.cell["anchors"].append(record)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag not in VOID_TAGS:
            self.depth = max(0, self.depth - 1)
            if self.teaser and self.depth < self.teaser["depth"]:
                self.teaser = None
        if tag == "title":
            self.in_title = False
            return
        if tag == "a" and self.anchor_stack:
            record = self.anchor_stack.pop()
            record["anchorText"] = clean_text("".join(record["anchorText"]))
            return
        if tag in HEADING_TAGS and self.current_heading is not None:
            text = clean_text("".join(self.current_heading))
            if text:
                self.last_heading = text
            self.current_heading = None
            return
        if tag == "table" and self.table_depth:
            self.table_depth -= 1
            if self.table_depth == 0:
                self.row = None
            return
        if tag == "tr":
            self.row = None
            return
        if tag in ("td", "th"):
            self.cell = None
            return

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title += data
        if self.current_heading is not None:
            self.current_heading.append(data)
        if self.anchor_stack:
            self.anchor_stack[-1]["anchorText"].append(data)
        if self.cell is not None:
            self.cell["text"].append(data)

    def documents(self) -> list[dict]:
        out = []
        seen = set()
        for record in self.anchors:
            href = record["href"]
            if not is_doc_url(href):
                continue
            uuid = uuid_of(href)
            dedupe = (uuid or href.split("?")[0]).lower()
            row_cells = []
            if record["row"] is not None:
                row_cells = [
                    clean_text("".join(cell["text"])) for cell in record["row"]["cells"]
                ]
            key = (dedupe, clean_text(record["anchorText"]), record["cardTitle"])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "uuid": uuid,
                    "href": href,
                    "cardTitle": record["cardTitle"],
                    "anchorText": clean_text(record["anchorText"]),
                    "ariaLabel": record["ariaLabel"],
                    "heading": record["heading"],
                    "teaserType": record["teaserType"],
                    "tableCells": row_cells,
                    "gName": record["gName"],
                }
            )
        return out


def parse_data_layer_tables(attrs: list[str], page_url: str) -> list[dict]:
    """Tables embedded as escaped HTML inside `data-cmp-data-layer` JSON."""
    tables = []
    for raw in attrs:
        if "<table" not in raw and "&lt;table" not in raw:
            continue
        try:
            payload = json.loads(html_lib.unescape(raw))
        except Exception:
            continue
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            xdm = value.get("xdm:text") or ""
            if "<table" not in xdm:
                continue
            header_cells = []
            rows = re.findall(r"<tr>(.*?)</tr>", xdm, re.S | re.I)
            for row_html in rows:
                cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)
                if not header_cells and all("<a" not in cell for cell in cells):
                    header_cells = [clean_text(re.sub(r"<[^>]+>", "", c)) for c in cells]
                    continue
                parsed = [
                    clean_text(re.sub(r"<[^>]+>", "", html_lib.unescape(cell)))
                    for cell in cells
                ]
                for href in HREF_RE.findall(row_html):
                    url = abs_url(href, page_url)
                    if not is_doc_url(url):
                        continue
                    tables.append(
                        {
                            "uuid": uuid_of(url),
                            "href": url,
                            "cells": parsed,
                            "headers": header_cells,
                        }
                    )
    return tables


def parse_page(url: str, html: str) -> dict:
    extractor = DocumentExtractor(url)
    extractor.feed(html)
    extractor.close()
    documents = extractor.documents()
    table_rows = parse_data_layer_tables(extractor.data_layers, url)
    # Attach matching table cells (by uuid/href) to anchor records.
    by_id: dict[str, dict] = {}
    for table in table_rows:
        key = (table["uuid"] or table["href"].split("?")[0]).lower()
        by_id.setdefault(key, table)
    for document in documents:
        key = (document["uuid"] or document["href"].split("?")[0]).lower()
        table = by_id.get(key)
        if table:
            document["tableCells"] = table["cells"]
            document["tableHeaders"] = table["headers"]
    dates = list(extractor.metas.values()) + DATE_TEXT_RE.findall(html)
    return {
        "url": url,
        "title": clean_text(extractor.title) or clean_text(extractor.metas.get("title", "")),
        "dates": [clean_text(d) for d in dates if clean_text(d)],
        "documents": documents,
        "tableRows": table_rows,
    }


def fetch_html(url: str, timeout: int, retries: int) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return data.decode(charset, "replace"), response.geturl()
        except Exception as error:  # noqa: BLE001
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code in {404, 410}:
                break
            time.sleep(1.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def cache_path(item_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "__", item_id)
    return CACHE_DIR / f"{safe}.json"


def process_item(item: dict, timeout: int, retries: int, delay: float, force: bool) -> dict:
    path = cache_path(item["id"])
    if path.exists() and not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("url") == item["url"] and not cached.get("error"):
                return {"id": item["id"], "cached": True, "error": None}
        except Exception:
            pass
    time.sleep(delay)
    try:
        html, final_url = fetch_html(item["url"], timeout, retries)
        page = parse_page(final_url or item["url"], html)
        page["id"] = item["id"]
        page["fetchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        return {
            "id": item["id"],
            "cached": False,
            "error": None,
            "documents": len(page["documents"]),
        }
    except Exception as error:  # noqa: BLE001
        status = getattr(error, "code", None)
        identifier = f"{type(error).__name__}: {error}"
        if status in {404, 410} or status is None:
            record = {
                "id": item["id"],
                "url": item["url"],
                "error": identifier,
                "status": status,
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return {"id": item["id"], "cached": False, "error": identifier}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="", help="comma-separated item ids")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    prefer_ipv4()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = catalog["items"]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        items = [i for i in items if i["id"] in wanted]
    if args.limit:
        items = items[: args.limit]
    print(f"[documents] {len(items)} pages, {args.workers} workers")

    started = time.time()
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                process_item, item, args.timeout, args.retries, args.delay, args.force
            ): item
            for item in items
        }
        done = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            done += 1
            if result["error"]:
                failures.append(f"{result['id']}: {result['error']}")
                print(f"[documents] FAIL {result['id']} :: {result['error']}")
            elif done % 25 == 0 or done == len(items):
                print(f"[documents] {done}/{len(items)}")

    items_out: dict[str, dict] = {}
    total_documents = 0
    for item in items:
        path = cache_path(item["id"])
        if not path.exists():
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        if page.get("error"):
            items_out[item["id"]] = {
                "url": item["url"],
                "error": page["error"],
                "documents": [],
                "dates": [],
            }
            continue
        items_out[item["id"]] = {
            "url": page["url"],
            "title": page.get("title", ""),
            "dates": page.get("dates", []),
            "documents": page.get("documents", []),
        }
        total_documents += len(page.get("documents", []))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "items": items_out,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"[documents] wrote {OUT.relative_to(ROOT)} — "
        f"{len(items_out)} pages, {total_documents} document links in {time.time() - started:.0f}s"
    )
    if failures:
        print(f"[documents] {len(failures)} failures")
        for failure in failures[:10]:
            print("  " + failure)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
