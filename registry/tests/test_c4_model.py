"""c4's content rules, zones, crossings, DFD roles, records and changes, on the worked example."""
import json
import unittest
from pathlib import Path

from tmreg import c4

FIXTURES = Path(__file__).parent / "fixtures"
SHOP = (FIXTURES / "c4/shop.dsl").read_bytes()
I12, I16, I20, I24 = " " * 12, " " * 16, " " * 20, " " * 24
_ENV1_END = f"{I16}softwareSystemInstance S2\n            }}\n        }}\n"
_SEQ1 = '        dynamic C2 "SEQ1" {'
# mutate() pairs that add ENV2 "Staging": TB8 holds every container; A1 and S2 are outside, and
# A2 sits in TB8. The result has no problems.
ENV2 = ((_ENV1_END, _ENV1_END + '        ENV2 = deploymentEnvironment "ENV2 Staging" {\n'
         '            TB8 = deploymentNode "TB8 Staging" "One box." "VM" "Trust boundary" {\n'
         f'{I16}properties {{\n{I20}"tm.enforced_by" "Firewall"\n{I16}}}\n'
         f'{I16}containerInstance C1\n{I16}containerInstance C2\n'
         f'{I16}containerInstance C3\n            }}\n        }}\n'),
        ('"tm.zone.ENV1" "TB1"', '"tm.zone.ENV1" "TB1"\n"tm.zone.ENV2" "outside"'),
        ('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "TB5"\n"tm.zone.ENV2" "TB8"'),
        ('"Takes card payments." "External"',
         '"Takes card payments." "External" {\n            properties {\n'
         '                "tm.zone.ENV2" "outside"\n            }\n        }'),
        (_SEQ1, '        deployment * ENV2 "deployment-ENV2" {\n'
         '            title "Deployment diagram for S1 Shop in ENV2 Staging"\n'
         '            include *\n        }\n' + _SEQ1))


def mutate(*pairs: tuple[str, str]) -> bytes:
    """SHOP with each (old, new) applied once, in order. Each old must occur exactly once."""
    text = SHOP.decode()
    for old, new in pairs:
        if text.count(old) != 1:
            raise AssertionError(f"{old!r} occurs {text.count(old)} times")
        text = text.replace(old, new)
    return text.encode()


def line_of(text: str, data: bytes = SHOP) -> int:
    """The line of data on which `text` starts."""
    return data[:data.index(text.encode())].count(b"\n") + 1


_ENV1 = "        ENV1 = deploymentEnvironment"
_STYLES = "        styles {"


def add_path(line: str) -> tuple[str, str]:
    """A mutate() pair adding a path, with its required properties, before ENV1."""
    return (_ENV1, f'        {line} {{\n{I12}properties {{\n{I16}"tm.data.sent" "none"\n'
                   f'{I16}"tm.data.returned" "none"\n{I16}"tm.auth" "None"\n{I12}}}\n        }}\n'
                   + _ENV1)


def add_seq(scope: str, *steps: str) -> tuple[str, str]:
    """A mutate() pair adding the dynamic view SEQ2 with these steps, scoped to `scope`."""
    body = "".join(f"{I12}{s}\n" for s in steps)
    return (_STYLES, f'        dynamic {scope} "SEQ2" {{\n{I12}title "SEQ2 Probe"\n{body}'
                     f'        }}\n{_STYLES}')


class ExampleTest(unittest.TestCase):
    def test_example_has_no_problems(self):
        self.assertEqual(c4.problems(c4.parse(SHOP)), [])

    def test_crossings_of_the_example(self):
        x = c4.crossings(c4.parse(SHOP))
        want = {"R1": [], "R2": ["TB1", "TB2", "TB3"], "R3": ["TB3", "TB4"], "R4": [],
                "R5": ["TB2", "TB3", "TB7"], "R6": ["TB2", "TB3", "TB5", "TB6"],
                "R7": ["TB3", "TB4", "TB6"]}
        self.assertEqual({r: e["ENV1"] for r, e in x.items()}, want)

    def test_zones_and_where(self):
        m = c4.parse(SHOP)
        self.assertEqual(c4.zones(m)["K3"]["ENV1"], ["TB2", "TB3", "TB6"])
        self.assertEqual(c4.zones(m)["A2"]["ENV1"], ["TB5"])
        self.assertEqual(c4.where(m, "K3"), ["S1", "C2", "K3"])

    def test_zones_of_each_kind(self):
        z = c4.zones(c4.parse(SHOP))
        self.assertEqual(sorted(z), ["A1", "A2", "C1", "C2", "C3", "K1", "K2", "K3", "S1", "S2"])
        self.assertEqual(z["C1"], {"ENV1": ["TB1"]})  # N1 is not a boundary
        self.assertEqual(z["C3"], {"ENV1": ["TB2", "TB4"]})
        self.assertEqual(z["K1"], {"ENV1": ["TB2", "TB3"]})
        self.assertEqual(z["S2"], {"ENV1": ["TB7"]})  # from its instance
        self.assertEqual(z["A1"], {"ENV1": ["TB1"]})
        self.assertEqual(z["S1"], {"ENV1": []})

    def test_where(self):
        m = c4.parse(SHOP)
        self.assertEqual(c4.where(m, "A1"), ["A1"])
        self.assertEqual(c4.where(m, "TB6"), ["S1", "C2", "TB6"])
        self.assertEqual(c4.where(m, "TB3"), ["ENV1", "TB2", "TB3"])
        self.assertEqual(c4.where(m, "I1"), ["ENV1", "TB5", "I1"])
        self.assertEqual(c4.where(m, "R1"), ["R1"])
        with self.assertRaises(KeyError):
            c4.where(m, "C9")

    def test_roles(self):
        m = c4.parse(SHOP)
        for iid, want in (("A1", "External entity"), ("S2", "External entity"), ("S1", None),
                          ("C3", "Data store"), ("C2", "Process"), ("K1", "Process"),
                          ("R1", "Data flow"), ("TB6", "Trust boundary"),
                          ("TB3", "Trust boundary"), ("N1", None), ("I1", None), ("ENV1", None),
                          ("SEQ1", None)):
            with self.subTest(iid):
                self.assertEqual(c4.role(m, iid), want)
        with self.assertRaises(KeyError):
            c4.role(m, "C9")


class ZonesTest(unittest.TestCase):
    def test_several_instances_cross_the_union(self):
        m = c4.parse(mutate((f"{I20}containerInstance C3\n",
                             f"{I20}containerInstance C3\n{I20}containerInstance C2\n")))
        self.assertEqual(c4.problems(m), [])
        z, x = c4.zones(m), c4.crossings(m)
        self.assertEqual(z["C2"]["ENV1"], ["TB2", "TB3", "TB4"])
        self.assertEqual(z["K3"]["ENV1"], ["TB2", "TB3", "TB4", "TB6"])
        self.assertEqual(x["R2"]["ENV1"], ["TB1", "TB2", "TB3", "TB4"])
        self.assertEqual(x["R3"]["ENV1"], ["TB3", "TB4"])  # K1 in TB3 or TB4, C3 in TB4
        self.assertEqual(x["R4"]["ENV1"], [])  # both ends in C2: compared within one instance
        self.assertEqual(x["R6"]["ENV1"], ["TB2", "TB3", "TB4", "TB5", "TB6"])

    def test_a_path_inside_one_container_crosses_its_group(self):
        env1 = "        ENV1 = deploymentEnvironment"
        r8 = ('        R8 = K1 -> K3 "R8 Hands refunds to" "In-process call" {\n'
              f'            properties {{\n{I16}"tm.data.sent" "none"\n'
              f'{I16}"tm.data.returned" "none"\n{I16}"tm.auth" "None: same process"\n'
              '            }\n        }\n')
        m = c4.parse(mutate((env1, r8 + env1)))
        self.assertEqual(c4.problems(m), [])
        self.assertEqual(c4.crossings(m)["R8"]["ENV1"], ["TB6"])

    def test_an_external_system_without_an_instance_uses_its_zone(self):
        m = c4.parse(mutate((f"{I16}softwareSystemInstance S2\n",
                             f'{I16}I2 = infrastructureNode "I2 Edge" "Vendor edge." "CDN"\n'),
                            ('"Takes card payments." "External"',
                             '"Takes card payments." "External" {\n            properties {\n'
                             '                "tm.zone.ENV1" "outside"\n            }\n        }')))
        self.assertEqual(c4.problems(m), [])
        self.assertEqual(c4.zones(m)["S2"]["ENV1"], [])
        self.assertEqual(c4.crossings(m)["R5"]["ENV1"], ["TB2", "TB3"])

    def test_a_person_in_a_nested_zone(self):
        m = c4.parse(mutate(('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "TB3"')))
        self.assertEqual(c4.problems(m), [])
        self.assertEqual(c4.zones(m)["A2"]["ENV1"], ["TB2", "TB3"])
        self.assertEqual(c4.crossings(m)["R6"]["ENV1"], ["TB6"])

    def test_each_environment_is_separate(self):
        data = mutate(*ENV2)
        m = c4.parse(data)
        self.assertEqual(c4.problems(m), [])
        x = c4.crossings(m)
        self.assertEqual(x["R1"], {"ENV1": [], "ENV2": ["TB8"]})
        self.assertEqual(x["R2"], {"ENV1": ["TB1", "TB2", "TB3"], "ENV2": []})
        self.assertEqual(x["R6"], {"ENV1": ["TB2", "TB3", "TB5", "TB6"], "ENV2": ["TB6"]})
        self.assertEqual(x["R5"], {"ENV1": ["TB2", "TB3", "TB7"], "ENV2": ["TB8"]})
        self.assertEqual(c4.zones(m)["A1"], {"ENV1": ["TB1"], "ENV2": []})
        self.assertEqual(c4.zones(m)["S2"], {"ENV1": ["TB7"], "ENV2": []})
        # A missing environment is a problem on the item that lacks it.
        lacking = c4.problems(c4.parse(data.replace(b'"tm.zone.ENV2" "TB8"', b'"tm.x" "y"')))
        self.assertEqual(len(lacking), 2, lacking)
        self.assertTrue(all("A2" in p for p in lacking), lacking)


class ProblemsTest(unittest.TestCase):
    def assertOneProblem(self, data: bytes, line: int, *words: str):
        found = c4.problems(c4.parse(data))
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith(f"line {line}: "), found[0])
        for word in words:
            self.assertIn(word, found[0])

    def test_each_rule(self):
        c1 = "C1 = container"
        enforced_tb3 = f'{I20}"tm.enforced_by" "Security group: only the load balancer on 443"\n'
        for rule, pairs, at, words in (
            # Required text
            ("description", [("\"Single-page app that runs in the customer's browser.\"", '""')],
             c1, ["C1", "description"]),
            ("technology on a node", [('"WireGuard"', '""')], "I1 = infra", ["I1", "technology"]),
            ("technology on a path", [('using" "HTTPS" {\n            properties {\n'
                                       '                "tm.data.sent" "PII"\n',
                                       'using" " " {\n            properties {\n'
                                       '                "tm.data.sent" "PII"\n')],
             "R1 = ", ["R1", "technology"]),
            # Properties
            ("unknown property", [('"tm.owner" "Web team"',
                                   '"tm.owner" "Web team"\n"tm.colour" "red"')],
             c1, ["C1", "tm.colour"]),
            ("unknown workspace property", [('"tm.version" "1.0"',
                                             '"tm.version" "1.0"\n"tm.owner" "Ops"')],
             'workspace "Shop"', ["workspace", "tm.owner"]),
            ("owner", [(f'{I20}"tm.owner" "Web team"\n', "")], c1, ["C1", "tm.owner"]),
            ("empty value", [('"tm.owner" "Web team"', '"tm.owner" " "')], c1, ["C1", "tm.owner"]),
            ("enforced_by", [(enforced_tb3, "")], "TB3 = ", ["TB3", "tm.enforced_by"]),
            ("enforced_by.TB6", [(f'{I20}"tm.enforced_by.TB6" "Role check middleware; admin '
                                  'session from SSO"\n', "")], "C2 = ", ["C2", "tm.enforced_by.TB6"]),
            ("enforced_by.<TB> names its group", [('"tm.owner" "Web team"',
                                                   '"tm.owner" "Web team"\n'
                                                   '"tm.enforced_by.TB6" "x"')],
             c1, ["C1", "tm.enforced_by.TB6"]),
            ("was", [('"tm.owner" "Web team"', '"tm.owner" "Web team"\n"tm.was" "P1, X2"')],
             c1, ["C1", "X2"]),
            ("placement", [('"tm.zone.ENV1" "TB1"', '"tm.zone.ENV1" "TB1"\n"tm.owner" "Me"')],
             "A1 = ", ["A1", "tm.owner"]),
            ("enforced_by off a TB node", [('"tm.owner" "Web team"',
                                            '"tm.owner" "Web team"\n"tm.enforced_by" "x"')],
             c1, ["C1", "tm.enforced_by"]),
            ("zone off a person or External system", [('"tm.owner" "Web team"',
                                                       '"tm.owner" "Web team"\n'
                                                       '"tm.zone.ENV1" "outside"')],
             c1, ["C1", "tm.zone.ENV1"]),
            ("bare inspection name", [('"tm.version" "1.0"',
                                       '"tm.version" "1.0"\n"structurizr.inspection." "ignore"')],
             'workspace "Shop"', ["workspace", "structurizr.inspection."]),
            ("data class name", [('"tm.version" "1.0"',
                                  '"tm.version" "1.0"\n"tm.dataclass.A, B" "x"')],
             'workspace "Shop"', ["workspace", "A, B"]),
            ("data class none", [('"tm.version" "1.0"',
                                  '"tm.version" "1.0"\n"tm.dataclass.none" "x"')],
             'workspace "Shop"', ["workspace", "none"]),
            # Tags
            ("External on C1", [('"React SPA" {', '"React SPA" "External" {')], c1,
             ["C1", "External"]),
            ("Data store on S1", [('"Sells goods online." {', '"Sells goods online." "Data store" {')],
             "S1 = ", ["S1", "Data store"]),
            ("Data store needs stored", [(f'{I20}"tm.data.stored" "PII, Order history, Payment '
                                          'token"\n', "")], "C3 = ", ["C3", "tm.data.stored"]),
            ("stored needs Data store", [('"React SPA" {\n                properties {\n',
                                          '"React SPA" {\n                properties {\n'
                                          '"tm.data.stored" "PII"\n')], c1,
             ["C1", "tm.data.stored"]),
            ("Async on C1", [('"React SPA" {', '"React SPA" "Async" {')], c1, ["C1", "Async"]),
            ("Trust boundary on N1", [('"Web browser" {', '"Web browser" "Trust boundary" {')],
             "N1 = ", ["N1", "Trust boundary"]),
            ("TB node untagged", [('"Vendor SaaS" "Trust boundary" {', '"Vendor SaaS" {')],
             "TB7 = ", ["TB7", "Trust boundary"]),
            # Header
            ("configuration", [("    configuration {\n        scope softwaresystem\n    }\n", "")],
             'workspace "Shop"', ["configuration", "scope softwaresystem"]),
            # Scope
            ("two systems in scope", [('"Takes card payments." "External"',
                                       '"Takes card payments."')], "S2 = ", ["S2", "External"]),
            ("the scope is the one with containers", [  # S2 comes first, but S1 has containers
                ('        S2 = softwareSystem "S2 Payment provider" "Takes card payments." '
                 '"External"\n', ""),
                ("        S1 = softwareSystem", '        S2 = softwareSystem "S2 Payment provider" '
                                                '"Takes card payments."\n'
                                                "        S1 = softwareSystem")],
             "S2 = ", ["S2", "S1 is the system in scope"]),
            ("external with containers", [('"Takes card payments." "External"\n',
                                           '"Takes card payments." "External" {\n'
                                           'C9 = container "C9 Gateway" "Takes calls." "Java" {\n'
                                           'properties {\n"tm.owner" "Vendor"\n}\n}\n}\n')],
             "S2 = ", ["S2", "container"]),
            # Zones
            ("zone removed", [(f'{I16}"tm.zone.ENV1" "TB1"\n', "")], "A1 = ", ["A1", "tm.zone.ENV1"]),
            ("zone is a group", [('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "TB6"')], "A2 = ",
             ["A2", "TB6"]),
            ("zone is not a TB", [('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "N1"')], "A2 = ",
             ["A2", "N1"]),
            ("zone names no ENV", [('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "TB5"\n'
                                    '"tm.zone.ENV2" "outside"')], "A2 = ", ["A2", "ENV2"]),
            ("zone from another ENV", [*ENV2, ('"tm.zone.ENV1" "TB5"', '"tm.zone.ENV1" "TB8"')],
             "A2 = ", ["A2", "TB8", "ENV1"]),
            ("zone and an instance", [('"Takes card payments." "External"',
                                       '"Takes card payments." "External" {\nproperties {\n'
                                       '"tm.zone.ENV1" "outside"\n}\n}')], "S2 = ",
             ["S2", "tm.zone.ENV1"]),
            # Paths
            ("auth", [('                "tm.auth" "None until sign-in, then a session cookie"\n',
                       "")], "R1 = ", ["R1", "tm.auth"]),
            ("undeclared class", [('"tm.data.sent" "PII"\n', '"tm.data.sent" "Secrets"\n')],
             "R1 = ", ["R1", "Secrets"]),
            ("empty class", [('"tm.data.sent" "PII"\n', '"tm.data.sent" "PII, "\n')],
             "R1 = ", ["R1", "tm.data.sent"]),
            ("same ends", [("R4 = K1 -> K2", "R4 = K1 -> K1")], "R4 = ", ["R4", "K1"]),
            ("end is the system in scope", [("R1 = A1 -> C1", "R1 = A1 -> S1")], "R1 = ",
             ["R1", "S1"]),
            ("path tagged Data store", [('"R4 Asks for a charge from" "In-process call" {',
                                         '"R4 Asks for a charge from" "In-process call" '
                                         '"Data store" {')], "R4 = ", ["R4", "Data store"]),
            ("person on no path", [("        S1 = softwareSystem",
                                    '        A3 = person "A3 Visitor" "Looks around." {\n'
                                    '            properties {\n'
                                    '                "tm.zone.ENV1" "outside"\n'
                                    '            }\n        }\n        S1 = softwareSystem')],
             "A3 = ", ["A3", "no path"]),
            ("system on no path", [("        R1 = A1 -> C1",
                                    '        S3 = softwareSystem "S3 Courier" "Ships parcels." '
                                    '"External" {\n            properties {\n'
                                    '                "tm.zone.ENV1" "outside"\n'
                                    '            }\n        }\n        R1 = A1 -> C1')],
             "S3 = ", ["S3", "no path"]),
            ("path props on a node", [('"tm.zone.ENV1" "TB1"', '"tm.zone.ENV1" "TB1"\n'
                                       '"tm.auth" "x"')], "A1 = ", ["A1", "tm.auth"]),
            # Zoom
            ("zoom format", [('"2, 5: hands payment tokens to the provider; serves customers and '
                              'admins in one process"', '"9: x"')], "C2 = ", ["C2", "9: x"]),
            ("zoom missing", [(f'{I20}"tm.zoom" "2, 5: hands payment tokens to the provider; '
                               'serves customers and admins in one process"\n', "")],
             "C2 = ", ["C2", "tm.zoom"]),
            ("zoom without components", [('"tm.owner" "Web team"',
                                          '"tm.owner" "Web team"\n"tm.zoom" "1: x"')],
             c1, ["C1", "tm.zoom"]),
            # Deployment
            ("C1 instance removed", [(f"{I20}containerInstance C1\n",  # N1 must still hold one
                                      f'{I20}I2 = infrastructureNode "I2 Extension" "Runs in the '
                                      'browser." "WebExtension"\n')], c1, ["C1", "ENV1"]),
            ("empty group", [(f'{I16}group "TB6 Admin handlers" {{\n',
                              f'{I16}group "TB8 Empty" {{\n{I16}}}\n'
                              f'{I16}group "TB6 Admin handlers" {{\n'),
                             (f'{I20}"tm.enforced_by.TB6"',
                              f'{I20}"tm.enforced_by.TB8" "Nothing yet"\n'
                              f'{I20}"tm.enforced_by.TB6"')],
             'group "TB8', ["TB8", "holds nothing"]),
            ("I1 removed", [(f'{I16}I1 = infrastructureNode "I1 VPN gateway" "Lets staff reach '
                             'the admin handlers." "WireGuard"\n', "")], "TB5 = ", ["TB5"]),
            # Views
            ("containers title removed", [('            title "Container diagram for S1 Shop"\n',
                                           "")], '"containers"', ["containers", "title"]),
            ("title prefix", [('"Container diagram for S1 Shop"', '"Containers of S1 Shop"')],
             '"containers"', ["containers", "Container diagram for"]),
            ("components-C2 removed", [('        component C2 "components-C2" {\n'
                                        '            title "Component diagram for C2 Order API"\n'
                                        '            include *\n            autoLayout lr\n'
                                        '        }\n', "")], "C2 = ", ["C2", "components-C2"]),
            ("context view's kind", [('systemContext S1 "context"', 'container S1 "context"')],
             'container S1 "context"', ["context", "systemContext"]),
            ("deployment view scoped to S1", [('deployment * ENV1', 'deployment S1 ENV1')],
             'deployment S1 ENV1', ["deployment-ENV1", "deployment * ENV1"]),
            ("deployment-ENV1 removed", [('"deployment-ENV1"', '"deploy-1"')], "ENV1 = ",
             ["ENV1", "deployment-ENV1"]),
            ("extra view without a title", [('        dynamic C2 "SEQ1" {',
                                             '        container S1 "more" {\n'
                                             '            include *\n        }\n'
                                             '        dynamic C2 "SEQ1" {')],
             '"more"', ["more", "title"]),
            # Shapes the pinned Structurizr refuses (probed 2026-11-09)
            ("path to its own container (R38)", [add_path('R8 = K1 -> C2 "R8 Calls back" "HTTPS"')],
             "R8 = ", ["R8", "K1", "C2", "inside"]),
            ("path from a container to its own component (R38)",
             [add_path('R8 = C2 -> K1 "R8 Calls into" "HTTPS"')], "R8 = ", ["R8", "K1", "C2", "inside"]),
            ("system-scoped sequence with a component step", [add_seq("S1", "R1", "R2", "R4")],
             'dynamic S1 "SEQ2"', ["SEQ2", "S1", "R2", "K1", "dynamic C2"]),
            ("external-system-scoped sequence with a component step", [add_seq("S2", "R4")],
             'dynamic S2 "SEQ2"', ["SEQ2", "S2", "R4", "K1", "dynamic C2"]),
            ("step ends at the sequence's container scope",
             [add_path('R8 = A1 -> C2 "R8 Calls" "HTTPS"'), add_seq("C2", "R8")],
             'dynamic C2 "SEQ2"', ["SEQ2", "R8", "C2", "own scope"]),
            ("step ends at the sequence's system scope",
             [add_path('R8 = A1 -> S2 "R8 Pays" "HTTPS"'), add_seq("S2", "R8")],
             'dynamic S2 "SEQ2"', ["SEQ2", "R8", "S2", "own scope"]),
            ("sequence shows a container and its component",
             [add_path('R8 = A1 -> C2 "R8 Calls" "HTTPS"'), add_seq("C3", "R8", "R2")],
             'dynamic C3 "SEQ2"', ["SEQ2", "C2", "K1", "R8", "R2"]),
            ("empty deployment node (R43)",
             [(f"{I16}TB4 = deploymentNode", f'{I16}N2 = deploymentNode "N2 Spare host" "Nothing '
               f'runs here." "Linux" {{\n{I16}}}\n{I16}TB4 = deploymentNode')],
             "N2 = ", ["N2", "holds nothing"]),
            # Styles (R41): only lines of the standard block
            ("style shape Bogus", [("shape Cylinder", "shape Bogus")], "shape Bogus",
             ["Data store", "shape Bogus", "standard"]),
            ("style strokeWidth abc", [('element "Group" {\n                border Dashed\n'
                                        '                stroke #c0392b\n                strokeWidth 5',
                                        'element "Group" {\n                border Dashed\n'
                                        '                stroke #c0392b\n                strokeWidth abc')],
             "strokeWidth abc", ["Group", "strokeWidth abc"]),
            ("style color notacolor", [("color #ffffff", "color notacolor")], "color notacolor",
             ["External", "color notacolor"]),
            ("relationship style Wavy", [("style Dashed", "style Wavy")], "style Wavy",
             ["Async", "style Wavy"]),
            ("standard value under another tag", [("shape Person", "shape Cylinder")],
             "shape Cylinder", ["Person", "shape Cylinder"]),
            ("element value under a relationship selector",
             [('            relationship "Async" {',
               '            relationship "External" {\n                color #ffffff\n'
               '            }\n            relationship "Async" {')],
             "                color #ffffff\n            }\n            relationship",
             ["relationship", "External", "color #ffffff"]),
        ):
            with self.subTest(rule):
                data = mutate(*pairs)
                self.assertOneProblem(data, line_of(at, data), *words)

    def test_standard_styles_in_any_order_or_a_subset(self):
        text = SHOP.decode()
        block = text[text.index(_STYLES):text.index("        }\n    }\n}")]
        reordered = (f'{_STYLES}\n            relationship "Async" {{\n{I16}style Dashed\n'
                     f'{I12}}}\n            element "External" {{\n{I16}color #ffffff\n'
                     f'{I16}background #8c8c8c\n{I12}}}\n            element "Group" {{\n'
                     f'{I16}strokeWidth 5\n{I16}border Dashed\n{I16}stroke #c0392b\n{I12}}}\n'
                     f'            element "Person" {{\n{I16}shape Person\n{I12}}}\n')
        for label, new in (("reordered", reordered), ("empty", f"{_STYLES}\n"),
                           ("only Data store", f'{_STYLES}\n            element "Data store" '
                                               f'{{\n{I16}shape Cylinder\n{I12}}}\n')):
            with self.subTest(label):
                self.assertEqual(c4.problems(c4.parse(mutate((block, new)))), [])
        self.assertEqual(sorted(c4.STANDARD_STYLES), sorted(set(c4.STANDARD_STYLES)))
        self.assertEqual(len(c4.STANDARD_STYLES), 11)
        self.assertEqual(c4.parse(SHOP).styles[0][:4], ("element", "Person", "shape", "Person"))

    def test_sequences_structurizr_accepts_have_no_problems(self):
        for label, pairs in (
                ("system scope, container steps", [add_seq("S1", "R1")]),
                ("container scope, steps inside another container", [add_seq("C1", "R4")]),
                ("container scope, steps on its components", [add_seq("C2", "R6", "R7")]),
                ("path to an opened container", [add_path('R8 = A1 -> C2 "R8 Calls" "HTTPS"')])):
            with self.subTest(label):
                self.assertEqual(c4.problems(c4.parse(mutate(*pairs))), [])

    def test_a_bare_workspace(self):
        data = (b'workspace "X" "Y" {\n    !identifiers flat\n    properties {\n'
                b'        "tm.version" "1.0"\n    }\n    model {\n'
                b'        A1 = person "A1 P" "Uses it."\n    }\n    views {\n    }\n}\n')
        m = c4.parse(data)
        self.assertEqual(c4.problems(m), [
            "line 1: the workspace needs configuration { scope softwaresystem }",
            "line 1: no software system is in scope: the one being modeled has no External tag",
            "line 1: the model has no deployment environment: add ENV1 with its trust "
            "boundaries, so that paths have known crossings",
            'line 1: the workspace needs the view systemContext <S> "context"',
            'line 1: the workspace needs the view container <S> "containers"',
            "line 7: A1 is connected to no path, so no diagram shows it"])
        self.assertEqual((c4.zones(m), c4.crossings(m)), ({"A1": {}}, {}))
        self.assertEqual(c4.to_record(m)["items"]["A1"]["zones"], {})

    def test_all_problems_at_once_in_line_order(self):
        data = mutate((f'{I20}"tm.owner" "Web team"\n', ""),
                      ('"tm.data.sent" "PII"\n', '"tm.data.sent" "Secrets"\n'),
                      ("    configuration {\n        scope softwaresystem\n    }\n", ""))
        found = c4.problems(c4.parse(data))
        self.assertEqual([p.split(":", 1)[0] for p in found],
                         [f"line {line_of(t, data)}" for t in
                          ('workspace "Shop"', "C1 = container", "R1 = ")])


class RecordTest(unittest.TestCase):
    def test_record_is_canonical_json(self):
        r = c4.to_record(c4.parse(SHOP))
        self.assertEqual(json.loads(json.dumps(r, sort_keys=True)), r)
        self.assertEqual(r["rels"]["R6"]["crossings"]["ENV1"], ["TB2", "TB3", "TB5", "TB6"])

    def test_record_contents(self):
        r = c4.to_record(c4.parse(SHOP))
        self.assertEqual(sorted(r), ["dataclasses", "description", "items", "name", "rels",
                                     "version", "views"])
        self.assertEqual((r["version"], r["name"]), ("1.0", "Shop"))
        self.assertEqual(sorted(r["dataclasses"]), ["Order history", "PII", "Payment token"])
        self.assertEqual(r["items"]["K3"], {
            "kind": "component", "name": "K3 Admin handler",
            "description": "Lists orders and issues refunds.", "technology": "FastAPI router",
            "tags": [], "properties": {"tm.owner": "Orders team"}, "parent": "C2",
            "group": "TB6", "role": "Process", "where": ["S1", "C2", "K3"],
            "zones": {"ENV1": ["TB2", "TB3", "TB6"]}})
        self.assertEqual(r["items"]["TB3"]["zones"], {})
        # A group carries what enforces it, from its container, as a TB node does (R12).
        self.assertEqual(r["items"]["TB6"]["properties"],
                         {"tm.enforced_by": "Role check middleware; admin session from SSO"})
        self.assertEqual(r["items"]["TB3"]["properties"],
                         {"tm.enforced_by": "Security group: only the load balancer on 443"})
        self.assertEqual(r["items"]["C3"]["tags"], ["Data store"])
        self.assertEqual(sorted(r["items"]), sorted(c4.parse(SHOP).items))
        self.assertEqual(r["rels"]["R5"]["role"], "Data flow")
        self.assertEqual((r["rels"]["R5"]["source"], r["rels"]["R5"]["destination"]), ("K2", "S2"))
        self.assertEqual(r["views"]["SEQ1"], {"kind": "dynamic", "scope": "C2", "env": None,
                                              "title": "SEQ1 Checkout: an order is placed and paid",
                                              "steps": ["R1", "R2", "R4", "R5", "R3"]})
        self.assertEqual(r["views"]["deployment-ENV1"]["env"], "ENV1")

    def test_changes(self):
        old = c4.to_record(c4.parse(SHOP))
        moved = c4.to_record(c4.parse(mutate(          # move C3's instance from TB4 into TB3
            (f"{I20}containerInstance C3\n", ""),
            (f"{I20}containerInstance C2\n", f"{I20}containerInstance C2\n{I20}containerInstance C3\n"))))
        ch = c4.changes(old, moved)
        self.assertIn("crossings", ch["changed"]["R3"]); self.assertIn("zones", ch["changed"]["C3"])
        only_was = c4.to_record(c4.parse(mutate(
            (f'{I20}"tm.owner" "Web team"\n', f'{I20}"tm.owner" "Web team"\n{I20}"tm.was" "P9"\n'))))
        self.assertEqual(c4.changes(old, only_was)["changed"], {})
        self.assertEqual(c4.changes(None, old)["added"],
                         sorted(set(old["items"]) | set(old["rels"]) | {"SEQ1"}))

    def test_changes_in_detail(self):
        old = c4.to_record(c4.parse(SHOP))
        self.assertEqual(c4.changes(old, old), {"added": [], "removed": [], "changed": {}})
        self.assertEqual(c4.changes(None, old)["removed"], [])
        new = c4.to_record(c4.parse(mutate(
            ('"Sells goods online."', '"Sells goods."'),
            ('"tm.owner" "Web team"', '"tm.owner" "Web guild"'),
            ("R4 = K1 -> K2", "R4 = K2 -> K1"),
            ('"SEQ1 Checkout: an order is placed and paid"', '"SEQ1 Checkout"'))))
        self.assertEqual(c4.changes(old, new)["changed"], {
            "C1": ["properties"], "R4": ["source", "destination"], "S1": ["description"],
            "SEQ1": ["title"]})
        smaller = c4.to_record(c4.parse(mutate(
            ("        R7 = K3 -> C3", "        R8 = K3 -> C3"),
            ('"R7 Reads and refunds orders in"', '"R8 Reads and refunds orders in"'))))
        ch = c4.changes(old, smaller)
        self.assertEqual((ch["added"], ch["removed"], ch["changed"]), (["R8"], ["R7"], {}))

    def test_changes_to_a_group_and_a_sequence(self):
        old = c4.to_record(c4.parse(SHOP))
        enforced = c4.to_record(c4.parse(mutate(
            ('"Role check middleware; admin session from SSO"', '"Role check middleware only"'))))
        self.assertEqual(c4.changes(old, enforced)["changed"],
                         {"C2": ["properties"], "TB6": ["properties"]})
        rescoped = c4.to_record(c4.parse(mutate(('dynamic C2 "SEQ1"', 'dynamic S1 "SEQ1"'))))
        self.assertEqual(c4.changes(old, rescoped)["changed"], {"SEQ1": ["scope"]})

    def test_was_map(self):
        rec = c4.to_record(c4.parse(mutate(
            (f'{I20}"tm.zoom"', f'{I20}"tm.was" "P2"\n{I20}"tm.zoom"'),
            ('"FastAPI router" {\n' + f"{I20}properties {{\n",
             '"FastAPI router" {\n' + f'{I20}properties {{\n{I24}"tm.was" "P2, F9"\n'),
            ('"tm.data.sent" "PII"\n', '"tm.data.sent" "PII"\n"tm.was" "F1"\n'))))
        self.assertEqual(c4.was_map(rec), {"P2": ["C2", "K1"], "F9": ["K1"], "F1": ["R1"]})
        self.assertEqual(c4.was_map(c4.to_record(c4.parse(SHOP))), {})

    def test_next_free(self):
        m = c4.parse(SHOP)
        self.assertEqual(c4.next_free(m, {"C": {7}})["C"], "C8")
        free = c4.next_free(m, {"R": {2}})
        self.assertEqual(free, {"A": "A3", "S": "S3", "C": "C4", "K": "K4", "R": "R8", "TB": "TB8",
                                "N": "N2", "I": "I2", "ENV": "ENV2", "SEQ": "SEQ2"})


class ParseScopeTest(unittest.TestCase):
    def test_scope_is_parsed(self):
        self.assertEqual(c4.parse(SHOP).scope, "softwaresystem")
        self.assertIsNone(c4.parse(mutate(("        scope softwaresystem\n", ""))).scope)


if __name__ == "__main__":
    unittest.main()
