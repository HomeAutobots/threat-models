import subprocess
import unittest
from unittest import mock

from helpers import (SAMPLE_CATALOG, SAMPLE_DFD, TmpTestCase, ai_fields, human_terminal, make_registry,
                     session, start)
from tmreg import core, model
from tmreg.core import RegistryError, StaleRecord

NOTE = "Confirmed on F2 against the design doc."


class _Stream:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class _Closed:
    def isatty(self):
        raise ValueError("I/O operation on closed file")


class HasTtyTest(unittest.TestCase):
    def check(self, stdin, stdout):
        with mock.patch("tmreg.core.sys.stdin", stdin), mock.patch("tmreg.core.sys.stdout", stdout):
            return core._has_tty()

    def test_has_tty(self):
        self.assertTrue(self.check(_Stream(True), _Stream(True)))
        self.assertFalse(self.check(_Stream(True), _Stream(False)))
        self.assertFalse(self.check(_Stream(False), _Stream(True)))
        self.assertFalse(self.check(object(), _Stream(True)))
        self.assertFalse(self.check(_Closed(), _Stream(True)))
        self.assertFalse(self.check(None, _Stream(True)))


class ReviewTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.run = start(self.reg)

    def add(self, **kw):
        return self.reg.add_risk("demo", ai_fields(**kw), run_id=self.run)

    def add_approved(self):
        self.add()
        return self.reg.approve(session(), "demo", "T-01", NOTE)

    def edit(self, owner):
        return self.reg.edit_risk("demo", "T-01", {"owner": owner}, run_id=self.run)

    def test_approve(self):
        self.add()
        r = self.reg.approve(session(), "demo", "T-01", NOTE)
        self.assertEqual((r["review_state"], r["reviewed_by"], r["review_note"]),
                         ("approved", "Test Reviewer", NOTE))
        self.assertIsNotNone(r["reviewed_at"])
        self.assertEqual(self.reg.history("demo", "T-01")[-1]["actor"], "human:Test Reviewer")
        with self.assertRaisesRegex(RegistryError, "pending"):
            self.reg.approve(session(), "demo", "T-01", NOTE)

    def test_seen_stale_is_refused_and_writes_nothing(self):
        self.add()
        seen = self.reg.get_risk("demo", "T-01")
        self.reg.edit_risk("demo", "T-01", {"notes": "changed"}, run_id=self.run)
        before = len(self.reg.history("demo"))
        for call in (lambda: self.reg.approve(session(), "demo", "T-01", NOTE, seen=seen),
                     lambda: self.reg.reject(session(), "demo", "T-01", NOTE, seen=seen)):
            with self.assertRaisesRegex(RegistryError, "changed since it was shown"):
                call()
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "pending")
        self.assertEqual(len(self.reg.history("demo")), before)

    def test_seen_stale_merge_and_retire_raise_stale_record(self):
        self.add()
        self.add()
        self.reg.approve(session(), "demo", "T-01", NOTE)
        seen_new = self.reg.get_risk("demo", "T-02")
        seen_old = self.reg.get_risk("demo", "T-01")
        self.reg.edit_risk("demo", "T-02", {"notes": "x"}, run_id=self.run)
        self.reg.edit_risk("demo", "T-01", {"notes": "y"}, run_id=self.run)
        with self.assertRaises(StaleRecord):
            self.reg.merge(session(), "demo", "T-02", "T-01", NOTE, seen=seen_new)
        self.reg.approve(session(), "demo", "T-01", NOTE)
        with self.assertRaises(StaleRecord):
            self.reg.retire(session(), "demo", "T-01", NOTE, seen=seen_old)
        with self.assertRaises(StaleRecord):  # no longer pending counts as stale too
            self.reg.approve(session(), "demo", "T-01", NOTE, seen=seen_old)

    def test_seen_current_succeeds(self):
        self.add()
        seen = self.reg.get_risk("demo", "T-01")
        r = self.reg.approve(session(), "demo", "T-01", NOTE, seen=seen)
        self.assertEqual(r["review_state"], "approved")

    def test_approve_guards(self):
        self.add()
        with self.assertRaisesRegex(RegistryError, "20"):
            self.reg.approve(session(), "demo", "T-01", "ok")
        with self.assertRaises(RegistryError):
            self.reg.approve("Test Reviewer", "demo", "T-01", NOTE)
        with self.assertRaisesRegex(RegistryError, "no risk"):
            self.reg.approve(session(), "demo", "T-09", NOTE)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "pending")

    def test_all_methods_refuse_non_sessions(self):
        for call in (lambda: self.reg.reject("x", "demo", "T-01", NOTE),
                     lambda: self.reg.merge("x", "demo", "T-02", "T-01", NOTE),
                     lambda: self.reg.retire("x", "demo", "T-01", NOTE),
                     lambda: self.reg.import_legacy("x", "demo")):
            with self.assertRaises(RegistryError):
                call()

    def test_rejected_ids_are_never_reused(self):
        self.add()
        self.reg.reject(session(), "demo", "T-01", NOTE)
        self.assertEqual(self.add()["id"], "T-02")

    def test_reject_plain(self):
        self.add()
        r = self.reg.reject(session(), "demo", "T-01", NOTE)
        self.assertEqual((r["review_state"], r["review_note"]), ("rejected", NOTE))
        self.assertEqual(self.reg.history("demo", "T-01")[-1]["op"], "reject")

    def test_edit_approved_returns_to_review(self):
        self.add_approved()
        r = self.edit("A. Okafor")
        self.assertEqual((r["review_state"], r["reviewed_by"]), ("pending", None))
        self.assertEqual(r["last_approved"]["review_note"], NOTE)
        self.assertIsNone(r["last_approved"]["owner"])

    def test_second_edit_keeps_original_snapshot(self):
        self.add_approved()
        self.edit("A")
        self.edit("B")
        self.assertIsNone(self.reg.get_risk("demo", "T-01")["last_approved"]["owner"])

    def test_reject_re_review_restores_last_approved(self):
        self.add()
        with mock.patch("tmreg.db.now", return_value="2026-01-01T00:00:01Z"):
            self.reg.approve(session(), "demo", "T-01", NOTE)
        approved = self.reg.get_risk("demo", "T-01")
        with mock.patch("tmreg.db.now", return_value="2026-01-02T00:00:02Z"):
            self.edit("A")
        with mock.patch("tmreg.db.now", return_value="2026-01-03T00:00:03Z"):
            self.edit("B")
        with mock.patch("tmreg.db.now", return_value="2026-01-04T00:00:04Z"):
            r = self.reg.reject(session(), "demo", "T-01", "Owner change not agreed with Payments.")
        for f in model.SNAPSHOT_FIELDS:
            self.assertEqual(r[f], approved[f], f)
        self.assertEqual((r["owner"], r["review_state"], r["last_approved"], r["review_note"]),
                         (None, "approved", None, NOTE))
        last = self.reg.history("demo", "T-01")[-1]
        self.assertEqual(last["op"], "revert")
        self.assertEqual(last["note"], "Owner change not agreed with Payments.")

    def test_approve_re_review_clears_snapshot(self):
        self.add_approved()
        self.edit("A")
        r = self.reg.approve(session(), "demo", "T-01", NOTE)
        self.assertIsNone(r["last_approved"])
        self.assertEqual((r["owner"], r["review_state"]), ("A", "approved"))

    def test_editors_since_last_approval_reset_on_approval_and_revert(self):  # I2
        ai = f"ai:{self.run}"

        def since():
            return self.reg.editors("demo", "T-01", since_last_approval=True)
        self.add()
        self.assertEqual(since(), [])
        self.edit("A")
        self.assertEqual(since(), [ai])
        self.reg.approve(session(), "demo", "T-01", NOTE)
        self.assertEqual(since(), [])
        self.assertEqual(self.reg.editors("demo", "T-01", since_last_approval=False), [ai])
        with human_terminal():
            self.reg.edit_risk("demo", "T-01", {"owner": "B"}, run_id=None)
        self.assertEqual(since(), [])  # a human edit that leaves it approved is a new baseline
        self.edit("C")
        self.assertEqual(since(), [ai])
        self.reg.reject(session(), "demo", "T-01", "Owner change not agreed with Payments.")  # revert
        self.assertEqual(since(), [])
        self.assertEqual(self.reg.editors("demo", "T-01", since_last_approval=False),
                         [ai, "human:Test Reviewer"])
        with self.assertRaisesRegex(RegistryError, "no risk"):
            self.reg.editors("demo", "T-09", since_last_approval=True)

    def test_editors_human_edit_that_stays_approved_resets_the_baseline(self):
        ai = f"ai:{self.run}"
        self.add_approved()
        with human_terminal():
            self.reg.edit_risk("demo", "T-01", {"owner": "A"}, run_id=None)
            self.reg.edit_risk("demo", "T-01", {"owner": "B"}, run_id=None)
        self.assertEqual(self.reg.editors("demo", "T-01", since_last_approval=True), [])
        self.assertEqual(self.reg.editors("demo", "T-01", since_last_approval=False),
                         ["human:Test Reviewer"])
        self.edit("C")  # AI edit: pending
        with human_terminal():  # human edit of a pending risk leaves it pending: not a baseline
            self.reg.edit_risk("demo", "T-01", {"owner": "D"}, run_id=None)
        self.assertEqual(self.reg.editors("demo", "T-01", since_last_approval=True),
                         [ai, "human:Test Reviewer"])

    def test_merge(self):
        self.add_approved()
        self.add()  # T-02, pending duplicate
        before = self.reg.get_risk("demo", "T-01")
        n_hist = len(self.reg.history("demo", "T-01"))
        r = self.reg.merge(session(), "demo", "T-02", "T-01", NOTE)
        self.assertEqual((r["review_state"], r["merged_into"]), ("rejected", "T-01"))
        self.assertEqual(self.reg.get_risk("demo", "T-01"), before)
        self.assertEqual(len(self.reg.history("demo", "T-01")), n_hist)
        self.assertEqual(self.reg.history("demo", "T-02")[-1]["op"], "merge")

    def test_merge_refusals(self):
        self.add_approved()
        self.add()                   # T-02 pending
        self.add()                   # T-03 pending
        self.reg.reject(session(), "demo", "T-03", NOTE)
        self.edit("A")               # T-01 is now a re-review
        self.add(category="I")       # T-04 pending, no snapshot
        for args, pat in ((("T-04", "T-04"), "itself"), (("T-01", "T-02"), "re-review"),
                          (("T-04", "T-03"), "rejected"), (("T-04", "T-77"), "no risk"),
                          (("T-03", "T-02"), "pending")):
            with self.subTest(args=args), self.assertRaisesRegex(RegistryError, pat):
                self.reg.merge(session(), "demo", *args, NOTE)
        self.assertEqual(self.reg.get_risk("demo", "T-04")["review_state"], "pending")

    def test_retire_and_edit_refusals(self):
        reason = "Feature removed in release 4.3; no code path left."
        self.add_approved()
        self.add()
        self.reg.reject(session(), "demo", "T-02", NOTE)
        r = self.reg.retire(session(), "demo", "T-01", reason)
        self.assertEqual((r["status"], r["status_reason"]), ("retired", reason))
        self.assertEqual(self.reg.history("demo", "T-01")[-1]["op"], "retire")
        for rid in ("T-01", "T-02"):
            with self.subTest(rid=rid), self.assertRaises(RegistryError):
                self.reg.edit_risk("demo", rid, {"owner": "x"}, run_id=self.run)
        self.add()
        with self.assertRaisesRegex(RegistryError, "20"):
            self.reg.retire(session(), "demo", "T-03", "short")
        with self.assertRaisesRegex(RegistryError, "approved"):
            self.reg.retire(session(), "demo", "T-03", reason)
        with self.assertRaisesRegex(RegistryError, "already retired"):
            self.reg.retire(session(), "demo", "T-01", reason)

    def test_dfd_reapproval_warns_for_cited_ids(self):
        self.add(elements=["P2", "F3"])
        self.reg.approve(session(), "demo", "T-01", NOTE)
        (self.reg.root / "systems/demo/dfd.md").write_bytes(
            SAMPLE_DFD.replace(b"| F3 | P2 | D1 | SQL |\n", b""))
        prev = self.reg.dfd_preview("demo")
        self.assertEqual(prev["removed"], ["F3"])
        self.assertIn("T-01 cites F3", prev["warnings"][0])
        self.reg.dfd_approve(session(), "demo", "Removed the direct SQL flow per ADR-11.")
        with self.assertRaisesRegex(RegistryError, "F3"):
            self.reg.edit_risk("demo", "T-01", {"owner": "x"}, run_id=self.run)


class ImportLegacyTest(TmpTestCase):
    def test_import_preview(self):
        reg = make_registry(self.tmp, legacy=True)
        p = reg.import_preview("demo")
        self.assertEqual((p["count"], p["first"], p["last"]), (3, "T-01", "PT-01"))
        self.assertRegex(p["commit"], r"^[0-9a-f]{40}")
        self.assertEqual(reg.list_risks("demo"), [])

    def test_import_legacy(self):
        reg = make_registry(self.tmp, legacy=True)
        ids = reg.import_legacy(session(), "demo")
        self.assertEqual(ids, ["T-01", "T-02", "PT-01"])
        t1 = reg.get_risk("demo", "T-01")
        self.assertEqual((t1["review_state"], t1["drafted_by"], t1["detail_complete"]),
                         ("approved", "human:catalog-import", 0))
        self.assertRegex(t1["review_note"], r"commit [0-9a-f]{40}")
        self.assertEqual((t1["method"], t1["elements"], t1["status"], t1["dfd_approval_id"]),
                         ("stride-per-element", ["E1", "F1"], "open", "DFD-1"))  # M3: method names
        self.assertEqual(reg.get_risk("demo", "PT-01")["method"], "linddun")
        self.assertEqual(reg.history("demo", "T-01")[-1]["op"], "import")
        with human_terminal():  # a catalog mirror takes no AI runs (I4); the owner adds by hand
            self.assertEqual(reg.add_risk("demo", ai_fields(), run_id=None)["id"], "T-03")
            self.assertEqual(reg.add_risk("demo", ai_fields(category="Linking", elements=["D1"]),
                                          run_id=None)["id"], "PT-02")
        with self.assertRaisesRegex(RegistryError, "once"):
            reg.import_legacy(session(), "demo")

    def test_owner_edit_fills_imported_one_liner(self):
        reg = make_registry(self.tmp, legacy=True)
        reg.import_legacy(session(), "demo")
        have = ("title", "elements", "category", "method", "origin", "origin_ref", "description")
        detail = {f: ai_fields()[f] for f in model.AI_REQUIRED if f not in have}
        with human_terminal():
            reg.edit_risk("demo", "T-01", detail, run_id=None)
            reg.edit_risk("demo", "T-02", {"notes": "Owner confirmed the webhook path."}, run_id=None)
        r = reg.get_risk("demo", "T-01")
        self.assertEqual((r["review_state"], r["detail_complete"]), ("approved", 1))
        self.assertEqual(reg.history("demo", "T-01")[-1]["diff"]["detail_complete"], [0, 1])
        r = reg.get_risk("demo", "T-02")
        self.assertEqual((r["review_state"], r["detail_complete"]), ("approved", 0))
        self.assertEqual(reg.verify("demo"), [])

    def test_approve_still_marks_detail_complete_after_ai_edit(self):
        reg = make_registry(self.tmp, legacy=True, trial=True)
        reg.import_legacy(session(), "demo")
        run = start(reg)
        have = ("title", "elements", "category", "method", "origin", "origin_ref", "description")
        detail = {f: ai_fields()[f] for f in model.AI_REQUIRED if f not in have}
        reg.edit_risk("demo", "T-01", detail, run_id=run)
        self.assertEqual(reg.get_risk("demo", "T-01")["review_state"], "pending")
        reg.approve(session(), "demo", "T-01", NOTE)
        self.assertEqual(reg.get_risk("demo", "T-01")["detail_complete"], 1)

    def _catalog_path(self, reg):
        return reg.config.framework_path / "docs/reference/reference-system.md"

    def _set_catalog(self, reg, text):
        """Rewrite the catalog and commit it, so the import sees a clean, citable file."""
        self._catalog_path(reg).write_text(text)
        fw = str(reg.config.framework_path)
        subprocess.run(["git", "-C", fw, "-c", "user.name=t", "-c", "user.email=t@e.com",
                        "-c", "commit.gpgsign=false", "commit", "-qam", "edit", "--no-verify"],
                       check=True, capture_output=True)

    def test_import_refuses_malformed_catalog_rows(self):
        reg = make_registry(self.tmp, legacy=True)
        self._set_catalog(reg, SAMPLE_CATALOG.replace("| T-02 | F2, P2 | T |", "| T-02 | F2, P2 |\n| T-03 | F2 | T |", 1))
        with self.assertRaisesRegex(RegistryError, "T-02: catalog row needs"):
            reg.import_legacy(session(), "demo")
        self.assertEqual(reg.list_risks("demo"), [])

    def test_import_refuses_category_that_does_not_fit_id(self):
        reg = make_registry(self.tmp, legacy=True)
        for old, new in (("| PT-01 | D1 | Linking |", "| PT-01 | D1 | S |"),
                         ("| T-02 | F2, P2 | T |", "| T-02 | F2, P2 | Linking |"),
                         ("| T-02 | F2, P2 | T |", "| T-02 | F2, P2 | Bogus |")):
            with self.subTest(new=new):
                self._set_catalog(reg, SAMPLE_CATALOG.replace(old, new))
                with self.assertRaisesRegex(RegistryError, "T-02|PT-01"):
                    reg.import_legacy(session(), "demo")
        self.assertEqual(reg.list_risks("demo"), [])

    def test_import_refuses_dirty_catalog_but_allows_other_dirty_files(self):
        reg = make_registry(self.tmp, legacy=True)
        fw = reg.config.framework_path
        (fw / "docs/other.md").write_text("scratch")
        path = self._catalog_path(reg)
        path.write_text(path.read_text() + "\nedited\n")
        with self.assertRaisesRegex(RegistryError, "uncommitted changes"):
            reg.import_legacy(session(), "demo")
        self.assertEqual(reg.list_risks("demo"), [])
        subprocess.run(["git", "-C", str(fw), "checkout", "--", "docs/reference/reference-system.md"],
                       check=True, capture_output=True)
        reg.import_legacy(session(), "demo")
        self.assertRegex(reg.get_risk("demo", "T-01")["review_note"], r"commit [0-9a-f]{40}\+dirty")

    def test_import_refuses_unreadable_commit(self):
        reg = make_registry(self.tmp, legacy=True)
        with mock.patch("tmreg.core.framework_commit", return_value="unknown"):
            with self.assertRaisesRegex(RegistryError, "cannot read the guide's git commit"):
                reg.import_legacy(session(), "demo")

    def test_import_refuses_empty_catalog(self):
        reg = make_registry(self.tmp, legacy=True)
        self._set_catalog(reg, "## Threat catalog used in worked examples\n\nnothing yet\n")
        with self.assertRaisesRegex(RegistryError, "no catalog rows"):
            reg.import_legacy(session(), "demo")

    def test_import_into_nonempty_register_refused_before_parsing(self):
        reg = make_registry(self.tmp, legacy=True)
        with human_terminal():
            reg.add_risk("demo", ai_fields(), run_id=None)
        self._set_catalog(reg, "# garbage, no section")
        with self.assertRaisesRegex(RegistryError, "once"):
            reg.import_legacy(session(), "demo")
        self.assertEqual([r["id"] for r in reg.list_risks("demo")], ["T-01"])

    def test_import_needs_config_and_dfd(self):
        reg = make_registry(self.tmp)
        with self.assertRaisesRegex(RegistryError, "no legacy_catalog in system.toml"):
            reg.import_legacy(session(), "demo")

    def test_import_needs_approved_dfd(self):
        reg = make_registry(self.tmp, legacy=True, approve=False)
        with self.assertRaisesRegex(RegistryError, "DFD"):
            reg.import_legacy(session(), "demo")

    def test_import_refuses_unknown_elements_and_writes_nothing(self):
        reg = make_registry(self.tmp, legacy=True)
        self._set_catalog(reg, SAMPLE_CATALOG.replace("| PT-01 | D1 |", "| PT-01 | X9 |"))
        with self.assertRaisesRegex(RegistryError, "X9"):
            reg.import_legacy(session(), "demo")
        self.assertEqual(reg.list_risks("demo"), [])
        self.assertEqual([c for c in reg.history("demo") if c["tbl"] == "risks"], [])
        with human_terminal():
            self.assertEqual(reg.add_risk("demo", ai_fields(), run_id=None)["id"], "T-01")


if __name__ == "__main__":
    unittest.main()
