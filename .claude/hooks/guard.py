#!/usr/bin/env python3
"""PreToolUse hook: an allow-list of what Claude may run or write in this project.

Claude Code sends the tool call as JSON on stdin. Exit 0 lets it run. Exit 2 blocks it, and Claude
Code shows stderr to Claude. Anything unexpected also exits 2: the guard fails closed.

Standard library only, no tmreg imports, and Python 3.9 or later, because the hook may run under
/usr/bin/python3. Keep TMREG_OPTIONS in step with registry/tmreg/cli.py and the Bash allow rules in
.claude/settings.json. The README section "What the guard blocks" describes these rules.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PREFIX = "threat-models guard: "

SHELL_TOOLS = ("Bash", "Monitor")  # both carry tool_input.command
WRITE_TOOLS = ("Edit", "Write", "MultiEdit")

# The whole command is one plain command: no shell operators, quotes, globs, $, redirection,
# line breaks, or tabs.
PLAIN_COMMAND = re.compile(r"[A-Za-z0-9 ._:/=,@+-]+")

# Each ./tmreg subcommand Claude may run, with the only options it may pass, spelled in full.
# argparse accepts any unambiguous abbreviation (--d is --db, --o is --out, --js is --json), so an
# option word must match one of these exactly, and the --name=value form is refused.
TMREG_OPTIONS = {
    "list": ("--trial", "--state", "--json"),
    "show": ("--trial", "--json"),
    "history": ("--trial", "--json"),
    "report": ("--trial", "--format", "--include-pending", "--include-retired", "--include-rejected"),
    "verify": ("--trial",),
    "runs": ("--trial",),
    "add": ("--trial", "--run", "--json"),
    "edit": ("--trial", "--run", "--json"),
    "dfd status": ("--trial",),
    "dfd check": ("--trial",),
    "run start": ("--trial",),
}
TMREG_HUMAN_ONLY = ("review", "approve", "reject", "merge", "retire", "import-legacy", "dfd approve")
TMREG_JSON_INPUT = ("add", "edit")  # --json PATH; for list, show, and history it is an output flag
TMREG_FORBIDDEN = ("--db", "--out")
GIT_SUBCOMMANDS = ("status", "diff", "log")
GIT_FORBIDDEN = ("--output", "--ext-diff")

_SLUG = r"[a-z][a-z0-9-]{1,39}"
_PART = r"[A-Za-z0-9._-]+"
DFD_FILE = re.compile(rf"systems/{_SLUG}/dfd\.md")
RUN_FILE = re.compile(rf"systems/{_SLUG}/runs/{_PART}/(?:{_PART}/)*{_PART}\.(?:md|json)")
CANDIDATE_FILE = re.compile(rf"systems/{_SLUG}/runs/{_PART}/(?:{_PART}/)*{_PART}\.json")

ALLOWED_COMMANDS = ("./tmreg (" + ", ".join(TMREG_OPTIONS) + "), git status, git diff, git log, "
                    "and ls, one plain command per call")


def _names(word: str, option: str) -> bool:
    """True if word is option, starts with it (--output-x, --db=x), or abbreviates it (--o, --ou)."""
    name = word.split("=", 1)[0]
    return name.startswith(option) or (len(name) > 2 and option.startswith(name))


def _project_path(text: str, root: Path) -> str | None:
    """text as a POSIX path relative to the project root, symlinks resolved; None if outside it."""
    try:
        base = os.path.realpath(str(root))
        real = os.path.realpath(text if os.path.isabs(text) else os.path.join(base, text))
    except ValueError:  # an embedded NUL
        return None
    if real == base or os.path.commonpath([base, real]) != base:
        return None
    return Path(os.path.relpath(real, base)).as_posix()


def _check_tmreg(args: list[str], root: Path) -> tuple[bool, str]:
    if not args:
        return False, f"./tmreg needs a subcommand; Claude may run {ALLOWED_COMMANDS}"
    n = 2 if args[0] in ("dfd", "run") and len(args) > 1 else 1
    sub, rest = " ".join(args[:n]), args[n:]
    if sub in TMREG_HUMAN_ONLY:
        return False, (f"./tmreg {sub} is human-only. Do not look for another route: ask the owner "
                       "to run it in their own terminal")
    if sub not in TMREG_OPTIONS:
        return False, f"./tmreg {sub} is not needed by Claude; Claude may run {ALLOWED_COMMANDS}"
    for word in rest:
        if any(_names(word, o) for o in TMREG_FORBIDDEN):
            return False, f"./tmreg {sub}: --db and --out are not allowed (got {word})"
    allowed = TMREG_OPTIONS[sub]
    i = 0
    while i < len(rest):
        word = rest[i]
        if word == "--json" and sub in TMREG_JSON_INPUT:
            path = rest[i + 1] if i + 1 < len(rest) else ""
            rel = _project_path(path, root) if path else None
            if rel is None or not CANDIDATE_FILE.fullmatch(rel):
                return False, (f"./tmreg {sub}: --json must name a .json file under "
                               f"systems/<slug>/runs/<run-id>/ in this project (got {path or 'nothing'})")
            i += 2
            continue
        if word.startswith("-") and word not in allowed:
            return False, (f"./tmreg {sub}: option {word} is not allowed; use only "
                           f"{', '.join(allowed)}, spelled in full, as separate words")
        i += 1
    return True, ""


def _check_git(args: list[str]) -> tuple[bool, str]:
    if not args or args[0] not in GIT_SUBCOMMANDS:
        what = f"git {args[0]}" if args else "git with no subcommand"
        return False, f"{what} is not allowed; Claude may run only git status, git diff, and git log"
    for word in args[1:]:
        if any(_names(word, o) for o in GIT_FORBIDDEN):
            return False, f"git {args[0]}: --output and --ext-diff are not allowed (got {word})"
    return True, ""


def check_command(tool: str, command, root: Path) -> tuple[bool, str]:
    if not isinstance(command, str) or not command.strip():
        return False, f"malformed {tool} call: no command"
    if not PLAIN_COMMAND.fullmatch(command):
        bad = next(c for c in command if not PLAIN_COMMAND.fullmatch(c))
        return False, (f"{tool} runs only one plain command: no shell operators, quotes, globs, $, "
                       f"redirection, or line breaks (found {bad!r})")
    words = command.split()
    if words[0] == "./tmreg":
        return _check_tmreg(words[1:], root)
    if words[0] == "git":
        return _check_git(words[1:])
    if words[0] == "ls":
        return True, ""
    return False, f"{words[0]} is not allowed; Claude may run {ALLOWED_COMMANDS}"


def check_write(tool: str, tool_input: dict, root: Path) -> tuple[bool, str]:
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        return False, f"malformed {tool} call: no file_path"
    rel = _project_path(path, root)
    if rel is not None and (DFD_FILE.fullmatch(rel) or RUN_FILE.fullmatch(rel)):
        return True, ""
    return False, (f"{tool} may write only systems/<slug>/dfd.md and .md or .json files under "
                   f"systems/<slug>/runs/<run-id>/; {path} is not one of them")


def decide(payload: dict, root: Path) -> tuple[bool, str]:
    """(allowed, reason) for one PreToolUse payload. Raises on a payload of an unexpected shape."""
    if not isinstance(payload, dict):
        return False, "malformed hook payload: not a JSON object"
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return False, "malformed hook payload: no tool_name"
    if tool == "NotebookEdit":
        return False, "NotebookEdit is not allowed in this project"
    if tool in SHELL_TOOLS:
        return check_command(tool, payload.get("tool_input", {}).get("command"), root)
    if tool in WRITE_TOOLS:
        return check_write(tool, payload.get("tool_input", {}), root)
    return True, ""


def _block(reason: str) -> int:
    sys.stderr.write(PREFIX + reason + "\n")
    return 2


def main() -> int:
    try:
        try:
            payload = json.loads(sys.stdin.buffer.read())
        except ValueError:
            return _block("malformed hook payload: stdin is not JSON")
        root = os.environ.get("CLAUDE_PROJECT_DIR") or (
            payload.get("cwd") if isinstance(payload, dict) else None)
        if not isinstance(root, str) or not root or not os.path.isdir(root):
            return _block("no project root: CLAUDE_PROJECT_DIR is unset and the payload has no cwd")
        allowed, reason = decide(payload, Path(root))
        return 0 if allowed else _block(reason)
    except BaseException as e:  # fail closed: any surprise blocks the call
        return _block(f"internal error: {type(e).__name__}")


if __name__ == "__main__":
    sys.exit(main())
