#!/usr/bin/env python3
"""Clean and structure item body copy from the refetched page blocks.

Reads `data/siemens-energy/content-blocks.json` (produced by
`scripts/refetch-pages.py`) and rewrites each item's `body` in
`src/data/catalog.json` and the local archive copy as a list of blocks:

    {"type": "paragraph", "text": str, "bold": [str, ...]}
    {"type": "heading", "level": 2 | 3 | 4, "text": str}
    {"type": "list", "ordered": bool, "items": [str, ...]}

Drops the page H1 (the item hero already shows the title), CTA/nav/cookie
boilerplate, download/ToC sections, duplicate paragraphs, and the table blocks
(rendered separately from the normalized specs). Items without refetched
blocks fall back to splitting their old flat body into paragraphs.
Run `npm run catalog:split` afterwards.

    .venv-pages/Scripts/python scripts/clean-bodies.py --dry-run
    .venv-pages/Scripts/python scripts/clean-bodies.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
CONTENT_BLOCKS = DATA_DIR / "content-blocks.json"
CATALOGS = [ROOT / "src" / "data" / "catalog.json", DATA_DIR / "catalog.json"]

WHITESPACE = re.compile(r"\s+")
APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'"})

# Section headings whose content is navigation, download lists or PDF tables of
# contents; the app renders downloads and specs in their own sections already.
DROP_HEADINGS = {
    "what's inside",
    "sign up for free download",
    "explore our products and services",
    "latest articles",
    "downloads",
    "subscribe to our newsletter!",
    "download more information about siemens energy",
    "find out more about siemens energy gas turbine topics",
    "make use of our services",
    "related topics",
    "learn more about siemens energy's portfolio",
    "download resources",
    "product drawings",
    "let's discuss your next project",
    "brochures",
    "technical data",
    "downloads and links",
}

BOILERPLATE = {
    "i would like to receive marketing information from siemens energy based on my personal interests and give my consent as described in detail here.",
    "for information and questions, our support team is available 24/7 to assist you in english, spanish, and german.",
    "do you have a question regarding siemens energy products, solutions and services?",
    "do you have a question regarding our products, solutions and services?",
    "the download section offers brochures, technical papers, and more.",
    "if you require more information please contact us by using the contact button.",
    "are you a siemens energy equipment owner? you can access exclusive documents relevant to your unit on the customer energy portal.",
    "we're a true partner in your success. with our experts we're ready for your next project!",
    "together, we can navigate the evolving energy landscape and ensure your success for the future.",
    "with siemens energy, you gain more than just the latest technology; you receive reliable, customized solutions backed by deep domain expertise.",
    "we take great pride in a collaborative process that truly partners with your team to develop effective electrical solutions. siemens energy is offering you:",
    "visit the siemens energy app store to download the app.",
    "visit the siemens energy store on google play to download the app.",
    "you would like a brochure, are interested in technical details or further information? please visit our download section below.",
    "for your convenience, we have gathered relevant downloads in one spot. if your question is still unanswered, please feel free to contact our siemens energy support team.",
    "read more on the importance and potential of this ongoing development.",
    "harness the power of wind with our wind power business siemens gamesa.",
    "let's energize society.",
}

FOOTER_RE = re.compile(
    r"^siemens energy is a trademark licensed|^© siemens energy|^\(?c\) siemens energy",
    re.IGNORECASE,
)

# Texts removed by the orphan-heading sweep, kept for --show debugging.
ORPHANS: list[str] = []

CTA_RE = re.compile(
    r"^(read|learn|discover|view|watch|download|subscribe|sign up|contact|"
    r"get in touch|follow|explore|visit)\b.{0,40}$",
    re.IGNORECASE,
)
CTA_EXACT_RE = re.compile(
    r"^(read|learn|download)( more| now| here| article| the article| the full article|"
    r" the press release| success story| story)?[.!]?$",
    re.IGNORECASE,
)

# Paragraphs on many pages that are pure marketing filler even when unique
# enough to escape the exact blocklist.
FILLER_RE = re.compile(
    r"^(discover more|learn more about|find out more|for more information|"
    r"please contact|contact us|follow us|subscribe|sign up)\b",
    re.IGNORECASE,
)

IMAGE_RE = re.compile(
    r"^\((image|photo|picture|figure|source|graphic)s?\b[^)]*\)\.?$",
    re.IGNORECASE,
)

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def normalize(text: str) -> str:
    return WHITESPACE.sub(" ", (text or "").translate(APOSTROPHES)).strip()


def heading_key(text: str) -> str:
    return normalize(text).rstrip(":").lower()


def drop_exact_boilerplate(text: str) -> bool:
    return normalize(text).lower() in BOILERPLATE


def is_cta(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 160:
        return False
    return bool(CTA_RE.match(stripped) or CTA_EXACT_RE.match(stripped))


def clean_list(block: dict) -> dict | None:
    items = []
    seen = set()
    for entry in block.get("items") or []:
        if not isinstance(entry, dict):
            continue
        text = normalize(entry.get("text"))
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        items.append(text)
    items = [item for item in items if not is_cta(item)]
    if not items:
        return None
    return {"type": "list", "ordered": bool(block.get("ordered")), "items": items}


def clean_blocks(blocks: list, title: str) -> tuple[list, Counter]:
    stats = Counter()
    out: list = []
    seen_text: set[str] = set()
    drop_level: int | None = None
    title_key = normalize(title).lower()

    for block in blocks:
        kind = block.get("type")
        if kind == "table":
            stats["table"] += 1
            continue
        if kind == "heading":
            text = normalize(block.get("text"))
            key = heading_key(text)
            level = block.get("level") or "h2"
            if level == "h1":
                stats["h1"] += 1
                continue
            level_no = int(level[1])
            if drop_level is not None:
                if level_no > drop_level:
                    stats["section"] += 1
                    continue
                drop_level = None
            if key in DROP_HEADINGS or not text:
                stats["section"] += 1
                drop_level = level_no
                continue
            out.append({"type": "heading", "level": level_no, "text": text})
            continue
        if kind == "list":
            if drop_level is not None:
                stats["section-item"] += 1
                continue
            cleaned = clean_list(block)
            if not cleaned:
                stats["empty-list"] += 1
                continue
            out.append(cleaned)
            continue
        if kind != "paragraph":
            continue
        if drop_level is not None:
            stats["section-item"] += 1
            continue
        text = block.get("text")
        if not isinstance(text, str):
            stats["empty"] += 1
            continue
        text = normalize(text)
        if not text:
            stats["empty"] += 1
            continue
        if text.lower() == title_key:
            stats["title"] += 1
            continue
        if drop_exact_boilerplate(text):
            stats["boilerplate"] += 1
            continue
        if IMAGE_RE.match(text) or URL_RE.match(text):
            stats["image"] += 1
            continue
        if is_cta(text) or FILLER_RE.match(text):
            stats["cta"] += 1
            continue
        if text.lower() in seen_text:
            stats["duplicate"] += 1
            continue
        seen_text.add(text.lower())
        bold = []
        for phrase in block.get("bold") or []:
            phrase = normalize(phrase)
            if phrase and phrase.lower() in text.lower() and phrase not in bold:
                bold.append(phrase)
        entry = {"type": "paragraph", "text": text}
        if bold:
            entry["bold"] = bold
        out.append(entry)

    while out and out[-1].get("type") == "heading":
        out.pop()
        stats["trailing-heading"] += 1
    # Heading with nothing under it (its table was dropped, or the section had
    # only navigation): remove, then re-check the heading this may orphan.
    changed = True
    while changed:
        changed = False
        for index, block in enumerate(out):
            if block.get("type") != "heading":
                continue
            nxt = out[index + 1] if index + 1 < len(out) else None
            if nxt is None or (nxt.get("type") == "heading" and nxt["level"] <= block["level"]):
                out.pop(index)
                ORPHANS.append(block["text"])
                stats["orphan-heading"] += 1
                changed = True
                break
    return out, stats


def old_body_blocks(body: object) -> list:
    """Split the pre-refetch flat body and apply the same paragraph filters."""
    if not isinstance(body, str):
        return []
    out = []
    seen = set()
    for part in re.split(r"\n{2,}", body):
        text = normalize(part)
        if not text or text.lower() in seen:
            continue
        if drop_exact_boilerplate(text) or is_cta(text) or FILLER_RE.match(text):
            continue
        if FOOTER_RE.match(text):
            continue
        seen.add(text.lower())
        out.append({"type": "paragraph", "text": text})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show", default="", help="comma-separated item ids to print")
    args = parser.parse_args()

    content = json.loads(CONTENT_BLOCKS.read_text(encoding="utf-8"))["items"]
    stats = Counter()
    sample: dict[str, list] = {}
    empty_ids: list[str] = []

    for catalog_path in CATALOGS:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        changed = 0
        for item in catalog.get("items") or []:
            rec = content.get(item["id"]) or {}
            blocks = rec.get("blocks") or []
            if blocks:
                stats["items-with-blocks"] += 1
                cleaned, item_stats = clean_blocks(blocks, item.get("title") or "")
                stats.update(item_stats)
            elif isinstance(item.get("body"), list):
                stats["items-kept-structure"] += 1
                cleaned = item["body"]
            else:
                stats["items-fallback"] += 1
                cleaned = old_body_blocks(item.get("body"))
                stats["fallback-paragraphs"] += len(cleaned)
            cleaned = cleaned or []
            before = item.get("body")
            if cleaned:
                item["body"] = cleaned
                stats["items-with-body"] += 1
            else:
                item.pop("body", None)
                stats["items-empty"] += 1
                if item["id"] not in empty_ids:
                    empty_ids.append(item["id"])
            if args.show and item["id"] in args.show.split(","):
                sample[item["id"]] = cleaned
            if before != cleaned:
                changed += 1
        if not args.dry_run:
            indent = 2 if catalog_path.parts[-2] == "siemens-energy" else None
            catalog_path.write_text(
                json.dumps(catalog, indent=indent, ensure_ascii=False), encoding="utf-8"
            )
        print(f"[bodies] {catalog_path.relative_to(ROOT)}: {changed} items changed")

    for item_id, blocks in sample.items():
        print(f"\n===== {item_id} ({len(blocks)} blocks)")
        for block in blocks[:16]:
            if block["type"] == "heading":
                print(f"  [h{block['level']}] {block['text'][:110]}")
            elif block["type"] == "list":
                print(f"  [list ordered={block['ordered']}] " + " | ".join(block["items"][:6])[:150])
            else:
                bold = f" bold={block.get('bold')}" if block.get("bold") else ""
                print(f"  [p{bold}] {block['text'][:150]}")

    print("\n[bodies] stats:", dict(stats))
    if empty_ids:
        print("[bodies] items with no body:", ", ".join(empty_ids))


if __name__ == "__main__":
    main()
