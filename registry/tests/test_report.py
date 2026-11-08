import csv
import io
import re
from unittest import mock

from helpers import TmpTestCase, ai_fields, make_registry, session, start
from tmreg import report
from tmreg.core import RegistryError

NOTE = "Confirmed on F2 against the design doc."


class ReportTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.run = start(self.reg)

    def add(self, **kw):
        return self.reg.add_risk("demo", ai_fields(**kw), run_id=self.run)["id"]

    def approved(self, **kw):
        rid = self.add(**kw)
        self.reg.approve(session(), "demo", rid, NOTE)
        return rid

    def mixed(self):
        t1 = self.approved()
        t2 = self.add(title="Pending one")
        t3 = self.add(title="Rejected one")
        self.reg.reject(session(), "demo", t3, NOTE)
        t4 = self.approved(title="Retired one")
        self.reg.retire(session(), "demo", t4, "No longer part of the system design.")
        return t1, t2, t3, t4

    def test_default_report_is_approved_only(self):
        self.mixed()
        md = self.reg.report("demo")
        self.assertIn("| T-01 |", md)
        for rid in ["T-02", "T-03", "T-04"]:
            self.assertNotIn(f"| {rid} |", md)
        self.assertIn("Approved risks only.", md)

    def test_re_review_shows_last_approved_version(self):
        self.approved(owner=None)
        self.reg.edit_risk("demo", "T-01", {"owner": "Mallory"}, run_id=self.run)
        md = self.reg.report("demo")
        self.assertIn("(re-review pending)", md)
        self.assertNotIn("Mallory", md)
        both = self.reg.report("demo", include_pending=True)
        self.assertIn("Mallory", both)
        self.assertIn("(PENDING)", both)
        self.assertEqual(both.count("### T-01"), 2)
        self.assertLess(both.index("### T-01: P2 trusts client-supplied forwarded headers (re-review"),
                        both.index("headers (PENDING)"))

    def test_header_and_markers(self):
        self.mixed()
        md = self.reg.report("demo", include_pending=True, include_rejected=True,
                             include_retired=True)
        self.assertIn("| " + " | ".join(l for l, _ in report.REGISTER_COLUMNS) + " |", md)
        for m in ["(PENDING)", "(REJECTED)", "(RETIRED)"]:
            self.assertIn(m, md)

    def test_cells_escape_pipes_and_newlines(self):
        self.approved()
        self.reg.edit_risk("demo", "T-01", {"recommended_controls": "1. a | b\n2. c"},
                           run_id=self.run)
        md = self.reg.report("demo", include_pending=True)
        row = next(l for l in md.splitlines() if l.startswith("| T-01 |") and "PENDING" in l)
        self.assertIn("1. a \\| b<br>2. c", row)
        self.assertEqual(len(re.split(r"(?<!\\)\|", row)), len(report.REGISTER_COLUMNS) + 2)
        self.assertIn("1. a \\| b<br>2. c", md.split("## Risk detail")[1])

    def test_csv(self):
        self.approved()
        out = self.reg.report("demo", "csv")
        rows = list(csv.reader(io.StringIO(out)))
        self.assertEqual(rows[0], report.CSV_HEADER)
        self.assertEqual(rows[1][1], "P2;F2")

    def test_csv_marks_re_review_and_pending(self):
        self.approved()
        self.reg.edit_risk("demo", "T-01", {"owner": "Mallory"}, run_id=self.run)
        default = list(csv.reader(io.StringIO(self.reg.report("demo", "csv"))))
        self.assertEqual(len(default), 2)
        self.assertTrue(default[1][15].endswith("(re-review pending)"))
        both = list(csv.reader(io.StringIO(self.reg.report("demo", "csv", include_pending=True))))
        t01 = [r for r in both[1:] if r[0] == "T-01"]
        self.assertEqual(len(t01), 2)
        self.assertTrue(t01[0][15].endswith("(re-review pending)"))
        self.assertTrue(t01[1][15].endswith("(PENDING)"))

    def test_html_escapes(self):
        self.approved()
        self.reg.edit_risk("demo", "T-01", {"notes": "<script>x</script>"}, run_id=self.run)
        self.reg.approve(session(), "demo", "T-01", NOTE)
        out = self.reg.report("demo", "html")
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>x", out)
        self.assertIn("prefers-color-scheme", out)

    def test_unknown_format(self):
        with self.assertRaises(RegistryError):
            self.reg.report("demo", "pdf")

    def test_register_md_regenerated_and_deterministic(self):
        self.add()
        path = self.reg.root / "systems/demo/register.md"
        before = path.read_text()
        self.assertIn("change #", before)
        self.reg.approve(session(), "demo", "T-01", NOTE)
        after = path.read_text()
        self.assertNotEqual(before, after)
        self.assertIn("| T-01 |", after)
        self.assertEqual(self.reg.report("demo"), after)

    def test_start_run_does_not_write_register(self):
        path = self.reg.root / "systems/demo/register.md"
        before = path.read_text()
        path.write_text("sentinel")
        start(self.reg)
        self.assertEqual(path.read_text(), "sentinel")
        path.write_text(before)

    def test_trial_never_touches_register_md(self):
        self.approved()
        real = self.reg.root / "systems/demo/register.md"
        snapshot = real.read_bytes()
        trial = make_registry(self.tmp, root=self.reg.root, trial=True)
        t_run = start(trial)
        self.assertTrue(t_run.startswith("trial-"))
        trial.add_risk("demo", ai_fields(), run_id=t_run)
        self.assertEqual(real.read_bytes(), snapshot)
        self.assertTrue((self.reg.root / "systems/demo/register.trial.md").exists())

    def test_unexpected_render_error_is_wrapped(self):
        with mock.patch("tmreg.core.report_mod.render_md", side_effect=KeyError("boom")):
            with self.assertRaises(RegistryError) as cm:
                self.add()
        self.assertIsInstance(cm.exception.__cause__, KeyError)

    def test_register_write_leaves_no_temp_file(self):
        self.add()
        names = [p.name for p in (self.reg.root / "systems/demo").iterdir()]
        self.assertIn("register.md", names)
        self.assertFalse([n for n in names if n.endswith(".tmp")])

    def test_failed_render_write_raises_after_commit(self):
        with mock.patch("tmreg.core.Path.write_text", side_effect=OSError("disk full")):
            with self.assertRaises(RegistryError) as cm:
                self.add()
        self.assertIn("./tmreg report demo", str(cm.exception))
        self.assertIn("T-01 was written", str(cm.exception))
        self.assertEqual(len(self.reg.list_risks("demo")), 1)

    def test_imported_rows_flag_incomplete_detail(self):
        (self.tmp / "legacy").mkdir()
        reg = make_registry(self.tmp / "legacy", legacy=True)
        reg.import_legacy(session(), "demo")
        md = reg.report("demo", include_pending=True)
        self.assertIn("> Detail incomplete: imported from the reference catalog as a one-liner.", md)

    def test_summary_marks_incomplete_rows_and_detail_says_yes_or_no(self):  # M2
        self.approved()
        md = self.reg.report("demo")
        cells = re.split(r"(?<!\\)\|", next(l for l in md.splitlines() if l.startswith("| T-01 |")))
        self.assertEqual(cells[4].strip(), "P2 trusts client-supplied forwarded headers")
        self.assertIn("| Detail complete | yes |", md)
        (self.tmp / "legacy").mkdir()
        reg = make_registry(self.tmp / "legacy", legacy=True)
        reg.import_legacy(session(), "demo")
        md = reg.report("demo")
        cells = re.split(r"(?<!\\)\|", next(l for l in md.splitlines() if l.startswith("| T-01 |")))
        self.assertTrue(cells[4].strip().endswith(" (detail incomplete)"), cells[4])
        self.assertIn("| Detail complete | no |", md)
        self.assertNotIn("| Detail complete | 0 |", md)
        self.assertIn(" (detail incomplete)</td>", reg.report("demo", "html"))

    def test_drafted_by_names_later_editors(self):  # I2
        (self.tmp / "legacy").mkdir()
        reg = make_registry(self.tmp / "legacy", legacy=True, trial=True)
        reg.import_legacy(session(), "demo")
        run = start(reg)
        reg.edit_risk("demo", "T-01", {"notes": "Detail added by the model."}, run_id=run)
        reg.approve(session(), "demo", "T-01", NOTE)
        want = f"human:catalog-import; edited by ai:{run}"
        md = reg.report("demo")
        self.assertIn(f"| {want} |", next(l for l in md.splitlines() if l.startswith("| T-01 |")))
        self.assertIn("| human:catalog-import |", next(l for l in md.splitlines() if l.startswith("| T-02 |")))
        self.assertIn(f"| Drafted by | {want} |", md.split("### T-01")[1])
        rows = list(csv.reader(io.StringIO(reg.report("demo", "csv"))))
        col = report.CSV_HEADER.index("drafted_by")
        self.assertEqual((rows[1][0], rows[1][col]), ("T-01", want))
        self.assertIn(f"<td>{want}</td>", reg.report("demo", "html"))

    def test_drafted_by_unchanged_when_only_the_drafter_edited(self):  # I2
        rid = self.approved()
        self.reg.edit_risk("demo", rid, {"notes": "Same run, more detail."}, run_id=self.run)
        self.reg.approve(session(), "demo", rid, NOTE)
        row = next(l for l in self.reg.report("demo").splitlines() if l.startswith("| T-01 |"))
        self.assertIn(f"| ai:{self.run} |", row)
        self.assertNotIn("edited by", row)


class PureTest(TmpTestCase):
    def test_cell(self):
        self.assertEqual(report.cell(None), "")
        self.assertEqual(report.cell(["a", "b"]), "a; b")
        self.assertEqual(report.cell("a|b\r\nc\nd\re"), "a\\|b<br>c<br>d<br>e")

    def test_csv_neutralizes_formula_cells(self):  # M4
        risk = {"id": "T-01", "title": '=HYPERLINK("http://x")', "notes": "+1", "owner": "-x",
                "test": "@SUM(A1)", "ticket": "\tq", "evidence": "\rz", "assumptions": "safe = fine",
                "review_state": "approved", "status": "open", "updated_at": "2026-11-07T00:00:00Z",
                "drafted_by": "ai:r"}
        rows = list(csv.reader(io.StringIO(report.render_csv([report.ReportRow(risk, "")]))))
        self.assertEqual(rows[0], report.CSV_HEADER)
        got = dict(zip(rows[0], rows[1]))
        self.assertEqual([got[c] for c in ("threat", "notes", "owner", "test_ref", "ticket", "evidence")],
                         ["'=HYPERLINK(\"http://x\")", "'+1", "'-x", "'@SUM(A1)", "'\tq", "'\rz"])
        self.assertEqual((got["id"], got["assumptions"], got["elements"]), ("T-01", "safe = fine", ""))

    def test_cell_escapes_angle_brackets(self):  # I3
        self.assertEqual(report.cell("<b>bold</b>"), "&lt;b&gt;bold&lt;/b&gt;")
        self.assertEqual(report.cell("a<b\nc"), "a&lt;b<br>c")
