#!/usr/bin/env python3
"""Extract per-document metadata from the files themselves.

For every live unique asset in `src/data/catalog.json`, produce:

    title        PDF /Title or Office core-properties title
    author       PDF /Author or Office creator
    created      creation date where published
    pages        PDF page count
    firstLines   the largest-font lines on page 1 (title candidates)

Locally served files are read from `public/catalog/files/`; remote-only assets
are downloaded once into `data/siemens-energy/files/` (untracked) and kept as
the local archive. Results are resumable in
`data/siemens-energy/document-file-metadata.json`.

    .venv-pages/bin/python scripts/fetch-document-metadata.py --workers 4
"""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
FILES_DIR = DATA_DIR / "files"
CATALOG = ROOT / "src" / "data" / "catalog.json"
PROBE = DATA_DIR / "asset-probe.json"
OUT = DATA_DIR / "document-file-metadata.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)

PDF_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()


def asset_key(url: str) -> str:
    match = UUID_RE.search(url or "")
    return match.group(0).lower() if match else url


def download(url: str, dest: Path, timeout: int = 60) -> tuple[bool, str]:
    if dest.exists() and dest.stat().st_size > 0:
        return True, "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "*/*"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            head = data[:512].lstrip()
            if head[:1] == b"<" or head[:5].lower() == b"<!doc":
                return False, "html response"
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return True, "downloaded"
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
            time.sleep(1.0 * (attempt + 1))
    return False, last_error


def pdf_metadata(path: Path) -> dict:
    with PDF_LOCK:
        doc = pymupdf.open(path)
        try:
            meta = doc.metadata or {}
            lines: list[tuple[float, str]] = []
            try:
                page = doc[0]
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        text = " ".join(s.get("text", "") for s in spans).strip()
                        if not text:
                            continue
                        size = max((s.get("size", 0) for s in spans), default=0)
                        lines.append((float(size), text))
            except Exception:  # noqa: BLE001
                pass
            lines.sort(key=lambda item: item[0], reverse=True)
            first_lines = []
            for _, text in lines:
                if text not in first_lines:
                    first_lines.append(text)
                if len(first_lines) >= 4:
                    break
            return {
                "ok": True,
                "pages": doc.page_count,
                "title": (meta.get("title") or "").strip(),
                "author": (meta.get("author") or "").strip(),
                "created": (meta.get("creationDate") or "").strip(),
                "subject": (meta.get("subject") or "").strip(),
                "firstLines": first_lines,
            }
        finally:
            doc.close()


def office_metadata(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n == "docProps/core.xml"]
            if not names:
                return {"ok": True, "pages": None, "title": "", "author": "", "created": ""}
            raw = archive.read("docProps/core.xml").decode("utf-8", "replace")
        def tag(name: str) -> str:
            match = re.search(rf"<[^>]*{name}[^>]*>(.*?)</[^>]*{name}>", raw, re.S | re.I)
            return unescape(match.group(1)).strip() if match else ""
        return {
            "ok": True,
            "pages": None,
            "title": tag("title"),
            "author": tag("creator"),
            "created": tag("created") or tag("modified"),
            "firstLines": [],
        }
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def analyze(asset: dict) -> dict:
    key = asset["key"]
    path = asset["path"]
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            result = pdf_metadata(path)
            result["method"] = "local" if asset["local"] else "download"
            return result
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    return office_metadata(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    probe = json.loads(PROBE.read_text(encoding="utf-8"))["assets"]

    assets: dict[str, dict] = {}
    for item in catalog["items"]:
        for file in item["files"]:
            key = asset_key(file["url"])
            entry = assets.setdefault(
                key,
                {
                    "key": key,
                    "url": file["url"],
                    "status": file.get("status"),
                    "local": bool(file.get("downloaded") and file.get("publicPath")),
                    "publicPath": file.get("publicPath") or "",
                },
            )
            if file.get("downloaded") and file.get("publicPath"):
                entry["local"] = True
                entry["publicPath"] = file["publicPath"]

    existing = (
        json.loads(OUT.read_text(encoding="utf-8"))
        if OUT.exists()
        else {"generatedAt": None, "assets": {}}
    )
    results = existing["assets"]
    jobs = []
    for key, asset in assets.items():
        info = probe.get(key, {})
        if not info.get("live"):
            continue
        if not args.force and results.get(key, {}).get("ok"):
            continue
        suffix = Path(urlparse(asset["url"]).path or "").suffix
        if asset["local"] and asset["publicPath"]:
            path = ROOT / "public" / unquote(asset["publicPath"]).lstrip("/")
        else:
            path = FILES_DIR / f"{key}{suffix or '.bin'}"
        jobs.append({**asset, "path": path})
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"[pdf-meta] {len(jobs)} assets to analyse ({len(results)} already done)")

    done = 0

    def work(job: dict) -> None:
        nonlocal done
        if not job["local"]:
            ok, how = download(job["url"], job["path"])
            if not ok:
                with STATE_LOCK:
                    results[job["key"]] = {
                        "ok": False,
                        "error": f"download: {how}",
                        "url": job["url"],
                    }
                return
        result = analyze(job)
        result["url"] = job["url"]
        with STATE_LOCK:
            results[job["key"]] = result
            done += 1
            if done % 20 == 0:
                OUT.write_text(
                    json.dumps(
                        {
                            "generatedAt": existing["generatedAt"],
                            "assets": results,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                print(f"[pdf-meta] {done}/{len(jobs)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, jobs))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "assets": results,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok = sum(1 for entry in results.values() if entry.get("ok"))
    print(f"[pdf-meta] wrote {OUT.relative_to(ROOT)} — {ok}/{len(results)} ok")


if __name__ == "__main__":
    main()
