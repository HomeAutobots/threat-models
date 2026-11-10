"""The owner's real path, end to end: a DFD-era register on disk (schema version 1), opened by this
code (the v2 upgrade), adopted by its first C4 model approval (spec section 7.6), then C4-era work.
verify is clean at every step."""
import hashlib
import sqlite3
from pathlib import Path

from helpers import (FIXTURES, SAMPLE_DFD, SAMPLE_DFD_IDS, SAMPLE_WORKSPACE, TmpTestCase,
                     ai_fields, approve_model, make_project, session, start, write_model)
from tmreg import db, ledger
from tmreg.core import Registry
from tmreg.model import SNAPSHOT_FIELDS

REVIEWER, RUN = "Test Reviewer", "20261101-01"
HUMAN, AI = f"human:{REVIEWER}", f"ai:{RUN}"
NOTE = "Checked against the model checklist."
# What a v1 snapshot held: the field had no model_approval_id yet.
V1_SNAPSHOT_FIELDS = tuple(f for f in SNAPSHOT_FIELDS if f != "model_approval_id")


def _write(conn, key, fields, op, actor, note=""):
    ledger.write_row(conn, "demo", "risks", key, fields, op=op, actor=actor, note=note)


def build_v1(root: Path) -> None:
    """registry/registry.db as the DFD-era code left it: schema version 1, and system demo with
    the v1 tables, DFD-1, a run, and risks written through the ledger the way add, approve, edit,
    reject, merge and retire wrote them."""
    path = root / "registry" / "registry.db"
    path.parent.mkdir(parents=True)
    sysdir = root / "systems" / "demo"
    sysdir.mkdir(parents=True)
    (sysdir / "system.toml").write_text('name = "Demo"\n')
    (sysdir / "dfd.md").write_bytes(SAMPLE_DFD)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript((Path(db.__file__).parent / "schema.sql").read_text())
        conn.executescript((FIXTURES / "system_v1.sql").read_text().replace("{p}", "demo"))
        at = db.now()
        with conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
            conn.execute("INSERT INTO systems (slug, name, created_at) VALUES ('demo', 'Demo', ?)",
                         (at,))
            conn.executemany("INSERT INTO demo__sequences (prefix, next) VALUES (?, ?)",
                             [("T", 7), ("PT", 1), ("DFD", 2)])
            ledger.write_row(conn, "demo", "dfd_approvals", "DFD-1", {
                "version": "1.0", "sha256": hashlib.sha256(SAMPLE_DFD).hexdigest(),
                "ids": SAMPLE_DFD_IDS, "approved_by": REVIEWER, "approved_at": at,
                "note": "Checked against the DFD checklist."}, op="dfd-approve", actor=HUMAN)
            ledger.write_row(conn, "demo", "runs", RUN, {
                "started_at": at, "framework_commit": "0" * 40, "dfd_approval_id": "DFD-1",
                "methods": "stride-per-element", "actor": AI}, op="run-start", actor="tmreg")
            review = {"reviewed_by": REVIEWER, "reviewed_at": at, "review_note": NOTE}
            for rid, elements, title in (
                    ("T-01", ["P2", "F2"], "C2 trusts forwarded headers on F2"),
                    ("T-02", ["E1", "F1"], "A1 session fixation on F1"),
                    ("T-03", ["D1"], "D1 backups are readable"),
                    ("T-04", ["F3"], "F3 queries are not parameterized"),
                    ("T-05", ["TB1"], "TB1 lets admin routes through"),
                    ("T-06", ["P2", "F2"], "A duplicate of T-01")):
                _write(conn, rid, {**ai_fields(elements=elements, title=title), "status": "open",
                                   "review_state": "pending", "drafted_by": AI,
                                   "dfd_approval_id": "DFD-1", "detail_complete": 1,
                                   "created_at": at, "updated_at": at}, "add", AI)
            for rid in ("T-01", "T-03", "T-05"):
                _write(conn, rid, {"review_state": "approved", **review}, "approve", HUMAN)
            # T-01: a v1 re-review (its snapshot has no model_approval_id), approved again.
            cur = dict(conn.execute("SELECT * FROM demo__risks WHERE id = 'T-01'").fetchone())
            cur["elements"] = ["P2", "F2"]
            _write(conn, "T-01", {"notes": "The AI added a note.", "review_state": "pending",
                                  "last_approved": {f: cur[f] for f in V1_SNAPSHOT_FIELDS},
                                  "reviewed_by": None, "reviewed_at": None, "review_note": None,
                                  "updated_at": at}, "edit", AI)
            _write(conn, "T-01", {"review_state": "approved", "last_approved": None, **review},
                   "approve", HUMAN)
            _write(conn, "T-03", {"status": "retired", "status_reason": "D1 was decommissioned.",
                                  "updated_at": at}, "retire", HUMAN)
            _write(conn, "T-04", {"review_state": "rejected", **review}, "reject", HUMAN)
            _write(conn, "T-06", {"review_state": "rejected", "merged_into": "T-01", **review},
                   "merge", HUMAN)
    finally:
        conn.close()


class UpgradeThenAdoptTest(TmpTestCase):
    def open(self) -> Registry:
        reg = Registry(self.root)
        self.addCleanup(reg.close)
        return reg

    def test_upgrade_then_adoption_then_c4_work(self):
        self.root = make_project(self.tmp)
        build_v1(self.root)

        # ---- the first open runs the v2 upgrade
        reg = self.open()
        version = reg.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
        self.assertEqual(version.fetchone()[0], "2")
        self.assertEqual(reg.verify("demo"), [])
        before = {r["id"]: r for r in reg.list_risks("demo")}
        self.assertEqual({r["model_approval_id"] for r in before.values()}, {None})
        self.assertEqual(reg.c4_status("demo").state, "none")
        logs = {rid: len(reg.history("demo", rid)) for rid in before}

        # ---- the first model approval adopts the live risks through tm.was
        write_model(reg, "demo", SAMPLE_WORKSPACE)
        adoption = reg.c4_preview("demo")["adoption"]
        self.assertEqual((adoption["gaps"], adoption["pending_rereviews"]), ([], []))
        self.assertEqual(adoption["rewrites"], {
            "T-01": {"from": ["P2", "F2"], "to": ["C2", "R2"]},
            "T-02": {"from": ["E1", "F1"], "to": ["A1", "R1"]},
            "T-05": {"from": ["TB1"], "to": ["TB1"]}})
        self.assertEqual(approve_model(reg, "demo", "Adopting the C4 model, checked.")["id"],
                         "MODEL-1")
        risks = {r["id"]: r for r in reg.list_risks("demo")}
        for rid, elements, state, notes in (
                ("T-01", ["C2", "R2"], "approved", "P2→C2, F2→R2"),
                ("T-02", ["A1", "R1"], "pending", "E1→A1, F1→R1"),
                ("T-05", ["TB1"], "approved", "TB1→TB1")):
            with self.subTest(rid):
                r = risks[rid]
                self.assertEqual((r["elements"], r["review_state"], r["model_approval_id"],
                                  r["dfd_approval_id"]), (elements, state, "MODEL-1", "DFD-1"))
                self.assertEqual(r["reviewed_by"], before[rid]["reviewed_by"])  # approvals kept
                last = reg.history("demo", rid)
                self.assertEqual(len(last), logs[rid] + 1)  # one adoption edit
                self.assertEqual((last[-1]["op"], last[-1]["actor"], last[-1]["note"]),
                                 ("edit", HUMAN, f"Adopted the C4 model MODEL-1: {notes}"))
        for rid in ("T-03", "T-04", "T-06"):  # retired, rejected, merged: untouched
            with self.subTest(rid):
                self.assertEqual(risks[rid], before[rid])
                self.assertEqual(len(reg.history("demo", rid)), logs[rid])
        self.assertEqual(reg.verify("demo"), [])

        # ---- C4-era work: an AI edit, a reject of it, and a second model that moves on
        run = start(reg)
        self.assertEqual(reg.runs("demo")[-1]["model_approval_id"], "MODEL-1")
        reg.edit_risk("demo", "T-01", {"notes": "The AI rewords it after adoption."}, run_id=run)
        t1 = reg.get_risk("demo", "T-01")
        self.assertEqual((t1["review_state"], t1["last_approved"]["model_approval_id"]),
                         ("pending", "MODEL-1"))
        reg.reject(session(), "demo", "T-01", "Keeping the approved wording here.")
        t1 = reg.get_risk("demo", "T-01")
        self.assertEqual((t1["review_state"], t1["notes"], t1["model_approval_id"],
                          t1["last_approved"]), ("approved", "The AI added a note.", "MODEL-1", None))
        new = reg.add_risk("demo", ai_fields(), run_id=run)
        self.assertEqual((new["model_approval_id"], new["review_state"]), ("MODEL-1", "pending"))
        text = SAMPLE_WORKSPACE.decode()
        old = '"C2 API" "Answers the web app."'
        self.assertEqual(text.count(old), 1)
        write_model(reg, "demo", text.replace(old, '"C2 API" "Answers the web app and signs '
                                                   'its requests."').encode())
        self.assertEqual(approve_model(reg, "demo", "Second model: C2 signs requests.")["id"],
                         "MODEL-2")
        moved = reg.moved_on("demo", reg.get_risk("demo", "T-01"))
        self.assertEqual((moved["moved_on"], moved["written_against"], moved["latest"],
                          moved["changed"]), (True, "MODEL-1", "MODEL-2", ["C2"]))
        self.assertFalse(reg.moved_on("demo", reg.get_risk("demo", "T-05"))["moved_on"])
        self.assertEqual(reg.verify("demo"), [])
        reg.close()
        self.assertEqual(self.open().verify("demo"), [])  # and from a fresh open
