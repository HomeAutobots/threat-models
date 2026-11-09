"""Routes between model items and open-risk counts (spec section 7.5)."""
import time
from unittest import mock

from helpers import (FIXTURES, TmpTestCase, ai_fields, approve_model, human_terminal,
                     make_registry, session, start, write_model)
from tmreg.core import ROUTE_TOO_BROAD_MSG, RegistryError

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
        everything = self.reg.c4_routes("demo", "C2", "C3")  # via K1 (R3) or K3 (R7)
        self.assertGreater(len(everything), 1)
        capped = self.reg.c4_routes("demo", "C2", "C3", max_chains=1)
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


def synthetic(reg, edges, nodes=None):
    """Make c4_routes read a generated record: edges are (path ID, source, destination)."""
    ids = nodes or sorted({e[i] for e in edges for i in (1, 2)})
    record = {"items": {i: {"kind": "container", "where": [i]} for i in ids},
              "rels": {r: {"source": a, "destination": b, "crossings": {}} for r, a, b in edges}}
    return mock.patch.object(reg, "_require_model", return_value={"model": record})


class RouteLimitsTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry_shop(self.tmp)

    def dense(self):
        n = 40
        edges = [("R1", "C1", "C2"), ("R2", f"C{n}", "C39")]
        for i in range(2, n):  # C2..C39: each linked to the next four, a dense middle
            for j in range(i + 1, min(i + 5, n)):
                edges.append((f"R{len(edges) + 1}", f"C{i}", f"C{j}"))
        return edges

    def test_a_dense_model_returns_quickly_or_says_too_broad(self):
        started = time.monotonic()
        with synthetic(self.reg, self.dense()):
            try:
                chains = self.reg.c4_routes("demo", "C1", "C40", max_hops=12)
            except RegistryError as e:
                self.assertEqual(str(e), ROUTE_TOO_BROAD_MSG)
            else:
                self.assertLessEqual(len(chains), 25)
        self.assertLess(time.monotonic() - started, 10)

    def test_the_search_stops_at_a_ceiling(self):
        with synthetic(self.reg, self.dense()), mock.patch("tmreg.core._ROUTE_EXPANSION_LIMIT", 50):
            with self.assertRaises(RegistryError) as cm:
                self.reg.c4_routes("demo", "C1", "C40", max_hops=12, max_chains=10**6)
        self.assertEqual(str(cm.exception), ROUTE_TOO_BROAD_MSG)

    def test_enough_chains_stop_the_search_at_that_depth(self):
        # one 1-hop chain, then a dense mass deeper: max_chains=1 never explores it
        edges = self.dense() + [("R999", "C1", "C40")]
        with synthetic(self.reg, edges), mock.patch("tmreg.core._ROUTE_EXPANSION_LIMIT", 50):
            self.assertEqual(len(self.reg.c4_routes("demo", "C1", "C40", max_chains=1)), 1)
            with self.assertRaises(RegistryError):
                self.reg.c4_routes("demo", "C1", "C40", max_hops=12, max_chains=5)

    def test_hop_and_chain_limits_must_be_positive(self):
        for kw in ({"max_hops": 0}, {"max_chains": 0}, {"max_hops": -1}):
            with self.assertRaises(RegistryError):
                self.reg.c4_routes("demo", "A1", "C3", **kw)

    def test_a_system_end_gives_no_suffix_chains(self):
        chains = self.reg.c4_routes("demo", "S1", "S2")
        self.assertEqual([route_ids(c) for c in chains], [["R5"]])  # not K1->K2->S2 etc.
        self.assertEqual([route_ids(c) for c in self.reg.c4_routes("demo", "S1", "A2")], [["R6"]])
        self.assertEqual([route_ids(c) for c in self.reg.c4_routes("demo", "A1", "S1")], [["R1"]])

    def test_from_inside_or_equal_to_the_target_gives_nothing(self):
        self.assertEqual(self.reg.c4_routes("demo", "K1", "C2"), [])
        self.assertEqual(self.reg.c4_routes("demo", "C2", "C2"), [])
        self.assertEqual(self.reg.c4_routes("demo", "K1", "S1"), [])

    def test_equal_length_chains_sort_by_path_number(self):
        edges = [("R10", "C1", "C3"), ("R3", "C3", "C4"), ("R2", "C1", "C2"), ("R11", "C2", "C4")]
        with synthetic(self.reg, edges):
            chains = self.reg.c4_routes("demo", "C1", "C4")
        self.assertEqual([route_ids(c) for c in chains], [["R2", "R11"], ["R10", "R3"]])


class CountsTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry_shop(self.tmp)

    def test_a_pending_mitigated_risk_is_not_counted(self):
        a = draft(self.reg, ["R2"])
        self.reg.approve(session(), "demo", a, NOTE)
        self.reg.edit_risk("demo", a, {"status": "mitigated"}, run_id=start(self.reg))  # AI edit
        self.assertEqual(self.reg.get_risk("demo", a)["review_state"], "pending")
        self.assertEqual(self.reg.open_risk_counts("demo"), {})

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
