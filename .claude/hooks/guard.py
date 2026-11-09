#!/usr/bin/env python3
"""PreToolUse hook: an allow-list of what Claude may run or write in this project.

Claude Code sends the tool call as JSON on stdin. Exit 0 lets it run. Exit 2 blocks it, and Claude
Code shows stderr to Claude. Anything unexpected also exits 2: the guard fails closed.

Standard library only, no tmreg imports, and Python 3.9 or later, because the hook may run under
/usr/bin/python3. Keep TMREG_OPTIONS in step with registry/tmreg/cli.py, and TMREG_OPTIONS and
READ_COMMANDS in step with the Bash allow rules in .claude/settings.json. The README section "What
the guard blocks" describes these rules.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

PREFIX = "threat-models guard: "

SHELL_TOOLS = ("Bash", "Monitor")  # both carry tool_input.command
WRITE_TOOLS = ("Edit", "Write", "MultiEdit")

# The whole command is one plain command: no shell operators, quotes, globs, $, redirection,
# line breaks, or tabs. ./tmreg and git calls must be plain; read-only commands may also quote.
PLAIN_COMMAND = re.compile(r"[A-Za-z0-9 ._:/=,@+-]+")
PLAIN_CHAR = re.compile(r"[A-Za-z0-9._:/=,@+-]")


class ReadSpec(NamedTuple):
    """The only options a read-only command may pass. Options are allow-listed, never blocked one
    by one: in Claude Code's shell grep is ugrep and find is bfs, which run programs or write files
    through options such as --filter, --save-config, -exec, and -delete."""
    flags: str = ""            # short options without a value; may be combined (-rn)
    valued: str = ""           # short options that take a value (-A 3 or -A3)
    long: tuple = ()           # long options without a value
    long_valued: tuple = ()    # long options that take a value, as --name=value only
    path_values: tuple = ()    # options whose value is a file to read
    pattern: bool = False      # the first operand is a search pattern unless one of these is given
    pattern_given_by: tuple = ()
    counts: bool = False       # -NUM is a line count (head -20)
    max_operands: int = -1     # uniq's second operand is an output file


# Each read-only command Claude may run, alone or joined with |. Paths must be inside the project
# or a folder in additionalDirectories in .claude/settings.json (the guide). Options that follow
# symlinks out of a folder (grep -R, rg -L, find -L) are left out; -r does not follow them. So are
# the options that print or search binary files such as the registry database: -a and --text, and
# rg's -u, whose third use turns on --binary (use --no-ignore and --hidden instead).
_GREP_LONG = ("--count", "--ignore-case", "--line-number", "--recursive", "--files-with-matches",
              "--files-without-match", "--word-regexp", "--line-regexp", "--invert-match",
              "--only-matching", "--extended-regexp", "--fixed-strings", "--basic-regexp",
              "--perl-regexp", "--no-filename", "--with-filename", "--byte-offset", "--quiet",
              "--silent", "--no-messages", "--no-ignore-files", "--color", "--colour")
_GREP_VALUED = ("--include", "--exclude", "--include-dir", "--exclude-dir", "--max-count",
                "--context", "--after-context", "--before-context", "--regexp", "--file",
                "--color", "--colour")
_RG_LONG = ("--count", "--count-matches", "--ignore-case", "--smart-case", "--case-sensitive",
            "--line-number", "--no-line-number", "--files-with-matches", "--files-without-match",
            "--files", "--type-list", "--word-regexp", "--line-regexp", "--invert-match",
            "--only-matching", "--fixed-strings", "--hidden", "--no-ignore", "--no-ignore-vcs",
            "--heading", "--no-heading", "--with-filename", "--no-filename", "--vimgrep",
            "--multiline", "--pcre2", "--trim", "--json", "--quiet", "--color")
_RG_VALUED = ("--glob", "--iglob", "--type", "--type-not", "--max-count", "--context",
              "--after-context", "--before-context", "--regexp", "--file", "--color", "--max-depth",
              "--max-columns", "--max-filesize", "--sort", "--sortr")
READ_COMMANDS = {
    "grep": ReadSpec("EFGHILPbchilnoqrsvwx", "ABCefm", _GREP_LONG, _GREP_VALUED,
                     ("-f", "--file"), True, ("-e", "-f", "--regexp", "--file")),
    "rg": ReadSpec("FHINPSUcilnoqsvwx.", "ABCMdefgmtT", _RG_LONG, _RG_VALUED, ("-f", "--file"),
                   True, ("-e", "-f", "--regexp", "--file", "--files", "--type-list")),
    "ls": ReadSpec("@1ABCFGHOPRSTUWabcdefghiklmnopqrstuvwx%,"),
    "cat": ReadSpec("benstuv"),
    "head": ReadSpec(valued="nc", counts=True),
    "tail": ReadSpec("r", "nc", counts=True),
    "wc": ReadSpec("clmw"),
    "sort": ReadSpec("bdfhinru", "kt"),
    "uniq": ReadSpec("cdiu", "fs", max_operands=1),
    "cut": ReadSpec("ns", "bcdf"),
    "file": ReadSpec("bhiI", long=("--brief", "--mime", "--mime-type", "--mime-encoding")),
    "find": ReadSpec(),  # its expression is checked by _find_paths
}
FIND_OPTIONS = ("-E", "-H", "-P")
FIND_OPERATORS = ("(", ")", "!", ",", "-not", "-a", "-and", "-o", "-or")
FIND_TESTS = ("-print", "-print0", "-prune", "-empty", "-true", "-false", "-depth", "-xdev",
              "-mount", "-ls", "-quit", "-readable", "-writable", "-executable", "-nouser",
              "-nogroup", "-hidden", "-nohidden")
FIND_VALUED = ("-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex",
               "-iregex", "-regextype", "-type", "-xtype", "-maxdepth", "-mindepth", "-size",
               "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-perm", "-user", "-group",
               "-uid", "-gid", "-links", "-inum", "-newer", "-samefile", "-printf")
FIND_PATH_VALUES = ("-newer", "-samefile")
# Words dropped from a read-only stage: they only discard or merge error output.
STDERR_REDIRECTS = ("2>/dev/null", "2>&1")
REGISTRY_DB = re.compile(r"registry/[^/]+\.db(?:-journal|-wal|-shm)?", re.IGNORECASE)

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
# --no-index and --order-file (short -O, which git also takes bundled, as -pO<file>) open files
# outside the repo.
GIT_FORBIDDEN = ("--output", "--ext-diff", "--no-index", "--order-file")

_SLUG = r"[a-z][a-z0-9-]{1,39}"
_PART = r"[A-Za-z0-9._-]+"
DFD_FILE = re.compile(rf"systems/{_SLUG}/dfd\.md")
RUN_FILE = re.compile(rf"systems/{_SLUG}/runs/{_PART}/(?:{_PART}/)*{_PART}\.(?:md|json)")
CANDIDATE_FILE = re.compile(rf"systems/{_SLUG}/runs/{_PART}/(?:{_PART}/)*{_PART}\.json")

ALLOWED_COMMANDS = ("./tmreg (" + ", ".join(TMREG_OPTIONS) + ") and git status, git diff, and "
                    "git log, one plain command per call; and the read-only commands "
                    + ", ".join(READ_COMMANDS) + ", alone or joined with |")


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
            return False, (f"git {args[0]}: --output, --ext-diff, --no-index, and --order-file are "
                           f"not allowed (got {word})")
        if word.startswith("-") and not word.startswith("--") and "O" in word:
            return False, (f"git {args[0]}: -O (an order file) is not allowed (got {word}); give a "
                           "short option's value as its own word, as in -S Order")
    return True, ""


def _redirect_at(command: str, i: int) -> str:
    """The STDERR_REDIRECTS word starting at command[i], or ""."""
    for word in STDERR_REDIRECTS:
        end = i + len(word)
        if command.startswith(word, i) and command[end:end + 1] in ("", " ", "|"):
            return word
    return ""


def _split(command: str) -> tuple[list | None, str]:
    """command as pipeline stages of words with the quotes removed, or (None, reason).

    Allows single quotes, double quotes holding no $, `, \\, or !, and | between stages. Refuses
    every other shell operator, glob, and expansion outside quotes. Drops STDERR_REDIRECTS words.
    Claude Code runs commands in the user's shell, which may be zsh, so zsh's rules count too:
    '' is refused because the RC_QUOTES option reads it as a quote character."""
    bad = next((c for c in command if not c.isprintable()), None)
    if bad is not None:
        return None, f"no line breaks, tabs, or control characters (found {bad!r})"
    if "''" in command:
        return None, "no empty or doubled single quotes ('')"
    stages, words, word, i = [], [], None, 0
    while i < len(command):
        c = command[i]
        if c in " |":
            if word is not None:
                words.append(word)
                word = None
            if c == "|":
                if not words:
                    return None, "| must join two commands"
                stages.append(words)
                words = []
            i += 1
        elif word is None and _redirect_at(command, i):
            i += len(_redirect_at(command, i))
        elif c in "'\"":
            end = command.find(c, i + 1)
            if end < 0:
                return None, f"unclosed {c} quote"
            text = command[i + 1:end]
            if c == '"' and any(ch in text for ch in "$`\\!"):
                return None, "no $, `, \\, or ! inside double quotes; use single quotes"
            word = (word or "") + text
            i = end + 1
        elif c == "=" and word is None:
            return None, "no word may start with = outside quotes; zsh expands =name to a path"
        elif PLAIN_CHAR.fullmatch(c):
            word = (word or "") + c
            i += 1
        else:
            return None, (f"no shell operators, globs, $, or redirection outside quotes (found "
                          f"{c!r}); quote patterns with single quotes")
    if word is not None:
        words.append(word)
    if not words:
        return None, "| must join two commands" if stages else "no command"
    return stages + [words], ""


def _within(real: str, base: str) -> bool:
    return real == base or os.path.commonpath([base, real]) == base


def _read_roots(root: Path) -> list[str]:
    """The project, then each folder in additionalDirectories in .claude/settings.json, as real
    paths. Read-only commands may read only inside these."""
    folders = [str(root)]
    try:
        settings = json.loads((root / ".claude" / "settings.json").read_text())
        extra = settings["permissions"]["additionalDirectories"]
    except (OSError, ValueError, KeyError, TypeError):
        extra = []
    if isinstance(extra, list):
        folders += [os.path.join(str(root), os.path.expanduser(d)) for d in extra
                    if isinstance(d, str) and d]
    return [os.path.realpath(f) for f in folders]


def _read_path_reason(text: str, roots: list[str], cwd: str) -> str:
    """Why a read-only command may not read text, or "" if it may."""
    real = os.path.realpath(os.path.join(cwd, text))
    if not any(_within(real, r) for r in roots):
        return f"{text} is outside this project and the guide"
    if _within(real, roots[0]) and REGISTRY_DB.fullmatch(
            Path(os.path.relpath(real, roots[0])).as_posix()):
        return f"{text} is a registry database; read the registry only with ./tmreg"
    return ""


def _option_reason(name: str, word: str) -> str:
    spec = READ_COMMANDS[name]
    opt = word.split("=", 1)[0]
    if opt in spec.long_valued:
        return f"{name}: give {opt} its value in the same word, as {opt}=VALUE"
    shown = ([f"-{c}" for c in spec.flags + spec.valued] + list(spec.long)
             + [f"{o}=VALUE" for o in spec.long_valued if o not in spec.long])
    return f"{name}: option {word} is not allowed; {name} may use only {' '.join(shown)}"


def _read_paths(name: str, args: list[str]) -> tuple[list | None, str]:
    """The files and folders a read-only command would read, or (None, reason) if it passes an
    option it may not. Every operand counts as a path except a search pattern."""
    spec = READ_COMMANDS[name]
    operands, paths, pattern_given, i = [], [], False, 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            operands += args[i:]
            break
        if word == "-" or not word.startswith("-"):
            operands.append(word)
            continue
        if word.startswith("--"):
            opt, eq, value = word.partition("=")
            if not ((opt in spec.long and not eq) or (opt in spec.long_valued and eq)):
                return None, _option_reason(name, word)
            paths += [value] if opt in spec.path_values else []
            pattern_given = pattern_given or opt in spec.pattern_given_by
            continue
        if spec.counts and word[1:].isdigit():
            continue
        for j, ch in enumerate(word[1:], 2):
            if ch in spec.flags:
                continue
            if ch not in spec.valued:
                return None, _option_reason(name, f"-{ch}")
            value = word[j:]
            if not value:
                if i == len(args):
                    return None, f"{name}: -{ch} needs a value"
                value, i = args[i], i + 1
            paths += [value] if f"-{ch}" in spec.path_values else []
            pattern_given = pattern_given or f"-{ch}" in spec.pattern_given_by
            break
    if spec.pattern and not pattern_given and operands:
        operands = operands[1:]
    if 0 <= spec.max_operands < len(operands):
        return None, f"{name} takes at most {spec.max_operands} file here; it writes to a second one"
    return paths + [o for o in operands if o != "-"], ""


def _find_paths(args: list[str]) -> tuple[list | None, str]:
    """The folders and files find would read, or (None, reason) for a primary it may not use."""
    i = 0
    while i < len(args) and args[i] in FIND_OPTIONS:
        i += 1
    paths = []
    while i < len(args) and not args[i].startswith("-") and args[i] not in FIND_OPERATORS:
        paths.append(args[i])
        i += 1
    while i < len(args):
        word = args[i]
        i += 1
        if word in FIND_OPERATORS or word in FIND_TESTS:
            continue
        if word not in FIND_VALUED:
            return None, (f"find: {word} is not allowed; find may use only "
                          f"{' '.join(FIND_OPTIONS + FIND_OPERATORS + FIND_TESTS + FIND_VALUED)}")
        if i == len(args):
            return None, f"find: {word} needs a value"
        paths += [args[i]] if word in FIND_PATH_VALUES else []
        i += 1
    return paths, ""


def _check_read(words: list[str], roots: list[str], cwd: str) -> tuple[bool, str]:
    name = words[0]
    paths, reason = _find_paths(words[1:]) if name == "find" else _read_paths(name, words[1:])
    if paths is None:
        return False, reason
    for path in paths:
        reason = _read_path_reason(path, roots, cwd)
        if reason:
            return False, f"{name}: {reason}"
    return True, ""


def check_command(tool: str, command, root: Path) -> tuple[bool, str]:
    if not isinstance(command, str) or not command.strip():
        return False, f"malformed {tool} call: no command"
    stages, reason = _split(command)
    if stages is None:
        return False, f"{tool}: {reason}"
    words = stages[0]
    if words[0] in ("./tmreg", "git"):
        if len(stages) > 1 or not PLAIN_COMMAND.fullmatch(command):
            return False, (f"{words[0]} runs as one plain command per call: no shell operators, "
                           "quotes, globs, $, redirection, or line breaks")
        return _check_tmreg(words[1:], root) if words[0] == "./tmreg" else _check_git(words[1:])
    # Relative paths resolve from the project root, as for ./tmreg --json: cd is not allowed, so
    # the shell stays in the folder Claude Code started in.
    roots = _read_roots(root)
    for words in stages:
        if words[0] in ("./tmreg", "git"):
            return False, f"{words[0]} runs as one plain command per call, never in a pipeline"
        if words[0] not in READ_COMMANDS:
            return False, f"{words[0]} is not allowed; Claude may run {ALLOWED_COMMANDS}"
        allowed, reason = _check_read(words, roots, roots[0])
        if not allowed:
            return False, reason
    return True, ""


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
