"""Risk data never enters git: databases, generated registers, run records, threat model
documents, inputs, every DFD, every C4 model except the reference system's, its Structurizr
JSON, and the exported diagrams.

Three layers keep it out: .gitignore, the pre-commit and pre-push hooks in .githooks/ (installed
by `make hooks`, which `make test` runs), and the tracked-files check below.
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".githooks"
_spec = importlib.util.spec_from_file_location("check_risk_paths", HOOKS / "check_risk_paths.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

FORBIDDEN = [
    "registry/registry.db", "registry/trial.db", "registry/registry.db-wal", "backup.db",
    "exports/copy.sqlite3",
    "systems/ordering-platform/register.md", "systems/ordering-platform/register.trial.md",
    "systems/acme/runs/20261108-01/candidates/01.json", "systems/acme/runs/r/worksheet.md",
    "systems/ordering-platform/threat-model.md", "systems/acme/threat-model.md",
    "systems/acme/inputs/design.md", "systems/acme/dfd.md", "systems/ordering-platform/dfd.md",
    "systems/acme/workspace.dsl", "systems/acme/workspace.json",
    "systems/ordering-platform/workspace.json", "diagrams/a", "diagrams/main/acme/abc/index.html",
]
ALLOWED = [
    "systems/ordering-platform/workspace.dsl", "systems/ordering-platform/system.toml",
    "systems/acme/system.toml", "registry/tmreg/core.py", "registry/tmreg/schema.sql",
    "README.md", "project.example.toml", ".githooks/pre-commit", "sub/diagrams/x",
    "docs/diagrams/flow.svg",
]


def git(*args, cwd, check_=True, **kw):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, capture_output=True, text=True, check=check_, **kw)


def _is_git_checkout() -> bool:
    return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                          capture_output=True).returncode == 0


class PolicyTest(unittest.TestCase):
    def test_forbidden_and_allowed_paths(self):
        for path in FORBIDDEN:
            with self.subTest(path=path):
                self.assertIsNotNone(check.forbidden(path))
        for path in ALLOWED:
            with self.subTest(path=path):
                self.assertIsNone(check.forbidden(path))

    def test_model_paths(self):
        """Only the reference system's C4 model is tracked. Every other workspace.dsl, every
        workspace.json, the exported diagrams, and every dfd.md (the reference one included,
        now that its workspace.dsl replaces it) stay local."""
        self.assertIsNone(check.forbidden("systems/ordering-platform/workspace.dsl"))
        for path in ("systems/x/workspace.dsl", "systems/x/workspace.json",
                     "systems/ordering-platform/workspace.json", "diagrams/a",
                     "diagrams/main/x/0123/index.html", "systems/ordering-platform/dfd.md",
                     "systems/x/dfd.md"):
            with self.subTest(path=path):
                self.assertIsNotNone(check.forbidden(path))

    @unittest.skipUnless(_is_git_checkout(), "not a git checkout")
    def test_nothing_risky_is_tracked(self):
        tracked = git("ls-files", cwd=ROOT).stdout.split("\n")
        self.assertEqual([p for p in tracked if p and check.forbidden(p)], [])

    @unittest.skipUnless(_is_git_checkout(), "not a git checkout")
    def test_gitignore_covers_risk_data(self):
        for path in FORBIDDEN:
            with self.subTest(path=path):
                self.assertEqual(git("check-ignore", "--no-index", "-q", path, cwd=ROOT,
                                     check_=False).returncode, 0, f"{path} is not git-ignored")
        # Only the root diagrams/ holds exports; a folder of that name elsewhere is source.
        for path in ("systems/ordering-platform/workspace.dsl", "systems/acme/system.toml",
                     "sub/diagrams/x", "docs/diagrams/flow.svg"):
            with self.subTest(path=path):
                self.assertEqual(git("check-ignore", "--no-index", "-q", path, cwd=ROOT,
                                     check_=False).returncode, 1, f"{path} is git-ignored")


class HookTest(unittest.TestCase):
    """The hooks refuse risk data even when it is forced past .gitignore."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.remote = Path(self._tmp.name) / "remote.git"
        self.repo = Path(self._tmp.name) / "repo"
        git("init", "-q", "--bare", str(self.remote), cwd=self._tmp.name)
        git("init", "-q", "-b", "main", str(self.repo), cwd=self._tmp.name)
        shutil.copytree(HOOKS, self.repo / ".githooks")
        shutil.copy(ROOT / ".gitignore", self.repo / ".gitignore")
        git("config", "core.hooksPath", ".githooks", cwd=self.repo)
        git("remote", "add", "origin", str(self.remote), cwd=self.repo)
        git("add", ".", cwd=self.repo)
        git("commit", "-q", "-m", "init", cwd=self.repo)

    def write(self, path, text="x"):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_pre_commit_refuses_forced_risk_data(self):
        self.write("registry/registry.db")
        self.write("systems/acme/runs/r1/candidates/01.json")
        git("add", "-f", "registry/registry.db", "systems/acme/runs/r1/candidates/01.json",
            cwd=self.repo)
        result = git("commit", "-m", "oops", cwd=self.repo, check_=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("registry/registry.db", result.stderr)
        self.assertIn("systems/acme/runs/r1/candidates/01.json", result.stderr)
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=self.repo).stdout.strip(), "1")

    def test_pre_commit_refuses_forced_models_and_diagrams(self):
        paths = ["systems/acme/workspace.dsl", "systems/acme/workspace.json",
                 "diagrams/main/acme/0123/index.html", "systems/ordering-platform/dfd.md"]
        for path in paths:
            self.write(path)
        git("add", "-f", *paths, cwd=self.repo)
        result = git("commit", "-m", "oops", cwd=self.repo, check_=False)
        self.assertNotEqual(result.returncode, 0)
        for path in paths:
            self.assertIn(path, result.stderr)
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=self.repo).stdout.strip(), "1")

    def test_pre_commit_allows_tool_and_reference_files(self):
        self.write("systems/ordering-platform/workspace.dsl")
        self.write("systems/acme/system.toml")
        git("add", ".", cwd=self.repo)
        self.assertEqual(git("commit", "-q", "-m", "ok", cwd=self.repo, check_=False).returncode, 0)

    def test_pre_push_refuses_risk_data_committed_with_no_verify(self):
        git("push", "-q", "origin", "main", cwd=self.repo)
        self.write("systems/acme/register.md")
        git("add", "-f", "systems/acme/register.md", cwd=self.repo)
        git("commit", "-q", "--no-verify", "-m", "bypass", cwd=self.repo)
        self.write("notes.md")  # a later clean commit does not hide the earlier one
        git("add", "notes.md", cwd=self.repo)
        git("commit", "-q", "-m", "later", cwd=self.repo)
        result = git("push", "origin", "main", cwd=self.repo, check_=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("systems/acme/register.md", result.stderr)

    def test_pre_push_refuses_risk_data_on_a_new_branch(self):
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.write("systems/acme/threat-model.md")
        git("add", "-f", "systems/acme/threat-model.md", cwd=self.repo)
        git("commit", "-q", "--no-verify", "-m", "bypass", cwd=self.repo)
        result = git("push", "origin", "side", cwd=self.repo, check_=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("systems/acme/threat-model.md", result.stderr)

    def test_pre_push_allows_clean_history(self):
        self.write("README.md")
        git("add", "README.md", cwd=self.repo)
        git("commit", "-q", "-m", "docs", cwd=self.repo)
        self.assertEqual(git("push", "-q", "origin", "main", cwd=self.repo,
                             check_=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
