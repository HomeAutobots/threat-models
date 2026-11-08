import unittest
from unittest import mock

from helpers import SAMPLE_DFD, TmpTestCase, ai_fields, make_registry, session, start
from tmreg import core
from tmreg.core import RegistryError

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
        self.add_approved()
        self.edit("A")
        self.edit("B")
        r = self.reg.reject(session(), "demo", "T-01", "Owner change not agreed with Payments.")
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

    def test_merge(self):
        self.add_approved()
        self.add()  # T-02, pending duplicate
        r = self.reg.merge(session(), "demo", "T-02", "T-01", NOTE)
        self.assertEqual((r["review_state"], r["merged_into"]), ("rejected", "T-01"))
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "approved")
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
    def test_import_legacy(self):
        reg = make_registry(self.tmp, legacy=True)
        ids = reg.import_legacy(session(), "demo")
        self.assertEqual(ids, ["T-01", "T-02", "PT-01"])
        t1 = reg.get_risk("demo", "T-01")
        self.assertEqual((t1["review_state"], t1["drafted_by"], t1["detail_complete"]),
                         ("approved", "human:catalog-import", 0))
        self.assertRegex(t1["review_note"], r"commit [0-9a-f]{40}")
        self.assertEqual((t1["method"], t1["elements"], t1["status"], t1["dfd_approval_id"]),
                         ("STRIDE", ["E1", "F1"], "open", "DFD-1"))
        self.assertEqual(reg.get_risk("demo", "PT-01")["method"], "LINDDUN")
        self.assertEqual(reg.history("demo", "T-01")[-1]["op"], "import")
        run = start(reg)
        self.assertEqual(reg.add_risk("demo", ai_fields(), run_id=run)["id"], "T-03")
        self.assertEqual(reg.add_risk("demo", ai_fields(category="Linking", elements=["D1"]),
                                      run_id=run)["id"], "PT-02")
        with self.assertRaisesRegex(RegistryError, "once"):
            reg.import_legacy(session(), "demo")

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
        path = reg.config.framework_path / "docs/reference/reference-system.md"
        path.write_text(path.read_text().replace("| PT-01 | D1 |", "| PT-01 | X9 |"))
        with self.assertRaisesRegex(RegistryError, "X9"):
            reg.import_legacy(session(), "demo")
        self.assertEqual(reg.list_risks("demo"), [])
        self.assertEqual([c for c in reg.history("demo") if c["tbl"] == "risks"], [])
        self.assertEqual(reg.add_risk("demo", ai_fields(), run_id=start(reg))["id"], "T-01")


if __name__ == "__main__":
    unittest.main()
