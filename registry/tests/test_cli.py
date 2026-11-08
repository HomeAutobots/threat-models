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
