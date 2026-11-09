from helpers import TmpTestCase, ai_fields, make_registry, seed_dfd_era, session, start
from tmreg.core import RegistryError


class VerifyTest(TmpTestCase):
    def _reg(self):
        reg = make_registry(self.tmp)
        run = start(reg)
        self.rid = reg.add_risk("demo", ai_fields(), run_id=run)["id"]
        reg.approve(session(), "demo", self.rid, "Confirmed on R2 against the design doc.")
        return reg

    def test_clean_registry_verifies(self):
        self.assertEqual(self._reg().verify("demo"), [])

    def test_unknown_system_raises(self):
        with self.assertRaises(RegistryError):
            self._reg().verify("nope")

    def test_detects_missing_trigger(self):
        reg = self._reg()
        reg.conn.execute("DROP TRIGGER demo__risks_no_delete")
        self.assertIn("trigger demo__risks_no_delete is missing", reg.verify("demo"))

    def test_detects_direct_row_edit(self):
        reg = self._reg()
        reg.conn.execute("UPDATE demo__risks SET review_state='rejected' WHERE id='T-01'")
        reg.conn.commit()
        self.assertTrue(any("T-01: review_state differs" in p for p in reg.verify("demo")))

    def test_detects_row_missing_from_log(self):
        reg = self._reg()
        reg.conn.execute("INSERT INTO demo__risks (id, title) VALUES ('T-09', 'x')")
        reg.conn.commit()
        problems = reg.verify("demo")
        self.assertTrue(any("T-09 is in the table but not in the change log" in p for p in problems))
        self.assertTrue(any("sequence T is behind T-09" in p for p in problems))

    def test_detects_forged_change_row(self):
        reg = self._reg()
        reg.conn.execute("DROP TRIGGER demo__changes_no_update")
        reg.conn.execute("UPDATE demo__changes SET actor='human:Test Reviewer' WHERE op='add'")
        reg.conn.commit()
        self.assertTrue(any(p.startswith("change #") for p in reg.verify("demo")))

    def test_malformed_diff_is_reported_not_raised(self):
        reg = self._reg()
        reg.conn.execute("DROP TRIGGER demo__changes_no_update")
        reg.conn.execute("UPDATE demo__changes SET diff='{' WHERE seq=1")
        reg.conn.commit()
        problems = reg.verify("demo")
        self.assertIsInstance(problems, list)
        self.assertIn("change #1: diff is not valid JSON", problems)

    def test_malformed_json_cell_is_reported_not_raised(self):
        reg = self._reg()
        reg.conn.execute("UPDATE demo__risks SET elements='[' WHERE id='T-01'")
        reg.conn.commit()
        self.assertIn("risks T-01: elements is not valid JSON", reg.verify("demo"))

    def test_detects_row_missing_from_table_and_sequence_row(self):
        reg = self._reg()
        reg.conn.execute("DROP TRIGGER demo__risks_no_delete")
        reg.conn.execute("DELETE FROM demo__risks WHERE id='T-01'")
        reg.conn.execute("DELETE FROM demo__sequences WHERE prefix='PT'")
        reg.conn.commit()
        problems = reg.verify("demo")
        self.assertIn("risks T-01 is in the change log but not in the table", problems)
        self.assertIn("sequence PT is missing", problems)

    def test_verify_reports_model_sequence_behind(self):
        reg = self._reg()
        reg.conn.execute("INSERT INTO demo__model_approvals (id, version) VALUES ('MODEL-3', '1.0')")
        reg.conn.commit()
        self.assertIn("sequence MODEL is behind MODEL-3", reg.verify("demo"))

    def test_detects_schema_version_and_approval_sequences(self):
        reg = self._reg()
        seed_dfd_era(reg, "demo")  # verify accepts both eras' approvals
        self.assertEqual(reg.verify("demo"), [])
        reg.conn.execute("UPDATE meta SET value='9' WHERE key='schema_version'")
        reg.conn.execute("UPDATE demo__sequences SET next=1 WHERE prefix IN ('DFD', 'MODEL')")
        reg.conn.commit()
        problems = reg.verify("demo")
        self.assertIn("schema_version is 9, expected 2", problems)
        self.assertIn("sequence DFD is behind DFD-1", problems)
        self.assertIn("sequence MODEL is behind MODEL-1", problems)
