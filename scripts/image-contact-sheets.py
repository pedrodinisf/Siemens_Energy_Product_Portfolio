#!/usr/bin/env python3
"""Contact sheets for the self-managed image QC (no vision API).

    heroes      one sheet per ~24 items: picked thumb + id + title + source
    alternates  one sheet per flagged item: its candidate pool, ranked

Review the PNGs under `data/siemens-energy/review/`; write corrections to
`src/data/image-overrides.json`, then re-run the picker/apply.

    .venv-pages/Scripts/python scripts/image-contact-sheets.py
    .venv-pages/Scripts/python scripts/image-contact-sheets.py --mode alternates --items a/b,c/d
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
PICKS = DATA_DIR / "picks-v2.json"
OUT_DIR = DATA_DIR / "review"

CELL_W, CELL_H = 300, 210
LABEL_H = 72
COLS, ROWS = 4, 6
MARGIN = 16
HEADER_H = 64

SOURCE_COLORS = {
    "og": (37, 99, 235),
    "jsonld": (79, 70, 229),
    "pdf": (217, 119, 6),
    "page": (22, 163, 74),
    "current": (100, 116, 139),
    "family": (147, 51, 234),
    "override": (220, 38, 38),
}


def font(size: int):
    for candidate in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def thumb_path(name: str | None) -> Path | None:
    if not name:
        return None
    path = DATA_DIR / ".image-cache" / "thumbs" / name
    return path if path.exists() else None


def fit_image(path: Path | None, size: tuple[int, int]) -> Image.Image:
    box = Image.new("RGB", size, (241, 245, 249))
    if not path:
        return box
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return box
    image.thumbnail(size)
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    box.paste(image, (x, y))
    return box


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "__", value)


def label_name(entry: dict) -> str:
    return (entry.get("url") or entry.get("local") or "").split("/")[-1]


def heroes_sheets(picks: dict, source_filter: str = "") -> list[Path]:
    items = sorted(
        picks["items"].values(),
        key=lambda r: (r.get("bucket") or "", r.get("family") or "", r.get("slug") or ""),
    )
    if source_filter:
        items = [
            r for r in items if ((r.get("pick") or {}).get("source") or "none") == source_filter
        ]
    sheets: list[Path] = []
    per_sheet = COLS * ROWS
    for sheet_index in range(0, len(items), per_sheet):
        chunk = items[sheet_index : sheet_index + per_sheet]
        width = MARGIN * 2 + COLS * CELL_W + (COLS - 1) * MARGIN
        height = HEADER_H + MARGIN + ROWS * (CELL_H + LABEL_H) + (ROWS - 1) * MARGIN
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (MARGIN, 16),
            f"Hero contact sheet {sheet_index // per_sheet + 1} — items {sheet_index + 1}-{sheet_index + len(chunk)} of {len(items)}",
            font=font(24),
            fill=(15, 23, 42),
        )
        for cell_index, record in enumerate(chunk):
            row, col = divmod(cell_index, COLS)
            x = MARGIN + col * (CELL_W + MARGIN)
            y = HEADER_H + MARGIN + row * (CELL_H + LABEL_H + MARGIN)
            pick = record.get("pick") or {}
            image = fit_image(
                thumb_path(pick.get("thumb")),
                (CELL_W, CELL_H),
            )
            border = SOURCE_COLORS.get(pick.get("source"), (148, 163, 184))
            canvas.paste(image, (x, y))
            draw.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline=border, width=4)
            number = sheet_index + cell_index + 1
            bbox = draw.textbbox((0, 0), str(number), font=font(22))
            draw.rectangle([x + 6, y + 6, x + 20 + (bbox[2] - bbox[0]), y + 32], fill=(255, 255, 255))
            draw.text((x + 10, y + 6), str(number), font=font(22), fill=(15, 23, 42))
            label_y = y + CELL_H + 4
            source = pick.get("source") or "none"
            if not pick.get("valid"):
                source = "NO IMAGE"
            title = record.get("title") or ""
            short = textwrap.shorten(title, width=44, placeholder="…")
            draw.text((x, label_y), f"{number}. {record['id']}"[:46], font=font(13), fill=(15, 23, 42))
            draw.text((x, label_y + 17), short, font=font(13), fill=(71, 85, 105))
            detail = source
            if pick.get("url") or pick.get("local"):
                detail += " · " + label_name(pick)[:30]
            draw.text((x, label_y + 34), detail, font=font(12), fill=border)
            if pick.get("duplicate"):
                draw.text((x, label_y + 51), "SHARED with another item", font=font(12), fill=(220, 38, 38))
        prefix = f"heroes-{source_filter}" if source_filter else "heroes"
        path = OUT_DIR / f"{prefix}-{sheet_index // per_sheet + 1:02}.png"
        canvas.save(path)
        sheets.append(path)
    return sheets


def alternate_sheets(picks: dict, item_ids: list[str]) -> list[Path]:
    sheets: list[Path] = []
    for item_id in item_ids:
        record = picks["items"].get(item_id)
        if not record:
            print(f"  unknown item: {item_id}")
            continue
        candidates = record.get("candidates") or []
        pick = record.get("pick") or {}
        width = MARGIN * 2 + COLS * CELL_W + (COLS - 1) * MARGIN
        rows = max(1, (len(candidates) + COLS - 1) // COLS)
        height = 120 + MARGIN + rows * (CELL_H + LABEL_H) + (rows - 1) * MARGIN
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        draw.text((MARGIN, 14), item_id, font=font(26), fill=(15, 23, 42))
        draw.text((MARGIN, 50), (record.get("title") or "")[:100], font=font(16), fill=(71, 85, 105))
        draw.text(
            (MARGIN, 74),
            f"current pick: {(pick.get('source') or 'none')} score={pick.get('score')} {label_name(pick)[:60]}",
            font=font(15),
            fill=(15, 23, 42),
        )
        for index, cand in enumerate(candidates):
            row, col = divmod(index, COLS)
            x = MARGIN + col * (CELL_W + MARGIN)
            y = 110 + MARGIN + row * (CELL_H + LABEL_H + MARGIN)
            is_pick = pick and cand.get("key") == pick.get("key")
            image = fit_image(thumb_path(cand.get("thumb")), (CELL_W, CELL_H))
            border = SOURCE_COLORS.get(cand.get("source"), (148, 163, 184))
            canvas.paste(image, (x, y))
            draw.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline=border, width=6 if is_pick else 3)
            draw.text((x + 8, y + 6), f"#{index + 1} {cand.get('source')} {cand.get('score')}", font=font(16), fill=(15, 23, 42))
            if is_pick:
                draw.rectangle([x + CELL_W - 90, y + 4, x + CELL_W - 6, y + 30], fill=(15, 23, 42))
                draw.text((x + CELL_W - 82, y + 8), "PICK", font=font(15), fill=(255, 255, 255))
            label_y = y + CELL_H + 4
            draw.text((x, label_y), label_name(cand)[:44], font=font(12), fill=(51, 65, 85))
            reason = ", ".join(cand.get("reasons") or [])[:58]
            draw.text((x, label_y + 15), reason, font=font(11), fill=(100, 116, 139))
            dims = f"{cand.get('width')}x{cand.get('height')} {cand.get('fit')}"
            draw.text((x, label_y + 29), f"{dims} valid={cand.get('valid')}", font=font(11), fill=(100, 116, 139))
            alt_line = (cand.get("alt") or "")[:52]
            if alt_line:
                draw.text((x, label_y + 43), alt_line, font=font(11), fill=(71, 85, 105))
        path = OUT_DIR / f"alt-{safe_name(item_id)}.png"
        canvas.save(path)
        sheets.append(path)
    return sheets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["heroes", "alternates"], default="heroes")
    parser.add_argument("--items", default="", help="comma-separated ids for alternates")
    parser.add_argument("--source", default="", help="heroes mode: only picks from this source")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    picks = json.loads(PICKS.read_text(encoding="utf-8"))
    if args.mode == "heroes":
        paths = heroes_sheets(picks, args.source)
    else:
        item_ids = [s.strip() for s in args.items.split(",") if s.strip()]
        if not item_ids:
            parser.error("--items is required for alternates")
        paths = alternate_sheets(picks, item_ids)
    for path in paths:
        print(f"[sheets] {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
