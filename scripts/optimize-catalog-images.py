#!/usr/bin/env python3
"""Convert the locally served catalog images to WebP and repoint the catalog.

The scrape keeps the original hero images under data/siemens-energy/ (untouched
provenance); public/catalog/images/ is the copy the site ships, so it is
re-encoded to WebP (quality 82) and every local hero path in the catalogs is
updated. Run after the scraper, before `npm run catalog:split`:

    pip install Pillow
    python scripts/optimize-catalog-images.py
    npm run catalog:split
"""

from __future__ import annotations

import json
from pathlib import Path

QUALITY = 82
ROOT = Path(__file__).resolve().parent.parent
PUBLIC_IMAGES = ROOT / "public" / "catalog" / "images"
CATALOGS = [
    ROOT / "src" / "data" / "catalog.json",
    ROOT / "data" / "siemens-energy" / "catalog.json",
]


def convert(path: Path) -> bool:
    from PIL import Image

    target = path.with_suffix(".webp")
    try:
        with Image.open(path) as image:
            has_alpha = image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.save(target, "WEBP", quality=QUALITY, method=6)
    except Exception as err:  # noqa: BLE001
        print(f"[optimize] skip {path.name}: {err}")
        return False
    path.unlink()
    return True


def repoint(catalog: dict, webp_paths: set[str]) -> int:
    changed = 0

    def fix(value: str | None) -> str | None:
        nonlocal changed
        if not value or not value.startswith("/catalog/images/"):
            return value
        candidate = str(Path(value).with_suffix(".webp")).replace("\\", "/")
        if candidate in webp_paths:
            changed += 1
            return candidate
        return value

    for item in catalog.get("items", []):
        item["heroLocal"] = fix(item.get("heroLocal"))
    for family in catalog.get("families", []):
        family["hero"] = fix(family.get("hero"))
    return changed


def main() -> None:
    converted = 0
    before = 0
    after = 0
    webp_paths: set[str] = set()

    for path in sorted(PUBLIC_IMAGES.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        before += path.stat().st_size
        if convert(path):
            target = path.with_suffix(".webp")
            after += target.stat().st_size
            webp_paths.add("/" + target.relative_to(ROOT / "public").as_posix())
            converted += 1

    print(
        f"[optimize] {converted} images converted, "
        f"{before / 1048576:.1f} MB -> {after / 1048576:.1f} MB"
    )

    for catalog_path in CATALOGS:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        changed = repoint(catalog, webp_paths)
        indent = 2 if catalog_path.parts[-2] == "siemens-energy" else None
        catalog_path.write_text(
            json.dumps(catalog, indent=indent, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[optimize] {catalog_path.relative_to(ROOT)}: {changed} paths repointed")


if __name__ == "__main__":
    main()
