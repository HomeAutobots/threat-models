"""Parser for systems/<slug>/dfd.md: version, element and flow IDs, content hash."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

ID_RE = r"^(E|P|D|F|TB)[0-9]+$"
KINDS = ("E", "P", "D", "F", "TB")
_ENDPOINT_RE = re.compile(r"^(E|P|D)[0-9]+\b")
_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
# The version cell is AI-writable and shown at the DFD gate, so only a plain token parses:
# escape codes or bidi controls there could hide the preview's other lines from the owner.
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,31}")


def _escaped(text: str) -> str:
    """Cell text for an error message, with non-printable characters shown as escapes."""
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii")
                   for c in text)


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
    return int(re.search(r"[0-9]+", i).group())


def _live_lines(text: str) -> list[tuple[int, str | None]]:
    """(line number, text) per line; text is None for fenced, indented, or comment-only lines."""
    out: list[tuple[int, str | None]] = []
    fence: tuple[str, int, int] | None = None  # (char, length, opening line)
    in_comment = False
    comment_line = 0  # line of the most recent <!--
    for n, line in enumerate(text.splitlines(), 1):
        if fence is not None:
            m = _FENCE_RE.match(line)
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= fence[1] \
                    and not m.group(3).strip():
                fence = None
            out.append((n, None))
            continue
        if not in_comment:
            m = _FENCE_RE.match(line)
            if m:
                fence = (m.group(2)[0], len(m.group(2)), n)
                out.append((n, None))
                continue
            if re.match(r"^( {4,}|\t)", line):
                out.append((n, None))
                continue
        had_comment = in_comment
        rest = line
        kept = ""
        while rest:
            if in_comment:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                else:
                    rest = rest[end + 3:]
                    in_comment = False
            else:
                start = rest.find("<!--")
                if start < 0:
                    kept += rest
                    rest = ""
                else:
                    kept += rest[:start]
                    rest = rest[start + 4:]
                    in_comment = True
                    had_comment = True
                    comment_line = n
        out.append((n, None if had_comment and not kept.strip() else kept))
    if fence is not None:
        raise DfdError(f"unclosed code fence opened at line {fence[2]}")
    if in_comment:
        raise DfdError(f"unclosed HTML comment opened at line {comment_line}")
    return out


def parse(data: bytes) -> Dfd:
    sha = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DfdError("dfd.md is not UTF-8") from None
    lines = _live_lines(text)
    version = None
    ids: dict[str, list[str]] = {k: [] for k in KINDS}
    seen: set[str] = set()
    flows: list[tuple[str, str, str]] = []  # (flow id, from cell, to cell)
    header: list[str] | None = None  # normalized header of the current table, None outside

    skip = -1
    for idx, (n, line) in enumerate(lines):
        if idx == skip:
            continue
        stripped = (line or "").strip()
        if not stripped.startswith("|"):
            if header is not None and stripped and "|" in stripped:
                raise DfdError(f"line {n}: table row without a leading pipe")
            header = None
            continue
        cells = _cells(stripped)
        if header is None:
            nxt = lines[idx + 1][1] if idx + 1 < len(lines) else None
            if nxt is not None and _SEP_RE.match(nxt.strip()) and not _is_separator(cells):
                header = [c.lower() for c in cells]
                skip = idx + 1
                continue
            raise DfdError(f"line {n}: table row outside a table "
                           "(missing header or separator row?)")
        if cells[0] == "DFD version" and len(cells) > 1:
            version = cells[1]
            continue
        if header[0] != "id":
            continue
        rid = cells[0]
        if not re.match(ID_RE, rid):
            raise DfdError(f"line {n}: invalid ID cell {rid!r}: must match {ID_RE}")
        if rid in seen:
            raise DfdError(f"duplicate ID {rid}")
        seen.add(rid)
        kind = re.match(r"[A-Z]+", rid).group()
        ids[kind].append(rid)
        if kind == "F":
            if "from" not in header or "to" not in header:
                raise DfdError("flows table needs From and To columns")
            fi, ti = header.index("from"), header.index("to")
            flows.append((rid, cells[fi] if fi < len(cells) else "",
                          cells[ti] if ti < len(cells) else ""))

    if not version:
        raise DfdError("dfd.md has no '| DFD version | x.y |' row")
    if not _VERSION_RE.fullmatch(version):
        raise DfdError("DFD version must be letters, digits, '.', '-', '_' or '+', starting with "
                       f"a letter or digit (got {version!a})")

    endpoints = {i for k in "EPD" for i in ids[k]}
    if not endpoints:
        raise DfdError("dfd.md defines no elements")
    for fid, *ends in flows:
        for end in ends:
            m = _ENDPOINT_RE.match(end)
            if not m or m.group() not in endpoints:
                token = m.group() if m else (end.split()[0] if end.split() else "")
                raise DfdError(f"{fid}: unknown endpoint {_escaped(token)}")

    for lst in ids.values():
        lst.sort(key=_num)
    return Dfd(version=version, sha256=sha, ids=ids)


def load(path: Path) -> Dfd:
    return parse(Path(path).read_bytes())
