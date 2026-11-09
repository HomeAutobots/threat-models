"""Parser for systems/<slug>/workspace.dsl: a strict, safe subset of the Structurizr DSL.

The agent writes this file, and Structurizr's own tools run `!script` and `!plugin` and can fetch
from the network. So `parse` accepts only the dialect of the C4 model spec (section 6) and refuses
anything else with a C4Error whose message starts "line N: ". Every reader goes through it before
Structurizr sees the bytes. Content rules (required fields, property names, zones) live elsewhere.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

STRUCTURIZR_IMAGE = "structurizr/structurizr:2026.09.19@sha256:721136283c2f9cf1ba69037bc9de136c579d66fdcb2d771cb60546ec68def1a5"
ID_RE = r"^(A|S|C|K|R|TB|N|I|ENV|SEQ)[1-9][0-9]*$"
KINDS = ("A", "S", "C", "K", "R", "TB", "N", "I", "ENV", "SEQ")
MAX_BYTES = 512 * 1024
TAGS = ("Trust boundary", "Data store", "External", "Async")

_ID = re.compile(ID_RE, re.ASCII)
# tm.version is AI-writable and shown to the owner, so only a plain token parses (as in dfd.py).
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,31}")
_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # view keys end up in the viewer's links
_MAX_DEPTH = 12
_BOM = b"\xef\xbb\xbf"
# Structurizr's own tags and selectors, which a style may name besides TAGS.
_BUILTIN_TAGS = ("Element", "Relationship", "Person", "Software System", "Container", "Component",
                 "Deployment Node", "Infrastructure Node", "Software System Instance",
                 "Container Instance", "Group", "Boundary")
_REFUSED = frozenset("extends url icon logo theme themes image perspectives terminology users "
                     "visibility branding filtered custom animation archetypes".split())
_ELEMENT_STYLE = frozenset("shape background color colour stroke strokeWidth border opacity "
                           "fontSize width height metadata description".split())
_RELATIONSHIP_STYLE = frozenset("thickness color colour style routing fontSize width position "
                                "opacity".split())
_ODD = re.compile(r"[^\t -~]")  # anything but tab and printable ASCII: checked by category
_BANG = re.compile(r"![^\W\d_]")  # "!" then a letter, ASCII or not: a directive
_FLAT = re.compile(r"[ \t]*!identifiers[ \t]+flat[ \t]*")
_PATH_ENDS = ("person", "softwareSystem", "container", "component")

# construct: (ID kinds, positional strings, takes a tags string, needs a block)
_ELEMENTS = {
    "person": (("A",), ("name", "description"), False, False),
    "softwareSystem": (("S",), ("name", "description"), True, False),
    "container": (("C",), ("name", "description", "technology"), True, False),
    "component": (("K",), ("name", "description", "technology"), True, False),
    "deploymentEnvironment": (("ENV",), ("name",), False, True),
    "deploymentNode": (("N", "TB"), ("name", "description", "technology"), True, True),
    "infrastructureNode": (("I",), ("name", "description", "technology"), False, False),
}
# view kind: (its form, what its scope may name). A deployment view's scope may also be "*".
_VIEWS = {
    "systemContext": ('systemContext <S> "<key>" {', ("softwareSystem",)),
    "container": ('container <S> "<key>" {', ("softwareSystem",)),
    "component": ('component <C> "<key>" {', ("container",)),
    "deployment": ('deployment <*|S> <ENV> "<key>" {', ("softwareSystem",)),
    "dynamic": ('dynamic <S|C> "<SEQ key>" {', ("softwareSystem", "container")),
}
# Statements allowed in each block. "=x" is "<ID> = x ...", '"' a property line, "step" a
# dynamic view's path ID.
_ALLOWED = {
    "top": {"workspace"},
    "workspace": {"!identifiers", "properties", "configuration", "model", "views"},
    "configuration": {"scope"},
    "properties": {'"'},
    "model": {"=person", "=softwareSystem", "=path", "=deploymentEnvironment"},
    "person": {"properties"},
    "path": {"properties"},
    "softwareSystem": {"properties", "=container"},
    "container": {"properties", "=component", "group"},
    "group": {"=component"},
    "component": {"properties"},
    "deploymentEnvironment": {"=deploymentNode"},
    "deploymentNode": {"properties", "=deploymentNode", "=infrastructureNode",
                       "containerInstance", "softwareSystemInstance"},
    "infrastructureNode": {"properties"},
    "views": {"systemContext", "container", "component", "deployment", "dynamic", "styles"},
    "view": {"title", "include", "autoLayout"},
    "dynamic": {"title", "autoLayout", "step"},
    "styles": {"element", "relationship"},
    "element": _ELEMENT_STYLE,
    "relationship": _RELATIONSHIP_STYLE,
}


class C4Error(ValueError):
    """The file is outside the dialect. The message starts "line N: " when a line is known."""


@dataclass(frozen=True)
class Item:
    """An element. kind is its construct: person, softwareSystem, container, component,
    deploymentNode (an N, or a TB boundary), infrastructureNode, deploymentEnvironment, or group
    (a TB boundary inside a container)."""
    id: str
    kind: str
    name: str
    description: str
    technology: str
    tags: tuple[str, ...]
    properties: dict[str, str]
    parent: str | None  # S for C, C for K and for a group, node or ENV for a node
    group: str | None  # the TB group a component sits in
    line: int


@dataclass(frozen=True)
class Rel:
    """A path: a relationship with an R ID."""
    id: str
    source: str
    destination: str
    description: str
    technology: str
    tags: tuple[str, ...]
    properties: dict[str, str]
    line: int


@dataclass(frozen=True)
class Instance:
    of: str  # a C (containerInstance) or an S (softwareSystemInstance)
    node: str  # the N or TB node it sits in
    env: str
    line: int


@dataclass(frozen=True)
class View:
    key: str
    kind: str  # systemContext|container|component|deployment|dynamic
    scope: str  # an S or C ID, or "*" for a deployment view
    env: str | None  # the ENV of a deployment view
    title: str
    steps: tuple[str, ...]  # a dynamic view's R IDs
    line: int


@dataclass(frozen=True)
class Model:
    name: str
    description: str
    version: str
    sha256: str  # of the raw bytes
    properties: dict[str, str]  # workspace properties
    items: dict[str, Item]
    rels: dict[str, Rel]
    instances: tuple[Instance, ...]
    views: dict[str, View]

    def ids(self) -> dict[str, list[str]]:
        """Every KIND's IDs, sorted by number. SEQ IDs are dynamic view keys; TB includes groups."""
        out: dict[str, list[str]] = {k: [] for k in KINDS}
        seqs = [k for k, v in self.views.items() if v.kind == "dynamic"]
        for i in [*self.items, *self.rels, *seqs]:
            out[_kind(i)].append(i)
        for lst in out.values():
            lst.sort(key=lambda i: int(i[len(_kind(i)):]))
        return out

    def all_ids(self) -> set[str]:
        return {i for lst in self.ids().values() for i in lst}


def _kind(iid: str) -> str:
    return _ID.fullmatch(iid).group(1)


def _show(text: str) -> str:
    """Text for an error message: shortened, with non-printable characters as escapes."""
    text = text if len(text) <= 60 else text[:60] + "..."
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii")
                   for c in text)


def _is_str(token: str) -> bool:
    return token.startswith('"')


def _text(token: str) -> str:
    return token[1:-1]


def _check_text(line: str, n: int) -> None:
    """Refuse characters, comments, directives, and substitutions on one line, strings included."""
    for m in _ODD.finditer(line):
        if unicodedata.category(m.group()) in ("Cc", "Cf", "Zl", "Zp"):
            raise C4Error(f"line {n}: character U+{ord(m.group()):04X} is not allowed: no control, "
                          "invisible formatting, or line separator characters")
    if "\\" in line:
        raise C4Error(f"line {n}: backslashes are not allowed (no escapes or line continuations)")
    if line.lstrip(" \t").startswith(("//", "#")) or "/*" in line:
        raise C4Error(f"line {n}: comments are not allowed (// or # at the start of a line, or /*)")
    bang = _BANG.search(line)
    if bang and not _FLAT.fullmatch(line):
        word = re.match(r'![^\s"]*', line[bang.start():]).group()
        raise C4Error(f"line {n}: directives are refused, here {_show(word)}; "
                      "the only one allowed is !identifiers flat")
    if "${" in line:
        raise C4Error(f"line {n}: '${{' is refused: Structurizr would substitute a value there")


def _tokens(line: str, n: int) -> list[str]:
    """Split a line into double-quoted strings (kept with their quotes) and bare words."""
    toks: list[str] = []
    i, end = 0, len(line)
    while i < end:
        if line[i] in " \t":
            i += 1
        elif line[i] == '"':
            j = line.find('"', i + 1)
            if j < 0:
                raise C4Error(f"line {n}: a string must end on the line it starts on")
            if j + 1 < end and line[j + 1] not in " \t":
                raise C4Error(f"line {n}: a string must be followed by a space or the end of the "
                              'line, and strings contain no "')
            if line[i + 1:j].strip(" \t") in ("{", "}"):
                raise C4Error(f'line {n}: a string may not be just "{{" or "}}"')
            toks.append(line[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < end and line[j] not in " \t":
                j += 1
            tok = line[i:j]
            odd = next((c for c in tok if not "!" <= c <= "~"), None)
            if odd:
                raise C4Error(f"line {n}: character U+{ord(odd):04X} is not allowed outside a "
                              f"string (in {_show(tok)})")
            if '"' in tok:
                raise C4Error(f"line {n}: a quote inside {_show(tok)}: strings start after a space")
            if tok not in ("{", "}") and ("{" in tok or "}" in tok):
                raise C4Error(f"line {n}: {{ and }} must be separate words (in {_show(tok)})")
            toks.append(tok)
            i = j
    return toks


def _key(t: list[str], ctx: str) -> str:
    """What kind of statement the tokens are, as _ALLOWED names it."""
    if len(t) > 1 and t[1] == "=":
        return "=path" if len(t) > 3 and t[3] == "->" else "=" + (t[2] if len(t) > 2 else "")
    if _is_str(t[0]):
        return '"'
    if ctx == "dynamic" and t[0] not in ("title", "autoLayout", "include"):
        return "step"
    return t[0]


def _check_named(text: str, iid: str, field: str, n: int) -> None:
    if not text.startswith(iid + " ") or not text[len(iid) + 1:].strip():
        raise C4Error(f'line {n}: the {field} of {iid} must be "{iid} " followed by text '
                      f'(got "{_show(text)}")')


def _tags(text: str, n: int) -> tuple[str, ...]:
    tags = tuple(t.strip() for t in text.split(","))
    for tag in tags:
        if tag not in TAGS:
            raise C4Error(f'line {n}: unknown tag "{_show(tag)}"; the tags are ' + ", ".join(TAGS))
    return tags


class _Parser:
    def __init__(self) -> None:
        self.stack: list[tuple[str, str | None, int]] = [("top", None, 0)]  # (block, owner, line)
        self.workspace: tuple[str, str, int] | None = None
        self.flat = False
        self.done: set[tuple[int, str]] = set()  # (block's line, statement) for once-only ones
        self.lines: dict[str, int] = {}  # element and path IDs -> the line defining them
        self.items: dict[str, dict] = {}
        self.rels: dict[str, dict] = {}
        self.props: dict[str | None, dict[str, str]] = {None: {}}  # None: the workspace's
        self.instances: list[Instance] = []
        self.views: dict[str, dict] = {}
        self.refs: list[tuple[int, str, tuple[str, ...], str]] = []  # checked once all is read

    def statement(self, t: list[str], n: int) -> None:
        ctx, owner, _ = self.stack[-1]
        refused = next((x for x in t if x in _REFUSED), None)
        if refused:
            raise C4Error(f"line {n}: '{refused}' is refused: it is outside the safe dialect")
        if t == ["}"]:
            return self.close(n)
        if "}" in t:
            raise C4Error(f"line {n}: }} must stand alone on its line")
        block = t[-1] == "{"
        t = t[:-1] if block else t
        if "{" in t or not t:
            raise C4Error(f"line {n}: {{ must end the line of the statement it opens")
        if len(t) > 1 and t[1] == "->":
            raise C4Error(f"line {n}: a path needs an ID: R<n> = <source> -> <destination> ...")
        key = _key(t, ctx)
        if ctx == "workspace" and not self.flat and key != "!identifiers":
            raise C4Error(f"line {n}: the workspace must start with !identifiers flat")
        if key not in _ALLOWED[ctx]:
            self.misplaced(t, key, n)
        if ctx in ("element", "relationship"):
            return self.style_line(t, n, block)
        if key.startswith("=") and key != "=path":
            return self.element(t, n, block, owner)
        getattr(self, _METHODS[key])(t, n, block, owner)

    def misplaced(self, t: list[str], key: str, n: int) -> None:
        ctx, _, opened = self.stack[-1]
        if ctx == "top":
            raise C4Error(f'line {n}: the file holds one workspace "<name>" "<description>" {{ '
                          "block and nothing else")
        if key == "=path":
            what = "a path"
        elif key == '"':
            what = "a property"
        elif key[1:] in _ELEMENTS and key.startswith("="):
            what = f"a {key[1:]}"
        else:
            what = f"'{_show(' '.join(t[:3]) if key.startswith('=') else t[0])}'"
        raise C4Error(f"line {n}: {what} is not allowed in the {ctx} block opened on line {opened}")

    def push(self, ctx: str, owner: str | None, n: int) -> None:
        if len(self.stack) > _MAX_DEPTH:  # stack[0] is the top level, so _MAX_DEPTH blocks are open
            raise C4Error(f"line {n}: blocks nest more than {_MAX_DEPTH} deep")
        self.stack.append((ctx, owner, n))

    def once(self, what: str, n: int) -> None:
        mark = (self.stack[-1][2], what)
        if mark in self.done:
            raise C4Error(f"line {n}: {what} appears twice in one block")
        self.done.add(mark)

    def close(self, n: int) -> None:
        ctx, owner, _ = self.stack[-1]
        if ctx == "top":
            raise C4Error(f"line {n}: }} closes no block")
        if ctx == "workspace" and not self.flat:
            raise C4Error(f"line {n}: the workspace must start with !identifiers flat")
        if ctx in ("view", "dynamic"):
            v = self.views[owner]
            if ctx == "view" and not v["include"]:
                raise C4Error(f'line {v["line"]}: view "{owner}" needs include *')
            if ctx == "dynamic":
                _check_named(v["title"], owner, "title", v["title_line"] or v["line"])
        self.stack.pop()

    def new_id(self, token: str, kinds: tuple[str, ...], what: str, n: int) -> str:
        if not _ID.fullmatch(token):
            raise C4Error(f"line {n}: {_show(token)} is not an ID: IDs match {ID_RE}")
        if _kind(token) not in kinds:
            raise C4Error(f"line {n}: a {what}'s ID starts with {' or '.join(kinds)}, not {token}")
        if token in self.lines:
            raise C4Error(f"line {n}: {token} is already defined on line {self.lines[token]}")
        self.lines[token] = n
        return token

    def add_item(self, iid: str, kind: str, name: str, n: int, parent: str | None, *,
                 description: str = "", technology: str = "", tags: tuple[str, ...] = (),
                 group: str | None = None) -> None:
        self.items[iid] = {"id": iid, "kind": kind, "name": name, "description": description,
                           "technology": technology, "tags": tags, "parent": parent,
                           "group": group, "line": n}
        self.props[iid] = {}

    # Statements, each called with (tokens without a final "{", line, whether "{" ended it, owner).

    def workspace_(self, t, n, block, owner):
        if self.workspace:
            raise C4Error(f"line {n}: the file holds one workspace; nothing may follow it")
        if len(t) != 3 or not all(map(_is_str, t[1:])) or not block:
            raise C4Error(f'line {n}: write workspace "<name>" "<description>" {{')
        self.workspace = (_text(t[1]), _text(t[2]), n)
        self.push("workspace", None, n)

    def identifiers(self, t, n, block, owner):
        if self.flat or block:
            raise C4Error(f"line {n}: !identifiers flat is the workspace's first statement, once")
        self.flat = True

    def block(self, t, n, block, owner):
        if len(t) != 1 or not block:
            raise C4Error(f"line {n}: write {t[0]} {{")
        self.once(t[0], n)
        self.push(t[0], owner, n)

    def scope(self, t, n, block, owner):
        if t != ["scope", "softwaresystem"] or block:
            raise C4Error(f"line {n}: the only configuration is scope softwaresystem")
        self.once("scope", n)

    def property(self, t, n, block, owner):
        if len(t) != 2 or not _is_str(t[1]) or block:
            raise C4Error(f'line {n}: a property line is "<name>" "<value>"')
        name, value = _text(t[0]), _text(t[1])
        props = self.props[owner]
        if name in props:
            raise C4Error(f'line {n}: property "{_show(name)}" is set twice')
        if owner is None and name == "tm.version" and not _VERSION_RE.fullmatch(value):
            raise C4Error(f"line {n}: tm.version must be letters, digits, '.', '-', '_' or '+', "
                          f'starting with a letter or digit, up to 32 (got "{_show(value)}")')
        props[name] = value

    def element(self, t, n, block, owner):
        construct = t[2]
        kinds, fields, takes_tags, needs_block = _ELEMENTS[construct]
        iid = self.new_id(t[0], kinds, construct, n)
        args = t[3:]
        if not all(map(_is_str, args)) or len(args) not in (len(fields), len(fields) + takes_tags) \
                or (needs_block and not block):
            usage = " ".join(f'"<{f}>"' for f in fields) + (' ["<tags>"]' if takes_tags else "")
            raise C4Error(f"line {n}: write {'|'.join(kinds)}<n> = {construct} {usage} "
                          + ("{" if needs_block else "[{]"))
        values = dict(zip(fields, map(_text, args)))
        _check_named(values["name"], iid, "name", n)
        parent, group = owner, None
        if self.stack[-1][0] == "group":
            parent, group = self.items[owner]["parent"], owner
        self.add_item(iid, construct, values["name"], n, parent, group=group,
                      description=values.get("description", ""),
                      technology=values.get("technology", ""),
                      tags=_tags(_text(args[-1]), n) if len(args) > len(fields) else ())
        if block:
            self.push(construct, iid, n)

    def path(self, t, n, block, owner):
        rid = self.new_id(t[0], ("R",), "path", n)
        args = t[5:]
        if len(t) not in (7, 8) or not all(_ID.fullmatch(e) for e in (t[2], t[4])) \
                or not all(map(_is_str, args)):
            raise C4Error(f'line {n}: write R<n> = <source ID> -> <destination ID> "<description>" '
                          '"<technology>" ["<tags>"] [{]')
        description = _text(args[0])
        _check_named(description, rid, "description", n)
        self.rels[rid] = {"id": rid, "source": t[2], "destination": t[4],
                          "description": description, "technology": _text(args[1]),
                          "tags": _tags(_text(args[2]), n) if len(args) == 3 else (), "line": n}
        self.props[rid] = {}
        self.refs += [(n, t[2], _PATH_ENDS, "path end"), (n, t[4], _PATH_ENDS, "path end")]
        if block:
            self.push("path", rid, n)

    def group(self, t, n, block, owner):
        if len(t) != 2 or not _is_str(t[1]) or not block:
            raise C4Error(f'line {n}: write group "TB<n> <name>" {{')
        name = _text(t[1])
        gid = name.split(" ", 1)[0]
        if not _ID.fullmatch(gid) or _kind(gid) != "TB":
            raise C4Error(f'line {n}: a group is a trust boundary: its name starts with "TB<n> " '
                          f'(got "{_show(name)}")')
        self.new_id(gid, ("TB",), "group", n)
        _check_named(name, gid, "name", n)
        self.add_item(gid, "group", name, n, owner)
        self.push("group", gid, n)

    def instance(self, t, n, block, owner):
        if len(t) != 2 or _is_str(t[1]) or block:
            raise C4Error(f"line {n}: write {t[0]} <ID>, with no block")
        env = next(o for ctx, o, _ in reversed(self.stack) if ctx == "deploymentEnvironment")
        self.instances.append(Instance(of=t[1], node=owner, env=env, line=n))
        want = "container" if t[0] == "containerInstance" else "softwareSystem"
        self.refs.append((n, t[1], (want,), t[0]))

    def view(self, t, n, block, owner):
        kind = t[0]
        usage, scopes = _VIEWS[kind]
        if len(t) != (4 if kind == "deployment" else 3) or not block or not _is_str(t[-1]) \
                or any(map(_is_str, t[1:-1])):
            raise C4Error(f"line {n}: write {usage}")
        key = _text(t[-1])
        if kind == "dynamic" and not (_ID.fullmatch(key) and _kind(key) == "SEQ"):
            raise C4Error(f'line {n}: a dynamic view\'s key is its ID, SEQ<n> (got "{_show(key)}")')
        if not _KEY_RE.fullmatch(key):
            raise C4Error(f"line {n}: a view key is up to 64 letters, digits, '-' and '_' "
                          f'(got "{_show(key)}")')
        if key in self.views:
            raise C4Error(f'line {n}: view key "{key}" is already used on line '
                          f'{self.views[key]["line"]}')
        env = t[2] if kind == "deployment" else None
        if t[1] != "*" or kind != "deployment":
            self.refs.append((n, t[1], scopes, f"the {kind} view's scope"))
        if env is not None:
            self.refs.append((n, env, ("deploymentEnvironment",),
                              "the deployment view's environment"))
        self.views[key] = {"key": key, "kind": kind, "scope": t[1], "env": env, "title": "",
                           "title_line": None, "steps": [], "include": False, "line": n}
        self.push("dynamic" if kind == "dynamic" else "view", key, n)

    def title(self, t, n, block, owner):
        if len(t) != 2 or not _is_str(t[1]) or block:
            raise C4Error(f'line {n}: write title "<text>"')
        self.once("title", n)
        self.views[owner].update(title=_text(t[1]), title_line=n)

    def include(self, t, n, block, owner):
        if t != ["include", "*"] or block:
            raise C4Error(f"line {n}: a view includes only *: write include *")
        self.once("include", n)
        self.views[owner]["include"] = True

    def auto_layout(self, t, n, block, owner):
        if len(t) > 2 or t[1:] and t[1] not in ("tb", "bt", "lr", "rl") or block:
            raise C4Error(f"line {n}: write autoLayout [tb|bt|lr|rl]")
        self.once("autoLayout", n)

    def step(self, t, n, block, owner):
        if len(t) != 1 or block or not (_ID.fullmatch(t[0]) and _kind(t[0]) == "R"):
            raise C4Error(f"line {n}: a dynamic view's step is one path ID, R<n>, alone on its "
                          f"line (got {_show(' '.join(t))})")
        self.views[owner]["steps"].append(t[0])
        self.refs.append((n, t[0], ("path",), "dynamic view step"))

    def style(self, t, n, block, owner):
        if len(t) != 2 or not _is_str(t[1]) or not block:
            raise C4Error(f'line {n}: write {t[0]} "<tag>" {{')
        if _text(t[1]) not in TAGS + _BUILTIN_TAGS:
            raise C4Error(f'line {n}: a style names a tag, and "{_show(_text(t[1]))}" is not one: '
                          + ", ".join(TAGS + _BUILTIN_TAGS))
        self.push(t[0], None, n)

    def style_line(self, t, n, block):
        if len(t) != 2 or block:
            raise C4Error(f"line {n}: a style line is one property and one value")

    def finish(self, sha: str) -> Model:
        if len(self.stack) > 1:
            ctx, _, opened = self.stack[-1]
            raise C4Error(f"line {opened}: the {ctx} block opened here is never closed "
                          "(missing })")
        if self.workspace is None:
            raise C4Error("line 1: the file has no workspace block")
        name, description, ws_line = self.workspace
        if "tm.version" not in self.props[None]:
            raise C4Error(f"line {ws_line}: the workspace has no tm.version property")
        for n, ref, kinds, what in self.refs:
            found = ref in self.rels if kinds == ("path",) else \
                ref in self.items and self.items[ref]["kind"] in kinds
            if not found:
                raise C4Error(f"line {n}: {what} {_show(ref)} is not a defined "
                              + " or ".join(kinds))
        return Model(
            name=name, description=description, version=self.props[None]["tm.version"], sha256=sha,
            properties=self.props[None],
            items={i: Item(**d, properties=self.props[i]) for i, d in self.items.items()},
            rels={i: Rel(**d, properties=self.props[i]) for i, d in self.rels.items()},
            instances=tuple(self.instances),
            views={k: View(key=k, kind=v["kind"], scope=v["scope"], env=v["env"], title=v["title"],
                           steps=tuple(v["steps"]), line=v["line"]) for k, v in self.views.items()})


_METHODS = {"workspace": "workspace_", "!identifiers": "identifiers", "properties": "block",
            "configuration": "block", "model": "block", "views": "block", "styles": "block",
            "scope": "scope", '"': "property", "=path": "path", "group": "group",
            "containerInstance": "instance", "softwareSystemInstance": "instance",
            **{kind: "view" for kind in _VIEWS}, "title": "title", "include": "include",
            "autoLayout": "auto_layout", "step": "step", "element": "style",
            "relationship": "style"}


def parse(data: bytes) -> Model:
    """The model in a workspace.dsl, or C4Error at the first line outside the safe dialect."""
    if len(data) > MAX_BYTES:
        n = data.count(b"\n", 0, MAX_BYTES) + 1
        raise C4Error(f"line {n}: the file is {len(data)} bytes, over the 512 KiB limit "
                      f"({MAX_BYTES} bytes), which falls on this line")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:  # e.start counts from after a BOM
        n = data.count(b"\n", 0, e.start + (len(_BOM) if data.startswith(_BOM) else 0)) + 1
        raise C4Error(f"line {n}: the file is not valid UTF-8") from None
    p = _Parser()
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        _check_text(line, n)
        tokens = _tokens(line, n)
        if tokens:
            p.statement(tokens, n)
    return p.finish(hashlib.sha256(data).hexdigest())
