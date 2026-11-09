"""Routes between model items and open-risk counts (spec section 7.5)."""
from helpers import (FIXTURES, TmpTestCase, ai_fields, approve_model, human_terminal,
                     make_registry, session, start, write_model)
from tmreg.core import RegistryError

SHOP = (FIXTURES / "c4" / "shop.dsl").read_bytes()
NOTE = "Checked against the model checklist."


def make_registry_shop(tmp):
    reg = make_registry(tmp, approve=False)
    write_model(reg, "demo", SHOP)
    approve_model(reg, "demo")
    return reg


def draft(reg, elements, **over):
    return reg.add_risk("demo", ai_fields(elements=elements, **over), run_id=start(reg))["id"]


def route_ids(chain):
    return [h["path"] for h in chain["hops"]]


class RoutesTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry_shop(self.tmp)

    def test_route_customer_to_database(self):
        chains = self.reg.c4_routes("demo", "A1", "C3")
        self.assertEqual([route_ids(c) for c in chains], [["R1", "R2", "R3"]])
        self.assertEqual(list(chains[0]["elements"]), ["A1", "C1", "K1", "C3"])
        self.assertFalse(any(h["against_arrow"] for h in chains[0]["hops"]))
        self.assertEqual([(h["from"], h["to"]) for h in chains[0]["hops"]],
                         [("A1", "C1"), ("C1", "K1"), ("K1", "C3")])

    def test_route_marks_hops_against_the_arrow(self):
        chains = self.reg.c4_routes("demo", "A1", "A2")
        self.assertEqual([route_ids(c) for c in chains], [["R1", "R2", "R3", "R7", "R6"]])
        self.assertEqual([h["path"] for h in chains[0]["hops"] if h["against_arrow"]],
                         ["R7", "R6"])

    def test_route_respects_max_hops(self):
        self.assertEqual(self.reg.c4_routes("demo", "A1", "A2", max_hops=4), [])

    def test_route_into_a_container_reaches_its_parts(self):
        chains = self.reg.c4_routes("demo", "A1", "C2")  # R22: K1 is inside C2
        self.assertEqual([route_ids(c) for c in chains], [["R1", "R2"]])
        self.assertEqual(chains[0]["hops"][-1]["to"], "K1")

    def test_route_caps_chains_after_sorting(self):
        everything = self.reg.c4_routes("demo", "C2", "S2")
        self.assertGreater(len(everything), 1)
        capped = self.reg.c4_routes("demo", "C2", "S2", max_chains=1)
        self.assertEqual(capped, everything[:1])
        self.assertEqual(sorted(len(c["hops"]) for c in everything),
                         [len(c["hops"]) for c in everything])

    def test_chains_sort_path_ids_by_number(self):
        from tmreg.core import _natural
        self.assertLess(_natural("R2"), _natural("R10"))
        self.assertLess(_natural("R9"), _natural("R10"))

    def test_route_lists_risks_per_hop(self):
        on_r2 = draft(self.reg, ["R2"])
        on_k1 = draft(self.reg, ["K1"], title="K1 trusts input")
        self.reg.approve(session(), "demo", on_r2, NOTE)
        chain = self.reg.c4_routes("demo", "A1", "C3")[0]
        r2 = chain["hops"][1]["risks"]
        self.assertEqual(r2, {"open": [on_r2], "pending": []})
        self.assertEqual(chain["hops"][0]["risks"], {"open": [], "pending": []})
        self.assertEqual(chain["elements"]["K1"], {"open": [], "pending": [on_k1]})
        self.assertEqual(chain["elements"]["A1"], {"open": [], "pending": []})
        self.assertIn("crossings", chain["hops"][0])

    def test_route_errors(self):
        with self.assertRaisesRegex(RegistryError, "Z9"):
            self.reg.c4_routes("demo", "Z9", "C3")
        with self.assertRaisesRegex(RegistryError, "R1"):  # a path is not an endpoint
            self.reg.c4_routes("demo", "A1", "R1")
        with self.assertRaisesRegex(RegistryError, "K9"):
            self.reg.c4_routes("demo", "K9", "C3")

    def test_route_without_an_approval(self):
        (self.tmp / "x").mkdir()
        reg = make_registry(self.tmp / "x", approve=False)
        with self.assertRaises(RegistryError) as cm:
            reg.c4_routes("demo", "A1", "C3")
        self.assertEqual(str(cm.exception),
                         "no approved C4 model for demo; approve systems/demo/workspace.dsl first")


class CountsTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry_shop(self.tmp)

    def test_open_risk_counts(self):
        reg, h = self.reg, session()
        a = draft(reg, ["R2", "K1"])
        reg.approve(h, "demo", a, NOTE)                               # approved open
        b = draft(reg, ["R2"], title="Second on R2")                   # pending draft
        c = draft(reg, ["K1"], title="Mitigated one")
        reg.approve(h, "demo", c, NOTE)
        with human_terminal():  # an owner edit keeps the approval
            reg.edit_risk("demo", c, {"status": "mitigated"}, run_id=None, note="done")
        e = draft(reg, ["R2"], title="Planned one")
        reg.approve(h, "demo", e, NOTE)
        with human_terminal():
            reg.edit_risk("demo", e, {"status": "planned"}, run_id=None)
        d = draft(reg, ["C3"], title="Rejected one")
        reg.reject(h, "demo", d, NOTE)
        self.assertEqual(reg.open_risk_counts("demo"), {
            "R2": {"open": 2, "pending": 1}, "K1": {"open": 1, "pending": 0}})
        self.assertNotIn("C3", reg.open_risk_counts("demo"))
        self.assertEqual(reg.get_risk('demo', b)['review_state'], 'pending')
