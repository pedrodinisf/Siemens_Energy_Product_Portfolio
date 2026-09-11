#!/usr/bin/env python3
"""Normalize page spec tables into labeled catalog specs.

Reads `data/siemens-energy/spec-tables.json` (produced by
`scripts/refetch-pages.py`) and rewrites each item's `specs` in
`src/data/catalog.json` and the local archive copy into per-table records:

    {"kind": "pairs",  "rows": [{"name", "value"}, ...]}
    {"kind": "matrix", "labelHeader": str, "columns": [str, ...],
     "rows": [{"label": str, "values": [str, ...]}, ...]}

Empty rows/columns are dropped, repeated rows and tables deduped, and the
transposed tables regain the metric label column that the original scrape lost.
Run `npm run catalog:split` afterwards.

    .venv-pages/Scripts/python scripts/normalize-spec-tables.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "siemens-energy"
SPEC_TABLES = DATA_DIR / "spec-tables.json"
CATALOGS = [ROOT / "src" / "data" / "catalog.json", DATA_DIR / "catalog.json"]

FILLER = re.compile(r"[\ufffd\u00a0\u200b\u200c\u200d]+")
WHITESPACE = re.compile(r"\s+")

GENERIC_HEADER = {
    "parameter", "parameters", "specification", "specifications",
    "feature", "features", "description", "descriptions", "name", "names",
    "value", "values", "item", "items", "drawing", "drawings",
    "property", "properties", "characteristic", "characteristics",
    "criteria", "criterion", "type", "types", "category", "categories",
    "metric", "metrics", "attribute", "attributes", "detail", "details",
    "aspect", "aspects", "topic", "topics", "field", "fields", "unit",
    "units", "comment", "comments", "notes", "note", "reference",
    "references", "figure", "figures", "symbol", "symbols", "term", "terms",
}

GENERIC_LABEL_RE = re.compile(
    r"^(features?|specifications?|parameters?|criteri(a|on)|descriptions?|"
    r"portfolio element|grid situation|drawings?|items?|types?|names?|"
    r"propert(y|ies)|characteristics?|categor(y|ies)|metrics?|values?|"
    r"attributes?|aspects?|topics?|fields?|units?|notes?|references?)$",
    re.IGNORECASE,
)

TITLE_RE = re.compile(r"combined cycle|power plant", re.IGNORECASE)
METRIC_RE = re.compile(
    r"gross|output|fuel|frequency|efficiency|weight|length|speed|pressure|"
    r"temperature|rating|power|voltage|current|capacity|emission|ramp|heat rate",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    return WHITESPACE.sub(" ", FILLER.sub(" ", text or "")).strip()


def normalize_table(raw: dict) -> dict | None:
    rows = [
        [clean(cell.get("text")) for cell in row.get("cells") or []]
        for row in raw.get("rows") or []
    ]
    rows = [row for row in rows if any(row)]
    if not rows:
        return None

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    # Drop columns that are empty everywhere.
    keep = [i for i in range(width) if any(row[i] for row in rows)]
    if not keep:
        return None
    rows = [[row[i] for i in keep] for row in rows]
    width = len(keep)

    headerised = any(
        cell.get("tag") == "th"
        for cell in (raw.get("rows") or [{}])[0].get("cells") or []
    )

    caption = ""
    header: list[str] | None = None

    if headerised:
        if (
            len(rows) > 1
            and sum(1 for cell in rows[0] if cell) == 1
            and not rows[1][0]
            and sum(1 for cell in rows[1][1:] if cell) >= 2
        ):
            caption = next(cell for cell in rows[0] if cell)
            header, body = rows[1], rows[2:]
        else:
            header, body = rows[0], rows[1:]
    else:
        first = rows[0]
        if first[0] == "" and sum(1 for cell in first[1:] if cell) >= 2:
            header, body = first, rows[1:]
        elif GENERIC_LABEL_RE.match(first[0]):
            header, body = first, rows[1:]
        elif (
            TITLE_RE.search(first[0])
            and len(rows) > 1
            and METRIC_RE.search(rows[1][0])
        ):
            header, body = first, rows[1:]
        elif (
            len(first[0]) >= 25
            and all(len(cell) < 25 for cell in first[1:])
            and len(rows) > 1
            and len(rows[1][0]) < 25
            and any(len(cell) >= 30 for cell in rows[1][1:])
        ):
            header, body = first, rows[1:]
        else:
            body = rows

    if width == 2:
        if header and (
            header[0].lower() in GENERIC_HEADER
            or header[1].lower() in GENERIC_HEADER
        ):
            header = None
        if header is None:
            pairs = [
                {"name": row[0], "value": row[1]}
                for row in body
                if row[0] or row[1]
            ]
            pairs = dedupe(pairs)
            if not pairs:
                return None
            out = {"kind": "pairs", "rows": pairs}
            if caption:
                out["caption"] = caption
            return out
        label_header, columns = header[0], [header[1]]
    else:
        if header is None:
            label_header, columns = "", [""] * (width - 1)
        else:
            label_header, columns = header[0], header[1:]

    matrix_rows = []
    for row in body:
        values = (row[1:] + [""] * len(columns))[: len(columns)]
        if not row[0] and not any(values):
            continue
        matrix_rows.append({"label": row[0], "values": values})
    matrix_rows = dedupe(matrix_rows)
    if not matrix_rows:
        return None
    out = {
        "kind": "matrix",
        "labelHeader": label_header,
        "columns": columns,
        "rows": matrix_rows,
    }
    if caption:
        out["caption"] = caption
    return out


def dedupe(rows: list) -> list:
    seen = set()
    out = []
    for row in rows:
        key = json.dumps(row, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> None:
    spec_tables = json.loads(SPEC_TABLES.read_text(encoding="utf-8"))["items"]
    normalized = {}
    stats = {"tables": 0, "used": 0, "skipped": 0, "pairs": 0, "matrix": 0}
    for item_id, record in spec_tables.items():
        tables = []
        for raw in record.get("tables") or []:
            stats["tables"] += 1
            table = normalize_table(raw)
            if not table:
                stats["skipped"] += 1
                continue
            key = json.dumps(table, ensure_ascii=False)
            if key in {json.dumps(t, ensure_ascii=False) for t in tables}:
                continue
            tables.append(table)
            stats[table["kind"]] += 1
            stats["used"] += 1
        if tables:
            normalized[item_id] = tables

    for catalog_path in CATALOGS:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        changed = 0
        for item in catalog.get("items") or []:
            tables = normalized.get(item["id"])
            if tables is None:
                continue
            if item.get("specs") != tables:
                item["specs"] = tables
                changed += 1
        indent = 2 if catalog_path.parts[-2] == "siemens-energy" else None
        catalog_path.write_text(
            json.dumps(catalog, indent=indent, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[specs] {catalog_path.relative_to(ROOT)}: {changed} items updated")

    print(
        f"[specs] tables={stats['tables']} used={stats['used']} "
        f"pairs={stats['pairs']} matrix={stats['matrix']} skipped={stats['skipped']} "
        f"items={len(normalized)}"
    )


if __name__ == "__main__":
    main()
