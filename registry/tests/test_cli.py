import contextlib
import io
import json
import os
import sqlite3
import unittest
from unittest import mock

from helpers import (SAMPLE_WORKSPACE, TmpTestCase, ai_fields, approve_model, human_terminal,
                     make_registry, seed_dfd_era, seed_dfd_risk, start, write_model)
from tmreg import cli, ledger, model, report

NOTE = "Checked against the DFD and the evidence."


class CliTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.root = self.reg.root

    def dsl(self, old=None, new=None) -> bytes:
        text = SAMPLE_WORKSPACE.decode()
        if old is not None:
            assert old in text
            text = text.replace(old, new, 1)
        return text.encode()

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
                     ("import-legacy", "demo"), ("c4", "approve", "demo")]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("interactive terminal", err)
                self.assertEqual(out, "")
        self.assertEqual(len(self.reg.history("demo")), before)

    def test_human_only_refused_in_a_claude_code_shell_even_with_a_terminal(self):  # I6
        self.ai_add()
        before = len(self.reg.history("demo"))
        for argv in [("approve", "demo", "T-01"), ("review", "demo"), ("c4", "approve", "demo")]:
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

    def test_reject_merge_retire(self):
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

    def test_run_start_status_runs_history(self):
        code, out, _ = self.run_cli("run", "start", "demo")
        lines = out.splitlines()
        self.assertEqual(len(lines[0].split()), 1)
        self.assertTrue(lines[1].startswith("methods: "))
        self.assertEqual(lines[2], "model: MODEL-1 (current)")
        self.assertIn(lines[0], self.run_cli("runs", "demo")[1])
        self.assertEqual(self.run_cli("history", "demo")[0], 0)

    def test_run_start_model_line_none_and_changed(self):
        write_model(self.reg, "demo", self.dsl("Answers the web app.", "Answers it well."))
        self.assertEqual(self.run_cli("run", "start", "demo")[1].splitlines()[2],
                         "model: MODEL-1 (changed)")
        fresh = make_registry(self.tmp / "fresh", approve=False)
        self.root = fresh.root
        code, out, err = self.run_cli("run", "start", "demo")
        self.assertEqual((code, out.splitlines()[2]), (0, "model: none"))

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

    # ---- c4 ------------------------------------------------------------------------------

    def test_c4_status(self):
        self.assertEqual(self.run_cli("c4", "status", "demo")[1],
                         "state: current\nlatest: MODEL-1 (version 1.0)\n")
        write_model(self.reg, "demo", self.dsl("Answers the web app.", "Answers it well."))
        self.assertEqual(self.run_cli("c4", "status", "demo")[1].splitlines()[0], "state: changed")
        fresh = make_registry(self.tmp / "fresh", approve=False)
        self.root = fresh.root
        self.assertEqual(self.run_cli("c4", "status", "demo")[1], "state: none\n")
        self.assertEqual(self.run_cli("c4", "status", "demo", "--trial")[0], 1)  # no trial register

    def test_c4_check_on_the_approved_model(self):
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], "version: 1.0")
        self.assertRegex(lines[1], r"^sha256: [0-9a-f]{64}$")
        self.assertEqual(lines[2], "ids: A=1 S=1 C=3 K=0 R=3 TB=2 N=1 I=0 ENV=1 SEQ=0")
        self.assertEqual(lines[3:6], ["added: none", "removed: none", "changed: none"])
        self.assertEqual(lines[6], "next: A2 S2 C4 K1 R4 TB3 N2 I1 ENV2 SEQ1")
        self.assertEqual(lines[-1], "ok")

    def test_c4_check_shows_added_removed_and_changed_without_writing(self):
        text = SAMPLE_WORKSPACE.decode()
        edited = (text.replace('"Answers the web app." "Python"', '"Answers it well." "Python 3"')
                  .replace('"SQL over TLS"', '"SQL over mTLS"'))
        self.assertNotEqual(edited, text)
        write_model(self.reg, "demo", edited.encode())
        before = len(self.reg.history("demo"))
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("changed: C2 (description+technology), R3 (", out)
        self.assertEqual(out.splitlines()[-1], "ok")
        self.assertEqual(len(self.reg.history("demo")), before)

    def test_c4_check_first_model_says_no_approved_model_yet(self):
        fresh = make_registry(self.tmp / "fresh", approve=False)
        self.root = fresh.root
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[3], "added: (no approved model yet)")

    def test_c4_check_exits_1_with_problems(self):
        bad = SAMPLE_WORKSPACE.decode().replace('"tm.auth" "Service token"', '"tm.auth" ""')
        write_model(self.reg, "demo", bad.encode())
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual(code, 1)
        problems = [l for l in out.splitlines() if l.startswith("problem: ")]
        self.assertTrue(problems)
        self.assertNotIn("ok", out.splitlines())
        self.assertEqual(err, f"tmreg: {len(problems)} problem(s); fix workspace.dsl and check again\n")

    def test_c4_check_parse_error_and_missing_file(self):
        write_model(self.reg, "demo", b"workspace {\n")
        code, out, err = self.run_cli("c4", "check", "demo")
        lines = out.splitlines()
        self.assertEqual(code, 1)
        self.assertRegex(lines[0], r"^sha256: [0-9a-f]{64}$")
        self.assertTrue(lines[1].startswith("problem: "))
        self.assertEqual(len(lines), 2)
        self.assertEqual(err, "tmreg: 1 problem(s); fix workspace.dsl and check again\n")
        (self.root / "systems/demo/workspace.dsl").unlink()
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("problem: "))
        self.assertNotIn("sha256", out)

    def test_c4_check_takes_no_trial(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_cli("c4", "check", "demo", "--trial")

    def test_c4_check_reports_a_reused_id(self):
        write_model(self.reg, "demo", self.dsl("C3 = container", "C9 = container")
                    .replace(b"C3", b"C9"))
        approve_model(self.reg, "demo")
        write_model(self.reg, "demo")  # C3 is back
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual(code, 1)
        self.assertIn("problem: C3 was used by an earlier approval; next free C: C10", out)

    def test_c4_check_lists_adoption_gaps_and_pending_rereviews(self):
        reg = make_registry(self.tmp / "era", approve=False)
        self.root = reg.root
        seed_dfd_era(reg, "demo")
        seed_dfd_risk(reg, "T-01", ["P2", "F2"], review_state="approved")
        seed_dfd_risk(reg, "T-02", ["P2"], review_state="pending", last_approved={"title": "x"})
        write_model(reg, "demo", self.dsl('"tm.was" "F2"', '"tm.was" "F9"'))
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertIn("adoption: F2 is cited by T-01 and claimed by nothing", out)
        self.assertIn("adoption: T-02 awaits re-review", out)

    def test_c4_check_never_prints_raw_escape_codes(self):
        bad = SAMPLE_WORKSPACE.decode().replace('"tm.version" "1.0"', '"tm.version" "1.0\x1b[8m"')
        write_model(self.reg, "demo", bad.encode())
        code, out, err = self.run_cli("c4", "check", "demo")
        self.assertEqual(code, 1)
        self.assertNotIn("\x1b", out + err)

    def test_c4_approve_flow(self):
        write_model(self.reg, "demo", self.dsl("Answers the web app.", "Answers it well."))
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[NOTE, "wrong"])
        self.assertEqual((code, self.reg.c4_status("demo").latest["id"]), (1, "MODEL-1"))
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("changed: C2 (description)", out)
        self.assertIn("If an AI run drafted this model, check that this sha256 matches the one quoted "
                      "in systems/demo/runs/<run-id>/model-check.md.", out)
        self.assertEqual(out.splitlines()[-1], "MODEL-2 approved")
        self.assertEqual(self.reg.c4_status("demo").state, "current")

    def test_c4_approve_unchanged_is_refused_before_any_prompt(self):
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[])
        self.assertEqual((code, out, err), (1, "", "tmreg: already approved as MODEL-1\n"))

    def test_c4_approve_refuses_problems_before_any_prompt(self):
        write_model(self.reg, "demo", SAMPLE_WORKSPACE.replace(b'"tm.auth" "Service token"', b'"tm.auth" ""'))
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[])
        self.assertEqual(code, 1)
        self.assertIn("problem: ", out)
        self.assertIn("problem(s); fix workspace.dsl and check again", err)
        self.assertEqual(self.reg.c4_status("demo").latest["id"], "MODEL-1")

    def test_c4_approve_refuses_a_file_changed_between_preview_and_confirm(self):
        path = self.root / "systems/demo/workspace.dsl"
        path.write_bytes(self.dsl("Answers the web app.", "Answers it well."))

        def hook(prompt):
            if prompt.startswith("Type demo"):
                path.write_bytes(self.dsl("Answers the web app.", "Swapped in after the preview."))
                return "demo"
            return NOTE
        out, err = io.StringIO(), io.StringIO()
        with human_terminal(), mock.patch("builtins.input", side_effect=hook), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["c4", "approve", "demo"], project_root=self.root)
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue(), "tmreg: workspace.dsl changed since it was shown; review it again\n")
        self.assertEqual(self.reg.c4_status("demo").latest["id"], "MODEL-1")

    def test_c4_approve_with_adoption(self):
        reg = make_registry(self.tmp / "era", approve=False)
        self.root = reg.root
        seed_dfd_era(reg, "demo")
        seed_dfd_risk(reg, "T-01", ["P2", "F2"], review_state="approved")
        write_model(reg, "demo")
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("adoption: 1 risk(s) will move to the new IDs", out)
        self.assertEqual(reg.get_risk("demo", "T-01")["elements"], ["C2", "R2"])

    def test_c4_approve_adoption_gap_refused_before_prompt(self):
        reg = make_registry(self.tmp / "era", approve=False)
        self.root = reg.root
        seed_dfd_era(reg, "demo")
        seed_dfd_risk(reg, "T-01", ["P2", "F2"], review_state="approved")
        write_model(reg, "demo", self.dsl('"tm.was" "F2"', '"tm.was" "F9"'))
        code, out, err = self.run_cli("c4", "approve", "demo", tty=True, inputs=[])
        self.assertEqual(code, 1)
        self.assertIn("adoption: F2 is cited by T-01 and claimed by nothing", out)
        self.assertEqual(reg.c4_status("demo").state, "none")

    def test_dfd_prints_the_pointer_and_is_not_human_only(self):
        pointer = "tmreg: dfd was replaced by c4: use ./tmreg c4 status|check|approve <slug>\n"
        for argv in [("dfd",), ("dfd", "status", "demo"), ("dfd", "approve", "demo"),
                     ("dfd", "check", "demo", "--trial"), ("dfd", "--trial")]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)  # no terminal: a human-only command would refuse
                self.assertEqual((code, out, err), (2, "", pointer))
        self.assertFalse(cli.build_parser().parse_args(["dfd", "status", "demo"]).human)

    def test_show_prints_the_moved_on_line_only_when_it_moved(self):
        self.ai_add()
        self.assertNotIn("moved on", self.run_cli("show", "demo", "T-01")[1])
        write_model(self.reg, "demo", self.dsl("Answers the web app.", "Answers it well."))
        approve_model(self.reg, "demo")
        out = self.run_cli("show", "demo", "T-01")[1]
        self.assertIn("Model has moved on: written against MODEL-1, latest is MODEL-2 (changed: C2)", out)

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
