"""The C4 model in systems/<slug>/workspace.dsl: a strict, safe subset of the Structurizr DSL.

The agent writes this file, and Structurizr's own tools run `!script` and `!plugin` and can fetch
from the network. So `parse` accepts only the dialect of the C4 model spec (section 6) and refuses
anything else with a C4Error whose message starts "line N: ". Every reader goes through it before
Structurizr sees the bytes.

On a parsed model, `problems` lists every content rule it breaks (spec section 5): required
fields, property names, tags, zones, paths, zoom-ins, deployment, and views. `zones`, `crossings`
and `role` compute its trust zones, boundary crossings and DFD roles. `to_record` turns it into
the canonical JSON an approval stores, and `changes` compares two records (spec section 7.4).
Everything here is pure: it reads only the model it is given.
"""
from __future__ import annotations

import hashlib
import re
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
_MAX_DIGITS = 6  # after an ID's prefix; int() refuses over 4,300
_COMMENTS = ("//", "#", "/*")
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
_ODD = re.compile(r"[^\t -~]")  # anything but tab and printable ASCII: checked by isprintable
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
    scope: str | None = None  # the configuration's scope (only "softwaresystem" parses), or None
    line: int = 1  # the workspace statement's line, where problems with the header are reported

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
    for m in _ODD.finditer(line):  # the set cli.visible and the web app's visible() mark
        if not m.group().isprintable():
            raise C4Error(f"line {n}: character U+{ord(m.group()):04X} is not allowed: only "
                          "printable characters, spaces and tabs")
    if "\\" in line:
        raise C4Error(f"line {n}: backslashes are not allowed (no escapes or line continuations)")
    if line.lstrip(" \t").startswith(_COMMENTS):
        raise C4Error(f"line {n}: comments are not allowed (a line starting //, # or /*)")
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
            if "/*" in tok:
                raise C4Error(f"line {n}: /* outside a string is refused: Structurizr may read a "
                              "comment there")
            if tok not in ("{", "}") and ("{" in tok or "}" in tok):
                raise C4Error(f"line {n}: {{ and }} must be separate words (in {_show(tok)})")
            toks.append(tok)
            i = j
    # Structurizr looks for a comment in the first token with its quotes removed.
    if toks and toks[0].strip('"').lstrip(" \t").startswith(_COMMENTS):
        raise C4Error(f"line {n}: a line may not start with //, # or /*, even in quotes: "
                      "Structurizr reads it as a comment")
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
    if len(set(tags)) < len(tags):
        raise C4Error(f'line {n}: a tag appears twice in "{_show(text)}"')
    return tags


def _check_digits(iid: str, n: int) -> None:
    if len(iid) - len(_kind(iid)) > _MAX_DIGITS:
        raise C4Error(f"line {n}: {_show(iid)} has more than {_MAX_DIGITS} digits")


class _Parser:
    def __init__(self) -> None:
        self.stack: list[tuple[str, str | None, int]] = [("top", None, 0)]  # (block, owner, line)
        self.workspace: tuple[str, str, int] | None = None
        self.config_scope: str | None = None
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
        _check_digits(token, n)
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
        self.config_scope = t[1]

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
        if kind == "dynamic":
            _check_digits(key, n)
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
                           steps=tuple(v["steps"]), line=v["line"]) for k, v in self.views.items()},
            scope=self.config_scope, line=ws_line)


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


# ---- Content rules, zones, crossings, roles and records (spec sections 5 and 7.4)

_WAS = re.compile(r"(E|P|D|F|TB)[0-9]+", re.ASCII)  # an old DFD ID, as dfd.ID_RE
_ZOOM = re.compile(r"[1-7](, [1-7])*: .+")
_DATACLASS, _INSPECTION = "tm.dataclass.", "structurizr.inspection."
_ZONE, _ENFORCED = "tm.zone.", "tm.enforced_by."
_PROPS = ("tm.owner", "tm.zoom", "tm.enforced_by", "tm.data.stored", "tm.data.sent",
          "tm.data.returned", "tm.auth", "tm.assumed", "tm.was")
_PROP_LIST = ("tm.owner, tm.zoom, tm.enforced_by, tm.enforced_by.<TB>, tm.zone.<ENV>, "
              "tm.data.stored, tm.data.sent, tm.data.returned, tm.auth, tm.assumed, tm.was")
_DATA = ("tm.data.stored", "tm.data.sent", "tm.data.returned")
_PATH_NEEDS = {"tm.data.sent": "the data classes it sends, or none",
               "tm.data.returned": "the data classes it gets back, or none",
               "tm.auth": "the authentication and authorization on this hop"}
_PROCESS = ("container", "component")
# What may carry each kind-specific property, by _what(); tm.assumed and tm.was go anywhere, and
# tm.zoom, tm.zone.<ENV> and tm.enforced_by.<TB> have rules of their own.
_PLACES = {
    "tm.owner": ("containers and components", lambda x: _what(x) in _PROCESS),
    "tm.enforced_by": ("trust boundary nodes",
                       lambda x: _what(x) == "deploymentNode" and _kind(x.id) == "TB"),
    "tm.data.stored": ("containers and components tagged Data store",
                       lambda x: _what(x) in _PROCESS and "Data store" in x.tags),
    **{name: ("paths", lambda x: _what(x) == "path") for name in _PATH_NEEDS},
}
_TAG_PLACES = {"Data store": ("a container or component", _PROCESS),
               "External": ("a software system", ("softwareSystem",)),
               "Async": ("a path", ("path",)),
               "Trust boundary": ("a deployment node", ("deploymentNode",))}
_TITLES = {"systemContext": "System context diagram for", "container": "Container diagram for",
           "component": "Component diagram for", "deployment": "Deployment diagram for"}
# What `changes` compares; properties leave out tm.was (spec section 7.4).
_CHANGE_FIELDS = ("name", "description", "technology", "tags", "properties", "parent", "group",
                  "source", "destination", "crossings", "zones", "title", "steps")


def _num(iid: str) -> int:
    return int(iid[len(_kind(iid)):])


def _id_order(iid: str) -> tuple[int, int]:
    """Sort key for IDs of mixed kinds: by kind, in KINDS order, then by number."""
    return KINDS.index(_kind(iid)), _num(iid)


def _what(x: Item | Rel) -> str:
    return "path" if isinstance(x, Rel) else x.kind


def _parts(value: str) -> list[str]:
    """A comma-separated property value's entries, stripped; empty entries are kept."""
    return [p.strip() for p in value.split(",")]


def _dataclasses(m: Model) -> dict[str, str]:
    return {k[len(_DATACLASS):]: v for k, v in m.properties.items() if k.startswith(_DATACLASS)}


def _scope_system(m: Model) -> str | None:
    """The system in scope: the software system without the External tag. When `problems`
    finds several, the first that has containers, or else the first."""
    inside = [i.id for i in m.items.values()
              if i.kind == "softwareSystem" and "External" not in i.tags]
    holders = {i.parent for i in m.items.values() if i.kind == "container"}
    return next((s for s in inside if s in holders), inside[0] if inside else None)


def _is_tb_node(m: Model, iid: str) -> bool:
    it = m.items.get(iid)
    return it is not None and it.kind == "deploymentNode" and _kind(iid) == "TB"


def _env_of(m: Model, node: str) -> str | None:
    """The environment a deployment node sits in."""
    it = m.items.get(node)
    while it is not None and it.kind == "deploymentNode":
        it = m.items.get(it.parent)
    return it.id if it is not None and it.kind == "deploymentEnvironment" else None


def _container_of(m: Model, iid: str) -> str | None:
    """The container an element is, or sits in."""
    it = m.items[iid]
    return iid if it.kind == "container" else it.parent if it.kind == "component" else None


class _Places:
    """Where elements sit in each environment, as chains of TB IDs from outer to inner."""

    def __init__(self, m: Model) -> None:
        self.m = m
        self.instances: dict[tuple[str, str], list[Instance]] = {}
        for inst in m.instances:
            self.instances.setdefault((inst.of, inst.env), []).append(inst)
        self.chains: dict[str, list[str]] = {}

    def chain(self, node: str) -> list[str]:
        """The TB nodes around a deployment node, and the node itself if it is one."""
        if node not in self.chains:
            chain, it = [], self.m.items.get(node)
            while it is not None and it.kind == "deploymentNode":
                if _kind(it.id) == "TB":
                    chain.append(it.id)
                it = self.m.items.get(it.parent)
            self.chains[node] = chain[::-1]
        return self.chains[node]

    def of(self, iid: str, env: str) -> list[tuple[Instance | None, list[str]]]:
        """Each place an A, S, C or K sits in env: (the instance, or None for a tm.zone; chain).

        A container sits at each of its instances, and a component at its container's, inside
        its group. A system with instances sits at those. A person, or an external system with
        no instance in env, sits in its tm.zone.<env> node, or in none for outside (or for a
        zone that is missing or wrong, which `problems` reports). The system in scope sits
        nowhere: its containers do.
        """
        it = self.m.items[iid]
        if it.kind in _PROCESS:
            inner = [it.group] if it.group else []
            return [(i, self.chain(i.node) + inner)
                    for i in self.instances.get((_container_of(self.m, iid), env), [])]
        own = [(i, self.chain(i.node)) for i in self.instances.get((iid, env), [])]
        if own or it.kind == "softwareSystem" and "External" not in it.tags:
            return own
        node = it.properties.get(_ZONE + env, "").strip()
        inside = _is_tb_node(self.m, node) and _env_of(self.m, node) == env
        return [(None, self.chain(node) if inside else [])]


def _union(chains: list[list[str]]) -> list[str]:
    """Every TB in the chains, outer to inner: by depth, then by number."""
    depth: dict[str, int] = {}
    for chain in chains:
        for d, tb in enumerate(chain):
            depth[tb] = min(d, depth.get(tb, d))
    return sorted(depth, key=lambda tb: (depth[tb], _num(tb)))


def zones(m: Model) -> dict[str, dict[str, list[str]]]:
    """Each A, S, C and K's zones in each environment: the TBs around it, outer to inner (spec
    section 5.6). Several instances give the union of their chains."""
    places, ids = _Places(m), m.ids()
    return {iid: {env: _union([chain for _, chain in places.of(iid, env)]) for env in ids["ENV"]}
            for kind in ("A", "S", "C", "K") for iid in ids[kind]}


def crossings(m: Model) -> dict[str, dict[str, list[str]]]:
    """The TBs each path crosses in each environment, in ID order (spec section 5.6).

    A path crosses the TBs around one end and not the other, unioned over every pair of the
    ends' places. When both ends sit in one container, only places in the same instance pair up.
    """
    places, ids = _Places(m), m.ids()
    out: dict[str, dict[str, list[str]]] = {}
    for rid in ids["R"]:
        r = m.rels[rid]
        box = _container_of(m, r.source)
        same = box is not None and box == _container_of(m, r.destination)
        out[rid] = {}
        for env in ids["ENV"]:
            crossed: set[str] = set()
            for a, chain_a in places.of(r.source, env):
                for b, chain_b in places.of(r.destination, env):
                    if not same or a == b:
                        crossed |= set(chain_a) ^ set(chain_b)
            out[rid][env] = sorted(crossed, key=_num)
    return out


def role(m: Model, item_id: str) -> str | None:
    """The item's DFD role (spec section 5.8): External entity, Process, Data store, Data flow,
    Trust boundary, or None. KeyError for an ID the model lacks."""
    if item_id in m.rels:
        return "Data flow"
    if item_id not in m.items:
        if item_id in m.views and m.views[item_id].kind == "dynamic":
            return None
        raise KeyError(item_id)
    it = m.items[item_id]
    if it.kind == "person" or it.kind == "softwareSystem" and "External" in it.tags:
        return "External entity"
    if it.kind in _PROCESS:
        return "Data store" if "Data store" in it.tags else "Process"
    return "Trust boundary" if _kind(item_id) == "TB" else None


def where(m: Model, item_id: str) -> list[str]:
    """The items enclosing an item, outermost first, ending with the item: ["S1", "C2", "K3"].
    A path or a sequence stands alone. KeyError for an ID the model lacks."""
    if item_id in m.rels or item_id in m.views and m.views[item_id].kind == "dynamic":
        return [item_id]
    chain = [item_id]
    parent = m.items[item_id].parent
    while parent is not None:
        chain.append(parent)
        parent = m.items[parent].parent
    return chain[::-1]


def to_record(m: Model) -> dict:
    """The model as canonical, JSON-safe data: what an approval stores and `changes` compares."""
    zs, xs, ids = zones(m), crossings(m), m.ids()
    items, rels = {}, {}
    for iid in (i for kind in KINDS for i in ids[kind] if i in m.items):
        it = m.items[iid]
        items[iid] = {"kind": it.kind, "name": it.name, "description": it.description,
                      "technology": it.technology, "tags": list(it.tags),
                      "properties": dict(it.properties), "parent": it.parent, "group": it.group,
                      "role": role(m, iid), "where": where(m, iid), "zones": zs.get(iid, {})}
    for rid in ids["R"]:
        r = m.rels[rid]
        rels[rid] = {"source": r.source, "destination": r.destination,
                     "description": r.description, "technology": r.technology,
                     "tags": list(r.tags), "properties": dict(r.properties), "role": "Data flow",
                     "crossings": xs[rid]}
    views = {k: {"kind": v.kind, "scope": v.scope, "env": v.env, "title": v.title,
                 "steps": list(v.steps)} for k, v in m.views.items()}
    return {"version": m.version, "name": m.name, "description": m.description,
            "dataclasses": _dataclasses(m), "items": items, "rels": rels, "views": views}


def _comparable(record: dict | None) -> dict[str, dict]:
    if record is None:
        return {}
    seqs = {k: v for k, v in record["views"].items() if v["kind"] == "dynamic"}
    return {**record["items"], **record["rels"], **seqs}


def _field(entry: dict, name: str):
    value = entry.get(name)
    if name == "properties" and value is not None:
        value = {k: v for k, v in value.items() if k != "tm.was"}
    return value


def changes(old: dict | None, new: dict) -> dict:
    """What differs between two records, by ID, over items, paths and sequences (spec section
    7.4): {"added": [IDs], "removed": [IDs], "changed": {ID: [fields]}}. tm.was is left out."""
    a, b = _comparable(old), _comparable(new)
    changed = {}
    for iid in sorted(a.keys() & b.keys()):
        fields = [f for f in _CHANGE_FIELDS if _field(a[iid], f) != _field(b[iid], f)]
        if fields:
            changed[iid] = fields
    return {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
            "changed": changed}


def was_map(record: dict) -> dict[str, list[str]]:
    """Each old DFD ID that a tm.was claims -> the items and paths claiming it, in ID order."""
    claims: dict[str, set[str]] = {}
    for iid, entry in [*record["items"].items(), *record["rels"].items()]:
        for old in _parts(entry["properties"].get("tm.was", "")):
            if old:
                claims.setdefault(old, set()).add(iid)
    return {old: sorted(ids, key=_id_order) for old, ids in sorted(claims.items())}


def next_free(m: Model, used: dict[str, set[int]]) -> dict[str, str]:
    """Each kind's next free ID: one above the highest number in the file or in `used`."""
    ids = m.ids()
    top = {kind: max({_num(i) for i in ids[kind]} | set(used.get(kind, ())), default=0)
           for kind in KINDS}
    return {kind: f"{kind}{n + 1}" for kind, n in top.items()}


def problems(m: Model) -> list[str]:
    """Every content rule the model breaks (spec section 5), each "line N: ...", in line order.
    An empty list means the model may be approved."""
    rules = _Rules(m)
    for check in (rules.header, rules.text, rules.properties, rules.tags, rules.scope,
                  rules.zones, rules.paths, rules.zoom, rules.deployment, rules.views):
        check()
    rules.found.sort(key=lambda p: p[0])
    return [f"line {n}: {text}" for n, text in rules.found]


class _Rules:
    """The content rules. Each check adds (line, message) for the item or path at fault."""

    def __init__(self, m: Model) -> None:
        self.m = m
        self.found: list[tuple[int, str]] = []
        self.envs = m.ids()["ENV"]
        self.in_scope = _scope_system(m)
        self.classes = set(_dataclasses(m))
        self.deployed = {(i.of, i.env) for i in m.instances}
        self.opened = {i.parent for i in m.items.values() if i.kind == "component"}

    def add(self, line: int, text: str) -> None:
        self.found.append((line, text))

    def header(self) -> None:
        m = self.m
        if m.scope != "softwaresystem":
            self.add(m.line, "the workspace needs configuration { scope softwaresystem }")
        for name, value in m.properties.items():
            if name.startswith(_DATACLASS):
                cls = name[len(_DATACLASS):]
                if not cls or cls != cls.strip() or "," in cls or cls == "none":
                    self.add(m.line, f'the workspace declares the data class "{_show(cls)}": a '
                             'class name is not empty or "none", has no comma, and has no space '
                             "at either end")
                    continue
            elif name != "tm.version" and not (name.startswith(_INSPECTION)
                                               and name != _INSPECTION):
                self.add(m.line, f'the workspace has the property "{_show(name)}"; its '
                         "properties are tm.version, tm.dataclass.<Name> and "
                         "structurizr.inspection.*")
                continue
            if not value.strip():
                self.add(m.line, f"the workspace's {_show(name)} is empty")

    def text(self) -> None:
        for it in self.m.items.values():
            if it.kind not in ("deploymentEnvironment", "group") and not it.description.strip():
                self.add(it.line, f"{it.id} needs a description")
            if it.kind in (*_PROCESS, "deploymentNode", "infrastructureNode") \
                    and not it.technology.strip():
                self.add(it.line, f"{it.id} needs a technology")
        for r in self.m.rels.values():
            if not r.technology.strip():
                self.add(r.line, f"{r.id} needs a technology: the protocol and transport")

    def properties(self) -> None:
        for x in [*self.m.items.values(), *self.m.rels.values()]:
            for name, value in x.properties.items():
                self.one_property(x, name, value)
        for it in self.m.items.values():
            if it.kind in _PROCESS and "tm.owner" not in it.properties:
                self.add(it.line, f"{it.id} needs tm.owner: the team that owns it")
            if _is_tb_node(self.m, it.id) and "tm.enforced_by" not in it.properties:
                self.add(it.line, f"{it.id} needs tm.enforced_by: what enforces the boundary")
            if it.kind == "group":
                box = self.m.items[it.parent]
                if _ENFORCED + it.id not in box.properties:
                    self.add(box.line, f"{box.id} needs tm.enforced_by.{it.id}: what enforces "
                             f"its group {it.id}")

    def one_property(self, x: Item | Rel, name: str, value: str) -> None:
        if name.startswith(_ZONE):
            env = self.m.items.get(name[len(_ZONE):])
            if env is None or env.kind != "deploymentEnvironment":
                return self.add(x.line, f'{x.id} has the property "{_show(name)}", but '
                                f"{_show(name[len(_ZONE):])} is not an environment")
        elif name.startswith(_ENFORCED):
            group = self.m.items.get(name[len(_ENFORCED):])
            if group is None or group.kind != "group" or group.parent != x.id:
                return self.add(x.line, f'{x.id} has the property "{_show(name)}", but '
                                f"{_show(name[len(_ENFORCED):])} is not a group in {x.id}")
        elif name not in _PROPS:
            return self.add(x.line, f'{x.id} has the property "{_show(name)}", which is not '
                            f"allowed; the names are {_PROP_LIST}")
        if not value.strip():
            return self.add(x.line, f"{x.id}'s {name} is empty")
        if name in _PLACES and not _PLACES[name][1](x):
            return self.add(x.line, f"{x.id} has {name}, which belongs only on {_PLACES[name][0]}")
        if name.startswith(_ZONE):
            self.zone(x, name[len(_ZONE):], value.strip())
        elif name == "tm.zoom":
            if _what(x) != "container" or x.id not in self.opened:
                self.add(x.line, f"{x.id} has tm.zoom, but only a container with components "
                         "takes it")
            elif not _ZOOM.fullmatch(value):
                self.add(x.line, f'{x.id}\'s tm.zoom is "{_show(value)}": write the zoom '
                         'triggers (1 to 7) and a reason, as in "2, 4: holds payment tokens and '
                         'issues refunds"')
        elif name == "tm.was":
            for part in _parts(value):
                if not _WAS.fullmatch(part):
                    self.add(x.line, f'{x.id}\'s tm.was holds "{_show(part)}": it lists old DFD '
                             "IDs (E, P, D, F or TB and a number), separated by commas")
        elif name in _DATA and value.strip() != "none":
            parts = _parts(value)
            if "" in parts:
                self.add(x.line, f"{x.id}'s {name} has an empty entry: write none, or declared "
                         "data classes separated by commas")
            for part in parts:
                if part and part not in self.classes:
                    self.add(x.line, f'{x.id}\'s {name} names "{_show(part)}", which no '
                             "tm.dataclass.<Name> declares: write none, or declared data classes "
                             "separated by commas")

    def zone(self, x: Item | Rel, env: str, value: str) -> None:
        if not (_what(x) == "person" or _what(x) == "softwareSystem" and "External" in x.tags):
            return self.add(x.line, f"{x.id} has tm.zone.{env}, which belongs only on people and "
                            "External systems")
        if (x.id, env) in self.deployed:
            return self.add(x.line, f"{x.id} has an instance in {env}, so its zones come from "
                            f"there: remove tm.zone.{env}")
        if value != "outside" and not (_is_tb_node(self.m, value)
                                       and _env_of(self.m, value) == env):
            self.add(x.line, f'{x.id}\'s tm.zone.{env} is "{_show(value)}": it must be a TB node '
                     f"in {env}, or outside")

    def tags(self) -> None:
        for x in [*self.m.items.values(), *self.m.rels.values()]:
            for tag in x.tags:
                what, kinds = _TAG_PLACES[tag]
                if _what(x) not in kinds:
                    self.add(x.line, f"{x.id} is tagged {tag}, which only {what} may carry")
                elif tag == "Trust boundary" and _kind(x.id) != "TB":
                    self.add(x.line, f"{x.id} is tagged Trust boundary, so its ID must start with "
                             "TB: give it the next free TB number")
                elif tag == "Data store" and "tm.data.stored" not in x.properties:
                    self.add(x.line, f"{x.id} is tagged Data store, so it needs tm.data.stored: "
                             "the data classes it holds")
            if _is_tb_node(self.m, x.id) and "Trust boundary" not in x.tags:
                self.add(x.line, f"{x.id} is a deployment node with a TB ID, so it needs the tag "
                         "Trust boundary")

    def scope(self) -> None:
        systems = [i for i in self.m.items.values() if i.kind == "softwareSystem"]
        inside = [s for s in systems if "External" not in s.tags]
        if not inside:
            self.add(self.m.line, "no software system is in scope: the one being modeled has no "
                     "External tag")
        for s in inside:
            if s.id != self.in_scope:
                self.add(s.line, f"{s.id} has no External tag, but {self.in_scope} is the system "
                         "in scope: tag every other system External")
        holders = {i.parent for i in self.m.items.values() if i.kind == "container"}
        for s in systems:
            if s.id != self.in_scope and s.id in holders:
                self.add(s.line, f"{s.id} has containers, but only the system in scope may")

    def zones(self) -> None:
        for it in self.m.items.values():
            if it.kind == "person" or it.kind == "softwareSystem" and "External" in it.tags:
                for env in self.envs:
                    if (it.id, env) not in self.deployed and _ZONE + env not in it.properties:
                        self.add(it.line, f"{it.id} needs tm.zone.{env}: the TB node it sits in "
                                 f"within {env}, or outside")

    def paths(self) -> None:
        for r in self.m.rels.values():
            for name, need in _PATH_NEEDS.items():
                if name not in r.properties:
                    self.add(r.line, f"{r.id} needs {name}: {need}")
            if r.source == r.destination:
                self.add(r.line, f"{r.id} starts and ends at {r.source}: a path joins two "
                         "different elements")
            if self.in_scope in (r.source, r.destination):
                self.add(r.line, f"{r.id} ends at {self.in_scope}, the system in scope: point it "
                         "at a container or component, so that its crossings are known")

    def zoom(self) -> None:
        for c in self.m.items.values():
            if c.kind == "container" and c.id in self.opened and "tm.zoom" not in c.properties:
                self.add(c.line, f"{c.id} has components, so it needs tm.zoom: the zoom triggers "
                         "(1 to 7) and a reason")

    def deployment(self) -> None:
        if not self.envs:
            self.add(self.m.line, "the model has no deployment environment: add ENV1 with its "
                     "trust boundaries, so that paths have known crossings")
        for c in self.m.items.values():
            if c.kind == "container" and c.parent == self.in_scope:
                for env in self.envs:
                    if (c.id, env) not in self.deployed:
                        self.add(c.line, f"{c.id} has no instance in {env}: every container of "
                                 f"{self.in_scope} needs one in every environment, so that its "
                                 "paths have known crossings")
        held = {i.node for i in self.m.instances} | {
            i.parent for i in self.m.items.values()
            if i.kind in ("deploymentNode", "infrastructureNode")}
        for it in self.m.items.values():
            if _is_tb_node(self.m, it.id) and it.id not in held:
                self.add(it.line, f"{it.id} holds nothing: a trust boundary holds at least one "
                         "node, instance or infrastructure node, or Structurizr does not draw it")

    def views(self) -> None:
        m, s = self.m, self.in_scope
        at, owner = (m.items[s].line, s) if s else (m.line, "the workspace")
        # (key, kind, the scopes it may have, its environment, who needs it, where, its form).
        # Without a system in scope (a problem already), the scope of context and containers
        # goes unchecked.
        required = [("context", "systemContext", {s}, None, owner, at,
                     f'systemContext {s or "<S>"} "context"'),
                    ("containers", "container", {s}, None, owner, at,
                     f'container {s or "<S>"} "containers"')]
        required += [(f"components-{c.id}", "component", {c.id}, None, c.id, c.line,
                      f'component {c.id} "components-{c.id}"')
                     for c in m.items.values() if c.kind == "container" and c.id in self.opened]
        required += [(f"deployment-{e}", "deployment", {"*", s}, e, e, m.items[e].line,
                      f'deployment * {e} "deployment-{e}"') for e in self.envs]
        for key, kind, scopes, env, owner, line, form in required:
            v, scopes = m.views.get(key), scopes - {None}
            if v is None:
                self.add(line, f"{owner} needs the view {form}")
            elif v.kind != kind or v.env != env or scopes and v.scope not in scopes:
                self.add(v.line, f'view "{key}" must be {form}')
            elif v.title.strip() and not v.title.startswith(_TITLES[kind] + " "):
                self.add(v.line, f'view "{key}"\'s title must start "{_TITLES[kind]}"')
        for v in m.views.values():
            if not v.title.strip():
                self.add(v.line, f'view "{v.key}" has no title')
