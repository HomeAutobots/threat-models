import contextlib
import io
import json
import os
import sqlite3
import unittest
from unittest import mock

from helpers import (TmpTestCase, ai_fields, human_terminal, make_registry, seed_dfd_era,
                     seed_dfd_risk, start, write_dfd)
from tmreg import cli, ledger, model, report

NOTE = "Checked against the DFD and the evidence."


class CliTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.root = self.reg.root

    def dfd_era(self):
        """Switch to a register from before the C4 model: SAMPLE_DFD in dfd.md, approved as DFD-1,
        and no model approval. The dfd commands stay until Task 9 replaces them."""
        self.reg = make_registry(self.tmp / "dfd", approve=False)
        self.root = self.reg.root
        write_dfd(self.reg, "demo")
        seed_dfd_era(self.reg, "demo")

    def run_cli(self, *argv, tty=False, inputs=(), env=None):
        """env: variables to set for this call only, after CLAUDECODE has been dropped."""
        out, err = io.StringIO(), io.StringIO()
        with human_terminal(tty), \
                mock.patch("builtins.input", side_effect=list(inputs)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            os.environ.update(env or {})
            code = cli.main(list(argv), project_root=self.root)
        return code, out.getvalue(), err.getvalue()

    def ai_add(self):
        code, out, _ = self.run_cli("run", "start", "demo")
        run = out.split()[0]
        p = self.root / "systems/demo/runs" / run / "candidates/01.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(ai_fields()))
        return run, self.run_cli("add", "demo", "--run", run, "--json", str(p))

    def test_human_only_commands_refuse_without_terminal(self):
        self.ai_add()
        before = len(self.reg.history("demo"))
        for argv in [("review", "demo"), ("approve", "demo", "T-01"), ("reject", "demo", "T-01"),
                     ("merge", "demo", "T-01", "--into", "T-01"),
                     ("retire", "demo", "T-01", "--reason", "x" * 25),
                     ("import-legacy", "demo"), ("dfd", "approve", "demo")]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("interactive terminal", err)
                self.assertEqual(out, "")
        self.assertEqual(len(self.reg.history("demo")), before)

    def test_human_only_refused_in_a_claude_code_shell_even_with_a_terminal(self):  # I6
        self.ai_add()
        before = len(self.reg.history("demo"))
        for argv in [("approve", "demo", "T-01"), ("review", "demo"), ("dfd", "approve", "demo")]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv, tty=True, inputs=[NOTE, "T-01"],
                                              env={"CLAUDECODE": "1"})
                self.assertEqual((code, out), (1, ""))
                self.assertIn("(this shell was started by Claude Code)", err)
        self.assertEqual(len(self.reg.history("demo")), before)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "pending")

    def test_add_with_run_prints_id_and_without_run_is_refused(self):
        run, (code, out, _) = self.ai_add()
        self.assertEqual((code, out.split()[:2]), (0, ["T-01", "pending"]))
        p = self.root / "c.json"
        p.write_text(json.dumps(ai_fields()))
        code, _, err = self.run_cli("add", "demo", "--json", str(p))
        self.assertEqual(code, 1)
        self.assertIn("--run", err)

    def test_approve_flow_and_confirm_mismatch(self):
        self.ai_add()
        code, out, _ = self.run_cli("approve", "demo", "T-01", tty=True, inputs=[NOTE, "T-99"])
        self.assertEqual(code, 1)
        self.assertIn("Not changed.", out)
        self.assertIn(ai_fields()["description"], out)
        code, _, _ = self.run_cli("approve", "demo", "T-01", tty=True,
                                  inputs=["too short", NOTE, "T-01"])
        self.assertEqual(code, 0)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "approved")

    def test_empty_note_aborts(self):
        self.ai_add()
        code, out, _ = self.run_cli("approve", "demo", "T-01", tty=True, inputs=[""])
        self.assertEqual(code, 1)
        self.assertIn("Not changed.", out)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "pending")

    def test_review_loop(self):
        self.ai_add()
        self.ai_add()
        code, out, _ = self.run_cli("review", "demo", tty=True, inputs=["a", NOTE, "T-01", "s"])
        self.assertIn("1 reviewed, 1 skipped, 1 still pending", out)

    def test_edit_set_as_human(self):
        self.ai_add()
        self.run_cli("edit", "demo", "T-01", "--set", "status=planned", "--set",
                     "control_refs=ADR-07; BR-AUTHN-01", tty=True)
        r = self.reg.get_risk("demo", "T-01")
        self.assertEqual((r["status"], r["control_refs"]), ("planned", ["ADR-07", "BR-AUTHN-01"]))

    def test_re_review_shows_diff(self):
        self.ai_add()
        self.run_cli("approve", "demo", "T-01", tty=True, inputs=[NOTE, "T-01"])
        self.reg.edit_risk("demo", "T-01", {"status": "planned"}, run_id=start(self.reg))
        code, out, _ = self.run_cli("show", "demo", "T-01")
        self.assertIn("Status:\n  - open\n  + planned", out)

    def test_interactive_add_offers_approval(self):
        p = self.root / "h.json"
        p.write_text(json.dumps({k: ai_fields()[k] for k in model.HUMAN_REQUIRED}))
        code, out, _ = self.run_cli("add", "demo", "--json", str(p), tty=True,
                                    inputs=["a", NOTE, "T-01"])
        self.assertEqual(code, 0)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "approved")

    def test_show_and_review_name_editors_since_last_approval(self):  # I2
        p = self.root / "h.json"
        p.write_text(json.dumps({k: ai_fields()[k] for k in model.HUMAN_REQUIRED}))
        self.run_cli("add", "demo", "--json", str(p), tty=True, inputs=["s"])  # skip: stays pending
        self.assertEqual(self.reg.get_risk("demo", "T-01")["drafted_by"], "human:Test Reviewer")
        self.assertNotIn("Edited by", self.run_cli("show", "demo", "T-01")[1])
        run = self.run_cli("run", "start", "demo")[1].split()[0]
        e = self.root / "systems/demo/runs" / run / "candidates/edit-T-01.json"
        e.parent.mkdir(parents=True)
        e.write_text(json.dumps({"notes": "Added by the model."}))
        self.assertEqual(self.run_cli("edit", "demo", "T-01", "--run", run, "--json", str(e))[0], 0)
        line = f"Edited by (since last approval): ai:{run}"
        self.assertIn(line, self.run_cli("show", "demo", "T-01")[1])
        self.assertIn(line, self.run_cli("review", "demo", tty=True, inputs=["q"])[1])
        self.run_cli("approve", "demo", "T-01", tty=True, inputs=[NOTE, "T-01"])
        self.assertNotIn("Edited by", self.run_cli("show", "demo", "T-01")[1])

    def test_show_and_list_escape_control_characters_already_stored(self):  # I3
        self.ai_add()
        with self.reg.conn:  # a row written before the check existed, or out of band
            ledger.write_row(self.reg.conn, "demo", "risks", "T-01",
                             {"notes": "ok\u001b[8mhidden\u001b[0m\u200b", "title": "T\u001b[2Kx"},
                             op="test", actor="human:test")
        code, out, _ = self.run_cli("show", "demo", "T-01")
        self.assertEqual(code, 0)
        self.assertNotIn("\u001b", out)
        self.assertIn("Notes: ok\\x1b[8mhidden\\x1b[0m\\u200b\n", out)
        self.assertIn("Title: T\\x1b[2Kx\n", out)
        out = self.run_cli("list", "demo")[1]
        self.assertNotIn("\u001b", out)
        self.assertIn("T\\x1b[2Kx", out)

    def test_review_redisplays_fresh_record_after_stale_refusal(self):
        run, _ = self.ai_add()
        state = {"edited": False, "answers": iter(["a", "a"])}

        def hook(prompt):
            if prompt.startswith("[a]pprove"):
                return next(state["answers"], "q")
            if prompt.startswith("Review note"):
                if not state["edited"]:
                    state["edited"] = True
                    self.reg.edit_risk("demo", "T-01", {"notes": "edited-by-ai"}, run_id=run)
                return NOTE
            return "T-01"
        out, err = io.StringIO(), io.StringIO()
        with human_terminal(), \
                mock.patch("builtins.input", side_effect=hook), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main(["review", "demo"], project_root=self.root)
        text = out.getvalue()
        self.assertIn("T-01 changed since it was shown; showing the current version.", text)
        self.assertIn("edited-by-ai", text.split("showing the current version.")[1])
        self.assertIn("1 reviewed, 0 skipped, 0 still pending", text)
        r = self.reg.get_risk("demo", "T-01")
        self.assertEqual((r["review_state"], r["notes"]), ("approved", "edited-by-ai"))

    def test_review_approved_elsewhere_between_display_and_confirm(self):
        self.ai_add()
        state = {"done": False}

        def hook(prompt):
            if prompt.startswith("[a]pprove"):
                return "a"
            if prompt.startswith("Review note"):
                if not state["done"]:
                    state["done"] = True
                    from helpers import session
                    self.reg.approve(session(), "demo", "T-01", NOTE)
                return NOTE
            return "T-01"
        out = io.StringIO()
        with human_terminal(), \
                mock.patch("builtins.input", side_effect=hook), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["review", "demo"], project_root=self.root)
        self.assertIn("T-01 is no longer pending; skipped.", out.getvalue())
        self.assertIn("0 reviewed, 0 skipped, 0 still pending, 1 no longer pending", out.getvalue())

    def test_review_skips_item_approved_elsewhere(self):
        self.ai_add()
        self.ai_add()
        state = {"done": False}

        def hook(prompt):
            if not state["done"]:
                state["done"] = True
                from helpers import session
                self.reg.approve(session(), "demo", "T-02", NOTE)
            return "s" if prompt.startswith("[a]pprove") else ""
        out = io.StringIO()
        with human_terminal(), \
                mock.patch("builtins.input", side_effect=hook), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            cli.main(["review", "demo"], project_root=self.root)
        self.assertIn("T-02 is no longer pending; skipped.", out.getvalue())

    def test_merge_and_retire_prechecks_precede_prompts(self):
        self.ai_add()
        code, _, err = self.run_cli("merge", "demo", "T-01", "--into", "T-01", tty=True)
        self.assertEqual((code, "itself" in err), (1, True))
        self.run_cli("approve", "demo", "T-01", tty=True, inputs=[NOTE, "T-01"])
        self.run_cli("retire", "demo", "T-01", "--reason", NOTE, tty=True, inputs=["T-01"])
        code, _, err = self.run_cli("retire", "demo", "T-01", "--reason", NOTE, tty=True)
        self.assertEqual((code, "already retired" in err), (1, True))

    def test_reject_merge_retire_dfd_import(self):
        self.ai_add()
        self.ai_add()
        code, out, _ = self.run_cli("reject", "demo", "T-02", tty=True, inputs=[NOTE, "T-99"])
        self.assertEqual((code, self.reg.get_risk("demo", "T-02")["review_state"]), (1, "pending"))
        code, _, _ = self.run_cli("reject", "demo", "T-02", tty=True, inputs=[NOTE, "T-02"])
        self.assertEqual((code, self.reg.get_risk("demo", "T-02")["review_state"]), (0, "rejected"))
        self.ai_add()
        self.run_cli("approve", "demo", "T-01", tty=True, inputs=[NOTE, "T-01"])
        code, _, _ = self.run_cli("merge", "demo", "T-03", "--into", "T-01", tty=True,
                                  inputs=[NOTE, "T-01"])
        self.assertEqual(code, 1)  # mismatch: typed the target, not the pending ID
        code, _, _ = self.run_cli("merge", "demo", "T-03", "--into", "T-01", tty=True,
                                  inputs=[NOTE, "T-03"])
        self.assertEqual((code, self.reg.get_risk("demo", "T-03")["merged_into"]), (0, "T-01"))
        code, _, _ = self.run_cli("retire", "demo", "T-01", "--reason", NOTE, tty=True, inputs=["T-00"])
        self.assertEqual(code, 1)
        code, _, _ = self.run_cli("retire", "demo", "T-01", "--reason", NOTE, tty=True, inputs=["T-01"])
        self.assertEqual((code, self.reg.get_risk("demo", "T-01")["status"]), (0, "retired"))
        # dfd approve: an unchanged DFD is refused before the preview and the prompts
        write_dfd(self.reg, "demo")
        seed_dfd_era(self.reg, "demo")
        code, out, err = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("already approved", err)
        (self.root / "systems/demo/dfd.md").write_text(
            (self.root / "systems/demo/dfd.md").read_text() + "\nMore prose.\n")
        code, _, _ = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "wrong"])
        self.assertEqual(code, 1)
        code, _, _ = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual((code, self.reg.dfd_status("demo").state), (0, "current"))

    def test_dfd_approve_unchanged_is_refused_before_any_prompt(self):  # I1
        self.dfd_era()
        code, out, err = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[])
        self.assertEqual((code, out, err), (1, "", "tmreg: already approved as DFD-1\n"))

    def test_dfd_approve_refuses_dfd_changed_between_preview_and_confirm(self):  # I1
        self.dfd_era()
        path = self.root / "systems/demo/dfd.md"
        path.write_bytes(path.read_bytes() + b"\nThe version the owner reads.\n")

        def hook(prompt):
            if prompt.startswith("Type demo"):
                path.write_bytes(path.read_bytes() + b"\nSwapped in after the preview.\n")
                return "demo"
            return NOTE
        out, err = io.StringIO(), io.StringIO()
        with human_terminal(), mock.patch("builtins.input", side_effect=hook), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["dfd", "approve", "demo"], project_root=self.root)
        self.assertEqual(code, 1)
        self.assertIn("runs/<run-id>/dfd-check.md", out.getvalue())
        self.assertEqual(err.getvalue(), "tmreg: dfd.md changed since it was shown; review it again\n")
        self.assertEqual(self.reg.dfd_status("demo").latest["id"], "DFD-1")
        self.assertEqual([c["op"] for c in self.reg.history("demo")], ["dfd-approve"])

    def test_import_legacy_flow(self):
        reg = make_registry(self.tmp / "legacy", slug="demo", legacy=True)
        self.root = reg.root
        code, out, _ = self.run_cli("import-legacy", "demo", tty=True, inputs=["nope"])
        self.assertEqual(code, 1)
        self.assertIn("rows: 3", out)
        self.assertEqual(reg.list_risks("demo"), [])
        code, out, _ = self.run_cli("import-legacy", "demo", tty=True, inputs=["demo"])
        self.assertEqual((code, len(reg.list_risks("demo"))), (0, 3))

    def test_edit_without_run_or_terminal_is_refused(self):
        self.ai_add()
        code, out, err = self.run_cli("edit", "demo", "T-01", "--set", "status=planned")
        self.assertEqual(code, 1)
        self.assertIn("--run", err)

    def test_template_with_run_is_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["add", "demo", "--template", "--run", "x"], project_root=self.root)
        self.assertEqual(cm.exception.code, 2)

    def test_list_json_all_states(self):
        self.ai_add()
        code, out, _ = self.run_cli("list", "demo", "--state", "all", "--json")
        self.assertEqual(json.loads(out)[0]["review_state"], "pending")
        code, out, _ = self.run_cli("list", "demo")
        self.assertEqual(out.split()[:3], ["T-01", "pending", "open"])

    def test_trial_flag_uses_trial_db(self):
        self.run_cli("init-system", "demo2", "--name", "Demo 2", "--trial")
        self.assertTrue((self.root / "registry/trial.db").exists())
        code, _, err = self.run_cli("list", "demo2")
        self.assertEqual(code, 1)

    def test_report_csv_and_template_and_verify(self):
        code, out, _ = self.run_cli("report", "demo", "--format", "csv")
        self.assertEqual(out.splitlines()[0], ",".join(report.CSV_HEADER))
        code, out, _ = self.run_cli("add", "demo", "--template")
        self.assertEqual(list(json.loads(out)), list(model.EDITABLE_FIELDS))
        self.assertEqual(self.run_cli("verify", "demo")[0], 0)

    def test_run_start_dfd_status_runs_history(self):
        self.dfd_era()
        code, out, _ = self.run_cli("run", "start", "demo")
        lines = out.splitlines()
        self.assertEqual(len(lines[0].split()), 1)
        self.assertTrue(lines[1].startswith("methods: "))
        self.assertEqual(lines[2], "dfd: DFD-1 (current)")
        self.assertTrue(self.run_cli("dfd", "status", "demo")[1].startswith("state: current"))
        self.assertIn(lines[0], self.run_cli("runs", "demo")[1])
        self.assertEqual(self.run_cli("history", "demo")[0], 0)

    def test_run_start_on_a_catalog_mirror(self):  # I4
        self.assertNotIn("note:", self.run_cli("run", "start", "demo", "--trial")[1])  # no legacy_catalog
        reg = make_registry(self.tmp / "legacy", legacy=True)
        self.root = reg.root
        code, out, err = self.run_cli("run", "start", "demo")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("tmreg: demo mirrors the guide's catalog", err)
        make_registry(self.tmp / "legacy", root=reg.root, trial=True)
        code, out, _ = self.run_cli("run", "start", "demo", "--trial")
        lines = out.splitlines()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("trial-"))
        self.assertEqual(lines[3:], ["note: trial register is empty; the catalog is withheld "
                                     "(evaluation mode)"])

    def test_dfd_check_prints_preview_and_ok_without_writing(self):
        self.dfd_era()
        code, out, err = self.run_cli("dfd", "check", "demo")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], "version: 1.0")
        self.assertRegex(lines[1], r"^sha256: [0-9a-f]{64}$")
        self.assertEqual(lines[2:], ["ids: E=1 P=2 D=1 F=3 TB=1", "added: none", "removed: none", "ok"])
        seed_dfd_risk(self.reg, "T-01", ["P2", "F2"])  # add needs a model approval now
        path = self.root / "systems/demo/dfd.md"
        path.write_text(path.read_text().replace("| F2 | P1 | P2 (via CDN) | REST |\n", "")
                        .replace("| D1 | DB | Data store |\n", "| D1 | DB | Data store |\n| D2 | Cache | Data store |\n"))
        before = len(self.reg.history("demo"))
        code, out, _ = self.run_cli("dfd", "check", "demo")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[2:], [
            "ids: E=1 P=2 D=2 F=2 TB=1", "added: D2", "removed: F2",
            "warning: T-01 cites F2, which this DFD no longer has", "ok"])
        self.assertEqual(len(self.reg.history("demo")), before)  # read-only
        fresh = make_registry(self.tmp / "fresh", approve=False)
        write_dfd(fresh, "demo")
        self.root = fresh.root
        code, out, _ = self.run_cli("dfd", "check", "demo")
        self.assertEqual(out.splitlines()[3:], ["added: (no approved DFD yet)", "removed: none", "ok"])

    def test_dfd_check_parse_error_exits_1(self):
        (self.root / "systems/demo/dfd.md").write_text(
            "| ID | Element | Type |\n|---|---|---|\n| E1 | Customer | External entity |\n")
        code, out, err = self.run_cli("dfd", "check", "demo")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, "tmreg: dfd.md has no '| DFD version | x.y |' row\n")

    def test_dfd_gate_never_prints_raw_escape_codes(self):
        self.dfd_era()
        path = self.root / "systems/demo/dfd.md"
        path.write_text(path.read_text().replace("| DFD version | 1.0 |",
                                                 "| DFD version | 1.1\x1b[8m |"))
        code, out, err = self.run_cli("dfd", "check", "demo")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("DFD version must be", err)
        self.assertNotIn("\x1b", err)
        code, out, err = self.run_cli("dfd", "approve", "demo", tty=True)
        self.assertEqual((code, out), (1, ""))
        self.assertNotIn("\x1b", err)

    def test_busy_database_is_reported(self):  # M7
        for target in ("tmreg.cli.Registry.list_risks", "tmreg.cli.open_registry"):
            with self.subTest(target=target), \
                    mock.patch(target, side_effect=sqlite3.OperationalError("database is locked")):
                code, out, err = self.run_cli("list", "demo")
            self.assertEqual((code, out, err),
                             (1, "", "tmreg: database is busy or unavailable: database is locked\n"))

    def test_usage_error_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["list"], project_root=self.root)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
