"""The first model approval adopts a DFD-era register's live risks through tm.was (spec 7.6)."""
import hashlib
import unittest
from unittest import mock

from helpers import (SAMPLE_WORKSPACE, TmpTestCase, approve_model, make_registry, seed_dfd_era,
                     seed_dfd_risk, write_model)
from tmreg import ledger
from tmreg.core import RegistryError

TEXT = SAMPLE_WORKSPACE.decode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AdoptTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp, approve=False)
        seed_dfd_era(self.reg)

    def approve(self):
        return approve_model(self.reg, "demo")

    def risk(self, rid):
        return self.reg.get_risk("demo", rid)

    def test_adoption_rewrites_live_risks(self):
        seed_dfd_risk(self.reg, "T-01", ["P2", "F2"], review_state="approved",
                      last_approved="2026-11-01T00:00:00Z")
        seed_dfd_risk(self.reg, "T-02", ["E1"])
        seed_dfd_risk(self.reg, "T-03", ["D1"], status="retired")
        self.approve()
        a = self.risk("T-01")
        self.assertEqual(a["elements"], ["C2", "R2"])
        self.assertEqual(a["review_state"], "approved")
        self.assertEqual(a["model_approval_id"], "MODEL-1")
        self.assertEqual(a["dfd_approval_id"], "DFD-1")
        last = self.reg.history("demo", "T-01")[-1]
        self.assertEqual(last["op"], "edit")
        self.assertEqual(last["actor"], "human:Test Reviewer")
        self.assertEqual(last["note"], "Adopted the C4 model MODEL-1: P2→C2, F2→R2")
        self.assertEqual(self.risk("T-02")["elements"], ["A1"])
        self.assertEqual(self.risk("T-02")["review_state"], "pending")
        self.assertEqual(self.risk("T-03")["elements"], ["D1"])
        self.assertEqual(self.reg.verify("demo"), [])

    def test_preview_shows_adoption(self):
        seed_dfd_risk(self.reg, "T-01", ["P2", "F2"])
        seed_dfd_risk(self.reg, "T-02", ["P9"])
        ad = self.reg.c4_preview("demo")["adoption"]
        self.assertEqual(ad["gaps"], [{"id": "P9", "cited_by": ["T-02"]}])
        self.assertEqual(ad["pending_rereviews"], [])
        self.assertEqual(ad["rewrites"], {"T-01": {"from": ["P2", "F2"], "to": ["C2", "R2"]}})

    def test_no_adoption_outside_dfd_era(self):
        reg = make_registry(self.tmp / "x", approve=False, slug="other")
        self.assertIsNone(reg.c4_preview("other")["adoption"])
        approve_model(reg, "other")
        self.assertIsNone(reg.c4_preview("other")["adoption"])

    def test_adoption_refuses_gaps(self):
        seed_dfd_risk(self.reg, "T-04", ["P9"])
        with self.assertRaises(RegistryError) as cm:
            self.approve()
        self.assertIn("P9", str(cm.exception))
        self.assertIn("T-04", str(cm.exception))
        self.assertEqual(self.reg.model_approvals("demo"), [])

    def test_gaps_ignore_retired_rejected_and_merged(self):
        seed_dfd_risk(self.reg, "T-01", ["P9"], status="retired")
        seed_dfd_risk(self.reg, "T-02", ["P8"], review_state="rejected")
        seed_dfd_risk(self.reg, "T-03", ["P7"], merged_into="T-04")
        seed_dfd_risk(self.reg, "T-04", ["P1"])
        self.assertEqual(self.reg.c4_preview("demo")["adoption"]["gaps"], [])
        self.approve()
        self.assertEqual(self.risk("T-01")["elements"], ["P9"])
        self.assertEqual(self.risk("T-02")["elements"], ["P8"])
        self.assertEqual(self.risk("T-03")["elements"], ["P7"])
        self.assertEqual(self.risk("T-04")["elements"], ["C1"])
        self.assertEqual(self.reg.verify("demo"), [])

    def test_adoption_refuses_pending_rereviews(self):
        seed_dfd_risk(self.reg, "T-05", ["P1"], last_approved="2026-11-01T00:00:00Z")
        with self.assertRaises(RegistryError) as cm:
            self.approve()
        self.assertIn("T-05 awaits re-review", str(cm.exception))
        self.assertEqual(self.reg.c4_preview("demo")["adoption"]["pending_rereviews"], ["T-05"])
        self.assertEqual(self.reg.model_approvals("demo"), [])

    def test_split_mapping(self):
        anchor = '            C3 = container "C3 Database"'
        extra = ('            C4 = container "C4 Worker" "Splits C2." "Python" {\n'
                 '                properties {\n                    "tm.owner" "Demo team"\n'
                 '                    "tm.was" "P2"\n                }\n            }\n')
        data = TEXT.replace(anchor, extra + anchor, 1).replace(
            "                containerInstance C3\n", "                containerInstance C3\n                containerInstance C4\n", 1).encode()
        write_model(self.reg, "demo", data)
        seed_dfd_risk(self.reg, "T-01", ["P2", "F2"])
        ad = self.reg.c4_preview("demo")
        self.assertEqual(ad["problems"], [])
        self.approve()
        self.assertEqual(self.risk("T-01")["elements"], ["C2", "C4", "R2"])
        self.assertEqual(self.reg.history("demo", "T-01")[-1]["note"],
                         "Adopted the C4 model MODEL-1: P2→C2/C4, F2→R2")

    def test_adoption_happens_once(self):
        seed_dfd_risk(self.reg, "T-01", ["P1"])
        self.approve()
        self.assertEqual(self.risk("T-01")["elements"], ["C1"])
        n = len(self.reg.history("demo", "T-01"))
        write_model(self.reg, "demo", TEXT.replace("Serves the pages.", "Serves pages.").encode())
        self.assertIsNone(self.reg.c4_preview("demo")["adoption"])
        self.approve()
        self.assertEqual(len(self.reg.history("demo", "T-01")), n)
        self.assertEqual(self.reg.verify("demo"), [])

    def test_unchanged_risk_gets_no_edit(self):
        seed_dfd_risk(self.reg, "T-01", ["TB1"])
        self.approve()
        self.assertEqual([c["op"] for c in self.reg.history("demo", "T-01")], ["add"])

    def test_failure_partway_rolls_back_the_approval(self):
        seed_dfd_risk(self.reg, "T-01", ["P1"])
        seed_dfd_risk(self.reg, "T-02", ["P2"])
        real = ledger.write_row
        calls = []

        def flaky(conn, slug, tbl, key, fields, **kw):
            if tbl == "risks":
                calls.append(key)
                if len(calls) == 2:
                    raise RuntimeError("boom")
            return real(conn, slug, tbl, key, fields, **kw)

        with mock.patch("tmreg.core.ledger.write_row", side_effect=flaky):
            with self.assertRaises(RuntimeError):
                self.approve()
        self.assertEqual(self.reg.model_approvals("demo"), [])
        self.assertEqual(self.risk("T-01")["elements"], ["P1"])
        self.assertEqual(len(self.reg.history("demo", "T-01")), 1)
        self.assertEqual(self.reg.verify("demo"), [])
        self.approve()  # and the retry works
        self.assertEqual(self.risk("T-02")["elements"], ["C2"])


if __name__ == "__main__":
    unittest.main()
