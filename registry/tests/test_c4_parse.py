"""c4.parse: the safe subset of the Structurizr DSL, refused line by line with "line N: " errors."""
import hashlib
import unittest
from pathlib import Path

from tmreg import c4

FIXTURES = Path(__file__).parent / "fixtures"
SHOP = (FIXTURES / "c4/shop.dsl").read_bytes()
FLAT = "    !identifiers flat\n"


def _b(text: str | bytes) -> bytes:
    return text.encode() if isinstance(text, str) else text


def mutate(old: str | bytes, new: str | bytes) -> bytes:
    """SHOP with its one occurrence of `old` replaced by `new`."""
    if SHOP.count(_b(old)) != 1:
        raise AssertionError(f"{old!r} occurs {SHOP.count(_b(old))} times in shop.dsl")
    return SHOP.replace(_b(old), _b(new))


def line_of(text: str) -> int:
    """The line of SHOP on which `text` starts."""
    return SHOP[:SHOP.index(text.encode())].count(b"\n") + 1


class ParseTest(unittest.TestCase):
    def assertRefused(self, data: bytes, line: int | None = None, words: str = ""):
        head = rf"^line {line}: " if line else r"^line \d+: "
        with self.assertRaisesRegex(c4.C4Error, head + (rf".*{words}" if words else "")):
            c4.parse(data)

    def test_example_parses(self):
        m = c4.parse(SHOP)
        self.assertEqual(m.version, "1.0")
        self.assertEqual(m.sha256, hashlib.sha256(SHOP).hexdigest())
        self.assertEqual(m.ids()["R"], [f"R{n}" for n in range(1, 8)])
        self.assertEqual(m.ids()["TB"], ["TB1", "TB2", "TB3", "TB4", "TB5", "TB6", "TB7"])
        self.assertEqual(m.ids()["SEQ"], ["SEQ1"])
        self.assertEqual((m.items["K3"].parent, m.items["K3"].group), ("C2", "TB6"))
        self.assertEqual((m.rels["R6"].source, m.rels["R6"].destination), ("A2", "K3"))
        self.assertEqual(m.views["SEQ1"].steps, ("R1", "R2", "R4", "R5", "R3"))
        self.assertEqual(m.items["C3"].tags, ("Data store",))
        self.assertIn(("C2", "TB3", "ENV1"), {(i.of, i.node, i.env) for i in m.instances})

    def test_example_details(self):
        m = c4.parse(SHOP)
        self.assertEqual((m.name, m.properties["tm.version"]), ("Shop", "1.0"))
        self.assertEqual(sorted(m.ids()), sorted(c4.KINDS))
        self.assertEqual(m.ids()["N"], ["N1"])
        self.assertEqual(len(m.all_ids()), sum(len(v) for v in m.ids().values()))
        self.assertEqual(m.items["TB6"].kind, "group")
        self.assertEqual(m.items["TB6"].parent, "C2")
        self.assertEqual(m.items["TB3"].kind, "deploymentNode")
        self.assertEqual(m.items["TB3"].parent, "TB2")
        self.assertEqual(m.items["TB1"].parent, "ENV1")
        self.assertEqual(m.items["I1"].parent, "TB5")
        self.assertEqual(m.items["C2"].properties["tm.owner"], "Orders team")
        self.assertEqual(m.items["C2"].technology, "Python, FastAPI")
        self.assertEqual(m.items["C2"].line, line_of("C2 = container"))
        self.assertEqual(m.rels["R3"].properties["tm.auth"],
                         "Database user for the API; unknown — ask platform team")
        self.assertEqual(m.views["deployment-ENV1"].env, "ENV1")
        self.assertEqual(m.views["deployment-ENV1"].scope, "*")
        self.assertEqual(m.views["SEQ1"].title, "SEQ1 Checkout: an order is placed and paid")
        self.assertIn(("S2", "TB7", "ENV1"), {(i.of, i.node, i.env) for i in m.instances})

    def test_refuses_each_directive(self):
        for d in ("!script groovy {", "!plugin com.x.P", "!include more.dsl", "!docs docs",
                  "!adrs adrs", "!const X 1", "!impliedRelationships false",
                  "!identifiers hierarchical"):
            with self.subTest(d):
                self.assertRefused(mutate(FLAT, f"{FLAT}    {d}\n"), line_of(FLAT) + 1)

    def test_refuses_directive_inside_a_string(self):
        self.assertRefused(mutate('"Sells goods online."', '"Runs !script at start"'),
                           line_of("S1 = softwareSystem"))
        self.assertRefused(mutate('"tm.owner" "Web team"', '"tm.owner" "Web !Include"'),
                           line_of('"tm.owner" "Web team"'))

    def test_keyword_words_in_text_are_fine(self):
        for iid, field, old, new in (
                ("S1", "description", '"Sells goods online."', "Fetches the URL"),
                ("S1", "name", '"S1 Shop"', "S1 Theme park"),
                ("S2", "description", '"Takes card payments."', "Wow! Fast"),
                ("K3", "description", '"Lists orders and issues refunds."',
                 "Shows an image, icon, logo and url!"),
                ("R1", "description", '"R1 Places orders using"',
                 "R1 Extends filtered perspectives using")):
            with self.subTest(new):
                m = c4.parse(mutate(old, f'"{new}"'))
                self.assertEqual(getattr(m.items.get(iid) or m.rels[iid], field), new)

    def test_refuses_statement_keywords(self):
        a1 = 'A1 = person "A1 Customer" "Browses the shop and places orders." {\n'
        person = 'element "Person" {\n'
        views = "    views {\n"
        c1 = '"React SPA" {\n'
        title = '            title "System context diagram for S1 Shop"\n'
        for kw, data in (
                ("url", mutate(a1, a1 + '            url "https://example.com"\n')),
                ("icon", mutate(person, person + '                icon "https://example.com/i.png"\n')),
                ("theme", mutate(views, views + "        theme default\n")),
                ("perspectives", mutate(c1, c1 + "                perspectives {\n                }\n")),
                ("image", mutate(views, views + '        image * "img" {\n        }\n')),
                ("filtered", mutate(views, views + '        filtered "context" include "Element" "f"\n')),
                ("extends", mutate('workspace "Shop"', 'workspace extends "https://example.com/a.dsl"')),
                ("animation", mutate(title, title + "            animation {\n            }\n"))):
            with self.subTest(kw):
                self.assertRefused(data, words=kw)

    def test_refuses_comments(self):
        for comment in ("// x", "# x", "/* x */"):
            with self.subTest(comment):
                self.assertRefused(mutate(FLAT, f"{FLAT}    {comment}\n"), line_of(FLAT) + 1)
        self.assertRefused(mutate('"Sells goods online."', '"Sells /* goods */ online."'),
                           line_of("S1 = softwareSystem"))

    def test_refuses_bad_text(self):
        s1 = line_of("S1 = softwareSystem")
        for bad in ("\x07", "\u202e", "\u200b", "\ufeff", "\r", "\x85", "\u2028"):
            with self.subTest(hex(ord(bad))):
                self.assertRefused(mutate("Sells goods", f"Sells{bad} goods"), s1)
        self.assertRefused(SHOP.replace(b"\n", b"\r"), 1)  # old Mac line ends: one long line
        self.assertRefused(mutate("Sells goods", b"Sells \xff goods"), s1, "UTF-8")
        self.assertRefused(mutate("Sells goods", b"Sells \xed\xa0\x80 goods"), s1, "UTF-8")
        with self.assertRaisesRegex(c4.C4Error, r"^line \d+: .*512 KiB"):
            c4.parse(SHOP + b" " * (c4.MAX_BYTES + 1 - len(SHOP)))
        with self.assertRaisesRegex(c4.C4Error, r"^line \d+: .*512 KiB"):
            c4.parse(SHOP + b"\n" * (600 * 1024 - len(SHOP)))
        c4.parse(SHOP + b"\n" * (c4.MAX_BYTES - len(SHOP)))  # exactly the limit is fine

    def test_accepts_bom_and_crlf(self):
        m = c4.parse(b"\xef\xbb\xbf" + SHOP.replace(b"\n", b"\r\n"))
        self.assertEqual(m.ids(), c4.parse(SHOP).ids())
        self.assertNotEqual(m.sha256, c4.parse(SHOP).sha256)
        self.assertEqual(m.items["C3"].name, "C3 Orders DB")  # no stray \r on the last token

    def test_id_rules(self):
        c3 = 'C3 = container "C3 Orders DB"'
        for label, old, new in (
                ("C0", c3, 'C0 = container "C0 Orders DB"'),
                ("c3", c3, 'c3 = container "c3 Orders DB"'),
                ("X1", c3, 'X1 = container "X1 Orders DB"'),
                ("C01", c3, 'C01 = container "C01 Orders DB"'),
                ("Cyrillic", c3, '\u04213 = container "\u04213 Orders DB"'),
                ("wrong kind", c3, 'K9 = container "K9 Orders DB"'),
                ("duplicate", c3, 'C2 = container "C2 Orders DB"'),
                ("name", '"C2 Order API"', '"C4 Order API"'),
                ("bare name", '"C2 Order API"', '"C2 "'),
                ("description", '"R2 Submits orders to"', '"R9 Submits orders to"'),
                ("group", 'group "TB6 Admin handlers"', 'group "Admin handlers"'),
                ("group kind", 'group "TB6 Admin handlers"', 'group "C6 Admin handlers"'),
                ("key", 'dynamic C2 "SEQ1"', 'dynamic C2 "seq1"'),
                ("title", '"SEQ1 Checkout: an', '"SEQ2 Checkout: an'),
                ("no R =", "R2 = C1 -> K1", "C1 -> K1")):
            with self.subTest(label):
                self.assertRefused(mutate(old, new), line_of(old))

    def test_structure_errors_are_clear(self):
        end = SHOP.count(b"\n") + 1  # the line after the last
        c1 = line_of("C1 = container")
        c1_end = '"tm.owner" "Web team"\n                }\n            }\n'
        a1_end = "            }\n        }\n        A2"
        env1 = 'ENV1 = deploymentEnvironment "ENV1 Production" {\n'
        nest = "".join(f'{" " * (12 + i)}N{i + 10} = deploymentNode "N{i + 10} x" "y" "z" {{\n'
                       for i in range(50))
        nest += "".join(f'{" " * (12 + i)}}}\n' for i in reversed(range(50)))
        title = '"System context diagram for S1 Shop"'
        stray = '        K9 = component "K9 Stray" "Does nothing." "Python"\n'
        tb1 = '"Untrusted public network." "Public internet" "Trust boundary"'
        context_end = "            include *\n            autoLayout lr\n        }\n        container"
        for label, data, line in (
                ("missing } at the end", mutate("\n}\n", "\n"), 1),
                ("missing } in the middle", mutate(c1_end, c1_end[:-14]),
                 line_of("C2 = container") - 1),  # one line fewer above it
                ("extra } at the end", SHOP + b"}\n", end),
                ("extra } in the middle", mutate(a1_end, a1_end.replace("A2", "}\n        A2")),
                 line_of("A2 = person") + 1),
                ("{ mid-line", mutate('C1 = container "C1', 'C1 = container { "C1'), c1),
                ("lone {", mutate(FLAT, FLAT + "    {\n"), line_of(FLAT) + 1),
                ("} with more", mutate(a1_end, "            } }\n        A2"),
                 line_of("A1 = person") + 3),
                ("two statements", mutate(f"{title}\n            include *", f"{title} include *"),
                 line_of(title)),
                ("string over two lines", mutate('"C1 Web front end"', '"C1 Web\nfront end"'), c1),
                ("quote in a string", mutate('"C1 Web front end"', '"C1 Web "front" end"'), c1),
                ("backslash in a string", mutate('"C1 Web front end"', '"C1 Web front\\end"'), c1),
                ("text block", mutate('"C1 Web front end"', '"""C1 Web front end"""'), c1),
                ("50 nested blocks", mutate(env1, env1 + nest), line_of(env1) + 10),
                ("component in the model", mutate("        S2 =", stray + "        S2 ="),
                 line_of("S2 = softwareSystem")),
                ("no !identifiers flat", mutate(FLAT, ""), line_of("properties {") - 1),
                ("second !identifiers flat", mutate("    model {\n", "    model {\n" + FLAT),
                 line_of("    model {") + 1),
                ("empty file", b"", 1),
                ("missing argument", mutate(' "React SPA" {', " {"), c1),
                ("required block", mutate(tb1 + " {", tb1), line_of("TB1 = deploymentNode")),
                ("no include", mutate(context_end, context_end.split("\n", 1)[1]),
                 line_of("systemContext S1")),
                ("statement after the workspace", SHOP + b'workspace "x" "y" {\n}\n', end)):
            with self.subTest(label):
                self.assertRefused(data, line)

    def test_reference_errors(self):
        for old, new in (("R6 = A2 -> K3", "R6 = A2 -> K9"),
                         ("R5 = K2 -> S2", "R5 = K2 -> TB7"),
                         ("containerInstance C1", "containerInstance S1"),
                         ("softwareSystemInstance S2", "softwareSystemInstance C2"),
                         ("            R1\n", "            C1\n"),
                         ("            R4\n", "            R9\n"),
                         ('component C2 "', 'component C9 "'),
                         ('container S1 "', 'container C1 "'),
                         ("deployment * ENV1", "deployment * ENV2")):
            with self.subTest(new):
                self.assertRefused(mutate(old, new), line_of(old))

    def test_tags(self):
        db = '"PostgreSQL 16" "Data store"'
        c3 = line_of("C3 = container")
        self.assertRefused(mutate(db, '"PostgreSQL 16" "Database"'), c3, "Database")
        self.assertRefused(mutate(db, '"PostgreSQL 16" "Data store,"'), c3)
        m = c4.parse(mutate(db, '"PostgreSQL 16" "Data store, Async"'))
        self.assertEqual(m.items["C3"].tags, ("Data store", "Async"))
        self.assertEqual(c4.parse(SHOP).items["C3"].tags, ("Data store",))
        self.assertEqual(c4.parse(SHOP).items["C2"].tags, ())
        self.assertRefused(mutate('element "Data store"', 'element "Database"'),
                           line_of('element "Data store"'), "Database")

    def test_version(self):
        version = '"tm.version" "1.0"'
        self.assertRefused(mutate(f"        {version}\n", ""), 1, "tm.version")
        for bad in ("", "1.0 beta", "-1", "v" * 33):
            with self.subTest(bad):
                self.assertRefused(mutate(version, f'"tm.version" "{bad}"'), line_of(version),
                                   "tm.version")
        self.assertEqual(c4.parse(mutate(version, '"tm.version" "2.13"')).version, "2.13")

    def test_refuses_what_structurizr_reads_differently(self):
        owner = '"tm.owner" "Web team"'
        sells = '"Sells goods online."'
        for label, old, new, line in (
                ("substitution", sells, '"Sells ${HOME} online."', "S1 = softwareSystem"),
                ("{ as a string", sells, '"{"', "S1 = softwareSystem"),
                ("} as a string", owner, '"}" "Web team"', owner),
                ("non-ASCII outside a string", "S1 = softwareSystem", "S1 =\u00a0softwareSystem",
                 "S1 = softwareSystem"),
                ("bad view key", '"components-C2"', '"components/C2"', 'component C2 "')):
            with self.subTest(label):
                self.assertRefused(mutate(old, new), line_of(line))
        self.assertRefused(mutate(owner, f"{owner}\n{' ' * 20}\"tm.owner\" \"Ops team\""),
                           line_of(owner) + 1, "tm.owner")
        ws_props = "\n    properties {\n"
        self.assertRefused(mutate(ws_props, ws_props + "    }" + ws_props),
                           line_of("properties {") + 2)


if __name__ == "__main__":
    unittest.main()
