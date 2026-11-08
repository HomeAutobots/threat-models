import sqlite3
import tempfile
import unittest
from pathlib import Path

from tmreg import db, ledger


class SlugTest(unittest.TestCase):
    def test_accepts_and_rejects(self):
        self.assertEqual(db.validate_slug("ordering-platform"), "ordering-platform")
        for bad in ["Ordering", "a", "1abc", "a_b", "a" * 41, "x;drop", "-ab", "", "ab\n"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                db.validate_slug(bad)

    def test_table_names(self):
        self.assertEqual(db.table("ordering-platform", "risks"), "ordering_platform__risks")
        with self.assertRaises(ValueError):
            db.table("ordering-platform", "systems")
        with self.assertRaises(ValueError):
            db.table("Bad Slug", "risks")


class SystemTablesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conn = db.connect(Path(self._tmp.name) / "r.db")
        self.addCleanup(self.conn.close)
        db.create_system(self.conn, "alpha", "Alpha")

    def test_tables_triggers_and_meta(self):
        names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master")}
        for t in ["risks", "changes", "dfd_approvals", "runs", "sequences"]:
            self.assertIn(f"alpha__{t}", names)
        for trig in db.trigger_names("alpha"):
            self.assertIn(trig, names)
        self.assertEqual(
            self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "1")

    def test_sequences_seeded(self):
        rows = {r["prefix"]: r["next"] for r in self.conn.execute("SELECT * FROM alpha__sequences")}
        self.assertEqual(rows, {"T": 1, "PT": 1, "DFD": 1})
        self.assertTrue(db.system_exists(self.conn, "alpha"))
        self.assertFalse(db.system_exists(self.conn, "beta"))

    def test_now_format(self):
        self.assertRegex(db.now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_create_twice_refused(self):
        with self.assertRaises(ValueError):
            db.create_system(self.conn, "alpha", "Alpha")

    def test_risk_rows_cannot_be_deleted(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "x"}, op="add", actor="ai:r1")
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM alpha__risks")

    def test_changes_and_dfd_approvals_are_append_only(self):
        ledger.write_row(self.conn, "alpha", "dfd_approvals", "DFD-1", {"version": "1.0"},
                         op="dfd-approve", actor="human:R")
        for sql in ["UPDATE alpha__changes SET note='x'", "DELETE FROM alpha__changes",
                    "UPDATE alpha__dfd_approvals SET version='2'", "DELETE FROM alpha__dfd_approvals"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                self.conn.execute(sql)


if __name__ == "__main__":
    unittest.main()
