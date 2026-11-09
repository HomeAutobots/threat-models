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
        for t in ["risks", "changes", "dfd_approvals", "model_approvals", "runs", "sequences"]:
            self.assertIn(f"alpha__{t}", names)
        for trig in db.trigger_names("alpha"):
            self.assertIn(trig, names)
        self.assertEqual(
            self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "2")

    def test_sequences_seeded(self):
        rows = {r["prefix"]: r["next"] for r in self.conn.execute("SELECT * FROM alpha__sequences")}
        self.assertEqual(rows, {"T": 1, "PT": 1, "DFD": 1, "MODEL": 1})
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

    def test_model_approvals_are_append_only(self):
        ledger.write_row(self.conn, "alpha", "model_approvals", "MODEL-1", {"version": "1.0"},
                         op="model-approve", actor="human:R")
        for sql in ["UPDATE alpha__model_approvals SET version='2'",
                    "DELETE FROM alpha__model_approvals"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError) as cm:
                self.conn.execute(sql)
            self.assertIn("append-only", str(cm.exception))


class UpgradeTest(unittest.TestCase):
    def _v1(self, path):
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.executescript((Path(db.__file__).parent / "schema.sql").read_text())
        conn.executescript((Path(__file__).parent / "fixtures" / "system_v1.sql")
                           .read_text().replace("{p}", "demo"))
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        conn.execute("INSERT INTO systems (slug, name, created_at) VALUES ('demo', 'Demo', ?)",
                     (db.now(),))
        conn.executemany("INSERT INTO demo__sequences (prefix, next) VALUES (?, 1)",
                         [("T",), ("PT",), ("DFD",)])
        conn.execute("UPDATE demo__sequences SET next = 2 WHERE prefix = 'T'")
        conn.commit()
        ledger.write_row(conn, "demo", "risks", "T-01", {"title": "A v1 risk"}, op="add", actor="ai:r1")
        conn.commit()
        return conn

    def test_upgrade_adds_model_tables_to_a_v1_database(self):
        from tmreg.core import Registry
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.db"
            self._v1(path).close()
            conn = db.connect(path)
            self.addCleanup(conn.close)
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
            self.assertIn("demo__model_approvals", names)
            self.assertIn("demo__model_approvals_no_update", names)
            self.assertIn("demo__model_approvals_no_delete", names)
            for t in ("risks", "runs"):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info(demo__{t})")]
                self.assertIn("model_approval_id", cols)
            self.assertEqual(conn.execute(
                "SELECT next FROM demo__sequences WHERE prefix='MODEL'").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], "2")
            row = conn.execute("SELECT * FROM demo__risks WHERE id='T-01'").fetchone()
            self.assertEqual((row["title"], row["model_approval_id"]), ("A v1 risk", None))
            reg = Registry.__new__(Registry)
            reg.conn = conn
            reg.root = Path(tmp)
            reg._require = lambda slug: None
            self.assertEqual(reg.verify("demo"), [])

    def test_upgrade_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.db"
            self._v1(path).close()
            db.connect(path).close()
            conn = db.connect(path)
            self.addCleanup(conn.close)
            db.upgrade(conn)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM demo__sequences WHERE prefix='MODEL'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
