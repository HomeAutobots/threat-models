"""Run the c4 dialect through the pinned Structurizr and compare with tmreg's own parser.

Skipped unless TM_C4_CONFORMANCE=1 and `docker info` succeeds. Run with `make test-c4`.
Docker always runs with --network none.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmreg import c4

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "c4"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
IDENT = "structurizr.dsl.identifier"


def _skip_reason():
    if os.environ.get("TM_C4_CONFORMANCE") != "1":
        return "c4 conformance tests need TM_C4_CONFORMANCE=1 (run `make test-c4`)"
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return None if ok else "c4 conformance tests need a running Docker (`docker info` failed)"


SKIP = _skip_reason()  # once: it may run docker info
ENV1 = "        ENV1 = deploymentEnvironment"
STYLES = "        styles {"


def _swap(text: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def _seq(key: str, scope: str, *steps: str) -> tuple[str, str]:
    body = "".join(f"            {s}\n" for s in steps)
    return (STYLES, f'        dynamic {scope} "{key}" {{\n            title "{key} Probe"\n{body}'
                    f"        }}\n{STYLES}")


def _path(line: str) -> tuple[str, str]:
    return (ENV1, f"        {line} {{\n            properties {{\n"
                  '                "tm.data.sent" "none"\n                "tm.data.returned" "none"\n'
                  '                "tm.auth" "None"\n            }\n        }\n' + ENV1)


# Files tmreg's problems refuse because the pinned Structurizr refuses them too (probed
# 2026-11-09): (label, shop.dsl changes, words of Structurizr's message).
REFUSED = (
    ("a path from a component to its own container (R38)",
     [_path('R8 = K1 -> C2 "R8 Calls back" "HTTPS"')], "between parents and children"),
    ("a path from a container to its own component (R38)",
     [_path('R8 = C2 -> K1 "R8 Calls into" "HTTPS"')], "between parents and children"),
    ("a component in a system-scoped sequence", [_seq("SEQ2", "S1", "R2")],
     "Components can't be added to a dynamic view"),
    ("a step that ends at the sequence's scope",
     [_path('R8 = A1 -> C2 "R8 Calls" "HTTPS"'), _seq("SEQ2", "C2", "R8")],
     "is already the scope of this view"),
    ("a container and its own component in one sequence",
     [_path('R8 = A1 -> C2 "R8 Calls" "HTTPS"'), _seq("SEQ2", "C3", "R8", "R2")],
     "is already in this view"),
    ("a non-standard style value", [("shape Cylinder", "shape Bogus")], "is not valid"),
)


def _inputs():
    """(label, bytes) for each fixture and each variant of shop.dsl."""
    out = []
    files = sorted(FIXTURES.glob("*.dsl"))
    ordering = ROOT / "systems" / "ordering-platform" / "workspace.dsl"
    if ordering.exists():
        files.append(ordering)
    for p in files:
        out.append((p.name if p.parent == FIXTURES else "ordering-platform/workspace.dsl",
                    p.read_bytes()))
    shop = (FIXTURES / "shop.dsl").read_text(encoding="utf-8")
    swaps = [("Sells goods online.", "Sells goods at https://example.com online."),
             ("Browses the shop and places orders.", "Calls /api/* routes."),
             ("Looks up orders and issues refunds.", "Shows /* not a comment */ text.")]
    strings = shop
    for old, new in swaps:
        assert old in strings, old
        strings = strings.replace(old, new, 1)
    out.append(("shop.dsl with comment-like strings", strings.encode("utf-8")))
    crlf = shop.replace("\n", "\r\n").encode("utf-8")
    out.append(("shop.dsl with BOM and CRLF", b"\xef\xbb\xbf" + crlf))
    # Sequences near the dynamic-view rules, which Structurizr accepts.
    out.append(("shop.dsl with more sequences", _swap(
        shop, _seq("SEQ2", "S1", "R1"), _seq("SEQ3", "C1", "R4"),
        _seq("SEQ4", "C2", "R6", "R7")).encode("utf-8")))
    # The standard styles in another order, and only some of them (ruling R41).
    styles = shop[shop.index(STYLES):shop.index("        }\n    }\n}")]
    out.append(("shop.dsl with some standard styles reordered", _swap(shop, (styles, (
        f'{STYLES}\n            relationship "Async" {{\n                style Dashed\n'
        '            }\n            element "External" {\n                color #ffffff\n'
        '                background #8c8c8c\n            }\n            element "Group" {\n'
        '                strokeWidth 5\n                border Dashed\n'
        '                stroke #c0392b\n            }\n'))).encode("utf-8")))
    return out


@unittest.skipIf(SKIP, SKIP or "")
class ConformanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="tm-c4-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)  # even if this raises
        cls.runs = {}  # label -> (model, validate result, export result, exported json or None)
        for label, data in _inputs():
            model = c4.parse(data)  # a fixture tmreg refuses is a test bug, not a skip
            probs = c4.problems(model)
            if probs:
                raise AssertionError(f"tmreg refuses {label}: {probs}")
            d = cls.tmp / str(len(cls.runs))
            d.mkdir()
            (d / "workspace.dsl").write_bytes(data)
            val = cls._docker(d, ["validate", "-workspace", "workspace.dsl"])
            exp = cls._docker(d, ["export", "-workspace", "workspace.dsl", "-format", "json",
                                  "-output", "out"])
            js = None
            if exp.returncode == 0:
                js = json.loads((d / "out" / "workspace.json").read_text(encoding="utf-8"))
            cls.runs[label] = (model, val, exp, js)

    @staticmethod
    def _docker(d, args):
        return subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "-v", f"{d}:/usr/local/structurizr",
             c4.STRUCTURIZR_IMAGE, *args], capture_output=True, text=True, timeout=300)

    def each(self, check):
        """check(model, js) for every input, each in a subtest of its own, so that one input's
        failure is reported under its label and doesn't hide the others. An input that
        Structurizr didn't export fails its own subtest here."""
        for label, (model, _, exp, js) in self.runs.items():
            with self.subTest(label):
                self.assertIsNotNone(js, f"Structurizr exported no JSON: {exp.stdout}{exp.stderr}")
                check(model, js)

    def test_structurizr_validates(self):
        for label, (_, val, exp, _) in self.runs.items():
            with self.subTest(label):
                self.assertEqual(val.returncode, 0, val.stdout + val.stderr)
                self.assertEqual(exp.returncode, 0, exp.stdout + exp.stderr)

    def test_structurizr_refuses_what_tmreg_refuses(self):
        """Each shape behind one of tmreg's Structurizr rules is a real Structurizr refusal."""
        shop = (FIXTURES / "shop.dsl").read_text(encoding="utf-8")
        for i, (label, pairs, words) in enumerate(REFUSED):
            with self.subTest(label):
                data = _swap(shop, *pairs).encode("utf-8")
                self.assertTrue(c4.problems(c4.parse(data)), "tmreg should refuse it")
                d = self.tmp / f"refused-{i}"
                d.mkdir()
                (d / "workspace.dsl").write_bytes(data)
                val = self._docker(d, ["validate", "-workspace", "workspace.dsl"])
                self.assertNotEqual(val.returncode, 0, val.stdout + val.stderr)
                self.assertIn(words, val.stdout + val.stderr)

    @staticmethod
    def _elements(js):
        """Every element and relationship in the model, flattened, with its own dict."""
        m = js["model"]
        elems, rels = [], []

        def walk_node(n):
            elems.append(n)
            for key in ("containerInstances", "softwareSystemInstances", "infrastructureNodes"):
                elems.extend(n.get(key, []))
            for c in n.get("children", []):
                walk_node(c)

        for p in m.get("people", []):
            elems.append(p)
        for s in m.get("softwareSystems", []):
            elems.append(s)
            for c in s.get("containers", []):
                elems.append(c)
                elems.extend(c.get("components", []))
        for dn in m.get("deploymentNodes", []):
            walk_node(dn)
        for e in elems:
            rels.extend(e.get("relationships", []))
        return elems, rels

    @staticmethod
    def _ident(x):
        v = x.get("properties", {}).get(IDENT)
        return None if v is None or UUID.match(v) else v

    def test_identifiers_match(self):
        def check(model, js):
            elems, rels = self._elements(js)
            got = {i for i in map(self._ident, elems + rels) if i}
            ids = model.ids()
            want = set()
            for kind in ("A", "S", "C", "K", "R", "N", "I"):
                want.update(ids[kind])
            want.update(i for i in ids["TB"] if model.items[i].kind != "group")
            self.assertEqual(got, want)

        self.each(check)

    def test_views_and_environments_match(self):
        def check(model, js):
            views = js.get("views", {})
            keys = set()
            envs = {}
            for field, entries in views.items():
                if not isinstance(entries, list):
                    continue
                for v in entries:
                    if "key" in v:
                        keys.add(v["key"])
                        if field == "deploymentViews":
                            envs[v["key"]] = v.get("environment", "")
            self.assertEqual(keys, set(model.views))
            for key, v in model.views.items():
                if v.kind == "deployment":
                    self.assertTrue(envs[key].startswith(v.env), (key, envs[key], v.env))
            want_envs = set(model.ids()["ENV"])
            got_envs = {e.get("environment", "") for e in js["model"].get("deploymentNodes", [])}
            for env in want_envs:
                self.assertTrue(any(g.startswith(env) for g in got_envs), (env, got_envs))

        self.each(check)

    def test_deployment_pairs_match(self):
        def check(model, js):
            elems, _ = self._elements(js)
            by_id = {e["id"]: e for e in elems}
            owner = {}  # instance id -> identifier of its container or system
            for e in elems:
                ref = e.get("containerId") or e.get("softwareSystemId")
                if ref is not None and "environment" in e and (
                        "containerId" in e or "softwareSystemId" in e):
                    owner[e["id"]] = self._ident(by_id[ref])
            got = set()
            for e in elems:
                if e["id"] in owner:
                    for r in e.get("relationships", []):
                        if r["destinationId"] in owner:
                            got.add((owner[e["id"]], owner[r["destinationId"]]))

            def end(i):
                it = model.items[i]
                if it.kind == "person":
                    return None
                return it.parent if it.kind == "component" else i

            want = set()
            for r in model.rels.values():
                a, b = end(r.source), end(r.destination)
                if a and b and a != b:
                    want.add((a, b))
            self.assertEqual(got, want)
            if model.instances:
                self.assertTrue(want)

        self.each(check)

    def test_strings_match(self):
        def check(model, js):
            elems, rels = self._elements(js)
            checked = 0
            for x in elems:
                i = self._ident(x)
                if i is None or i not in model.items:
                    continue
                it = model.items[i]
                if it.kind == "group":
                    continue
                for f in ("name", "description", "technology"):
                    self.assertEqual(x.get(f, ""), getattr(it, f), (i, f))
                checked += 1
            for x in rels:
                i = self._ident(x)
                if i is None:
                    continue
                r = model.rels[i]
                self.assertEqual(x.get("description", ""), r.description, (i, "description"))
                self.assertEqual(x.get("technology", ""), r.technology, (i, "technology"))
                checked += 1
            self.assertGreater(checked, 0)

        self.each(check)


if __name__ == "__main__":
    unittest.main()
