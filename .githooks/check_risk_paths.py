#!/usr/bin/env python3
"""Refuse risk data in git. tmreg creates registers locally; they never enter the repository.

Refused anywhere: database files. Refused under systems/<slug>/: generated registers, run records,
threat model documents, inputs, and DFDs other than the reference system's.

    check_risk_paths.py staged          pre-commit: check the staged paths
    check_risk_paths.py push <remote>   pre-push: check every commit being pushed (stdin as git gives it)

Stdlib only, Python 3.9+, so it runs under any python3 git finds.
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import PurePosixPath

REFERENCE_DFDS = {"systems/ordering-platform/dfd.md"}
DB_PATTERNS = ("*.db", "*.db-journal", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3")
ZERO = "0" * 40


def forbidden(path: str) -> str | None:
    """Why path must stay out of git, or None if it may be committed."""
    p = PurePosixPath(path)
    if any(fnmatch.fnmatch(p.name, pat) for pat in DB_PATTERNS):
        return "database file"
    parts = p.parts
    if len(parts) >= 4 and parts[0] == "systems" and parts[2] in ("runs", "inputs"):
        return f"{parts[2]}/ holds risk or system data"
    if len(parts) == 3 and parts[0] == "systems":
        if fnmatch.fnmatch(p.name, "register*.md"):
            return "generated risk register"
        if p.name == "threat-model.md":
            return "threat model document"
        if p.name == "dfd.md" and path not in REFERENCE_DFDS:
            return "system DFD"
    return None


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _paths(nul_separated: str) -> set[str]:
    return {p for p in nul_separated.split("\0") if p}


def staged_paths() -> set[str]:
    return _paths(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"))


def pushed_paths(remote: str, refs: str) -> set[str]:
    """Paths added or modified by any commit in the push, not just the tip's tree."""
    out: set[str] = set()
    for line in refs.splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[1] == ZERO:  # malformed, or a branch deletion
            continue
        local_sha, remote_sha = fields[1], fields[3]
        span = [f"{remote_sha}..{local_sha}"] if remote_sha != ZERO else \
            [local_sha, "--not", f"--remotes={remote}"]
        out |= _paths(_git("log", "--format=", "--name-only", "--diff-filter=ACMR", "-z", *span))
    return out


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["staged"]:
            paths, verb = staged_paths(), "commit"
        elif argv[:1] == ["push"] and len(argv) >= 2:
            paths, verb = pushed_paths(argv[1], sys.stdin.read()), "push"
        else:
            print("usage: check_risk_paths.py staged | push <remote>", file=sys.stderr)
            return 2
    except (OSError, subprocess.CalledProcessError) as e:  # fail closed
        print(f"risk-data check could not run: {e}", file=sys.stderr)
        return 1
    bad = sorted((p, why) for p in paths if (why := forbidden(p)))
    if not bad:
        return 0
    print(f"refusing to {verb} risk data; tmreg keeps registers local and out of git:",
          file=sys.stderr)
    for path, why in bad:
        print(f"  {path}: {why}", file=sys.stderr)
    print("Unstage it (git rm --cached <path>), or rewrite the commit that added it.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
