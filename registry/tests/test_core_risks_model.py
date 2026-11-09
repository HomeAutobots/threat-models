"""Risks cite the approved C4 model: add, edit, runs, import through tm.was, and moved_on."""
import subprocess
import unittest

from helpers import (FIXTURES, SAMPLE_WORKSPACE, TmpTestCase, ai_fields,
                     approve_model, human_terminal, make_registry, seed_dfd_approval, seed_dfd_era, seed_dfd_risk,
                     session, start, write_model)
from tmreg.core import RegistryError

NOTE = "Checked against the model checklist."
TEXT = SAMPLE_WORKSPACE.decode()
NO_MODEL = "no approved C4 model for demo; approve systems/demo/workspace.dsl first"
WAITING = "demo is waiting for its C4 model to be approved; AI edits resume after that"


def edited(old: str, new: str) -> bytes:
    assert old in TEXT
    return TEXT.replace(old, new, 1).encode()


C3_BLOCK = TEXT[TEXT.index("            C3 = container"):TEXT.index("        }\n\n        R1 =")]
R3_BLOCK = TEXT[TEXT.index("        R3 = C2 -> C3"):TEXT.index("        ENV1 =")]


def without_c3() -> bytes:
    return (TEXT.replace(C3_BLOCK, "").replace(R3_BLOCK, "")
            .replace("                containerInstance C3\n", "")).encode()


class AddTest(TmpTestCase):
    def test_add_needs_a_model_approval(self):
        reg = make_registry(self.tmp, approve=False)
        run = start(reg)
        with self.assertRaises(RegistryError) as cm:
            reg.add_risk("demo", ai_fields(), run_id=run)
        self.assertEqual(str(cm.exception), NO_MODEL)
        seed_dfd_era(reg, "demo")  # a DFD approval is not enough (P5), for AI or owner
        with self.assertRaisesRegex(RegistryError, "^" + NO_MODEL + "$"):
            reg.add_risk("demo", ai_fields(elements=["P2", "F2"]), run_id=run)
        with human_terminal(), self.assertRaisesRegex(RegistryError, "^" + NO_MODEL + "$"):
            reg.add_risk("demo", ai_fields(elements=["P2", "F2"]), run_id=None)
        self.assertEqual(reg.list_risks("demo"), [])
        approve_model(reg, "demo")
        self.assertEqual(reg.add_risk("demo", ai_fields(), run_id=run)["id"], "T-01")

    def test_add_validates_against_the_model(self):
        reg = make_registry(self.tmp)
        run = start(reg)
        for bad in (["ENV1"], ["C9"], ["C2", "P2"]):
            with self.subTest(bad=bad), self.assertRaises(RegistryError) as cm:
                reg.add_risk("demo", ai_fields(elements=bad), run_id=run)
            self.assertEqual(str(cm.exception), f"unknown element ID(s) for MODEL-1: {bad[-1]}")
        self.assertEqual(reg.list_risks("demo"), [])
        r = reg.add_risk("demo", ai_fields(elements=["C2", "R2"]), run_id=run)
        self.assertEqual((r["id"], r["elements"]), ("T-01", ["C2", "R2"]))
        for ok in (["A1"], ["S1"], ["TB1", "TB2"], ["N1"], ["R3", "C3"]):  # any kind but ENV
            with self.subTest(ok=ok):
                reg.add_risk("demo", ai_fields(elements=ok), run_id=run)

    def test_add_cites_every_kind_but_env(self):  # shop.dsl has SEQ, a group TB, I and K
        reg = make_registry(self.tmp, approve=False)
        write_model(reg, "demo", (FIXTURES / "c4" / "shop.dsl").read_bytes())
        approve_model(reg, "demo")
        run = start(reg)
        for ok in ("SEQ1", "TB6", "I1", "K1"):
            with self.subTest(ok=ok):
                r = reg.add_risk("demo", ai_fields(title=f"Risk on {ok}", elements=[ok]), run_id=run)
                self.assertEqual((r["elements"], r["model_approval_id"]), ([ok], "MODEL-1"))
        self.assertEqual(reg.model_record("demo", "MODEL-1")["items"]["TB6"]["kind"], "group")
        with self.assertRaises(RegistryError) as cm:
            reg.add_risk("demo", ai_fields(elements=["ENV1"]), run_id=run)
        self.assertEqual(str(cm.exception), "unknown element ID(s) for MODEL-1: ENV1")
        self.assertEqual(len(reg.list_risks("demo")), 4)

    def test_add_records_model_approval_id(self):
        reg = make_registry(self.tmp)
        r = reg.add_risk("demo", ai_fields(), run_id=start(reg))
        self.assertEqual((r["model_approval_id"], r["dfd_approval_id"]), ("MODEL-1", None))
        write_model(reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        approve_model(reg, "demo")
        r = reg.add_risk("demo", ai_fields(), run_id=start(reg))
        self.assertEqual(r["model_approval_id"], "MODEL-2")
        self.assertEqual(reg.verify("demo"), [])

    def test_runs_record_the_latest_model_approval(self):
        reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(reg, "demo")
        run = reg.start_run("demo")
        self.assertEqual((run["model_approval_id"], run["dfd_approval_id"]), (None, None))
        approve_model(reg, "demo")
        run = reg.start_run("demo")
        self.assertEqual((run["model_approval_id"], run["dfd_approval_id"]), ("MODEL-1", None))
        self.assertEqual(reg.verify("demo"), [])


class EditTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.run = start(self.reg)

    def _approve_model_2(self):
        write_model(self.reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        self.assertEqual(approve_model(self.reg, "demo")["id"], "MODEL-2")

    def test_owner_edit_keeps_the_basis_unless_elements_change(self):  # D1 on model_approval_id
        reg = self.reg
        reg.add_risk("demo", ai_fields(), run_id=self.run)  # T-01
        reg.approve(session(), "demo", "T-01", NOTE)
        self._approve_model_2()
        with human_terminal():
            r = reg.edit_risk("demo", "T-01", {"owner": "Demo team"}, run_id=None)
        self.assertEqual((r["review_state"], r["model_approval_id"]), ("approved", "MODEL-1"))
        with human_terminal():
            r = reg.edit_risk("demo", "T-01", {"elements": ["C2", "R2", "R3"]}, run_id=None)
        self.assertEqual((r["review_state"], r["model_approval_id"]), ("approved", "MODEL-2"))
        self.assertIsNone(r["dfd_approval_id"])
        self.assertEqual(reg.verify("demo"), [])

    def test_pending_and_ai_edits_move_the_basis(self):
        reg = self.reg
        reg.add_risk("demo", ai_fields(), run_id=self.run)  # T-01, pending
        reg.add_risk("demo", ai_fields(), run_id=self.run)  # T-02, approved below
        reg.approve(session(), "demo", "T-02", NOTE)
        self._approve_model_2()
        with human_terminal():
            r = reg.edit_risk("demo", "T-01", {"owner": "Demo team"}, run_id=None)
        self.assertEqual((r["review_state"], r["model_approval_id"]), ("pending", "MODEL-2"))
        r = reg.edit_risk("demo", "T-02", {"owner": "Demo team"}, run_id=self.run)
        self.assertEqual((r["review_state"], r["model_approval_id"]), ("pending", "MODEL-2"))
        self.assertEqual(r["last_approved"]["model_approval_id"], "MODEL-1")

    def test_edit_validates_against_the_latest_model(self):
        reg = self.reg
        reg.add_risk("demo", ai_fields(elements=["C3", "R3"]), run_id=self.run)  # T-01
        write_model(reg, "demo", without_c3())
        approve_model(reg, "demo")
        with self.assertRaises(RegistryError) as cm:
            reg.edit_risk("demo", "T-01", {"owner": "x"}, run_id=self.run)
        self.assertEqual(str(cm.exception), "unknown element ID(s) for MODEL-2: C3, R3")
        for bad in (["ENV1"], ["P2"]):
            with self.subTest(bad=bad), self.assertRaisesRegex(RegistryError, "MODEL-2: " + bad[0]):
                reg.edit_risk("demo", "T-01", {"elements": bad}, run_id=self.run)
        r = reg.edit_risk("demo", "T-01", {"elements": ["C2"]}, run_id=self.run)
        self.assertEqual((r["elements"], r["model_approval_id"]), (["C2"], "MODEL-2"))


class DfdEraTest(TmpTestCase):
    """P5: a register with DFD approvals and no model approval is awaiting adoption."""

    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(self.reg, "demo")
        seed_dfd_risk(self.reg, "T-01", ["P2", "F2"], review_state="approved")
        self.run = start(self.reg)

    def test_ai_edit_waits_for_adoption(self):
        before = self.reg.get_risk("demo", "T-01")
        for fields in ({"owner": "Demo team"}, {"elements": ["C2"]}, {"elements": ["P2", "F3"]}):
            with self.subTest(fields=fields), self.assertRaises(RegistryError) as cm:
                self.reg.edit_risk("demo", "T-01", fields, run_id=self.run)
            self.assertEqual(str(cm.exception), WAITING)
        self.assertEqual(self.reg.get_risk("demo", "T-01"), before)

    def test_owner_edit_in_dfd_era_uses_old_ids(self):
        reg = self.reg
        with human_terminal():
            with self.assertRaises(RegistryError) as cm:
                reg.edit_risk("demo", "T-01", {"elements": ["C2", "R2"]}, run_id=None)
            self.assertEqual(str(cm.exception), "unknown element ID(s) for DFD-1: C2, R2")
            r = reg.edit_risk("demo", "T-01", {"owner": "Demo team"}, run_id=None)
        self.assertEqual((r["review_state"], r["dfd_approval_id"], r["model_approval_id"]),
                         ("approved", "DFD-1", None))
        # D1 still holds on dfd_approval_id before adoption
        self.assertEqual(seed_dfd_approval(reg, "demo")["id"], "DFD-2")
        with human_terminal():
            r = reg.edit_risk("demo", "T-01", {"notes": "Owner confirmed."}, run_id=None)
            self.assertEqual(r["dfd_approval_id"], "DFD-1")
            r = reg.edit_risk("demo", "T-01", {"elements": ["P2", "F3"]}, run_id=None)
        self.assertEqual((r["review_state"], r["elements"], r["dfd_approval_id"]),
                         ("approved", ["P2", "F3"], "DFD-2"))
        self.assertIsNone(r["model_approval_id"])
        self.assertEqual(reg.verify("demo"), [])


    def test_owner_edit_of_pending_in_dfd_era_moves_the_dfd_basis(self):
        reg = self.reg
        seed_dfd_risk(reg, "T-02", ["P1", "F1"])  # pending, on DFD-1
        self.assertEqual(seed_dfd_approval(reg, "demo")["id"], "DFD-2")
        with human_terminal():
            r = reg.edit_risk("demo", "T-02", {"notes": "Owner confirmed."}, run_id=None)
        self.assertEqual((r["review_state"], r["dfd_approval_id"], r["model_approval_id"]),
                         ("pending", "DFD-2", None))
        self.assertEqual(reg.verify("demo"), [])


class NoApprovalTest(TmpTestCase):
    def test_edit_with_no_approval_at_all(self):
        reg = make_registry(self.tmp, approve=False)
        seed_dfd_risk(reg, "T-01", ["P2"], dfd_approval_id=None)  # no approval of either kind
        before = reg.get_risk("demo", "T-01")
        run = start(reg)
        for run_id in (run, None):
            with self.subTest(run_id=run_id), human_terminal(), \
                    self.assertRaises(RegistryError) as cm:
                reg.edit_risk("demo", "T-01", {"owner": "Demo team"}, run_id=run_id)
            self.assertEqual(str(cm.exception), NO_MODEL)
        self.assertEqual(reg.get_risk("demo", "T-01"), before)


class ImportTest(TmpTestCase):
    def test_import_maps_catalog_ids_through_tm_was(self):
        reg = make_registry(self.tmp, legacy=True)
        self.assertEqual(reg.import_preview("demo")["count"], 3)
        self.assertEqual(reg.import_legacy(session(), "demo"), ["T-01", "T-02", "PT-01"])
        got = {r["id"]: r["elements"] for r in reg.list_risks("demo")}
        self.assertEqual(got, {"T-01": ["A1", "R1"], "T-02": ["R2", "C2"], "PT-01": ["C3"]})
        for r in reg.list_risks("demo"):
            self.assertEqual((r["model_approval_id"], r["dfd_approval_id"]), ("MODEL-1", None))
        self.assertEqual(reg.verify("demo"), [])

    def test_import_expands_splits_and_drops_duplicates(self):
        reg = make_registry(self.tmp, legacy=True, approve=False)
        # C1 claims P1 and P2, so P2 splits into C1 and C2, and P1 adds nothing new after it
        write_model(reg, "demo", edited('"tm.was" "P1"', '"tm.was" "P1, P2"'))
        approve_model(reg, "demo")
        _set_catalog(reg, "| T-02 | F2, P2 |", "| T-02 | P2, F2, P1 |")
        reg.import_legacy(session(), "demo")
        got = {r["id"]: r["elements"] for r in reg.list_risks("demo")}
        self.assertEqual(got, {"T-01": ["A1", "R1"], "T-02": ["C1", "C2", "R2"], "PT-01": ["C3"]})

    def test_import_refuses_unclaimed_tb_and_new_style_ids(self):  # R20
        cases = (
            # TB is the one prefix both grammars share: the model has TB1, but nothing claims it
            ("TB1", edited('                    "tm.was" "TB1"\n', ""), "| PT-01 | TB1, D1 |"),
            # a bare new-style ID is not a claim either, though the model has C3
            ("C3", SAMPLE_WORKSPACE, "| PT-01 | C3 |"),
        )
        for n, (bad, data, cell) in enumerate(cases):
            with self.subTest(bad=bad):
                reg = make_registry(self.tmp / str(n), legacy=True, approve=False)
                write_model(reg, "demo", data)
                approve_model(reg, "demo")
                self.assertIn(bad, reg.model_approvals("demo")[0]["ids"][bad[:-1]])
                _set_catalog(reg, "| PT-01 | D1 |", cell)
                for call in (lambda: reg.import_preview("demo"),
                             lambda: reg.import_legacy(session(), "demo")):
                    with self.assertRaises(RegistryError) as cm:
                        call()
                    self.assertEqual(str(cm.exception),
                                     f"PT-01: {bad} is not claimed by any item's tm.was")
                self.assertEqual(reg.list_risks("demo"), [])
                self.assertEqual([c for c in reg.history("demo") if c["tbl"] == "risks"], [])

    def test_import_refuses_an_unclaimed_id(self):
        reg = make_registry(self.tmp, legacy=True, approve=False)
        write_model(reg, "demo", edited('                    "tm.was" "D1"\n', ""))
        approve_model(reg, "demo")
        for call in (lambda: reg.import_preview("demo"), lambda: reg.import_legacy(session(), "demo")):
            with self.assertRaises(RegistryError) as cm:
                call()
            self.assertEqual(str(cm.exception), "PT-01: D1 is not claimed by any item's tm.was")
        self.assertEqual(reg.list_risks("demo"), [])
        self.assertEqual([c for c in reg.history("demo") if c["tbl"] == "risks"], [])

    def test_import_needs_a_model_approval(self):
        reg = make_registry(self.tmp, legacy=True, approve=False)
        seed_dfd_era(reg, "demo")
        for call in (lambda: reg.import_preview("demo"), lambda: reg.import_legacy(session(), "demo")):
            with self.assertRaises(RegistryError) as cm:
                call()
            self.assertEqual(str(cm.exception), NO_MODEL)
        self.assertEqual(reg.list_risks("demo"), [])


def _set_catalog(reg, old: str, new: str) -> None:
    """Edit the guide's catalog and commit it, so the import sees a clean, citable file."""
    path = reg.config.framework_path / "docs/reference/reference-system.md"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))
    fw = str(reg.config.framework_path)
    subprocess.run(["git", "-C", fw, "-c", "user.name=t", "-c", "user.email=t@e.com",
                    "-c", "commit.gpgsign=false", "commit", "-qam", "edit", "--no-verify"],
                   check=True, capture_output=True)


class MovedOnTest(TmpTestCase):
    def test_moved_on(self):
        reg = make_registry(self.tmp)
        run = start(reg)
        c2 = reg.add_risk("demo", ai_fields(elements=["C2", "R2"]), run_id=run)
        c1 = reg.add_risk("demo", ai_fields(category="S", elements=["C1"]), run_id=run)
        same = reg.moved_on("demo", c2)
        self.assertEqual(same, {"moved_on": False, "written_against": "MODEL-1", "latest": "MODEL-1",
                                "changed": []})
        write_model(reg, "demo", edited("Answers the web app.", "Answers the web app well."))
        approve_model(reg, "demo")
        self.assertEqual(reg.moved_on("demo", reg.get_risk("demo", c2["id"])),
                         {"moved_on": True, "written_against": "MODEL-1", "latest": "MODEL-2",
                          "changed": ["C2"]})
        self.assertEqual(reg.moved_on("demo", reg.get_risk("demo", c1["id"])),
                         {"moved_on": False, "written_against": "MODEL-1", "latest": "MODEL-2",
                          "changed": []})

    def test_removed_ids_count_in_the_risks_order(self):
        reg = make_registry(self.tmp)
        r = reg.add_risk("demo", ai_fields(elements=["R3", "C1", "C3"]), run_id=start(reg))
        write_model(reg, "demo", without_c3())
        approve_model(reg, "demo")
        self.assertEqual(reg.moved_on("demo", r)["changed"], ["R3", "C3"])

    def test_tm_was_only_is_not_a_change(self):
        reg = make_registry(self.tmp)
        r = reg.add_risk("demo", ai_fields(elements=["C2"]), run_id=start(reg))
        write_model(reg, "demo", edited('"tm.was" "P2"', '"tm.was" "P2, P9"'))
        approve_model(reg, "demo")
        self.assertEqual(reg.moved_on("demo", r)["moved_on"], False)

    def test_dfd_era_risk_has_no_basis(self):
        reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(reg, "demo")
        r = seed_dfd_risk(reg, "T-01", ["P2"])
        self.assertEqual(reg.moved_on("demo", r), {"moved_on": False, "written_against": None,
                                                   "latest": None, "changed": []})
        approve_model(reg, "demo")
        self.assertEqual(reg.moved_on("demo", r), {"moved_on": False, "written_against": None,
                                                   "latest": "MODEL-1", "changed": []})


class CitedItemsTest(TmpTestCase):
    def moved(self, elements, new):
        reg = make_registry(self.tmp)
        r = reg.add_risk("demo", ai_fields(elements=elements), run_id=start(reg))
        write_model(reg, "demo", new)
        approve_model(reg, "demo")
        return reg, r, reg.cited_items("demo", r)

    def test_same_changed_and_removed(self):
        reg, r, out = self.moved(["C1", "C2", "R3"], without_c3().replace(
            b"Answers the web app.", b"Answers the web app well."))
        self.assertEqual(list(out), ["C1", "C2", "R3"])
        self.assertEqual(out["C1"]["state"], "same")
        self.assertEqual(out["C1"]["written"]["name"], "C1 Web app")
        self.assertIsNone(out["C1"]["latest"])
        self.assertEqual(out["C2"]["state"], "changed")
        self.assertEqual(out["C2"]["written"]["description"], "Answers the web app.")
        self.assertEqual(out["C2"]["latest"]["description"], "Answers the web app well.")
        self.assertEqual(out["R3"]["state"], "removed")
        self.assertIsNotNone(out["R3"]["written"])
        self.assertIsNone(out["R3"]["latest"])
        # the same meaning of changed as moved_on
        self.assertEqual(reg.moved_on("demo", r)["changed"], ["C2", "R3"])

    def test_tm_was_only_is_same(self):
        _, _, out = self.moved(["C2"], edited('"tm.was" "P2"', '"tm.was" "P2, P9"'))
        self.assertEqual(out["C2"]["state"], "same")
        self.assertIsNone(out["C2"]["latest"])

    def test_dfd_era_risk_is_dfd_with_nulls_even_for_tb1(self):
        reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(reg, "demo")
        r = seed_dfd_risk(reg, "T-01", ["P2", "TB1"])
        approve_model(reg, "demo")  # the C4 model has a TB1 too
        self.assertEqual(reg.cited_items("demo", r), {
            "P2": {"written": None, "latest": None, "state": "dfd"},
            "TB1": {"written": None, "latest": None, "state": "dfd"}})

    def test_only_dynamic_views_are_entries(self):
        reg = make_registry(self.tmp)
        risk = {"elements": ["containers", "context"], "model_approval_id": "MODEL-1"}
        out = reg.cited_items("demo", risk)
        self.assertEqual({k: (v["written"], v["latest"]) for k, v in out.items()},
                         {"containers": (None, None), "context": (None, None)})

    def test_no_model_approval_yet(self):
        reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(reg, "demo")
        r = seed_dfd_risk(reg, "T-01", ["P2"])
        self.assertEqual(reg.cited_items("demo", r)["P2"]["state"], "dfd")


class SkeletonTest(TmpTestCase):
    def test_skeleton_points_to_workspace(self):
        reg = make_registry(self.tmp, approve=False)
        skel = (reg.root / "systems/demo/threat-model.md").read_text()
        self.assertIn("## 2. System model\n\nSee [workspace.dsl](workspace.dsl), the system's C4 "
                      "model. Open its diagrams from the web app's Architecture page; check its "
                      "approval with ./tmreg c4 status demo.\n\n## 3. Assumptions", skel)
        self.assertNotIn("dfd", skel.lower())


if __name__ == "__main__":
    unittest.main()
