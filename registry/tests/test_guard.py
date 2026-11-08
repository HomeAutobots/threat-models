"""The approval guard (.claude/hooks/guard.py). Runs against the real project, not a temp dir."""
import ast
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / ".claude" / "hooks" / "guard.py"

_spec = importlib.util.spec_from_file_location("guard", GUARD)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

ALLOW = [
    "./tmreg list ordering-platform --state all --json",
    "./tmreg show ordering-platform T-33 --json --trial",
    "./tmreg dfd status ordering-platform",
    "./tmreg run start ordering-platform --trial",
    "./tmreg add ordering-platform --run 20261107-01 --json systems/ordering-platform/runs/20261107-01/candidates/01.json",
    "./tmreg edit ordering-platform T-34 --run 20261107-01 --json systems/ordering-platform/runs/20261107-01/candidates/edit-T-34.json",
    "./tmreg report ordering-platform --format md --include-pending", "./tmreg verify ordering-platform",
    "git status", "git diff systems/ordering-platform/dfd.md", "git log --oneline -5", "ls systems/ordering-platform",
    "./tmreg dfd check ordering-platform",
    "git log -1 --oneline .claude/commands/tm-model.md",
]
BLOCK = [
    "./tmreg approve ordering-platform T-37", "./tmreg dfd approve ordering-platform", "./tmreg review ordering-platform",
    "./tmreg reject ordering-platform T-37", "./tmreg merge ordering-platform T-37 --into T-33",
    "./tmreg retire ordering-platform T-02 --reason x", "./tmreg import-legacy ordering-platform",
    "./tmreg init-system x --name y", "python3 -m tmreg approve ordering-platform T-37", "python3 ./tmreg list ordering-platform",
    "./tmreg list ordering-platform; ./tmreg approve ordering-platform T-37", "./tmreg list ordering-platform && ls",
    "./tmreg list ordering-platform | cat", "./tmreg report ordering-platform > out.md",
    "./tmreg list ordering-platform\n./tmreg approve ordering-platform T-37", "./tmreg list ordering-platform $(x)",
    "./tmreg list ordering-platform --db registry/registry.db", "./tmreg report ordering-platform --out /tmp/r.md",
    "./tmreg add ordering-platform --run R --json -", "./tmreg add ordering-platform --run R --json /tmp/a.json",
    "./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/../../../registry/x.json",
    "script -q /dev/null ./tmreg approve ordering-platform T-37", "unbuffer ./tmreg review ordering-platform",
    "expect -f approve.exp", "sqlite3 registry/registry.db .tables", "python3 -c 'import tmreg'", "python3 scratch.py",
    "bash scratch.sh", "git checkout registry/registry.db", "git restore .", "git reset --hard", "git stash",
    "git diff --output=x", "cat registry/registry.db", "FOO=1 ./tmreg list ordering-platform",
    "script -q /dev/null ./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/R/candidates/01.json",
    "./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/R/candidates/01.json < /dev/tty",
    "./tmreg dfd approve ordering-platform --trial",
    "bash -c ls",
    "python3 -m tmreg list ordering-platform",
]
# argparse accepts unambiguous abbreviations (--d is --db, --o is --out, --js is --json), so a
# literal prefix check is not enough. These must be blocked too.
BLOCK_FORMS = [
    "./tmreg list ordering-platform --d registry/other.db",
    "./tmreg report ordering-platform --o r.md",
    "./tmreg report ordering-platform --ou=r.md",
    "./tmreg add ordering-platform --run R --js /tmp/a.json",
    "./tmreg add ordering-platform --run R --json=/tmp/a.json",
    "./tmreg add ordering-platform --run R --json",
    "./tmreg edit ordering-platform T-34 --run R --set status=accepted",
    "./tmreg list -- ordering-platform",
    "./tmreg dfd", "./tmreg", "git", "git diff --out=x", "git log --ext-dif", "git diff --ext-diff",
    "ls\n", "", "   ",
]
WRITE_ALLOW = ["systems/ordering-platform/dfd.md", "systems/ordering-platform/runs/20261107-01/worksheet.md",
               "systems/ordering-platform/runs/20261107-01/candidates/01.json"]
WRITE_BLOCK = ["registry/tmreg/core.py", "registry/registry.db", ".claude/settings.json", ".claude/hooks/guard.py",
               "systems/ordering-platform/register.md", "systems/ordering-platform/threat-model.md",
               "systems/ordering-platform/system.toml", "tmreg", "CLAUDE.md", "project.toml", "/tmp/x.py",
               "../threat-model-framework/docs/index.md", "systems/ordering-platform/runs/r/x.py",
               "systems/ordering-platform/runs/../../../registry/x.md"]


def bash(cmd, tool="Bash"):
    return guard.decide({"tool_name": tool, "tool_input": {"command": cmd}}, ROOT)


def write(path, tool="Write", key="file_path"):
    return guard.decide({"tool_name": tool, "tool_input": {key: path}}, ROOT)


def run_main(payload, env=None):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(GUARD)], input=text, capture_output=True, text=True,
                          env={"CLAUDE_PROJECT_DIR": str(ROOT)} if env is None else env)


class GuardTest(unittest.TestCase):
    def test_bash_rules(self):
        for cmd in ALLOW:
            with self.subTest(cmd=cmd):
                self.assertTrue(guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, ROOT)[0])
        for cmd in BLOCK:
            with self.subTest(cmd=cmd):
                self.assertFalse(guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, ROOT)[0])

    def test_option_abbreviations_and_odd_forms_blocked(self):
        for cmd in BLOCK_FORMS:
            with self.subTest(cmd=cmd):
                self.assertFalse(bash(cmd)[0])

    def test_monitor_gets_the_bash_rules(self):
        self.assertFalse(bash("./tmreg approve ordering-platform T-37", tool="Monitor")[0])
        self.assertFalse(bash("python3 scratch.py", tool="Monitor")[0])
        self.assertTrue(bash("./tmreg verify ordering-platform", tool="Monitor")[0])

    def test_reasons_name_the_rule(self):
        for cmd in ("./tmreg approve ordering-platform T-37", "./tmreg dfd approve ordering-platform --trial",
                    "./tmreg review ordering-platform"):
            with self.subTest(cmd=cmd):
                self.assertIn("human-only", bash(cmd)[1])
        self.assertIn("not needed", bash("./tmreg init-system x --name y")[1])
        self.assertIn("shell", bash("./tmreg list ordering-platform | cat")[1])
        self.assertIn("--db", bash("./tmreg list ordering-platform --d registry/other.db")[1])
        self.assertIn("runs/", bash("./tmreg add ordering-platform --run R --json /tmp/a.json")[1])
        self.assertIn("git status", bash("git reset --hard")[1])
        self.assertIn("--output", bash("git diff --output=x")[1])
        self.assertIn("python3", bash("python3 -m tmreg list ordering-platform")[1])

    def test_write_rules(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            for path in WRITE_ALLOW:
                for given in (path, str(ROOT / path)):
                    with self.subTest(tool=tool, path=given):
                        self.assertTrue(write(given, tool)[0])
            for path in WRITE_BLOCK:
                with self.subTest(tool=tool, path=path):
                    self.assertFalse(write(path, tool)[0])
        # file_path falls back to notebook_path
        self.assertTrue(write(WRITE_ALLOW[0], "Edit", key="notebook_path")[0])
        self.assertFalse(write("registry/x.ipynb", "Edit", key="notebook_path")[0])

    def test_notebook_edit_and_malformed_payload_blocked(self):
        self.assertFalse(write(WRITE_ALLOW[0], "NotebookEdit", key="notebook_path")[0])
        self.assertFalse(write(WRITE_ALLOW[0], "NotebookEdit")[0])
        for payload in ({}, [], {"tool_name": ""}, {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": {}},
                        {"tool_name": "Bash", "tool_input": {"command": ["ls"]}},
                        {"tool_name": "Edit", "tool_input": {}}, {"tool_name": "Write", "tool_input": {"file_path": 3}}):
            with self.subTest(payload=payload):
                self.assertFalse(guard.decide(payload, ROOT)[0])

    def test_other_tools_pass(self):
        self.assertTrue(guard.decide({"tool_name": "Read", "tool_input": {"file_path": "registry/registry.db"}}, ROOT)[0])
        self.assertTrue(guard.decide({"tool_name": "Grep", "tool_input": {"pattern": "x"}}, ROOT)[0])

    def test_every_tmreg_line_in_tm_model_is_allowed(self):
        text = (ROOT / ".claude/commands/tm-model.md").read_text()
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith("./tmreg ")]
        self.assertGreaterEqual(len(lines), 6)
        self.assertIn("./tmreg dfd check <slug>", lines)
        for line in lines:
            cmd = (line.replace(" [--trial]", " --trial").replace("<slug>", "ordering-platform")
                       .replace("<run-id>", "20261107-01").replace("<id>", "T-34").replace("<nn>", "01"))
            with self.subTest(line=line):
                self.assertTrue(guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, ROOT)[0])

    def test_main_exit_codes(self):
        allowed = run_main({"tool_name": "Bash", "tool_input": {"command": ALLOW[0]}})
        self.assertEqual((allowed.returncode, allowed.stderr), (0, ""))
        blocked = run_main({"tool_name": "Bash", "tool_input": {"command": BLOCK[0]}})
        self.assertEqual(blocked.returncode, 2)
        self.assertTrue(blocked.stderr.startswith("threat-models guard:"), blocked.stderr)
        monitor = run_main({"tool_name": "Monitor", "tool_input": {"command": BLOCK[0]}})
        self.assertEqual(monitor.returncode, 2)
        # the root falls back to the payload's cwd; with neither, the call is blocked
        cwd = {"tool_name": "Bash", "cwd": str(ROOT), "tool_input": {"command": ALLOW[0]}}
        self.assertEqual(run_main(cwd, env={}).returncode, 0)
        no_root = run_main({"tool_name": "Bash", "tool_input": {"command": ALLOW[0]}}, env={})
        self.assertEqual(no_root.returncode, 2)
        self.assertIn("threat-models guard:", no_root.stderr)
        self.assertEqual(run_main("not json").returncode, 2)

    def test_main_fails_closed_when_decide_raises(self):
        payload = {"tool_name": "Bash", "tool_input": ["./tmreg", "list", "ordering-platform"]}
        with self.assertRaises(Exception):
            guard.decide(payload, ROOT)
        result = run_main(payload)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith("threat-models guard: internal error: "), result.stderr)

    def test_guard_parses_as_python_39(self):
        ast.parse(GUARD.read_text(), feature_version=(3, 9))
        self.assertNotIn("import tmreg", GUARD.read_text())
        self.assertNotIn("from tmreg", GUARD.read_text())


if __name__ == "__main__":
    unittest.main()
