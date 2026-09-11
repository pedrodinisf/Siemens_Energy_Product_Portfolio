#!/usr/bin/env python3
"""Compose page-review contact sheets from the crops of item-page-review.mjs.

    .venv-pages/Scripts/python scripts/item-page-sheets.py --mode top
    .venv-pages/Scripts/python scripts/item-page-sheets.py --mode specs
    .venv-pages/Scripts/python scripts/item-page-sheets.py --mode body --ids a,b

Outputs JPEG sheets under `data/siemens-energy/review/sheets/` (gitignored).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
SHOT_DIR = DATA_DIR / "review" / "pages"
SHEET_DIR = DATA_DIR / "review" / "sheets"
CATALOG = json.loads((ROOT / "src" / "data" / "catalog.json").read_text(encoding="utf-8"))

SECTOR_ORDER = [
    "Generation",
    "Grid",
    "Compression",
    "Hydrogen & storage",
    "Digital",
    "Marine & subsea",
    "Services",
    "Industry solutions",
    "Use cases",
    "Publications",
    "Other products",
]

BG = (11, 18, 25)
FG = (220, 228, 234)
ACCENT = (26, 166, 160)


def font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def shot_path(item_id: str, kind: str) -> Path:
    family, _, slug = item_id.partition("/")
    return SHOT_DIR / f"{family}__{slug}--{kind}.jpg"


def compose(rows: list[tuple[str, Path, str]], cols: int, thumb_w: int, out: Path) -> None:
    label_h = 30
    pad = 10
    header_h = 40
    thumbs = []
    for item_id, path, label in rows:
        image = Image.open(path).convert("RGB")
        ratio = thumb_w / image.width
        image = image.resize((thumb_w, int(image.height * ratio)), Image.LANCZOS)
        thumbs.append((item_id, image, label))
    row_h = max(image.height for _, image, _ in thumbs) + label_h
    sheet_w = pad + cols * (thumb_w + pad)
    sheet_h = header_h + len(range(0, len(thumbs), cols)) * (row_h + pad)
    sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 12), out.stem, fill=ACCENT, font=font(18))
    label_font = font(14)
    for index, (item_id, image, label) in enumerate(thumbs):
        x = pad + (index % cols) * (thumb_w + pad)
        y = header_h + (index // cols) * (row_h + pad)
        sheet.paste(image, (x, y))
        draw.text((x, y + image.height + 4), f"{label}  [{item_id}]", fill=FG, font=label_font)
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=72)
    print(f"[sheets] {out.relative_to(ROOT)} ({len(thumbs)} items)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["top", "specs", "body"], required=True)
    parser.add_argument("--ids", default="", help="comma-separated item ids (required for body)")
    parser.add_argument("--per-sheet", type=int, default=0)
    args = parser.parse_args()

    items = CATALOG["items"]
    by_id = {item["id"]: item for item in items}
    ordered = sorted(
        items,
        key=lambda item: (
            SECTOR_ORDER.index(item.get("sector") or "Other products")
            if (item.get("sector") or "Other products") in SECTOR_ORDER
            else len(SECTOR_ORDER),
            item.get("familyLabel") or item["family"],
            item["title"],
        ),
    )

    if args.ids:
        wanted = [i for i in ordered if i["id"] in args.ids.split(",")]
    else:
        wanted = ordered

    rows = []
    for item in wanted:
        path = shot_path(item["id"], args.mode)
        if not path.exists():
            continue
        label = (item.get("title") or "")[:60]
        rows.append((item["id"], path, label))

    if not rows:
        raise SystemExit(f"[sheets] no {args.mode} crops found under {SHOT_DIR}")

    if args.mode == "top":
        per_sheet = args.per_sheet or 30
        # Group by sector so each sheet is one sector (or a chunk of a large one).
        groups: dict[str, list] = {}
        for row in rows:
            sector = by_id[row[0]].get("sector") or "Other products"
            groups.setdefault(sector, []).append(row)
        for sector, group in groups.items():
            for chunk in range(0, len(group), per_sheet):
                part = group[chunk : chunk + per_sheet]
                suffix = f"-{chunk // per_sheet + 1}" if len(group) > per_sheet else ""
                name = f"top-{sector.lower().replace(' ', '-').replace('&', 'and')}{suffix}"
                compose(part, cols=5, thumb_w=300, out=SHEET_DIR / f"{name}.jpg")
    elif args.mode == "specs":
        per_sheet = args.per_sheet or 24
        for chunk in range(0, len(rows), per_sheet):
            part = rows[chunk : chunk + per_sheet]
            name = f"specs-{chunk // per_sheet + 1:02d}"
            compose(part, cols=3, thumb_w=470, out=SHEET_DIR / f"{name}.jpg")
    else:
        compose(rows, cols=4, thumb_w=420, out=SHEET_DIR / "body.jpg")


if __name__ == "__main__":
    main()
