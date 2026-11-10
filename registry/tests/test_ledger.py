import tempfile
import unittest
from pathlib import Path

from tmreg import db, ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conn = db.connect(Path(self._tmp.name) / "r.db")
        self.addCleanup(self.conn.close)
        db.create_system(self.conn, "alpha", "Alpha")
        db.create_system(self.conn, "beta", "Beta")

    def _two_writes(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "A", "owner": "x"},
                         op="add", actor="ai:r1")
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"owner": "y", "title": "A"},
                         op="edit", actor="human:R")

    def test_insert_then_update_logs_only_changed_fields(self):
        self._two_writes()
        ch = ledger.changes(self.conn, "alpha", "T-01")
        self.assertEqual(ch[0]["diff"]["title"], [None, "A"])
        self.assertEqual(ch[1]["diff"], {"owner": ["x", "y"]})

    def test_no_change_raises(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "A"}, op="add", actor="ai:r1")
        with self.assertRaisesRegex(ValueError, "no changes"):
            ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "A"}, op="edit", actor="ai:r1")
        self.assertEqual(len(ledger.changes(self.conn, "alpha")), 1)

    def test_unknown_field_and_table_rejected(self):
        with self.assertRaises(ValueError):
            ledger.write_row(self.conn, "alpha", "risks", "T-01", {"nope": "A"}, op="add", actor="a")
        with self.assertRaises(ValueError):
            ledger.write_row(self.conn, "alpha", "changes", "1", {"note": "A"}, op="add", actor="a")
        self.assertEqual(ledger.changes(self.conn, "alpha"), [])

    def test_chain_links_and_hashes(self):
        self._two_writes()
        ch = ledger.changes(self.conn, "alpha")
        self.assertEqual(ch[0]["prev_hash"], ledger.GENESIS)
        self.assertEqual(ch[1]["prev_hash"], ch[0]["hash"])
        rec = {k: ch[1][k] for k in ("seq", "at", "op", "tbl", "row_key", "actor", "diff", "note")}
        self.assertEqual(ch[1]["hash"], ledger.content_hash(ch[1]["prev_hash"], rec))
        self.assertEqual(ledger.verify_chain(self.conn, "alpha"), [])

    def test_json_fields_round_trip(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"elements": ["C2", "R2"]},
                         op="add", actor="ai:r1")
        self.assertEqual(ledger.read_rows(self.conn, "alpha", "risks")["T-01"]["elements"], ["C2", "R2"])

    def test_dfd_approval_ids_dict_round_trip(self):
        ids = {"P": ["P1"], "F": ["F1"]}
        ledger.write_row(self.conn, "alpha", "dfd_approvals", "DFD-1", {"version": "1", "ids": ids},
                         op="dfd-approve", actor="human:R")
        row = ledger.read_rows(self.conn, "alpha", "dfd_approvals")["DFD-1"]
        self.assertEqual(row["ids"], ids)
        self.assertEqual(ledger.replay(self.conn, "alpha")[("dfd_approvals", "DFD-1")], row)

    def test_runs_keyed_by_run_id(self):
        ledger.write_row(self.conn, "alpha", "runs", "r1", {"actor": "ai:r1"}, op="run", actor="ai:r1")
        self.assertEqual(ledger.read_rows(self.conn, "alpha", "runs")["r1"]["run_id"], "r1")

    def test_replay_matches_tables(self):
        self._two_writes()
        self.assertEqual(ledger.replay(self.conn, "alpha")[("risks", "T-01")],
                         ledger.read_rows(self.conn, "alpha", "risks")["T-01"])

    def test_systems_are_isolated(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "A"}, op="add", actor="ai:r1")
        self.assertEqual(ledger.changes(self.conn, "beta"), [])
        self.assertEqual(ledger.replay(self.conn, "beta"), {})
        self.assertEqual(ledger.read_rows(self.conn, "beta", "risks"), {})

    def test_verify_chain_names_an_edited_change(self):
        ledger.write_row(self.conn, "alpha", "risks", "T-01", {"title": "A"}, op="add", actor="ai:r1")
        self.conn.execute("DROP TRIGGER alpha__changes_no_update")
        self.conn.execute("UPDATE alpha__changes SET note='forged' WHERE seq=1")
        self.assertIn("change #1", " ".join(ledger.verify_chain(self.conn, "alpha")))

    def test_verify_chain_names_a_broken_link(self):
        self._two_writes()
        self.conn.execute("DROP TRIGGER alpha__changes_no_update")
        self.conn.execute("UPDATE alpha__changes SET prev_hash=? WHERE seq=2", ("f" * 64,))
        self.assertIn("change #2", " ".join(ledger.verify_chain(self.conn, "alpha")))


if __name__ == "__main__":
    unittest.main()
