"""Command line: argparse, prompts, and the review loop. Rules live in core; this only asks and shows."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import config, core
from .core import Registry, RegistryError, ReviewerSession
from .model import EDITABLE_FIELDS, LABELS, NOTE_MIN, REVIEW_STATES, RISK_FIELDS

STATES = ("all",) + tuple(REVIEW_STATES)
LIST_FIELDS = ("elements", "control_refs")
EMPTY = "-"


class Abort(Exception):
    """The reviewer gave an empty answer or the wrong confirmation; nothing was changed."""


# ---- prompts ------------------------------------------------------------------------------------

def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def ask_note(prompt: str = "Note: ", what: str = "note") -> str:
    while True:
        text = _ask(prompt)
        if not text:
            raise Abort
        if len(text) >= NOTE_MIN:
            return text
        print(f"The {what} must be at least {NOTE_MIN} characters ({len(text)} so far).")


def confirm(expected: str, verb: str) -> None:
    if _ask(f"Type {expected} to {verb}: ") != expected:
        raise Abort


# ---- formatting ---------------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None or value == "" or value == []:
        return EMPTY
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def format_risk(reg: Registry, slug: str, risk: dict) -> str:
    lines = []
    for f in RISK_FIELDS:
        if f == "last_approved":
            continue
        value = risk.get(f)
        if f == "possible_duplicate_of" and value:
            try:
                value = f"{value}: {reg.get_risk(slug, value)['title']}"
            except RegistryError:
                pass
        lines.append(f"{LABELS[f]}: {_fmt(value)}")
    snap = risk.get("last_approved")
    if snap:
        lines.append("")
        lines.append("Changes since the last approval (re-review):")
        changed = [f for f in EDITABLE_FIELDS if snap.get(f) != risk.get(f)]
        for f in changed:
            lines += [f"{LABELS[f]}:", f"  - {_fmt(snap.get(f))}", f"  + {_fmt(risk.get(f))}"]
    latest = reg.dfd_status(slug).latest
    drafted = risk.get("dfd_approval_id")
    if latest and drafted and drafted != latest["id"]:
        lines.append("")
        lines.append(f"DFD has moved on: drafted against {drafted}, latest is {latest['id']}")
    return "\n".join(lines)


# ---- registry access ----------------------------------------------------------------------------

def open_registry(args, root: Path) -> Registry:
    return Registry(root, trial=args.trial, db_path=Path(args.db) if args.db else None)


def human_session(reg: Registry, command: str) -> ReviewerSession:
    return ReviewerSession(reg.config.reviewer_name, reg.config.reviewer_email, command)


def read_json_object(source: str) -> dict:
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        data = json.loads(text)
    except OSError as e:
        raise RegistryError(f"cannot read {source}: {e.strerror}") from None
    except ValueError as e:
        raise RegistryError(f"{source} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise RegistryError(f"{source} must hold one JSON object")
    return data


def parse_sets(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        field, sep, value = pair.partition("=")
        field = field.strip()
        if not sep or field not in EDITABLE_FIELDS:
            raise RegistryError(f"--set needs FIELD=VALUE with a field from: {', '.join(EDITABLE_FIELDS)}")
        out[field] = ([v.strip() for v in re.split(r"[;,]", value) if v.strip()]
                      if field in LIST_FIELDS else value)
    return out


# ---- human actions (each shows, asks for a note, then makes the reviewer type the ID) ----------

def _need_pending(risk: dict, verb: str) -> None:
    if risk["review_state"] != "pending":
        raise RegistryError(f"only a pending risk can be {verb}; {risk['id']} is "
                            f"{risk['review_state']}")


def _approve(reg, session, slug, seen) -> None:
    rid = seen["id"]
    _need_pending(seen, "approved")
    note = ask_note("Review note: ")
    confirm(rid, "approve")
    reg.approve(session, slug, rid, note, seen=seen)
    print(f"{rid} approved")


def _reject(reg, session, slug, seen) -> None:
    rid = seen["id"]
    _need_pending(seen, "rejected")
    note = ask_note("Review note: ")
    confirm(rid, "reject")
    result = reg.reject(session, slug, rid, note, seen=seen)
    print(f"{rid} reverted to its last approval" if result["review_state"] == "approved"
          else f"{rid} rejected")


def _merge(reg, session, slug, seen, into) -> None:
    rid = seen["id"]
    _need_pending(seen, "merged")
    if reg.get_risk(slug, into)["review_state"] == "rejected":
        raise RegistryError(f"{into} is rejected; merge into a live risk")
    note = ask_note("Review note: ")
    confirm(rid, "merge")
    reg.merge(session, slug, rid, into, note, seen=seen)
    print(f"{rid} merged into {into}")


def _retire(reg, session, slug, seen, reason) -> None:
    rid = seen["id"]
    if seen["review_state"] != "approved":
        raise RegistryError(f"only an approved risk can be retired; {rid} is {seen['review_state']}")
    if reason is not None and len(reason.strip()) < NOTE_MIN:
        raise RegistryError(f"the reason must be at least {NOTE_MIN} characters")
    if reason is None:
        reason = ask_note("Reason: ", "reason")
    confirm(rid, "retire")
    reg.retire(session, slug, rid, reason, seen=seen)
    print(f"{rid} retired")


def review_prompt(reg, session, slug, risk) -> str:
    """Show one pending risk and act on it. Returns reviewed, skipped, or quit."""
    rid = risk["id"]
    print(format_risk(reg, slug, risk))
    while True:
        choice = _ask("[a]pprove  [r]eject  [m]erge  [s]kip  [q]uit: ").lower()[:1]
        try:
            if choice == "a":
                _approve(reg, session, slug, risk)
            elif choice == "r":
                _reject(reg, session, slug, risk)
            elif choice == "m":
                default = risk.get("possible_duplicate_of")
                target = _ask(f"Merge into [{default}]: " if default else "Merge into: ") or default
                if not target:
                    print("Not changed.")
                    continue
                _merge(reg, session, slug, risk, target)
            elif choice == "s" or choice == "":
                return "skipped"
            elif choice == "q":
                return "quit"
            else:
                continue
            return "reviewed"
        except Abort:
            print("Not changed.")
        except RegistryError as e:
            print(f"tmreg: {e}", file=sys.stderr)


def cmd_review(args, reg, root) -> int:
    session = human_session(reg, "review")
    slug = args.slug
    pending = sorted(reg.list_risks(slug, "pending"),
                     key=lambda r: (r["created_at"] or "", core.id_sort_key(r["id"])))
    reviewed = skipped = 0
    for i, listed in enumerate(pending):
        risk = reg.get_risk(slug, listed["id"])  # fresh: it may have changed since the list
        if i:
            print()
        if risk["review_state"] != "pending":
            print(f"{risk['id']} is no longer pending; skipped.")
            continue
        outcome = review_prompt(reg, session, slug, risk)
        if outcome == "quit":
            break
        reviewed += outcome == "reviewed"
        skipped += outcome == "skipped"
    still = len(reg.list_risks(slug, "pending"))
    print(f"{reviewed} reviewed, {skipped} skipped, {still} still pending")
    return 0


# ---- commands ----------------------------------------------------------------------------------

def cmd_init_system(args, reg, root) -> int:
    reg.init_system(args.slug, args.name)
    print(f"created {args.slug}")
    return 0


def cmd_list(args, reg, root) -> int:
    risks = reg.list_risks(args.slug, args.state)
    if args.json:
        print(json.dumps(risks, indent=2, default=str))
    else:
        for r in risks:
            print(f"{r['id']}  {r['review_state']}  {r['status']}  {r['title']}")
    return 0


def cmd_show(args, reg, root) -> int:
    risk = reg.get_risk(args.slug, args.id)
    print(json.dumps(risk, indent=2, default=str) if args.json else format_risk(reg, args.slug, risk))
    return 0


def cmd_history(args, reg, root) -> int:
    changes = reg.history(args.slug, args.id)
    if args.json:
        print(json.dumps(changes, indent=2, default=str))
    else:
        for c in changes:
            print(f"#{c['seq']}  {c['at']}  {c['op']}  {c['row_key']}  {c['actor']}")
    return 0


def cmd_runs(args, reg, root) -> int:
    for r in reg.runs(args.slug):
        print(f"{r['run_id']}  {r['started_at']}  {r['methods']}  {r['actor']}")
    return 0


def cmd_run_start(args, reg, root) -> int:
    run = reg.start_run(args.slug)
    status = reg.dfd_status(args.slug)
    dfd_line = "none" if status.latest is None else f"{status.latest['id']} ({status.state})"
    print(run["run_id"])
    print(f"methods: {run['methods']}")
    print(f"dfd: {dfd_line}")
    return 0


def cmd_dfd_status(args, reg, root) -> int:
    status = reg.dfd_status(args.slug)
    print(f"state: {status.state}")
    if status.latest:
        print(f"latest: {status.latest['id']} (version {status.latest['version']})")
    return 0


def cmd_dfd_approve(args, reg, root) -> int:
    session = human_session(reg, "dfd approve")
    slug = args.slug
    preview = reg.dfd_preview(slug)
    parsed = preview["dfd"]
    print(f"version: {parsed.version}")
    print(f"sha256: {parsed.sha256}")
    print("counts: " + ", ".join(f"{k} {len(v)}" for k, v in parsed.ids.items()))
    print(f"added: {', '.join(preview['added']) or EMPTY}")
    print(f"removed: {', '.join(preview['removed']) or EMPTY}")
    for w in preview["warnings"]:
        print(f"warning: {w}")
    note = ask_note("Approval note: ")
    confirm(slug, "approve")
    approval = reg.dfd_approve(session, slug, note)
    print(f"{approval['id']} approved")
    return 0


def cmd_add(args, reg, root) -> int:
    fields = read_json_object(args.json)
    risk = reg.add_risk(args.slug, fields, run_id=args.run)
    print(f"{risk['id']} pending")
    if risk.get("possible_duplicate_of"):
        dup = risk["possible_duplicate_of"]
        print(f"possible duplicate of {dup}: {reg.get_risk(args.slug, dup)['title']}")
    if args.run is None and core._has_tty():
        session = human_session(reg, "add")
        print()
        print(format_risk(reg, args.slug, risk))
        if _ask("[a]pprove  [s]kip (stays pending): ").lower()[:1] == "a":
            try:
                _approve(reg, session, args.slug, risk)
            except Abort:
                print(f"Not approved; {risk['id']} stays pending.")
    return 0


def cmd_edit(args, reg, root) -> int:
    fields = read_json_object(args.json) if args.json else parse_sets(args.set)
    risk = reg.edit_risk(args.slug, args.id, fields, run_id=args.run)
    print(f"{risk['id']} {risk['review_state']}")
    return 0


def cmd_approve(args, reg, root) -> int:
    session = human_session(reg, "approve")
    seen = reg.get_risk(args.slug, args.id)
    print(format_risk(reg, args.slug, seen))
    _approve(reg, session, args.slug, seen)
    return 0


def cmd_reject(args, reg, root) -> int:
    session = human_session(reg, "reject")
    seen = reg.get_risk(args.slug, args.id)
    print(format_risk(reg, args.slug, seen))
    _reject(reg, session, args.slug, seen)
    return 0


def cmd_merge(args, reg, root) -> int:
    session = human_session(reg, "merge")
    seen = reg.get_risk(args.slug, args.id)
    print(format_risk(reg, args.slug, seen))
    _merge(reg, session, args.slug, seen, args.into)
    return 0


def cmd_retire(args, reg, root) -> int:
    session = human_session(reg, "retire")
    seen = reg.get_risk(args.slug, args.id)
    print(format_risk(reg, args.slug, seen))
    _retire(reg, session, args.slug, seen, args.reason)
    return 0


def cmd_import_legacy(args, reg, root) -> int:
    session = human_session(reg, "import-legacy")
    slug = args.slug
    preview = reg.import_preview(slug)
    print(f"rows: {preview['count']} ({preview['first']} to {preview['last']})")
    print(f"guide commit: {preview['commit']}")
    confirm(slug, "import")
    ids = reg.import_legacy(session, slug)
    print(f"imported {len(ids)} risks, all approved with detail incomplete")
    return 0


def cmd_report(args, reg, root) -> int:
    text = reg.report(args.slug, args.format, include_pending=args.include_pending,
                      include_retired=args.include_retired, include_rejected=args.include_rejected)
    if args.out:
        try:
            Path(args.out).write_text(text, encoding="utf-8")
        except OSError as e:
            raise RegistryError(f"cannot write {args.out}: {e.strerror}") from None
        print(f"wrote {args.out}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_verify(args, reg, root) -> int:
    problems = reg.verify(args.slug)
    if not problems:
        print("ok")
        return 0
    for p in problems:
        print(f"tmreg: {p}", file=sys.stderr)
    return 1


def cmd_template(args) -> int:
    template = {f: ([] if f in LIST_FIELDS else "") for f in EDITABLE_FIELDS}
    print(json.dumps(template, indent=2))
    return 0


# ---- parser ------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--trial", action="store_true", help="use registry/trial.db")
    common.add_argument("--db", metavar="PATH", help="use another database file")

    p = argparse.ArgumentParser(prog="tmreg", description="Threat-model risk registry")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    def add(name, func, *, human=False, help=None):
        sp = sub.add_parser(name, parents=[common], help=help or ("human-only" if human else None))
        sp.set_defaults(func=func, human=human)
        return sp

    def slug(sp):
        sp.add_argument("slug")

    sp = add("init-system", cmd_init_system)
    slug(sp)
    sp.add_argument("--name", required=True)

    sp = add("list", cmd_list)
    slug(sp)
    sp.add_argument("--state", choices=STATES, default="all")
    sp.add_argument("--json", action="store_true")

    sp = add("show", cmd_show)
    slug(sp)
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")

    sp = add("history", cmd_history)
    slug(sp)
    sp.add_argument("id", nargs="?")
    sp.add_argument("--json", action="store_true")

    sp = add("runs", cmd_runs)
    slug(sp)

    run = sub.add_parser("run", help="runs").add_subparsers(dest="run_command", required=True,
                                                            metavar="subcommand")
    sp = run.add_parser("start", parents=[common])
    sp.set_defaults(func=cmd_run_start, human=False)
    slug(sp)

    dfd = sub.add_parser("dfd", help="DFD approvals").add_subparsers(dest="dfd_command", required=True,
                                                                     metavar="subcommand")
    sp = dfd.add_parser("status", parents=[common])
    sp.set_defaults(func=cmd_dfd_status, human=False)
    slug(sp)
    sp = dfd.add_parser("approve", parents=[common], help="human-only")
    sp.set_defaults(func=cmd_dfd_approve, human=True, human_name="dfd approve")
    slug(sp)

    sp = add("add", cmd_add)
    slug(sp)
    grp = sp.add_mutually_exclusive_group(required=True)
    grp.add_argument("--json", metavar="PATH|-")
    grp.add_argument("--template", action="store_true")
    sp.add_argument("--run")
    sp.set_defaults(template_func=cmd_template)

    sp = add("edit", cmd_edit)
    slug(sp)
    sp.add_argument("id")
    grp = sp.add_mutually_exclusive_group(required=True)
    grp.add_argument("--json", metavar="PATH|-")
    grp.add_argument("--set", action="append", metavar="FIELD=VALUE")
    sp.add_argument("--run")

    sp = add("review", cmd_review, human=True)
    slug(sp)
    for name, func in (("approve", cmd_approve), ("reject", cmd_reject)):
        sp = add(name, func, human=True)
        slug(sp)
        sp.add_argument("id")
    sp = add("merge", cmd_merge, human=True)
    slug(sp)
    sp.add_argument("id", metavar="pending-id")
    sp.add_argument("--into", required=True)
    sp = add("retire", cmd_retire, human=True)
    slug(sp)
    sp.add_argument("id")
    sp.add_argument("--reason")
    sp = add("import-legacy", cmd_import_legacy, human=True)
    slug(sp)

    sp = add("report", cmd_report)
    slug(sp)
    sp.add_argument("--format", choices=("md", "csv", "html"), default="md")
    sp.add_argument("--include-pending", action="store_true")
    sp.add_argument("--include-retired", action="store_true")
    sp.add_argument("--include-rejected", action="store_true")
    sp.add_argument("--out", metavar="PATH")

    sp = add("verify", cmd_verify)
    slug(sp)
    return p


def main(argv: list[str] | None = None, *, project_root: Path | None = None) -> int:
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    args = build_parser().parse_args(argv)
    reg = None
    try:
        if getattr(args, "template", False):
            if args.run:
                build_parser().error("--template does not take --run")
            return args.template_func(args)
        if args.human:  # before the database opens, a file is read, or anything is printed
            core.require_interactive(getattr(args, "human_name", args.command))
        reg = open_registry(args, root)
        return args.func(args, reg, root)
    except Abort:
        print("Not changed.")
        return 1
    except (RegistryError, config.ConfigError) as e:
        print(f"tmreg: {e}", file=sys.stderr)
        return 1
    finally:
        if reg is not None:
            reg.close()
