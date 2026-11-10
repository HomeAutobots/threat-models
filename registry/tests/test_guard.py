"""The approval guard (.claude/hooks/guard.py). Runs against the real project, not a temp dir,
except the read-path test, which needs folders outside a project of its own."""
import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
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
    "./tmreg c4 status ordering-platform",
    "./tmreg run start ordering-platform --trial",
    "./tmreg add ordering-platform --run 20261107-01 --json systems/ordering-platform/runs/20261107-01/candidates/01.json",
    "./tmreg edit ordering-platform T-34 --run 20261107-01 --json systems/ordering-platform/runs/20261107-01/candidates/edit-T-34.json",
    "./tmreg report ordering-platform --format md --include-pending", "./tmreg verify ordering-platform",
    "git status", "git diff systems/ordering-platform/workspace.dsl", "git log --oneline -5", "ls systems/ordering-platform",
    "./tmreg c4 check ordering-platform",
    "git log -1 --oneline .claude/commands/tm-model.md",
    "./tmreg c4 status demo", "./tmreg c4 status demo --trial", "./tmreg c4 status --trial demo", "./tmreg c4 check demo",
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/01.json",
    "./tmreg add demo --run trial-20261109-02 --json systems/demo/runs/trial-20261109-02/candidates/123.json --trial",
    "./tmreg edit demo PT-07 --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/edit-PT-07.json",
]
BLOCK = [
    "./tmreg approve ordering-platform T-37", "./tmreg c4 approve ordering-platform", "./tmreg review ordering-platform",
    "./tmreg reject ordering-platform T-37", "./tmreg merge ordering-platform T-37 --into T-33",
    "./tmreg retire ordering-platform T-02 --reason x", "./tmreg import-legacy ordering-platform",
    "./tmreg init-system x --name y", "python3 -m tmreg approve ordering-platform T-37", "python3 ./tmreg list ordering-platform",
    "./tmreg list ordering-platform; ./tmreg approve ordering-platform T-37", "./tmreg list ordering-platform && ls",
    "./tmreg list ordering-platform | cat", "./tmreg report ordering-platform > out.md",
    "./tmreg list ordering-platform\n./tmreg approve ordering-platform T-37", "./tmreg list ordering-platform $(x)",
    "./tmreg list ordering-platform --db registry/registry.db", "./tmreg report ordering-platform --out /tmp/r.md",
    "./tmreg add ordering-platform --run R --json -", "./tmreg add ordering-platform --run R --json /tmp/a.json",
    "./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/../../../registry/x.json",
    "./tmreg add demo --run R --json systems/demo/runs/R/../R/01.json",
    # --json names a candidate file of a real run: candidates/<nn>.json or candidates/edit-<risk>.json
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/notes.json",
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/.x.json",
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/.claude/x.json",
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/sub/01.json",
    "./tmreg add demo --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/1.json",
    "./tmreg add demo --run R --json systems/demo/runs/R/candidates/01.json",
    "./tmreg edit demo T-34 --run 20261109-01 --json systems/demo/runs/20261109-01/candidates/edit-X-34.json",
    "script -q /dev/null ./tmreg approve ordering-platform T-37", "unbuffer ./tmreg review ordering-platform",
    "expect -f approve.exp", "sqlite3 registry/registry.db .tables", "python3 -c 'import tmreg'", "python3 scratch.py",
    "bash scratch.sh", "git checkout registry/registry.db", "git restore .", "git reset --hard", "git stash",
    "git diff --output=x", "cat registry/registry.db", "FOO=1 ./tmreg list ordering-platform",
    "script -q /dev/null ./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/R/candidates/01.json",
    "./tmreg add ordering-platform --run R --json systems/ordering-platform/runs/R/candidates/01.json < /dev/tty",
    "./tmreg c4 approve ordering-platform --trial",
    "bash -c ls",
    "python3 -m tmreg list ordering-platform",
    # the C4 model: c4 approve is human-only, c4 check takes no --trial, and dfd is gone
    "./tmreg c4 approve demo", "./tmreg c4 check demo --trial", "./tmreg c4 check --trial demo",
    "tmreg c4 approve demo", "python3 -m tmreg c4 approve demo", "script -q /dev/null ./tmreg c4 approve demo",
    "./tmreg dfd status demo", "./tmreg dfd status demo --trial", "./tmreg dfd check demo", "./tmreg dfd approve demo",
    "./tmreg dfd approve ordering-platform", "./tmreg dfd approve ordering-platform --trial",
    # Docker runs Structurizr, which runs scripts in a model; the agent never runs it
    "docker run --rm --network none structurizr/structurizr validate -workspace systems/demo/workspace.dsl",
    "docker ps", "docker", "docker compose up",
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
    "./tmreg dfd", "./tmreg c4", "./tmreg c4 stat demo", "./tmreg c4 chec demo", "./tmreg c4 statusx demo",
    "./tmreg c4 check demo --db registry/other.db", "./tmreg c4 check demo --d x", "./tmreg c4 status demo --db=x",
    "./tmreg c4 check demo -h", "./tmreg c4 check demo --tr", "./tmreg c4 status demo --tri", "./tmreg c4 status demo --out x",
    "./tmreg --trial c4 status demo", "./tmreg c4 check demo; ./tmreg c4 approve demo", "./tmreg c4 approve",
    "./tmreg", "git", "git diff --out=x", "git log --ext-dif", "git diff --ext-diff",
    "git diff --no-index /etc/passwd README.md", "git log 'x'", "git diff -O/etc/passwd",
    "git diff --order-file=/etc/passwd", "git diff --order=/etc/passwd", "git diff -pO/etc/passwd",
    "ls\n", "", "   ",
]
# Read-only search and reading, for drafting a model and assessing risk.
READ_ALLOW = [
    "grep -rn --no-ignore-files 'data store' systems/ordering-platform",
    "grep -n '^## ' systems/ordering-platform/workspace.dsl",
    "grep -rniE 'token|secret' systems/ordering-platform --include='*.md' --exclude-dir=runs",
    "grep -c -e foo -e bar README.md", "grep -A 3 -B2 -m 1 Trust systems/ordering-platform/workspace.dsl",
    'grep -n "order service" systems/ordering-platform/workspace.dsl',
    "grep -rl F18 systems | head -20", "grep -rn x systems 2>&1 | head", "grep -rn -- -x README.md",
    "grep -oh 'T-[0-9]*' systems/ordering-platform/workspace.dsl | sort | uniq -c | sort -rn",
    "rg -n --no-ignore TLS systems/ordering-platform", "rg --files systems",
    "rg --no-ignore --hidden -g '*.md' x", "git log -S Order --oneline",
    "find systems -maxdepth 2 -name system.toml",
    "find systems -type f -name '*.md' -not -path '*/runs/*' 2>/dev/null",
    "find . '(' -name '*.toml' -o -name '*.md' ')' | wc -l",
    "ls -la systems/ordering-platform", "ls", "cat systems/ordering-platform/system.toml",
    "head -n 40 systems/ordering-platform/workspace.dsl", "head -20 README.md", "tail -n +5 README.md",
    "wc -l systems/ordering-platform/workspace.dsl", "cut -d , -f 1 README.md", "sort -k 2 -t , README.md",
    "file systems/ordering-platform/workspace.dsl", "file --mime-type README.md", "cat README.md | uniq -c",
]
READ_BLOCK = [
    # options that run programs, write files, follow symlinks out, or print binary files
    "grep --filter='sh:cat' x README.md", "grep --save-config x", "grep -R x systems", "grep -z x README.md",
    "grep -a x registry", "grep --text x registry", "grep -Q x", "grep --pager=less x README.md",
    "rg --pre cat x systems", "rg --pre=cat x", "rg -z x", "rg -L x systems", "rg --hostname-bin=sh x",
    "rg -a x registry", "rg -uuu -c SQLite registry", "rg -u x",
    "find systems -exec cat '{}' ';'", "find systems -delete",
    "find systems -name x -fprint out.txt", "find -L systems", "find systems -execdir ls ';'",
    "sort -o out.txt README.md", "sort --output=out.txt README.md", "uniq README.md out.txt",
    "tail -f README.md", "file -C -m x", "head -n",
    # paths outside the project and the guide, and the registry databases
    "grep x /etc/passwd", "grep -f /etc/passwd README.md", "grep -e x /etc/passwd", "grep -e x -- /etc/passwd",
    "cat ../../.ssh/id_rsa", "cat /etc/hosts", "head -n 5 /etc/hosts", "ls /", "find /etc -name passwd",
    "find systems -newer /etc/passwd", "grep x registry/trial.db", "head registry/registry.db-wal",
    "cat Registry/REGISTRY.DB", "file registry/registry.db",
    # shell syntax
    "grep --include '*.md' x systems", "grep x README.md > out.txt", "grep x README.md >> out.txt",
    "grep x README.md 2>out.txt", "grep x README.md 2>/dev/nullx", "grep 'x' README.md | sh",
    'grep "$HOME" README.md', 'grep "`id`" README.md', 'grep "a\\b" README.md', "grep 'x README.md",
    "grep '' README.md", "cat README.md |", "| cat README.md", "cat README.md || ls", "grep x *.md",
    "grep x README.md\tls", "ls ~", "cat =ls", "ls | ./tmreg approve ordering-platform T-37",
    "grep x README.md | ./tmreg list ordering-platform", "cd systems", "cd systems && ls",
    'ls -la "$(id)"', "ls {a,b}", "ls #x",
    # commands that are not read-only
    "sed -n 1,5p README.md", "awk '{print}' README.md", "xargs grep x", "find systems | xargs cat",
    "echo hi", "tee out.txt", "env grep x README.md", "command grep x README.md",
]
# The run files tm-model.md names, in a run folder named like a tmreg run ID: (trial-)YYYYMMDD-NN.
WRITE_ALLOW = ["systems/ordering-platform/workspace.dsl", "systems/ordering-platform/runs/20261107-01/worksheet.md",
               "systems/ordering-platform/runs/20261107-01/candidates/01.json", "systems/demo/workspace.dsl",
               "systems/demo/runs/20261109-01/model-check.md", "systems/demo/runs/trial-20261109-01/summary.md",
               "systems/demo/runs/20261109-01/worksheet.md", "systems/demo/runs/20261109-01/summary.md", "systems/demo/runs/20261109-01/candidates/07.json", "systems/demo/runs/20261109-01/candidates/123.json",
               "systems/demo/runs/20261109-01/candidates/edit-T-34.json", "systems/demo/runs/20261109-01/candidates/edit-PT-07.json",
               "systems/demo/runs/trial-20261109-12/model-check.md", "systems/demo/runs/20261109-100/worksheet.md"]
WRITE_BLOCK = ["registry/tmreg/core.py", "registry/registry.db", ".claude/settings.json", ".claude/hooks/guard.py",
               "systems/ordering-platform/register.md", "systems/ordering-platform/threat-model.md",
               "systems/ordering-platform/system.toml", "tmreg", "CLAUDE.md", "project.toml", "/tmp/x.py",
               "../threat-model-framework/docs/index.md", "systems/ordering-platform/runs/r/x.py",
               "systems/ordering-platform/runs/../../../registry/x.md",
               # the DFD is gone, Structurizr's layout file and the exported diagrams are never written
               "systems/ordering-platform/dfd.md", "systems/demo/dfd.md", "systems/demo/runs/20261109-01/dfd.md",
               "systems/demo/workspace.json", "systems/ordering-platform/workspace.json",
               "systems/demo/runs/20261109-01/workspace.json", "systems/demo/runs/20261109-01/Workspace.JSON", "systems/demo/WORKSPACE.JSON",
               "diagrams/x", "diagrams/main/demo/0123abcd/site/index.html", "diagrams/main/demo/0123abcd/workspace.dsl",
               "diagrams/main/demo/0123abcd/x.md", "Diagrams/x.md",
               # only systems/<slug>/workspace.dsl, named exactly, with no .. anywhere in the path
               "systems/../workspace.dsl", "systems/demo/../other/workspace.dsl", "systems/demo/sub/workspace.dsl",
               "systems/demo/runs/20261109-01/workspace.dsl", "systems/demo/inputs/workspace.dsl", "systems/workspace.dsl",
               "workspace.dsl", "systems/demo/Workspace.dsl", "systems/demo/workspace.dsl.bak",
               "systems/demo/workspace.dsl.md", "systems/Demo/workspace.dsl", "systems/d/workspace.dsl",
               "systems/demo/runs/../workspace.dsl", "systems/demo/runs/r/../../workspace.dsl",
               "systems/./demo/../demo/workspace.dsl", "systems/demo/runs/20261109-01/../20261109-01/summary.md",
               "systems/demo/workspace.dsl/", "systems/demo/runs/20261109-01/summary.md/",
               "systems/demo/workspace.dsl/.", "systems/demo/runs/20261109-01/summary.md/.",
               "/tmp/systems/demo/workspace.dsl", "../threat-model-framework/systems/demo/workspace.dsl",
               # Claude Code loads a CLAUDE.md, or a skill, agent, or command under .claude/, that it finds in a
               # subfolder; a skill's hooks run shell commands outside the guard. Under runs/ only the run files
               # tm-model.md names are written, no part starts with ., and no CLAUDE.md is written anywhere.
               "systems/demo/runs/20261109-01/.claude/skills/fmt/SKILL.md", "systems/demo/runs/20261109-01/.claude/settings.json", "systems/demo/runs/20261109-01/.claude/commands/x.md",
               "systems/demo/runs/20261109-01/.claude/agents/x.md", "systems/demo/runs/20261109-01/CLAUDE.md", "systems/demo/runs/20261109-01/claude.md", "systems/demo/runs/20261109-01/Claude.MD", "systems/demo/runs/20261109-01/.mcp.json",
               "systems/demo/runs/.git/x.md", "systems/demo/runs/.claude/skills/x/SKILL.md", "systems/demo/runs/20261109-01/sub/deeper/x.md",
               "systems/demo/runs/20261109-01/notes.md", "systems/demo/runs/20261109-01/worksheet.json", "systems/demo/runs/20261109-01/Worksheet.md", "systems/demo/runs/20261109-01/dfd-check.md", "systems/demo/runs/20261109-01/x.md",
               "systems/demo/runs/20261109-01/candidates/.x.json", "systems/demo/runs/20261109-01/candidates/1.json", "systems/demo/runs/20261109-01/candidates/01.md", "systems/demo/runs/20261109-01/candidates/sub/01.json",
               "systems/demo/runs/20261109-01/candidates/edit-T-1.json", "systems/demo/runs/20261109-01/candidates/edit-X-34.json", "systems/demo/runs/20261109-01/candidates/edit-T-34.json.md",
               "systems/demo/runs/20261109-01/candidates/CLAUDE.md", "systems/demo/runs/20261109-01/candidates/x.json", "systems/demo/runs/20261109-01/model-check.md.json",
               "systems/demo/runs/r/worksheet.md", "systems/demo/runs/2026110901/worksheet.md",
               "systems/demo/runs/20261109-1/worksheet.md", "systems/demo/runs/Trial-20261109-01/summary.md",
               "systems/demo/runs/trial-20261109-01-x/summary.md", "systems/demo/runs/.20261109-01/summary.md",
               "systems/demo/runs/worksheet.md", "systems/demo/.claude/skills/x/SKILL.md", "systems/.claude/x.md",
               ".claude/skills/x/SKILL.md", "systems/demo/CLAUDE.md", "systems/CLAUDE.md", "systems/demo/.mcp.json"]


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

    def test_read_only_commands(self):
        for cmd in READ_ALLOW:
            with self.subTest(cmd=cmd):
                self.assertEqual(bash(cmd), (True, ""))
        for cmd in READ_BLOCK:
            with self.subTest(cmd=cmd):
                self.assertFalse(bash(cmd)[0])

    def test_read_reasons_name_the_rule(self):
        self.assertIn("-R", bash("grep -R x systems")[1])
        self.assertIn("--include=VALUE", bash("grep --include '*.md' x systems")[1])
        self.assertIn("-exec", bash("find systems -exec cat '{}' ';'")[1])
        self.assertIn("outside", bash("cat /etc/hosts")[1])
        self.assertIn("./tmreg", bash("cat registry/registry.db")[1])
        self.assertIn("single quotes", bash('grep "$HOME" README.md')[1])
        self.assertIn("one plain command", bash("git log 'x'")[1])
        self.assertIn("grep", bash("sed -n 1,5p README.md")[1])

    def test_read_paths_stay_in_the_project_and_its_additional_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            proj, guide, outside = base / "proj", base / "guide", base / "outside"
            for folder in (proj / ".claude", guide / "docs", outside):
                folder.mkdir(parents=True)
            (proj / ".claude" / "settings.json").write_text(
                json.dumps({"permissions": {"additionalDirectories": ["../guide"]}}))
            (guide / "docs" / "a.md").write_text("## A\n")
            (outside / "s.txt").write_text("secret\n")
            (proj / "link").symlink_to(outside, target_is_directory=True)
            (proj / "flink").symlink_to(outside / "s.txt")

            def run(cmd):
                return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, proj)[0]

            for cmd in ("grep -n '^## ' ../guide/docs/a.md", f"grep -rn A {guide}/docs",
                        "find ../guide -name '*.md'", "cat .claude/settings.json"):
                with self.subTest(cmd=cmd):
                    self.assertTrue(run(cmd))
            for cmd in ("cat ../outside/s.txt", "cat link/s.txt", "cat flink", "grep -r x link",
                        "ls ../outside", "find ../outside", f"head {outside}/s.txt", "ls ..",
                        "grep -rn A ../guide/../outside"):
                with self.subTest(cmd=cmd):
                    self.assertFalse(run(cmd))
            # without additionalDirectories, the guide is outside too
            (proj / ".claude" / "settings.json").write_text("{}")
            self.assertFalse(run("cat ../guide/docs/a.md"))
            (proj / ".claude" / "settings.json").write_text("not json")
            self.assertFalse(run("cat ../guide/docs/a.md"))
            self.assertTrue(run("ls"))

    def test_every_read_command_has_an_allow_rule(self):
        allow = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["allow"]
        for name in guard.READ_COMMANDS:
            with self.subTest(name=name):
                self.assertIn(f"Bash({name}:*)", allow)

    def test_every_tmreg_subcommand_has_an_allow_rule_and_every_human_one_a_deny(self):
        perms = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]
        tmreg_allow = {r for r in perms["allow"] if r.startswith("Bash(./tmreg ")}
        self.assertEqual(tmreg_allow, {f"Bash(./tmreg {sub}:*)" for sub in guard.TMREG_OPTIONS})
        for sub in guard.TMREG_HUMAN_ONLY:
            with self.subTest(sub=sub):
                self.assertIn(f"Bash(./tmreg {sub}:*)", perms["deny"])
                self.assertIn(f"Bash(tmreg {sub}:*)", perms["deny"])

    def test_monitor_gets_the_bash_rules(self):
        self.assertFalse(bash("./tmreg approve ordering-platform T-37", tool="Monitor")[0])
        self.assertFalse(bash("python3 scratch.py", tool="Monitor")[0])
        self.assertTrue(bash("./tmreg verify ordering-platform", tool="Monitor")[0])

        def monitor(given):
            return guard.decide({"tool_name": "Monitor", "tool_input": given}, ROOT)

        ok = "./tmreg verify ordering-platform"
        self.assertEqual(monitor({"command": ok, "description": "verify", "timeout_ms": 60000,
                                  "persistent": False}), (True, ""))
        # Monitor's ws source opens a WebSocket: a network channel. Only the listed keys pass.
        ws = {"url": "wss://events.example.com/stream"}
        for given in ({"command": ok, "ws": ws}, {"ws": ws, "description": "x", "timeout_ms": 60000},
                      {"command": ok, "description": "x", "url": "wss://x.example.com"},
                      {"command": ok, "shell": "/bin/sh"}, {"ws": ws}):
            with self.subTest(given=given):
                allowed, why = monitor(given)
                self.assertFalse(allowed)
                self.assertIn("Monitor may pass only", why)
        self.assertIn("ws", monitor({"command": ok, "ws": ws})[1])
        self.assertFalse(monitor(["./tmreg", "verify", "ordering-platform"])[0])

    def test_reasons_name_the_rule(self):
        for cmd in ("./tmreg approve ordering-platform T-37", "./tmreg c4 approve ordering-platform --trial",
                    "./tmreg c4 approve demo", "./tmreg review ordering-platform"):
            with self.subTest(cmd=cmd):
                self.assertIn("human-only", bash(cmd)[1])
        self.assertIn("not needed", bash("./tmreg init-system x --name y")[1])
        self.assertIn("shell", bash("./tmreg list ordering-platform | cat")[1])
        self.assertIn("--db", bash("./tmreg list ordering-platform --d registry/other.db")[1])
        self.assertIn("runs/", bash("./tmreg add ordering-platform --run R --json /tmp/a.json")[1])
        self.assertIn("git status", bash("git reset --hard")[1])
        self.assertIn("--output", bash("git diff --output=x")[1])
        self.assertIn("python3", bash("python3 -m tmreg list ordering-platform")[1])
        for cmd in ("./tmreg dfd status demo", "./tmreg dfd approve demo", "./tmreg dfd"):
            with self.subTest(cmd=cmd):
                self.assertIn("c4", bash(cmd)[1])
        self.assertIn("./tmreg c4 check takes no options", bash("./tmreg c4 check demo --trial")[1])
        self.assertIn("docker", bash("docker ps")[1])

    def test_write_rules(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            for path in WRITE_ALLOW:
                for given in (path, str(ROOT / path)):
                    with self.subTest(tool=tool, path=given):
                        self.assertTrue(write(given, tool)[0])
            for path in WRITE_BLOCK:
                with self.subTest(tool=tool, path=path):
                    self.assertFalse(write(path, tool)[0])
        # Write, Edit and MultiEdit write file_path alone: notebook_path is never a fallback
        for tool in ("Edit", "Write", "MultiEdit"):
            for given in ({"notebook_path": WRITE_ALLOW[0]}, {"file_path": "", "notebook_path": WRITE_ALLOW[0]},
                          {"file_path": None, "notebook_path": WRITE_ALLOW[0]},
                          {"file_path": 0, "notebook_path": WRITE_ALLOW[0]}):
                with self.subTest(tool=tool, given=given):
                    self.assertFalse(guard.decide({"tool_name": tool, "tool_input": given}, ROOT)[0])
        self.assertFalse(write("registry/x.ipynb", "Edit", key="notebook_path")[0])

    def test_write_reasons_name_the_rule(self):
        for path in ("systems/demo/dfd.md", "registry/tmreg/core.py"):
            with self.subTest(path=path):
                self.assertIn("systems/<slug>/workspace.dsl", write(path)[1])
        self.assertIn("..", write("systems/demo/../other/workspace.dsl")[1])
        self.assertIn("workspace.json", write("systems/demo/runs/20261109-01/workspace.json")[1])
        self.assertIn("CLAUDE.md", write("systems/demo/runs/20261109-01/CLAUDE.md")[1])
        self.assertIn("starts with .", write("systems/demo/runs/20261109-01/.claude/skills/fmt/SKILL.md")[1])
        self.assertIn("model-check.md", write("systems/demo/runs/20261109-01/notes.md")[1])
        self.assertIn("diagrams/", write("diagrams/main/demo/x/site/index.html")[1])

    def test_write_paths_resolve_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            proj, outside = base / "proj", base / "outside"
            for folder in (proj / "systems" / "demo" / "runs" / "20261109-01", proj / "registry",
                           outside / "runs" / "20261109-01"):
                folder.mkdir(parents=True)
            (proj / "registry" / "core.py").write_text("")
            (proj / "systems" / "demo" / "workspace.dsl").write_text("")
            # a model file that is a link to tmreg's code, a system folder outside the project, and
            # a run folder outside it
            (proj / "systems" / "linked").mkdir()
            (proj / "systems" / "linked" / "workspace.dsl").symlink_to(proj / "registry" / "core.py")
            (proj / "systems" / "away").symlink_to(outside, target_is_directory=True)
            (proj / "systems" / "demo" / "runs" / "20261109-02").symlink_to(outside / "runs" / "20261109-01",
                                                                            target_is_directory=True)
            # a link to the project's own registry folder, named like a system
            (proj / "systems" / "reg").symlink_to(proj / "registry", target_is_directory=True)

            def run(path):
                return guard.decide({"tool_name": "Write", "tool_input": {"file_path": path}}, proj)[0]

            for path in ("systems/demo/workspace.dsl", str(proj / "systems/demo/workspace.dsl"),
                         "systems/demo/runs/20261109-01/model-check.md"):
                with self.subTest(path=path):
                    self.assertTrue(run(path))
            for path in ("systems/linked/workspace.dsl", "systems/away/workspace.dsl",
                         "systems/away/runs/20261109-01/summary.md", "systems/demo/runs/20261109-02/summary.md",
                         "systems/reg/core.py", "systems/reg/workspace.dsl", str(outside / "runs/20261109-01/summary.md")):
                with self.subTest(path=path):
                    self.assertFalse(run(path))

    def test_notebook_edit_and_malformed_payload_blocked(self):
        self.assertFalse(write(WRITE_ALLOW[0], "NotebookEdit", key="notebook_path")[0])
        self.assertFalse(write(WRITE_ALLOW[0], "NotebookEdit")[0])
        for payload in ({}, [], {"tool_name": ""}, {"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": {}},
                        {"tool_name": "Bash", "tool_input": {"command": ["ls"]}},
                        {"tool_name": "Edit", "tool_input": {}}, {"tool_name": "Write", "tool_input": {"file_path": 3}}):
            with self.subTest(payload=payload):
                self.assertFalse(guard.decide(payload, ROOT)[0])

    def test_only_the_listed_tools_pass(self):
        dsl = str(ROOT / "systems/demo/workspace.dsl")
        allowed = [("Read", {"file_path": str(ROOT / "registry/registry.db")}), ("Read", {"file_path": dsl}),
                   ("Grep", {"pattern": "x"}), ("Glob", {"pattern": "systems/*/system.toml"}),
                   ("TodoWrite", {"todos": [{"content": "x", "status": "pending", "activeForm": "x"}]}),
                   # the default task-list tools, which replaced TodoWrite: a local checklist only
                   ("TaskCreate", {"subject": "Draft the model", "description": "x", "activeForm": "x"}),
                   ("TaskGet", {"taskId": "1"}), ("TaskList", {}),
                   ("TaskUpdate", {"taskId": "1", "status": "completed"}),
                   # it only loads deferred tools' schemas; each loaded tool still goes through decide()
                   ("ToolSearch", {"query": "select:Monitor,TaskCreate", "max_results": 2}),
                   ("AskUserQuestion", {"questions": [{"question": "x?", "header": "x", "multiSelect": False,
                                                       "options": [{"label": "a"}, {"label": "b"}]}]}),
                   ("Write", {"file_path": dsl, "content": "x"}),
                   ("Edit", {"file_path": dsl, "old_string": "a", "new_string": "b"}),
                   ("MultiEdit", {"file_path": dsl, "edits": [{"old_string": "a", "new_string": "b"}]}),
                   ("Bash", {"command": "./tmreg verify demo"}), ("Monitor", {"command": "./tmreg verify demo"})]
        for tool, given in allowed:
            with self.subTest(tool=tool, given=given):
                self.assertEqual(guard.decide({"tool_name": tool, "tool_input": given}, ROOT), (True, ""))
        # Everything else is blocked, whatever its input: skills (whose hooks run shell commands),
        # subagents, the web, worktrees, notebooks, deferred tools, and every MCP tool, such as the
        # claude.ai connectors that could send risk data off the machine.
        blocked = ["Skill", "Agent", "Task", "WebFetch", "WebSearch", "EnterWorktree",
                   "ExitWorktree", "NotebookEdit", "Workflow", "Artifact", "SendUserFile", "PushNotification",
                   "PowerShell", "LSP", "CronCreate", "RemoteTrigger", "SendMessage", "ExitPlanMode",
                   "mcp__claude_ai_Gmail__send", "mcp__claude_ai_Google_Drive__create_file",
                   "mcp__claude-in-chrome__navigate", "mcp__drawio__open_drawio_xml", "FooTool",
                   "read", "write", "bash", "Read ", " Write", "Write\n"]
        for tool in blocked:
            for given in ({}, {"file_path": dsl}, {"command": "./tmreg verify demo"}, {"skill": "fmt"},
                          {"url": "https://example.com"}):
                with self.subTest(tool=tool, given=given):
                    ok, why = guard.decide({"tool_name": tool, "tool_input": given}, ROOT)
                    self.assertFalse(ok)
                    self.assertIn(repr(tool), why)

    def test_every_tmreg_line_in_tm_model_is_allowed(self):
        text = (ROOT / ".claude/commands/tm-model.md").read_text()
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith("./tmreg ")]
        self.assertGreaterEqual(len(lines), 6)
        self.assertIn("./tmreg c4 check <slug>", lines)
        self.assertIn("./tmreg c4 status <slug> [--trial]", lines)
        self.assertFalse([l for l in lines if l.startswith("./tmreg dfd")], "tm-model.md still runs dfd")
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
        for tool in ("Skill", "mcp__claude_ai_Gmail__send", "WebFetch"):
            with self.subTest(tool=tool):
                result = run_main({"tool_name": tool, "tool_input": {}})
                self.assertEqual(result.returncode, 2)
                self.assertIn(tool, result.stderr)

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
