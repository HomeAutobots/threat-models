"""Parser for systems/<slug>/dfd.md: version, element and flow IDs, content hash."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

ID_RE = r"^(E|P|D|F|TB)\d+$"
KINDS = ("E", "P", "D", "F", "TB")
_ENDPOINT_RE = re.compile(r"^(E|P|D)\d+")


class DfdError(ValueError):
    pass


@dataclass(frozen=True)
class Dfd:
    version: str
    sha256: str
    ids: dict[str, list[str]]

    def all_ids(self) -> set[str]:
        return {i for lst in self.ids.values() for i in lst}


def _cells(line: str) -> list[str]:
    body = line.strip()[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c) and any(cells)


def _num(i: str) -> int:
    return int(re.search(r"\d+", i).group())


def parse(data: bytes) -> Dfd:
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8")
    version = None
    ids: dict[str, list[str]] = {k: [] for k in KINDS}
    seen: set[str] = set()
    flows: list[tuple[str, str, str]] = []  # (flow id, from cell, to cell)
    header: list[str] | None = None
    fence: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^(`{3,}|~{3,})", stripped)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            header = None
            continue
        if fence is not None:
            continue
        if not stripped.startswith("|"):
            header = None
            continue
        cells = _cells(stripped)
        if _is_separator(cells):
            continue
        if header is None:
            header = cells
            continue
        if cells[0] == "DFD version" and len(cells) > 1:
            version = cells[1]
            continue
        if not header or header[0] != "ID":
            continue
        rid = cells[0]
        if not re.match(ID_RE, rid):
            raise DfdError(f"invalid ID cell {rid!r}: must match {ID_RE}")
        if rid in seen:
            raise DfdError(f"duplicate ID {rid}")
        seen.add(rid)
        kind = re.match(r"[A-Z]+", rid).group()
        ids[kind].append(rid)
        if "From" in header and "To" in header:
            def cell(name: str) -> str:
                idx = header.index(name)
                return cells[idx] if idx < len(cells) else ""
            flows.append((rid, cell("From"), cell("To")))

    if version is None:
        raise DfdError("dfd.md has no '| DFD version | x.y |' row")

    endpoints = {i for k in "EPD" for i in ids[k]}
    for fid, *ends in flows:
        for end in ends:
            m = _ENDPOINT_RE.match(end)
            if not m or m.group() not in endpoints:
                token = m.group() if m else (end.split()[0] if end.split() else "")
                raise DfdError(f"{fid}: unknown endpoint {token}")

    for lst in ids.values():
        lst.sort(key=_num)
    return Dfd(version=version, sha256=sha, ids=ids)


def load(path: Path) -> Dfd:
    return parse(Path(path).read_bytes())
