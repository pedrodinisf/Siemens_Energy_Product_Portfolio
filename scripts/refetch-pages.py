#!/usr/bin/env python3
"""Re-fetch the catalog pages and save the raw material Phase 2/3 need.

One polite pass over every item URL in `src/data/catalog.json`, writing three
repo-local extracts under `data/siemens-energy/`:

    image-candidates.json  og:image, JSON-LD images, every <img> with alt and
                           nearest heading/link context
    content-blocks.json    main-article structure (h1-h4, paragraphs, lists)
                           for the typography pass
    spec-tables.json       raw spec <table> markup with parsed cells/headers
                           for the table pass

Per-page results are cached under `data/siemens-energy/.refetch-cache/` so an
interrupted run resumes without re-hitting the site. Run from the repo root:

    .venv-pages/Scripts/python scripts/refetch-pages.py
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
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
CACHE_DIR = DATA_DIR / ".refetch-cache"
CATALOG = ROOT / "src" / "data" / "catalog.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SKIP_TAGS = {"style", "noscript", "svg", "template", "iframe"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
CHROME_TAGS = {"nav", "footer", "header"}
HEADING_TAGS = {"h1", "h2", "h3", "h4"}
JSON_LD_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
TABLE_RE = re.compile(r"<table\b.*?</table>", re.S | re.I)
IMG_SRC_RE = re.compile(r"<img\b[^>]*\bsrc=\"([^\"]+)\"", re.I)

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


def best_srcset(srcset: str, page_url: str) -> str:
    """Largest width/density candidate in a srcset attribute."""
    best_url = ""
    best_rank = -1.0
    for entry in (srcset or "").split(","):
        parts = entry.strip().split()
        if not parts:
            continue
        url = abs_url(parts[0], page_url)
        if not url:
            continue
        rank = 0.0
        if len(parts) > 1:
            descriptor = parts[1].lower()
            try:
                if descriptor.endswith("w"):
                    rank = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    rank = float(descriptor[:-1]) * 1000
            except ValueError:
                rank = 0.0
        if rank >= best_rank:
            best_rank = rank
            best_url = url
    return best_url


def json_ld_images(payloads: list[str]) -> list[str]:
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in {"image", "thumbnailurl"}:
                    collect(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    def collect(value) -> None:
        if isinstance(value, str):
            if value and value.startswith(("http://", "https://")):
                found.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key in ("url", "contentUrl", "@id"):
                if isinstance(value.get(key), str):
                    found.append(value[key])
                    return
            walk(value)

    for payload in payloads:
        try:
            walk(json.loads(payload))
        except Exception:
            continue
    seen: set[str] = set()
    return [u for u in found if not (u in seen or seen.add(u))]


class PageExtractor(HTMLParser):
    """One page's images, content blocks and tables, in document order."""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.metas: dict[str, str] = {}
        self.json_ld_raw: list[str] = []
        self.title = ""
        self.in_title = False
        self.skip_depth = 0
        self.exclude_depth = 0
        self.in_json_ld = False

        self.blocks: list[dict] = []
        self.headings: list[dict] = []
        self.last_heading = {"level": None, "text": ""}
        self.in_heading: dict | None = None
        self.paragraph: dict | None = None
        self.list_stack: list[dict] = []
        self.item_stack: list[dict] = []
        self.bold_depth = 0
        self.bold_buf: list[str] | None = None
        self.bold_target: dict | None = None
        self.link_stack: list[dict] = []

        self.in_table = 0
        self.table: dict | None = None
        self.row: dict | None = None
        self.cell: dict | None = None

        self.images: list[dict] = []
        self.tables: list[dict] = []

    def _excluded(self, tag: str, attrs: dict) -> bool:
        if tag in CHROME_TAGS or "data-elastic-exclude" in attrs:
            return True
        ident = (attrs.get("id") or "") + " " + (attrs.get("class") or "")
        return bool(
            re.search(
                r"onetrust|cookie[-_]?(banner|consent)|consent[-_]banner|aem-embed|aem-video",
                ident,
                re.I,
            )
        )

    def _target(self) -> dict | None:
        if self.item_stack:
            return self.item_stack[-1]
        if self.cell is not None:
            return self.cell
        if self.paragraph is not None:
            return self.paragraph
        if self.in_heading is not None:
            return self.in_heading
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.exclude_depth:
            if tag not in VOID_TAGS:
                self.exclude_depth += 1
            return
        if self._excluded(tag, a):
            self.exclude_depth = 1
            return
        if tag == "script":
            script_type = (a.get("type") or "").lower()
            if "ld+json" in script_type:
                self.in_json_ld = True
            else:
                self.skip_depth += 1
            return
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "meta":
            key = a.get("name") or a.get("property") or a.get("itemprop")
            if key and a.get("content"):
                self.metas[key] = a["content"]
            return
        if tag == "title":
            self.in_title = not self.title
            return
        if tag == "br":
            target = self._target()
            if target is not None and "text" in target:
                target["text"].append(" ")
            return
        if tag in HEADING_TAGS:
            self.in_heading = {"level": tag, "text": [], "bold": [], "links": []}
            if self.in_table:
                return
            return
        if tag == "p":
            if not self.in_table and not self.item_stack and self.cell is None:
                self.paragraph = {"type": "paragraph", "text": [], "bold": [], "links": []}
                self.blocks.append(self.paragraph)
            return
        if tag in {"ul", "ol"}:
            if self.in_table:
                return
            block = {"type": "list", "ordered": tag == "ol", "items": [], "text": []}
            self.blocks.append(block)
            self.list_stack.append(block)
            return
        if tag == "li":
            if self.list_stack and not self.in_table:
                item = {
                    "text": [],
                    "bold": [],
                    "links": [],
                    "depth": len(self.list_stack) - 1,
                }
                self.list_stack[-1]["items"].append(item)
                self.item_stack.append(item)
            return
        if tag == "table":
            self.in_table += 1
            if self.in_table == 1:
                self.table = {"type": "table", "rows": []}
                self.blocks.append(self.table)
            return
        if tag == "tr" and self.in_table:
            self.row = {"cells": []}
            if self.table is not None:
                self.table["rows"].append(self.row)
            return
        if tag in {"td", "th"} and self.in_table:
            self.cell = {"tag": tag, "text": [], "bold": [], "links": []}
            if self.row is not None:
                self.row["cells"].append(self.cell)
            return
        if tag == "b" or tag == "strong":
            target = self._target()
            if target is not None:
                self.bold_depth += 1
                if self.bold_buf is None:
                    self.bold_buf = []
                    self.bold_target = target
            return
        if tag == "a":
            href = abs_url(a.get("href") or "", self.page_url)
            self.link_stack.append({"href": href, "text": []})
            return
        if tag == "img":
            self._add_image(a)
            return

    def _add_image(self, a: dict) -> None:
        src = abs_url(a.get("src") or a.get("data-src") or "", self.page_url)
        if not src or src.startswith("data:"):
            return
        link = self.link_stack[-1] if self.link_stack else None
        best = best_srcset(a.get("srcset") or a.get("data-srcset") or "", self.page_url) or src
        width = height = None
        for key, target in (("width", "w"), ("height", "h")):
            raw = a.get(key)
            if raw and str(raw).isdigit():
                if target == "w":
                    width = int(raw)
                else:
                    height = int(raw)
        self.images.append(
            {
                "src": src,
                "srcset_best": best,
                "alt": clean_text(a.get("alt") or ""),
                "class": (a.get("class") or "").strip(),
                "width": width,
                "height": height,
                "heading": dict(self.last_heading),
                "link": link,
            }
        )

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.exclude_depth:
            self.exclude_depth -= 1
            return
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "script" and self.in_json_ld:
            self.in_json_ld = False
            return
        if tag == "title":
            self.in_title = False
            return
        if tag in HEADING_TAGS and self.in_heading is not None:
            text = clean_text("".join(self.in_heading["text"]))
            self.in_heading = None
            if text:
                self.blocks.append({"type": "heading", "level": tag, "text": text})
                self.headings.append({"level": tag, "text": text})
                self.last_heading = {"level": tag, "text": text}
            return
        if tag == "p" and self.paragraph is not None:
            self._finish_text(self.paragraph)
            if not self.paragraph["text"]:
                self.blocks[:] = [b for b in self.blocks if b is not self.paragraph]
            self.paragraph = None
            return
        if tag in {"ul", "ol"} and self.list_stack:
            block = self.list_stack.pop()
            if not block["items"]:
                self.blocks[:] = [b for b in self.blocks if b is not block]
            return
        if tag == "li" and self.item_stack:
            item = self.item_stack.pop()
            self._finish_text(item)
            if not item["text"]:
                for block in self.list_stack:
                    if item in block["items"]:
                        block["items"].remove(item)
                        break
            return
        if tag in {"td", "th"} and self.cell is not None:
            self._finish_text(self.cell)
            self.cell = None
            return
        if tag == "tr":
            self.row = None
            return
        if tag == "table" and self.in_table:
            self.in_table -= 1
            if self.in_table == 0 and self.table is not None:
                self.tables.append(self.table)
                self.table = None
            return
        if tag in {"b", "strong"}:
            if self.bold_depth:
                self.bold_depth -= 1
            if self.bold_depth == 0 and self.bold_buf is not None:
                bold = clean_text("".join(self.bold_buf))
                if bold and self.bold_target is not None and "bold" in self.bold_target:
                    self.bold_target["bold"].append(bold)
                self.bold_buf = None
                self.bold_target = None
            return
        if tag == "a" and self.link_stack:
            link = self.link_stack.pop()
            text = clean_text("".join(link["text"]))
            link["text"] = text
            target = self._target()
            if target is not None and "links" in target and link["href"] and text:
                target["links"].append({"href": link["href"], "text": text})
            return

    def _finish_text(self, target: dict) -> None:
        target["text"] = clean_text("".join(target.get("text") or []))
        target["bold"] = [b for b in target.get("bold", []) if b]
        target["links"] = target.get("links") or []

    def handle_data(self, data):
        if self.exclude_depth:
            return
        if self.in_json_ld:
            self.json_ld_raw.append(data)
            return
        if self.skip_depth:
            return
        if self.in_title:
            self.title += data
        if self.link_stack:
            self.link_stack[-1]["text"].append(data)
        if self.in_heading is not None:
            self.in_heading["text"].append(data)
        if self.paragraph is not None:
            self.paragraph["text"].append(data)
        if self.item_stack:
            self.item_stack[-1]["text"].append(data)
        if self.cell is not None:
            self.cell["text"].append(data)
        if self.bold_buf is not None:
            self.bold_buf.append(data)

    def finish(self) -> dict:
        # headings become blocks only when closed (handle_endtag appends), so
        # nothing to do here except resolve image contexts.
        images = []
        for image in self.images:
            link = image.get("link")
            images.append(
                {
                    "src": image["src"],
                    "srcset_best": image["srcset_best"],
                    "alt": image["alt"],
                    "class": image["class"],
                    "width": image["width"],
                    "height": image["height"],
                    "heading": image["heading"],
                    "link": (
                        {"href": link["href"], "text": clean_text("".join(link["text"]))}
                        if link and link.get("href")
                        else None
                    ),
                }
            )
        blocks = [self._serialize_block(b) for b in self.blocks]
        return {
            "title": clean_text(self.title) or clean_text(self.metas.get("og:title", "")),
            "metaTitle": clean_text(self.metas.get("title", "")),
            "ogImage": abs_url(self.metas.get("og:image", ""), self.page_url),
            "twitterImage": abs_url(self.metas.get("twitter:image", ""), self.page_url),
            "jsonLdImages": [abs_url(u, self.page_url) for u in json_ld_images(self.json_ld_raw)],
            "jsonLd": [clean_text(p)[:1] for p in []],  # placeholder removed below
            "images": images,
            "blocks": blocks,
            "tables": [self._serialize_table(t) for t in self.tables],
        }

    @staticmethod
    def _serialize_block(block: dict) -> dict:
        out = {"type": block["type"]}
        if block["type"] == "heading":
            out["level"] = block["level"]
            out["text"] = block["text"]
        elif block["type"] == "paragraph":
            out["text"] = block["text"]
            out["bold"] = block["bold"]
            out["links"] = block["links"]
        elif block["type"] == "list":
            out["ordered"] = block["ordered"]
            out["items"] = [
                {
                    "text": item["text"],
                    "bold": item["bold"],
                    "links": item["links"],
                    "depth": item["depth"],
                }
                for item in block["items"]
            ]
        elif block["type"] == "table":
            out["rows"] = [
                {
                    "cells": [
                        {"tag": c["tag"], "text": c["text"], "bold": c["bold"], "links": c["links"]}
                        for c in row["cells"]
                    ]
                }
                for row in block["rows"]
            ]
        return out

    @staticmethod
    def _serialize_table(table: dict) -> dict:
        headers = []
        if table["rows"]:
            headers = [c["text"] for c in table["rows"][0]["cells"] if c["tag"] == "th"]
        return {
            "headers": headers,
            "rows": [
                {
                    "cells": [
                        {"tag": c["tag"], "text": c["text"], "bold": c["bold"], "links": c["links"]}
                        for c in row["cells"]
                    ]
                }
                for row in table["rows"]
            ],
        }


def extract_tables_raw(html: str) -> list[str]:
    return [m.group(0) for m in TABLE_RE.finditer(html)]


def parse_page(url: str, html: str) -> dict:
    parser = PageExtractor(url)
    parser.feed(html)
    parser.close()
    result = parser.finish()
    result.pop("jsonLd", None)

    raw_tables = extract_tables_raw(html)
    for index, table in enumerate(result["tables"]):
        table["index"] = index
        table["html"] = raw_tables[index] if index < len(raw_tables) else ""
    for index, img in enumerate(result["images"]):
        img["index"] = index

    result["url"] = url
    result["imageCandidateCount"] = len(result["images"])
    result["blockCount"] = len(result["blocks"])
    result["tableCount"] = len(result["tables"])
    return result


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
    item_id = item["id"]
    path = cache_path(item_id)
    if path.exists() and not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("url") == item["url"] and not cached.get("error"):
                return {"id": item_id, "cached": True, "error": None}
        except Exception:
            pass
    time.sleep(delay)
    try:
        html, final_url = fetch_html(item["url"], timeout, retries)
        page = parse_page(final_url or item["url"], html)
        page["id"] = item_id
        page["fetchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        return {
            "id": item_id,
            "cached": False,
            "error": None,
            "images": page["imageCandidateCount"],
            "blocks": page["blockCount"],
            "tables": page["tableCount"],
        }
    except Exception as error:  # noqa: BLE001
        status = getattr(error, "code", None)
        identifier = f"{type(error).__name__}: {error}"
        if status in {404, 410}:
            record = {
                "id": item_id,
                "url": item["url"],
                "error": identifier,
                "status": status,
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return {"id": item_id, "cached": False, "error": identifier}


def write_output(name: str, payload: dict) -> None:
    target = DATA_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[refetch] wrote {target.relative_to(ROOT)} ({target.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="", help="comma-separated item ids to fetch")
    parser.add_argument("--force", action="store_true", help="ignore the per-page cache")
    args = parser.parse_args()

    prefer_ipv4()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = catalog["items"]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        items = [i for i in items if i["id"] in wanted]
    if args.limit:
        items = items[: args.limit]
    print(f"[refetch] {len(items)} pages, {args.workers} workers")

    started = time.time()
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_item, item, args.timeout, args.retries, args.delay, args.force): item
            for item in items
        }
        done = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            done += 1
            if result["error"]:
                failures.append(f"{result['id']}: {result['error']}")
                print(f"[refetch] FAIL {result['id']} :: {result['error']}")
            elif done % 20 == 0 or done == len(items):
                print(f"[refetch] {done}/{len(items)}")

    image_items: dict[str, dict] = {}
    content_items: dict[str, dict] = {}
    table_items: dict[str, dict] = {}
    for item in items:
        path = cache_path(item["id"])
        if not path.exists():
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        if page.get("error"):
            image_items[item["id"]] = {
                "url": item["url"],
                "title": item["title"],
                "error": page["error"],
                "ogImage": "",
                "twitterImage": "",
                "jsonLdImages": [],
                "images": [],
            }
            content_items[item["id"]] = {
                "url": item["url"],
                "title": item["title"],
                "error": page["error"],
                "blocks": [],
            }
            table_items[item["id"]] = {
                "url": item["url"],
                "title": item["title"],
                "error": page["error"],
                "tables": [],
            }
            continue
        image_items[item["id"]] = {
            "url": page["url"],
            "title": page["title"],
            "ogImage": page["ogImage"],
            "twitterImage": page["twitterImage"],
            "jsonLdImages": page["jsonLdImages"],
            "images": page["images"],
        }
        content_items[item["id"]] = {
            "url": page["url"],
            "title": page["title"],
            "metaTitle": page.get("metaTitle", ""),
            "blocks": page["blocks"],
        }
        table_items[item["id"]] = {
            "url": page["url"],
            "title": page["title"],
            "tables": page["tables"],
        }

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_output("image-candidates.json", {"generatedAt": generated_at, "items": image_items})
    write_output("content-blocks.json", {"generatedAt": generated_at, "items": content_items})
    write_output("spec-tables.json", {"generatedAt": generated_at, "items": table_items})

    unique_images = len(
        {img["src"].split("?")[0] for entry in image_items.values() for img in entry["images"]}
    )
    with_og = sum(1 for entry in image_items.values() if entry["ogImage"])
    with_ld = sum(1 for entry in image_items.values() if entry["jsonLdImages"])
    with_tables = sum(1 for entry in table_items.values() if entry["tables"])
    print(
        f"[refetch] items={len(image_items)} images={unique_images} og={with_og} "
        f"jsonLd={with_ld} tables={with_tables} in {time.time() - started:.0f}s"
    )
    if failures:
        print(f"[refetch] {len(failures)} failures:")
        for failure in failures[:20]:
            print(f"  {failure}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
