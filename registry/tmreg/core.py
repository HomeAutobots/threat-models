"""Registry: every rule. Writes go through ledger.write_row, inside one transaction each."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import catalog, config, db, dfd, ledger, report as report_mod
from .model import (
    AI_REQUIRED, CONFIDENCE, EDITABLE_FIELDS, HUMAN_REQUIRED, JSON_COLUMNS, KEY_COLUMNS, LINDDUN,
    MIN_LENGTHS, NOTE_MIN, REVIEW_STATES, RISK_FIELDS, SNAPSHOT_FIELDS, STATUSES, STRIDE, SUPERSEDED_RE,
    TREATMENTS,
)

HUMAN_ONLY_MSG = ("{command} is human-only and needs an interactive terminal. Run it yourself in a "
                  "terminal window, not through Claude Code or its ! prefix.")
NO_RUN_MSG = "non-interactive writes must name a run: pass --run <run-id>"
TEMPLATE_PATH = Path("docs/templates/threat-model-document.md")
LIST_FIELDS = ("elements", "control_refs")

_RISK_ID_RE = re.compile(r"(P?T)-([0-9]+)")
_DFD_APPROVAL_RE = re.compile(r"DFD-([0-9]+)")
_DFD_ID_RE = re.compile(r"(E|P|D|F|TB)([0-9]+)")
_EXC_RE = re.compile(r"EXC-[0-9]{2,}")
_SUPERSEDED = re.compile(SUPERSEDED_RE, re.ASCII)
_TEMPLATE_BLOCK_RE = re.compile(r"^````markdown[ \t]*\n(.*?)^````[ \t]*$", re.M | re.S)
_PLAIN_STATUSES = tuple(s for s in STATUSES if s != "retired")

SYSTEM_TOML = """\
# tmreg system configuration. Keys:
#   name                   display name (required)
#   owner                  who answers for this system's risks
#   methods                elicitation methods: "stride-per-element", "linddun"
#                          (default ["stride-per-element"])
#   personal_data_classes  personal data classes in scope, e.g. ["PII"]; any entry adds linddun
#   legacy_catalog         framework-relative path of a reference catalog, for import-legacy
#   inputs_policy          what inputs/ may hold (default: no secrets, credentials, or customer data)
name = {name}
"""


class RegistryError(Exception):
    """A rule violation, with a message meant for the user."""


class StaleRecord(RegistryError):
    """The row is not what the reviewer was shown."""


def _has_tty() -> bool:
    """The only terminal check in the codebase. Tests patch it."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):  # a missing (None) or closed stream is not a terminal
        return False


CLAUDE_SHELL_NOTE = " (this shell was started by Claude Code)"


def _claude_shell() -> bool:
    """Claude Code exports CLAUDECODE to every Bash child, and the variable survives pty wrappers."""
    return bool(os.environ.get("CLAUDECODE"))


def require_interactive(command: str) -> None:
    """Refuse without a terminal, and refuse a shell Claude Code started even when it has one.
    The second check is one more refusal, never a bypass: an unset CLAUDECODE still needs a terminal."""
    if not _has_tty():
        raise RegistryError(HUMAN_ONLY_MSG.format(command=command))
    if _claude_shell():
        raise RegistryError(HUMAN_ONLY_MSG.format(command=command) + CLAUDE_SHELL_NOTE)


@dataclass(frozen=True)
class ReviewerSession:
    """Proof that a human is at an interactive terminal. Human-only operations require one."""
    name: str
    email: str
    command: str = "this command"

    def __post_init__(self):
        require_interactive(self.command)
        if not isinstance(self.name, str) or not self.name.strip():
            raise RegistryError("a reviewer session needs the reviewer's name")


@dataclass(frozen=True)
class DfdStatus:
    state: str  # "none", "current", or "changed"
    latest: dict | None
    current_sha256: str | None


def framework_commit(path: Path) -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                              check=True, timeout=30).stdout
    try:
        head = git("rev-parse", "HEAD").strip()
        dirty = git("status", "--porcelain").strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{head}+dirty" if dirty else head


def id_sort_key(risk_id) -> tuple[int, int]:
    """T before PT, then by number. Anything else sorts last."""
    m = _RISK_ID_RE.fullmatch(risk_id) if isinstance(risk_id, str) else None
    if m is None:
        return (2, 0)
    return (0 if m.group(1) == "T" else 1, int(m.group(2)))


# ---- validation helpers (module level so later tasks can reuse them) -------------------------

def _require_session(session) -> ReviewerSession:
    if not isinstance(session, ReviewerSession):
        raise RegistryError("this operation is human-only: it needs a ReviewerSession, which only "
                            "an interactive terminal can create")
    return session


def _require_note(text, what: str = "note") -> str:
    if not isinstance(text, str) or len(text.strip()) < NOTE_MIN:
        raise RegistryError(f"the {what} must be at least {NOTE_MIN} characters")
    return text.strip()


def _slug(slug) -> str:
    try:
        return db.validate_slug(slug)
    except ValueError as e:
        raise RegistryError(str(e)) from None


# C0 and C1 control characters, except tab and newline. CRLF is normalized to LF first.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _no_controls(field: str, text: str) -> str:
    text = text.replace("\r\n", "\n")
    if _CONTROL_RE.search(text):
        raise RegistryError(f"{field} contains control characters")
    return text


def _text(field: str, value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise RegistryError(f"{field} must be text, not {type(value).__name__}")
    return _no_controls(field, str(value)).strip() or None


def _str_list(field: str, value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = re.split(r"[;,]", value)
    elif isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        items = value
    else:
        raise RegistryError(f"{field} must be a list of strings or a ';'-separated string")
    out = list(dict.fromkeys(_no_controls(field, v).strip() for v in items if v.strip()))
    return out or None


def _category(value) -> str | None:
    text = _text("category", value)
    if text is None:
        return None
    if text.upper() in STRIDE:
        return text.upper()
    for name in LINDDUN:
        if text.casefold() == name.casefold():
            return name
    raise RegistryError(f"category must be a STRIDE letter ({', '.join(STRIDE)}) or a LINDDUN "
                        f"category ({', '.join(LINDDUN)}); got {text!r}")


def _check_status(status: str) -> None:
    if status == "retired":
        raise RegistryError("status retired is set only by retire: run ./tmreg retire <slug> <id> "
                            "--reason TEXT in your own terminal")
    if status not in _PLAIN_STATUSES and not _SUPERSEDED.fullmatch(status):
        raise RegistryError(f"status must be one of {', '.join(_PLAIN_STATUSES)}, or "
                            f"superseded-by-<ID>; got {status!r}")


def _clean(fields) -> dict:
    """Refuse unknown and system-managed keys, then normalize every value's type."""
    if not isinstance(fields, dict):
        raise RegistryError("risk fields must be a JSON object")
    unknown = [str(k) for k in fields if k not in RISK_FIELDS]
    managed = [k for k in RISK_FIELDS if k in fields and k not in EDITABLE_FIELDS]
    problems = []
    if unknown:
        problems.append(f"unknown field(s): {', '.join(unknown)}")
    if managed:
        problems.append(f"system-managed field(s) cannot be set: {', '.join(managed)}")
    if problems:
        raise RegistryError("; ".join(problems))
    out = {}
    for k in EDITABLE_FIELDS:
        if k not in fields:
            continue
        if k in LIST_FIELDS:
            out[k] = _str_list(k, fields[k])
        elif k == "category":
            out[k] = _category(fields[k])
        else:
            out[k] = _text(k, fields[k])
    return out


def _detail_now_complete(row: dict) -> bool:
    """An imported one-liner (detail_complete 0) whose every AI-required field is now filled."""
    return row["detail_complete"] == 0 and all(row.get(f) not in (None, "", [])
                                               for f in AI_REQUIRED)


def _check_required(row: dict, *, ai: bool) -> None:
    required = AI_REQUIRED if ai else HUMAN_REQUIRED
    missing = [f for f in required if row.get(f) in (None, "", [])]
    if missing:
        raise RegistryError(f"missing required field(s): {', '.join(missing)}")
    if ai:
        short = [f"{f} must be at least {n} characters"
                 for f, n in MIN_LENGTHS.items() if len(row[f]) < n]
        if short:
            raise RegistryError("; ".join(short))


def _dfd_ids(approval: dict) -> set[str]:
    return {i for ids in (approval.get("ids") or {}).values() for i in ids}


def _check_elements(elements, latest: dict) -> None:
    known = _dfd_ids(latest)
    unknown = [e for e in elements or [] if e not in known]
    if unknown:
        raise RegistryError(f"unknown element ID(s) for {latest['id']}: {', '.join(unknown)}")


def _dfd_id_key(i: str):
    m = _DFD_ID_RE.fullmatch(i)
    return (dfd.KINDS.index(m.group(1)), int(m.group(2)), "") if m else (len(dfd.KINDS), 0, i)


def _approval_number(approval: dict) -> int:
    m = _DFD_APPROVAL_RE.fullmatch(approval.get("id") or "")
    return int(m.group(1)) if m else -1


def _possible_duplicate(risks, category: str, elements: list[str]) -> str | None:
    """Most shared elements among non-rejected risks of the same category; ties go to the lowest ID."""
    best = None
    for r in risks:
        if r["review_state"] == "rejected" or r["category"] != category:
            continue
        shared = len(set(r["elements"] or ()) & set(elements))
        if shared:
            key = (-shared, id_sort_key(r["id"]))
            if best is None or key < best[0]:
                best = (key, r["id"])
    return best[1] if best else None


_APPROVAL_OPS = ("approve", "revert", "import")


def _editors(changes: list[dict], since_last_approval: bool) -> list[str]:
    """Distinct actors of the edit ops in one risk's changes, in order of first edit.

    With since_last_approval, the baseline is the latest approve, revert, or import, or a human
    edit that left the risk approved. Whether it is approved is tracked through the diffs."""
    if since_last_approval:
        state, last = "pending", -1
        for i, c in enumerate(changes):
            diff = c["diff"] if isinstance(c["diff"], dict) else {}  # anything else: no state change
            state = (diff.get("review_state") or [None, state])[1]
            if c["op"] in _APPROVAL_OPS or (
                    c["op"] == "edit" and not c["actor"].startswith("ai:") and state == "approved"):
                last = i
        changes = changes[last + 1:]
    return list(dict.fromkeys(c["actor"] for c in changes if c["op"] == "edit"))


def _is_stride_id(risk_id: str) -> bool:
    return id_sort_key(risk_id)[0] == 0


def _create(path: Path, text: str) -> None:
    """Write a new file; never overwrite one."""
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        pass


def _heading(lines: list[str], prefix: str, path: Path, start: int = 0) -> int:
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise RegistryError(f"{path}: the template block has no '{prefix}' heading")


class Registry:
    def __init__(self, root: Path, *, trial: bool = False, db_path: Path | None = None):
        self.root = Path(root)
        if trial and db_path is not None:
            raise RegistryError("pass trial or db_path, not both")
        try:
            self.config = config.load_project(self.root)
        except config.ConfigError as e:
            raise RegistryError(str(e)) from None
        real = self.root / "registry" / "registry.db"
        if trial:
            path = self.root / "registry" / "trial.db"
        else:
            path = real if db_path is None else self.root / db_path  # relative paths: from root
        self.db_path = path
        self.is_trial = bool(trial) or path.resolve() != real.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = db.connect(path)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def _write(self):
        """One transaction per public write; the write lock is taken before validation reads."""
        try:
            with self.conn:
                if not self.conn.in_transaction:
                    self.conn.execute("BEGIN IMMEDIATE")
                yield
        except ValueError as e:  # ledger, db, dfd, and config raise ValueError subclasses
            raise RegistryError(str(e)) from e

    # ---- systems and runs -------------------------------------------------------------------

    def _require(self, slug) -> str:
        _slug(slug)
        if not db.system_exists(self.conn, slug):
            raise RegistryError(f"no system {slug} in {self.db_path.name}")
        return slug

    def system(self, slug) -> config.SystemConfig:
        self._require(slug)
        try:
            return config.load_system(self.root, slug)
        except config.ConfigError as e:
            raise RegistryError(str(e)) from None

    def init_system(self, slug, name) -> None:
        _slug(slug)
        if not isinstance(name, str) or not name.strip():
            raise RegistryError("a system needs a name")
        name = name.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise RegistryError("the system name must be one line of plain text")
        if db.system_exists(self.conn, slug):
            raise RegistryError(f"system {slug} already exists in {self.db_path.name}")
        sysdir = self.root / "systems" / slug
        doc = sysdir / "threat-model.md"
        skeleton = None if doc.exists() else self._skeleton(slug, name)
        toml_text = SYSTEM_TOML.format(name=json.dumps(name, ensure_ascii=False))
        try:
            round_trips = tomllib.loads(toml_text).get("name") == name
        except tomllib.TOMLDecodeError:
            round_trips = False
        if not round_trips:
            raise RegistryError("the system name cannot be written to system.toml")
        try:
            with self.conn:  # create_system uses executescript, which commits on its own
                db.create_system(self.conn, slug, name)
        except ValueError as e:
            raise RegistryError(str(e)) from None
        try:
            for d in (sysdir, sysdir / "inputs", sysdir / "runs"):
                d.mkdir(parents=True, exist_ok=True)
            _create(sysdir / "system.toml", toml_text)
            if skeleton is not None:
                _create(doc, skeleton)
        except OSError as e:
            raise RegistryError(f"cannot create {e.filename}: {e.strerror}") from None
        self._write_register(slug)

    def _skeleton(self, slug: str, name: str) -> str:
        path = self.config.framework_path / TEMPLATE_PATH
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise RegistryError(f"cannot read the threat model template {path}: {e.strerror}") from None
        m = _TEMPLATE_BLOCK_RE.search(text)
        if m is None:
            raise RegistryError(f"{path} has no ````markdown block")
        lines = m.group(1).splitlines()
        s2 = _heading(lines, "## 2.", path)
        s3 = _heading(lines, "## 3.", path, s2 + 1)
        lines[s2 + 1:s3] = ["", "See [dfd.md](dfd.md). Approvals are recorded by tmreg; check with "
                            f"./tmreg dfd status {slug}.", ""]
        s4 = _heading(lines, "## 4.", path)
        lines[s4 + 1:s4 + 1] = ["", "Approved risks: [register.md](register.md), generated by tmreg."]
        body = "\n".join(lines).replace("<system or feature name>", name)
        return body.rstrip("\n") + "\n"

    def start_run(self, slug) -> dict:
        """Record a run. The result is the run row plus `evaluation`: true for a trial run on an
        empty trial register of a catalog mirror, where every catalog threat is withheld.

        A system with legacy_catalog mirrors the guide's catalog (spec 5.3), so AI runs on it use
        a trial database: an AI write in the real register would take catalog IDs and block the
        import, which runs only into an empty register."""
        system = self.system(slug)
        if system.legacy_catalog and not self.is_trial:
            raise RegistryError(f"{slug} mirrors the guide's catalog (legacy_catalog in system.toml); "
                                "AI runs on it use --trial. Add new catalog threats to the guide "
                                "first, then to the registry yourself.")
        methods = ",".join(system.effective_methods)
        commit = framework_commit(self.config.framework_path)  # before taking the write lock
        with self._write():
            evaluation = bool(system.legacy_catalog) and not ledger.read_rows(self.conn, slug, "risks")
            at = db.now()
            prefix = ("trial-" if self.is_trial else "") + at[:10].replace("-", "") + "-"
            used = [int(k[len(prefix):]) for k in ledger.read_rows(self.conn, slug, "runs")
                    if k.startswith(prefix) and re.fullmatch(r"[0-9]+", k[len(prefix):])]
            run_id = f"{prefix}{max(used, default=0) + 1:02d}"
            latest = self._latest_dfd(slug)
            ledger.write_row(self.conn, slug, "runs", run_id, {
                "started_at": at, "framework_commit": commit,
                "dfd_approval_id": latest["id"] if latest else None,
                "methods": methods, "actor": f"ai:{run_id}",
            }, op="run-start", actor="tmreg")
        return {**ledger.read_rows(self.conn, slug, "runs")[run_id], "evaluation": evaluation}

    def runs(self, slug) -> list[dict]:
        self._require(slug)
        return list(ledger.read_rows(self.conn, slug, "runs").values())

    # ---- DFD --------------------------------------------------------------------------------

    def _dfd_path(self, slug: str) -> Path:
        return self.root / "systems" / slug / "dfd.md"

    def _latest_dfd(self, slug: str) -> dict | None:
        rows = ledger.read_rows(self.conn, slug, "dfd_approvals")
        return max(rows.values(), key=_approval_number) if rows else None

    def list_systems(self) -> list[dict]:
        return db.list_systems(self.conn)

    def dfd_details(self, slug: str) -> dict[str, dict[str, str]]:
        """Element names and types from the current dfd.md, for display only."""
        return self._parse_dfd(slug).details

    def dfd_approvals(self, slug: str) -> list[dict]:
        rows = ledger.read_rows(self.conn, slug, "dfd_approvals")
        return sorted(rows.values(), key=_approval_number)

    def _require_dfd(self, slug: str) -> dict:
        latest = self._latest_dfd(slug)
        if latest is None:
            raise RegistryError(f"no approved DFD for {slug}; run ./tmreg dfd approve {slug}")
        return latest

    def _parse_dfd(self, slug: str) -> dfd.Dfd:
        path = self._dfd_path(slug)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise RegistryError(f"no dfd.md for {slug}: write systems/{slug}/dfd.md first") from None
        except OSError as e:
            raise RegistryError(f"cannot read {path}: {e.strerror}") from None
        try:
            return dfd.parse(data)
        except dfd.DfdError as e:
            raise RegistryError(str(e)) from None

    def dfd_status(self, slug) -> DfdStatus:
        self._require(slug)
        latest = self._latest_dfd(slug)
        path = self._dfd_path(slug)
        try:
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        except OSError:
            current = None  # unreadable: reported like a missing file
        if latest is None:
            state = "none"
        elif latest["sha256"] == current:
            state = "current"
        else:
            state = "changed"
        return DfdStatus(state=state, latest=latest, current_sha256=current)

    def dfd_preview(self, slug) -> dict:
        self._require(slug)
        parsed = self._parse_dfd(slug)
        latest = self._latest_dfd(slug)
        old = _dfd_ids(latest) if latest else set()
        new = parsed.all_ids()
        removed = sorted(old - new, key=_dfd_id_key)
        gone = set(removed)
        warnings = []
        for r in self.list_risks(slug):
            if r["review_state"] == "rejected" or r["status"] == "retired":
                continue
            cited = [e for e in r["elements"] or () if e in gone]
            if cited:
                warnings.append(f"{r['id']} cites {', '.join(cited)}, which this DFD no longer has")
        return {"dfd": parsed, "added": sorted(new - old, key=_dfd_id_key), "removed": removed,
                "warnings": warnings}

    def dfd_approve(self, session, slug, note, *, expected_sha256: str | None = None) -> dict:
        """Record an approval of dfd.md. With expected_sha256 (the hash the reviewer was shown),
        refuse when the file under the write lock is not that file."""
        _require_session(session)
        note = _require_note(note)
        self._require(slug)
        with self._write():
            parsed = self._parse_dfd(slug)  # under the write lock: this is the file recorded
            if expected_sha256 is not None and parsed.sha256 != expected_sha256:
                raise StaleRecord("dfd.md changed since it was shown; review it again")
            latest = self._latest_dfd(slug)
            if latest is not None and latest["sha256"] == parsed.sha256:
                raise RegistryError(f"already approved as {latest['id']}")
            approval_id = self._allocate(slug, "DFD", "dfd_approvals")
            ledger.write_row(self.conn, slug, "dfd_approvals", approval_id, {
                "version": parsed.version, "sha256": parsed.sha256,
                "ids": {k: list(v) for k, v in parsed.ids.items()},
                "approved_by": session.name, "approved_at": db.now(), "note": note,
            }, op="dfd-approve", actor=f"human:{session.name}")
        self._write_register(slug, approval_id)
        return ledger.read_rows(self.conn, slug, "dfd_approvals")[approval_id]

    # ---- drafting ---------------------------------------------------------------------------

    def _allocate(self, slug: str, prefix: str, tbl: str) -> str:
        """Take the next ID from a sequence. Call only after validation, inside the write."""
        seq = db.table(slug, "sequences")
        row = self.conn.execute(f"SELECT next FROM {seq} WHERE prefix = ?", (prefix,)).fetchone()
        if row is None:
            raise RegistryError(f"sequence {prefix} is missing for {slug}; run ./tmreg verify {slug}")
        n = row["next"]
        new_id = f"DFD-{n}" if prefix == "DFD" else f"{prefix}-{n:02d}"
        t, keycol = db.table(slug, tbl), KEY_COLUMNS[tbl]
        if self.conn.execute(f"SELECT 1 FROM {t} WHERE {keycol} = ?", (new_id,)).fetchone():
            raise RegistryError(f"sequence {prefix} is behind: {new_id} already exists; "
                                f"run ./tmreg verify {slug}")
        self.conn.execute(f"UPDATE {seq} SET next = ? WHERE prefix = ?", (n + 1, prefix))
        return new_id

    def _actor(self, slug: str, run_id) -> str:
        if run_id is None:  # attributed to the reviewer, so only from the reviewer's own terminal
            if not _has_tty():
                raise RegistryError(NO_RUN_MSG)
            if _claude_shell():
                raise RegistryError(NO_RUN_MSG + CLAUDE_SHELL_NOTE)
            return f"human:{self.config.reviewer_name}"
        t = db.table(slug, "runs")
        if not isinstance(run_id, str) or self.conn.execute(
                f"SELECT 1 FROM {t} WHERE run_id = ?", (run_id,)).fetchone() is None:
            raise RegistryError(f"no run {run_id!r} in {slug}; start one with ./tmreg run start {slug}")
        return f"ai:{run_id}"

    def _check_vocab(self, values: dict) -> None:
        checks = (("origin", self.config.origins), ("treatment", TREATMENTS),
                  ("ai_confidence", CONFIDENCE))
        for field, allowed in checks:
            v = values.get(field)
            if v is not None and v not in allowed:
                raise RegistryError(f"{field} must be one of {', '.join(allowed)}; got {v!r}")
        v = values.get("exception_ref")
        if v is not None and not _EXC_RE.fullmatch(v):
            raise RegistryError(f"exception_ref must look like EXC-01; got {v!r}")

    def add_risk(self, slug, fields: dict, *, run_id: str | None) -> dict:
        self._require(slug)
        with self._write():
            actor = self._actor(slug, run_id)
            values = _clean(fields)
            if values.get("status") is None:
                values["status"] = "open"
            _check_status(values["status"])
            _check_required(values, ai=run_id is not None)
            self._check_vocab(values)
            latest = self._require_dfd(slug)
            _check_elements(values["elements"], latest)
            risks = ledger.read_rows(self.conn, slug, "risks").values()
            dup = _possible_duplicate(risks, values["category"], values["elements"])
            risk_id = self._allocate(slug, "T" if values["category"] in STRIDE else "PT", "risks")
            at = db.now()
            ledger.write_row(self.conn, slug, "risks", risk_id, {
                **values, "review_state": "pending", "drafted_by": actor,
                "possible_duplicate_of": dup, "dfd_approval_id": latest["id"],
                "detail_complete": 1, "created_at": at, "updated_at": at,
            }, op="add", actor=actor)
        self._write_register(slug, risk_id)
        return self.get_risk(slug, risk_id)

    def edit_risk(self, slug, risk_id, fields: dict, *, run_id: str | None,
                  seen: dict | None = None, note: str = "") -> dict:
        self._require(slug)
        if note is not None and not isinstance(note, str):
            raise RegistryError("note must be text")
        note = _no_controls("note", note or "").strip()
        with self._write():
            actor = self._actor(slug, run_id)
            cur = self._risk(slug, risk_id)
            self._check_seen(seen, cur)
            if cur["review_state"] == "rejected":
                raise RegistryError("rejected risks are not edited; add a new risk")
            if cur["status"] == "retired":
                raise RegistryError("retired risks are not edited; add a new risk")
            values = _clean(fields)
            if "status" in values:
                if values["status"] is None:
                    raise RegistryError("status cannot be empty")
                _check_status(values["status"])
            cat = values.get("category")
            if cat is not None and (cat in STRIDE) != _is_stride_id(risk_id):
                kind = "STRIDE" if _is_stride_id(risk_id) else "LINDDUN"
                raise RegistryError(f"{risk_id} is a {kind} risk and {cat} is not a {kind} "
                                    "category; add a new risk instead")
            self._check_vocab(values)
            merged = {**cur, **values}
            latest = self._require_dfd(slug)
            _check_elements(merged["elements"], latest)
            _check_required(merged, ai=(cur["drafted_by"] or "").startswith("ai:"))
            update = {k: v for k, v in values.items() if cur.get(k) != v}
            if not update:
                raise RegistryError("no changes")
            keeps_approval = cur["review_state"] == "approved" and not actor.startswith("ai:")
            if cur["review_state"] == "approved":
                if actor.startswith("ai:"):
                    update["last_approved"] = {f: cur[f] for f in SNAPSHOT_FIELDS}
                    update.update(review_state="pending", reviewed_by=None, reviewed_at=None,
                                  review_note=None)
                elif _detail_now_complete(merged):
                    update["detail_complete"] = 1  # the owner filled an imported one-liner
            if not keeps_approval or "elements" in update:
                # An owner edit that keeps the approval moves the DFD basis only when it changes
                # the elements; otherwise "the DFD has moved on" must keep showing.
                update["dfd_approval_id"] = latest["id"]
            update["updated_at"] = db.now()
            ledger.write_row(self.conn, slug, "risks", risk_id, update, op="edit", actor=actor,
                             note=note)
        self._write_register(slug, risk_id)
        return self.get_risk(slug, risk_id)

    # ---- human review -----------------------------------------------------------------------

    def _review_fields(self, session: ReviewerSession, note: str) -> dict:
        return {"reviewed_by": session.name, "reviewed_at": db.now(), "review_note": note}

    @staticmethod
    def _check_seen(seen, cur: dict) -> None:
        """Refuse when the row is not what the reviewer was shown. Runs under the write lock."""
        if seen is not None and any(seen.get(f) != cur.get(f) for f in RISK_FIELDS):
            raise StaleRecord(f"{cur['id']} changed since it was shown; review it again")

    def _require_pending(self, slug: str, risk_id, verb: str) -> dict:
        cur = self._risk(slug, risk_id)
        if cur["review_state"] != "pending":
            raise RegistryError(f"only a pending risk can be {verb}; {risk_id} is "
                                f"{cur['review_state']}")
        return cur

    def approve(self, session, slug, risk_id, note, *, seen: dict | None = None) -> dict:
        _require_session(session)
        note = _require_note(note)
        self._require(slug)
        with self._write():
            self._check_seen(seen, self._risk(slug, risk_id))
            cur = self._require_pending(slug, risk_id, "approved")
            update = {"review_state": "approved", **self._review_fields(session, note),
                      "last_approved": None}
            if _detail_now_complete(cur):
                update["detail_complete"] = 1  # an imported one-liner whose detail is now filled
            ledger.write_row(self.conn, slug, "risks", risk_id, update, op="approve",
                             actor=f"human:{session.name}")
        self._write_register(slug, risk_id)
        return self._risk(slug, risk_id)

    def reject(self, session, slug, risk_id, note, *, seen: dict | None = None) -> dict:
        _require_session(session)
        note = _require_note(note)
        self._require(slug)
        with self._write():
            self._check_seen(seen, self._risk(slug, risk_id))
            cur = self._require_pending(slug, risk_id, "rejected")
            snap = cur["last_approved"]
            if snap is None:
                update = {"review_state": "rejected", **self._review_fields(session, note)}
                op, log_note = "reject", ""
            else:  # a re-review: put back what the last human approval covered
                update = {f: snap[f] for f in SNAPSHOT_FIELDS}
                update.update(review_state="approved", last_approved=None)
                op, log_note = "revert", note
            ledger.write_row(self.conn, slug, "risks", risk_id, update, op=op,
                             actor=f"human:{session.name}", note=log_note)
        self._write_register(slug, risk_id)
        return self._risk(slug, risk_id)

    def merge(self, session, slug, pending_id, into_id, note, *, seen: dict | None = None) -> dict:
        _require_session(session)
        note = _require_note(note)
        self._require(slug)
        with self._write():
            self._check_seen(seen, self._risk(slug, pending_id))
            cur = self._require_pending(slug, pending_id, "merged")
            if cur["last_approved"] is not None:
                raise RegistryError(f"{pending_id} is a re-review of an approved risk; approve or "
                                    "reject the re-review instead of merging it")
            if into_id == pending_id:
                raise RegistryError("a risk cannot be merged into itself")
            target = self._risk(slug, into_id)
            if target["review_state"] == "rejected":
                raise RegistryError(f"{into_id} is rejected; merge into a live risk")
            ledger.write_row(self.conn, slug, "risks", pending_id, {
                "review_state": "rejected", "merged_into": into_id,
                **self._review_fields(session, note),
            }, op="merge", actor=f"human:{session.name}")
        self._write_register(slug, pending_id)
        return self._risk(slug, pending_id)

    def retire(self, session, slug, risk_id, reason, *, seen: dict | None = None) -> dict:
        _require_session(session)
        reason = _require_note(reason, "reason")
        self._require(slug)
        with self._write():
            cur = self._risk(slug, risk_id)
            self._check_seen(seen, cur)
            if cur["review_state"] != "approved":
                raise RegistryError(f"only an approved risk can be retired; {risk_id} is "
                                    f"{cur['review_state']}")
            if cur["status"] == "retired":
                raise RegistryError(f"{risk_id} is already retired")
            ledger.write_row(self.conn, slug, "risks", risk_id, {
                "status": "retired", "status_reason": reason, "updated_at": db.now(),
            }, op="retire", actor=f"human:{session.name}")
        self._write_register(slug, risk_id)
        return self._risk(slug, risk_id)

    def _import_precheck(self, slug):
        """Everything import needs before the write lock: returns (path, rows, commit)."""
        self._require(slug)
        legacy = self.system(slug).legacy_catalog
        if not legacy:
            raise RegistryError("no legacy_catalog in system.toml")
        if ledger.read_rows(self.conn, slug, "risks"):
            raise RegistryError("import-legacy runs once, into an empty register")
        path = self.config.framework_path / legacy
        try:
            rows = catalog.parse(path.read_text(encoding="utf-8"))
        except OSError as e:
            raise RegistryError(f"cannot read {path}: {e.strerror}") from None
        except (catalog.CatalogError, UnicodeDecodeError) as e:
            raise RegistryError(f"{path}: {e}") from None
        commit = framework_commit(self.config.framework_path)  # before taking the write lock
        if commit == "unknown":
            raise RegistryError("cannot read the guide's git commit; import needs it for the "
                                "review note")
        try:
            dirty = subprocess.run(
                ["git", "-C", str(self.config.framework_path), "status", "--porcelain", "--", legacy],
                capture_output=True, text=True, check=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            raise RegistryError("cannot read the guide's git commit; import needs it for the "
                                "review note") from None
        if dirty:
            raise RegistryError("the legacy catalog has uncommitted changes; commit them in the "
                                "guide first")
        return path, rows, commit

    def _import_prepare(self, slug, path, rows):
        """Checks that read the register and DFD: returns (latest approval, [(row, category)])."""
        if ledger.read_rows(self.conn, slug, "risks"):
            raise RegistryError("import-legacy runs once, into an empty register")
        latest = self._require_dfd(slug)
        if not rows:
            raise RegistryError(f"{path} has no catalog rows to import")
        prepared = []
        for r in rows:
            _check_elements(r.elements, latest)
            try:
                category = _category(r.category)
            except RegistryError as e:
                raise RegistryError(f"{r.id}: {e}") from None
            valid = STRIDE if r.id.startswith("T-") else LINDDUN
            if category not in valid:
                raise RegistryError(f"{r.id}: category {r.category!r} does not fit its ID")
            prepared.append((r, category))
        return latest, prepared

    def import_preview(self, slug) -> dict:
        """What import_legacy would do, with the same preconditions and errors. Writes nothing."""
        path, rows, commit = self._import_precheck(slug)
        _, prepared = self._import_prepare(slug, path, rows)
        return {"count": len(prepared), "first": prepared[0][0].id, "last": prepared[-1][0].id,
                "commit": commit}

    def import_legacy(self, session, slug) -> list[str]:
        _require_session(session)
        path, rows, commit = self._import_precheck(slug)
        with self._write():
            latest, prepared = self._import_prepare(slug, path, rows)
            at = db.now()
            actor = f"human:{session.name}"
            note = f"Imported from the guide's reference catalog at commit {commit}"
            top = {"T": 0, "PT": 0}
            for r, category in prepared:
                prefix, num = r.id.rsplit("-", 1)
                top[prefix] = max(top[prefix], int(num))
                ledger.write_row(self.conn, slug, "risks", r.id, {
                    "title": catalog.title_for(r.text), "description": r.text,
                    "elements": r.elements or None, "category": category,
                    "method": "stride-per-element" if r.id.startswith("T-") else "linddun",
                    "origin": "threat-model", "origin_ref": "reference catalog",
                    "status": "open", "review_state": "approved",
                    "drafted_by": "human:catalog-import", "detail_complete": 0,
                    "dfd_approval_id": latest["id"], "reviewed_by": session.name,
                    "reviewed_at": at, "review_note": note, "created_at": at, "updated_at": at,
                }, op="import", actor=actor)
            seq = db.table(slug, "sequences")
            for prefix, n in top.items():
                self.conn.execute(f"UPDATE {seq} SET next = ? WHERE prefix = ?", (n + 1, prefix))
        self._write_register(slug, ", ".join(r.id for r, _ in prepared))
        return [r.id for r, _ in prepared]

    # ---- verification -----------------------------------------------------------------------

    def _table_rows(self, slug: str, tbl: str, problems: list[str]) -> dict[str, dict]:
        """Rows keyed by key column, JSON cells decoded; an undecodable cell is reported and left out."""
        keycol = KEY_COLUMNS[tbl]
        out = {}
        for r in self.conn.execute(f"SELECT * FROM {db.table(slug, tbl)} ORDER BY rowid"):
            row = dict(r)
            for col in JSON_COLUMNS[tbl]:
                if row.get(col) is None:
                    continue
                try:
                    row[col] = json.loads(row[col])
                except (TypeError, ValueError):
                    problems.append(f"{tbl} {row[keycol]}: {col} is not valid JSON")
                    del row[col]
            out[row[keycol]] = row
        return out

    def verify(self, slug) -> list[str]:
        """Check the registry against its own change log. Returns problems; empty means clean."""
        self._require(slug)
        problems: list[str] = []
        try:
            row = self.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            found = row["value"] if row else None
            if found != str(db.SCHEMA_VERSION):
                problems.append(f"schema_version is {found}, expected {db.SCHEMA_VERSION}")
            present = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
            problems += [f"trigger {t} is missing" for t in db.trigger_names(slug) if t not in present]
            problems += ledger.verify_chain(self.conn, slug)
            logged = ledger.replay(self.conn, slug)
            tables = {tbl: self._table_rows(slug, tbl, problems) for tbl in KEY_COLUMNS}
            for tbl in KEY_COLUMNS:
                rows = tables[tbl]
                keys = {k for (t, k) in logged if t == tbl}
                for key in sorted(set(rows) | keys, key=str):
                    if key not in keys:
                        problems.append(f"{tbl} {key} is in the table but not in the change log")
                    elif key not in rows:
                        problems.append(f"{tbl} {key} is in the change log but not in the table")
                    else:
                        want, have = logged[(tbl, key)], rows[key]
                        for field in want:
                            if field in have and want[field] != have[field]:
                                problems.append(f"{tbl} {key}: {field} differs "
                                                f"(log: {want[field]!r}, table: {have[field]!r})")
            problems += self._verify_sequences(slug, tables, logged)
        except sqlite3.Error as e:
            problems.append(f"the database could not be read: {e}")
        return problems

    def _verify_sequences(self, slug: str, tables: dict, logged: dict) -> list[str]:
        top = {"T": 0, "PT": 0, "DFD": 0}
        topid: dict[str, str] = {}
        ids = [(t, k) for t in ("risks", "dfd_approvals") for k in tables[t]] + list(logged)
        for tbl, key in ids:
            m = (_RISK_ID_RE if tbl == "risks" else _DFD_APPROVAL_RE).fullmatch(key) if isinstance(key, str) else None
            if m is None or tbl == "runs":
                continue
            prefix, n = (m.group(1), int(m.group(2))) if tbl == "risks" else ("DFD", int(m.group(1)))
            if prefix not in topid or n > top[prefix]:
                top[prefix], topid[prefix] = n, key
        problems = []
        seqs = {r["prefix"]: r["next"] for r in
                self.conn.execute(f"SELECT prefix, next FROM {db.table(slug, 'sequences')}")}
        for prefix in ("T", "PT", "DFD"):
            nxt = seqs.get(prefix)
            if prefix not in seqs:
                problems.append(f"sequence {prefix} is missing")
            elif not isinstance(nxt, int):
                problems.append(f"sequence {prefix} has a non-numeric value {nxt!r}")
            elif prefix in topid and nxt <= top[prefix]:
                problems.append(f"sequence {prefix} is behind {topid[prefix]}")
        return problems

    # ---- reading ----------------------------------------------------------------------------

    def _risk(self, slug: str, risk_id) -> dict:
        row = ledger.read_rows(self.conn, slug, "risks").get(risk_id)
        if row is None:
            raise RegistryError(f"no risk {risk_id} in {slug}")
        return row

    def get_risk(self, slug, risk_id) -> dict:
        self._require(slug)
        return self._risk(slug, risk_id)

    def list_risks(self, slug, state: str = "all") -> list[dict]:
        self._require(slug)
        if state != "all" and state not in REVIEW_STATES:
            raise RegistryError(f"state must be one of all, {', '.join(REVIEW_STATES)}; got {state!r}")
        rows = ledger.read_rows(self.conn, slug, "risks").values()
        return sorted((r for r in rows if state == "all" or r["review_state"] == state),
                      key=lambda r: id_sort_key(r["id"]))

    def history(self, slug, risk_id: str | None = None) -> list[dict]:
        self._require(slug)
        if risk_id is None:
            return ledger.changes(self.conn, slug)
        self._risk(slug, risk_id)
        return [c for c in ledger.changes(self.conn, slug, risk_id) if c["tbl"] == "risks"]

    def editors(self, slug, risk_id, *, since_last_approval: bool) -> list[str]:
        """Who edited a risk, from the change log: distinct actors of its edit ops, in order.

        With since_last_approval, only the edits after its latest approve, revert, or import, or
        after a human edit that left it approved (an owner edit that keeps the approval resets the
        list too), or every edit if there was no such baseline. Without it, every edit since
        creation."""
        return _editors(self.history(slug, risk_id), since_last_approval)

    # ---- reports ----------------------------------------------------------------------------

    def report(self, slug, fmt: str = "md", *, include_pending=False, include_retired=False,
               include_rejected=False) -> str:
        if fmt not in ("md", "csv", "html"):
            raise RegistryError(f"format must be md, csv, or html; got {fmt!r}")
        self._require(slug)
        changes: dict[str, list[dict]] = {}
        for c in ledger.changes(self.conn, slug):
            if c["tbl"] == "risks":
                changes.setdefault(c["row_key"], []).append(c)
        # Every editor since creation, also on a re-review row's last-approved version: a small
        # overstatement there, kept for simplicity.
        edited_by = {rid: _editors(chs, False) for rid, chs in changes.items()}
        rows = report_mod.select(self.list_risks(slug), include_pending=include_pending,
                                 include_retired=include_retired, include_rejected=include_rejected,
                                 edited_by=edited_by)
        if fmt == "csv":
            return report_mod.render_csv(rows)
        last = self.conn.execute(
            f"SELECT seq, at FROM {db.table(slug, 'changes')} ORDER BY seq DESC LIMIT 1").fetchone()
        stamp = "no changes yet" if last is None else f"change #{last['seq']} ({last['at']})"
        shown = ["approved"] + [name for name, on in (("pending", include_pending),
                                                      ("rejected", include_rejected),
                                                      ("retired", include_retired)) if on]
        scope = ("Approved risks only." if len(shown) == 1 else
                 f"Includes {', '.join(shown[:-1])} and {shown[-1]} risks.")
        title = f"{self.system(slug).name} ({slug})"
        render = report_mod.render_md if fmt == "md" else report_mod.render_html
        return render(rows, title=title, stamp=stamp, scope_note=scope)

    def _write_register(self, slug: str, ref: str | None = None) -> Path:
        """Regenerate register.md (register.trial.md for a trial database) after a committed write."""
        path = self.root / "systems" / slug / ("register.trial.md" if self.is_trial else "register.md")
        try:
            text = self.report(slug, "md")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except Exception as err:
            what = f" ({ref} was written)" if ref else ""
            raise RegistryError(f"the write succeeded{what} but {path.name} could not be "
                                f"regenerated ({err}); run ./tmreg report {slug}") from err
        return path
