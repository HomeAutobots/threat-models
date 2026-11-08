import contextlib
import io
import json
import unittest
from unittest import mock

from helpers import TmpTestCase, ai_fields, make_registry
from tmreg import cli, model, report

NOTE = "Checked against the DFD and the evidence."


class CliTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.reg = make_registry(self.tmp)
        self.root = self.reg.root

    def run_cli(self, *argv, tty=False, inputs=()):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("tmreg.core._has_tty", return_value=tty), \
                mock.patch("builtins.input", side_effect=list(inputs)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        self.run_cli("edit", "demo", "T-01", "--set", "status=planned", tty=True)
        code, out, _ = self.run_cli("show", "demo", "T-01")
        self.assertIn("Status:\n  - open\n  + planned", out)

    def test_interactive_add_offers_approval(self):
        p = self.root / "h.json"
        p.write_text(json.dumps({k: ai_fields()[k] for k in model.HUMAN_REQUIRED}))
        code, out, _ = self.run_cli("add", "demo", "--json", str(p), tty=True,
                                    inputs=["a", NOTE, "T-01"])
        self.assertEqual(code, 0)
        self.assertEqual(self.reg.get_risk("demo", "T-01")["review_state"], "approved")

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
        with mock.patch("tmreg.core._has_tty", return_value=True), \
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
        with mock.patch("tmreg.core._has_tty", return_value=True), \
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
        with mock.patch("tmreg.core._has_tty", return_value=True), \
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
        # dfd approve: unchanged DFD is refused by core after the prompts
        code, out, err = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual(code, 1)
        self.assertIn("version:", out)
        self.assertIn("already approved", err)
        (self.root / "systems/demo/dfd.md").write_text(
            (self.root / "systems/demo/dfd.md").read_text() + "\nMore prose.\n")
        code, _, _ = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "wrong"])
        self.assertEqual(code, 1)
        code, _, _ = self.run_cli("dfd", "approve", "demo", tty=True, inputs=[NOTE, "demo"])
        self.assertEqual((code, self.reg.dfd_status("demo").state), (0, "current"))

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
        code, out, _ = self.run_cli("run", "start", "demo")
        lines = out.splitlines()
        self.assertEqual(len(lines[0].split()), 1)
        self.assertTrue(lines[1].startswith("methods: "))
        self.assertEqual(lines[2], "dfd: DFD-1 (current)")
        self.assertTrue(self.run_cli("dfd", "status", "demo")[1].startswith("state: current"))
        self.assertIn(lines[0], self.run_cli("runs", "demo")[1])
        self.assertEqual(self.run_cli("history", "demo")[0], 0)

    def test_usage_error_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["list"], project_root=self.root)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
