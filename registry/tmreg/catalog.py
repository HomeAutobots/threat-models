"""Parse the guide's reference threat catalog (docs/reference/reference-system.md)."""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

SECTION = "## Threat catalog used in worked examples"
_ID_RE = re.compile(r"P?T-\d{2,}")
_SPLIT = re.compile(r"(?<!\\)\|")


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogRow:
    id: str
    elements: list[str]
    category: str
    text: str


def parse(text: str) -> list[CatalogRow]:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == SECTION), None)
    if start is None:
        raise CatalogError(f"no '{SECTION}' section in the catalog file")
    rows: list[CatalogRow] = []
    fence = False
    for line in lines[start + 1:]:
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith("## "):
            break
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip().replace("\\|", "|") for c in _SPLIT.split(s.strip("|"))]
        if not _ID_RE.fullmatch(cells[0]):
            continue
        if len(cells) != 4 or not all(cells):
            raise CatalogError(f"{cells[0]}: catalog row needs ID, elements, category, and text")
        elements = [e.strip() for e in cells[1].split(",") if e.strip()]
        if not elements:
            raise CatalogError(f"{cells[0]}: catalog row needs ID, elements, category, and text")
        if any(r.id == cells[0] for r in rows):
            raise CatalogError(f"duplicate catalog ID {cells[0]}")
        rows.append(CatalogRow(cells[0], elements, cells[2], cells[3]))
    return rows


def title_for(text: str) -> str:
    return textwrap.shorten(text, width=120, placeholder="…")
