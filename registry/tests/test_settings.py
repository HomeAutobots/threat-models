"""The installed .claude/settings.json keeps the guard hook and the section 6.5 deny rules.

Runs against the real project. The README's maintenance flow relies on this test to show that the
guard was restored after a session that lifted it.
"""
import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"

MATCHER = "Bash|Monitor|Edit|Write|MultiEdit|NotebookEdit"
GUARD_ARG_SUFFIX = ".claude/hooks/guard.py"
HUMAN_ONLY = ("review", "approve", "reject", "merge", "retire", "import-legacy", "dfd approve")
ALLOWED = ("list", "show", "history", "report", "verify", "runs", "dfd status", "dfd check",
           "run start", "add", "edit")
INVOCATIONS = ("./tmreg", "tmreg", "python3 -m tmreg", "python3 ./tmreg", "python3 tmreg")
REQUIRED_DENY = [f"Bash(./tmreg {sub}:*)" for sub in HUMAN_ONLY] + [
    f"Bash(tmreg {sub}:*)" for sub in HUMAN_ONLY] + [
    "Bash(python3 -m tmreg:*)", "Bash(python3 ./tmreg:*)", "Bash(python3 tmreg:*)",
    "Bash(script:*)", "Bash(expect:*)", "Bash(unbuffer:*)",
    "Bash(python3 -c:*)", "Bash(python3 -:*)", "Bash(python -c:*)", "Bash(sqlite3:*)",
    "Bash(git checkout:*)", "Bash(git restore:*)", "Bash(git reset:*)", "Bash(git stash:*)",
    "Edit(/registry/**)", "Edit(/.claude/**)", "Edit(/systems/*/register.md)", "Edit(/tmreg)",
    "Edit(/project.toml)", "Edit(/CLAUDE.md)", "Edit(/.githooks/**)", "Edit(/.gitignore)",
]


def _denied(command: str, deny: list) -> bool:
    """True if a Bash(prefix:*) deny rule covers command. Claude Code ignores a leading ./ when
    matching deny rules (observed 2026-11-08: Bash(tmreg:*) denied ./tmreg verify)."""
    forms = {command, command[2:] if command.startswith("./") else command}
    for rule in deny:
        if rule.startswith("Bash(") and rule.endswith(":*)"):
            prefix = rule[len("Bash("):-len(":*)")]
            if any(c == prefix or c.startswith(prefix + " ") for c in forms):
                return True
    return False


def problems(settings: dict) -> list:
    """Every way settings falls short of the installed guard; empty when it is intact."""
    out = []
    if settings.get("disableAllHooks"):
        out.append("disableAllHooks is set")
    entries = (settings.get("hooks") or {}).get("PreToolUse") or []
    guards = [h for e in entries if e.get("matcher") == MATCHER for h in e.get("hooks") or []
              if h.get("type") == "command" and h.get("command") == "python3"
              and (h.get("args") or [""])[-1].endswith(GUARD_ARG_SUFFIX)
              and h.get("onFailure") == "block"]
    if len(guards) != 1:
        out.append(f"want one PreToolUse guard hook (matcher {MATCHER}, exec form python3 "
                   f"…/{GUARD_ARG_SUFFIX}, onFailure block); found {len(guards)}")
    perms = settings.get("permissions") or {}
    deny = perms.get("deny") or []
    out += [f"missing deny rule {r}" for r in REQUIRED_DENY if r not in deny]
    out += [f"{inv} {sub} is not denied" for inv in INVOCATIONS for sub in HUMAN_ONLY
            if not _denied(f"{inv} {sub} ordering-platform", deny)]
    out += [f"./tmreg {sub} is denied, so Claude cannot run it" for sub in ALLOWED
            if _denied(f"./tmreg {sub} ordering-platform", deny)]
    rules = [r for key in ("allow", "deny", "ask") for r in perms.get(key) or []]
    out += [f"Write rule with a path: {r}" for r in rules if r.startswith("Write(")]
    return out


# A minimal intact settings file, so the checker's own test does not depend on the live file.
GOOD = {
    "permissions": {"allow": ["Read"], "deny": list(REQUIRED_DENY)},
    "hooks": {"PreToolUse": [{"matcher": MATCHER, "hooks": [{
        "type": "command", "command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/" + GUARD_ARG_SUFFIX],
        "onFailure": "block"}]}]},
}


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads(SETTINGS.read_text())

    def test_installed_settings_keep_the_guard(self):
        self.assertEqual(problems(self.settings), [])

    def test_hook_points_at_the_guard_file(self):
        hooks = [h for e in (self.settings.get("hooks") or {}).get("PreToolUse") or []
                 for h in e.get("hooks") or []]
        self.assertTrue(hooks, "no PreToolUse hook")
        path = hooks[0]["args"][-1].replace("${CLAUDE_PROJECT_DIR}", str(ROOT))
        self.assertTrue(Path(path).is_file(), path)

    def test_a_lifted_guard_is_caught(self):
        self.assertEqual(problems(GOOD), [])
        lifted = copy.deepcopy(GOOD)
        del lifted["hooks"]
        lifted["permissions"]["deny"] = [r for r in lifted["permissions"]["deny"]
                                         if r not in ("Edit(/registry/**)", "Bash(python3 -m tmreg:*)")]
        lifted["permissions"]["allow"].append("Write(/registry/**)")
        found = "\n".join(problems(lifted))
        for text in ("guard hook", "missing deny rule Edit(/registry/**)",
                     "python3 -m tmreg approve is not denied", "Write rule with a path"):
            with self.subTest(text=text):
                self.assertIn(text, found)
        for change in (("onFailure", "allow"), ("command", "sh"), ("args", ["other.py"])):
            weak = copy.deepcopy(GOOD)
            weak["hooks"]["PreToolUse"][0]["hooks"][0][change[0]] = change[1]
            with self.subTest(change=change):
                self.assertTrue(problems(weak))
        weak = copy.deepcopy(GOOD)
        weak["hooks"]["PreToolUse"][0]["matcher"] = "Bash|Edit|Write"
        self.assertTrue(problems(weak))
        self.assertTrue(problems({**GOOD, "disableAllHooks": True}))

    def test_a_deny_rule_that_blocks_allowed_commands_is_caught(self):
        broad = copy.deepcopy(GOOD)
        broad["permissions"]["deny"].append("Bash(tmreg:*)")
        found = "\n".join(problems(broad))
        for sub in ("verify", "dfd status", "add"):
            with self.subTest(sub=sub):
                self.assertIn(f"./tmreg {sub} is denied", found)


if __name__ == "__main__":
    unittest.main()
