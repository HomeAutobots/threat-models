"""Command line: argparse, prompts, and the review loop. Rules live in core; this only asks and shows."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from . import c4, config, core
from .core import Registry, RegistryError, ReviewerSession, StaleRecord
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

def visible(text: str) -> str:
    """Render non-printable characters as escapes (ESC as \\x1b), keeping newlines and tabs, so
    stored text cannot move the cursor, hide itself, or rewrite what the reviewer sees."""
    return "".join(c if c in "\n\t" or c.isprintable() else c.encode("unicode_escape").decode("ascii")
                   for c in text)


def _fmt(value) -> str:
    if value is None or value == "" or value == []:
        return EMPTY
    if isinstance(value, list):
        return visible(", ".join(str(v) for v in value))
    return visible(str(value))


def format_risk(reg: Registry, slug: str, risk: dict, editors=()) -> str:
    """The record as the reviewer sees it. editors: who edited it since its last approval or its
    last owner edit that kept the approval (the caller reads them from the change log; see
    show_risk)."""
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
        if f == "drafted_by" and editors:
            lines.append(f"Edited by (since last approval): {_fmt(list(editors))}")
    snap = risk.get("last_approved")
    if snap:
        lines.append("")
        lines.append("Changes since the last approval (re-review):")
        changed = [f for f in EDITABLE_FIELDS if snap.get(f) != risk.get(f)]
        for f in changed:
            lines += [f"{LABELS[f]}:", f"  - {_fmt(snap.get(f))}", f"  + {_fmt(risk.get(f))}"]
    moved = reg.moved_on(slug, risk)
    if moved["moved_on"]:
        lines.append("")
        lines.append(f"Model has moved on: written against {moved['written_against']}, "
                     f"latest is {moved['latest']} (changed: {', '.join(moved['changed'])})")
    return "\n".join(lines)


def show_risk(reg: Registry, slug: str, risk: dict) -> str:
    return format_risk(reg, slug, risk, reg.editors(slug, risk["id"], since_last_approval=True))


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
    if into == rid:
        raise RegistryError("a risk cannot be merged into itself")
    if seen["last_approved"] is not None:
        raise RegistryError(f"{rid} is a re-review of an approved risk; approve or reject the "
                            "re-review instead of merging it")
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
    if seen["status"] == "retired":
        raise RegistryError(f"{rid} is already retired")
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
    print(show_risk(reg, slug, risk))
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
        except StaleRecord:
            risk = reg.get_risk(slug, rid)
            if risk["review_state"] != "pending":
                print(f"{rid} is no longer pending; skipped.")
                return "gone"
            print(f"{rid} changed since it was shown; showing the current version.")
            print(show_risk(reg, slug, risk))
        except RegistryError as e:
            print(f"tmreg: {e}", file=sys.stderr)


def cmd_review(args, reg, root) -> int:
    session = human_session(reg, "review")
    slug = args.slug
    pending = sorted(reg.list_risks(slug, "pending"),
                     key=lambda r: (r["created_at"] or "", core.id_sort_key(r["id"])))
    reviewed = skipped = 0
    gone = 0
    for i, listed in enumerate(pending):
        risk = reg.get_risk(slug, listed["id"])  # fresh: it may have changed since the list
        if i:
            print()
        if risk["review_state"] != "pending":
            print(f"{risk['id']} is no longer pending; skipped.")
            gone += 1
            continue
        outcome = review_prompt(reg, session, slug, risk)
        if outcome == "quit":
            break
        reviewed += outcome == "reviewed"
        skipped += outcome == "skipped"
        gone += outcome == "gone"
    still = len(reg.list_risks(slug, "pending"))
    extra = f", {gone} no longer pending" if gone else ""
    print(f"{reviewed} reviewed, {skipped} skipped, {still} still pending{extra}")
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
            print(visible(f"{r['id']}  {r['review_state']}  {r['status']}  {r['title']}"))
    return 0


def cmd_show(args, reg, root) -> int:
    risk = reg.get_risk(args.slug, args.id)
    print(json.dumps(risk, indent=2, default=str) if args.json else show_risk(reg, args.slug, risk))
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
    latest = reg.c4_status(args.slug)
    model_line = "none" if latest.latest is None else f"{latest.latest['id']} ({latest.state})"
    print(run["run_id"])
    print(f"methods: {run['methods']}")
    print(f"model: {model_line}")
    if run["evaluation"]:
        print("note: trial register is empty; the catalog is withheld (evaluation mode)")
    return 0


DFD_MOVED = "dfd was replaced by c4: use ./tmreg c4 status|check|approve <slug>"


def cmd_dfd_moved(args, reg, root) -> int:
    print(f"tmreg: {DFD_MOVED}", file=sys.stderr)
    return 2


def cmd_c4_status(args, reg, root) -> int:
    status = reg.c4_status(args.slug)
    print(f"state: {status.state}")
    if status.latest:
        print(f"latest: {status.latest['id']} (version {visible(status.latest['version'])})")
    return 0


def _c4_problem_lines(preview: dict) -> list[str]:
    """One `problem:` line per content problem, parse error, or reused ID."""
    lines = [f"problem: {visible(p)}" for p in preview["problems"]]
    if preview["error"]:
        lines.append(f"problem: {visible(preview['error'])}")
    for iid in preview["reused"]:
        kind = re.match(r"[A-Z]+", iid).group(0)
        line = (f"problem: {iid} was used by an earlier approval; next free {kind}: "
                f"{preview['next_ids'].get(kind, '?')}")
        if iid in preview["reused_dfd"]:
            line += f'; if it is the same boundary, add "tm.was" "{iid}" to it'
        lines.append(line)
    return lines


def _c4_changed(changed: dict) -> str:
    return ", ".join(f"{i} ({'+'.join(fields)})" for i, fields in changed.items()) or "none"


def _c4_summary(slug: str, reg: Registry, preview: dict) -> None:
    """The lines shared by `c4 check` and `c4 approve`, up to the warnings."""
    model = preview["model"]
    if preview["sha256"] is None:
        return
    if model is not None:
        print(f"version: {visible(model.version)}")
    print(f"sha256: {preview['sha256']}")
    if model is None:
        return
    ids = model.ids()
    print("ids: " + " ".join(f"{k}={len(ids[k])}" for k in c4.KINDS))
    if reg.c4_status(slug).latest is None:
        print("added: (no approved model yet)")
    else:
        print(f"added: {', '.join(preview['added']) or 'none'}")
    print(f"removed: {', '.join(preview['removed']) or 'none'}")
    print(f"changed: {_c4_changed(preview['changed'])}")
    print("next: " + " ".join(preview["next_ids"].values()))
    for w in preview["warnings"]:
        print(f"warning: {visible(w)}")


def _c4_adoption_lines(preview: dict) -> list[str]:
    adoption = preview["adoption"]
    if adoption is None:
        return []
    lines = [f"adoption: {g['id']} is cited by {', '.join(g['cited_by'])} and claimed by nothing"
             for g in adoption["gaps"]]
    lines += [f"adoption: {rid} awaits re-review" for rid in adoption["pending_rereviews"]]
    return lines


def _c4_refuse(lines: list[str]) -> None:
    for line in lines:
        print(line)
    raise RegistryError(f"{len(lines)} problem(s); fix workspace.dsl and check again")


def cmd_c4_check(args, reg, root) -> int:
    """Read-only: parse workspace.dsl and show what an approval would record. Prints ok last."""
    preview = reg.c4_preview(args.slug)
    _c4_summary(args.slug, reg, preview)
    for line in _c4_adoption_lines(preview):
        print(visible(line))
    problems = _c4_problem_lines(preview)
    if problems:
        _c4_refuse(problems)
    print("ok")
    return 0


def cmd_c4_approve(args, reg, root) -> int:
    session = human_session(reg, "c4 approve")
    slug = args.slug
    preview = reg.c4_preview(slug)
    latest = reg.c4_status(slug).latest
    # Refused before any prompt: an unchanged file, then one with problems or reused IDs.
    if latest is not None and latest["sha256"] == preview["sha256"]:
        raise RegistryError(f"already approved as {latest['id']}")
    _c4_summary(slug, reg, preview)
    problems = _c4_problem_lines(preview)
    if problems:
        _c4_refuse(problems)
    print(f"If an AI run drafted this model, check that this sha256 matches the one quoted in "
          f"systems/{slug}/runs/<run-id>/model-check.md.")
    adoption = preview["adoption"]
    blockers = _c4_adoption_lines(preview)
    if blockers:
        _c4_refuse(blockers)
    if adoption is not None:
        print(f"adoption: {len(adoption['rewrites'])} risk(s) will move to the new IDs")
    note = ask_note("Approval note: ")
    confirm(slug, "approve")
    # The approval records only the file previewed above; a file changed since is refused.
    approval = reg.c4_approve(session, slug, note, expected_sha256=preview["sha256"])
    print(f"{approval['id']} approved")
    return 0


def cmd_add(args, reg, root) -> int:
    fields = read_json_object(args.json)
    risk = reg.add_risk(args.slug, fields, run_id=args.run)
    print(f"{risk['id']} pending")
    if risk.get("possible_duplicate_of"):
        dup = risk["possible_duplicate_of"]
        print(visible(f"possible duplicate of {dup}: {reg.get_risk(args.slug, dup)['title']}"))
    if args.run is None and core._has_tty():
        session = human_session(reg, "add")
        print()
        print(show_risk(reg, args.slug, risk))
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
    print(show_risk(reg, args.slug, seen))
    _approve(reg, session, args.slug, seen)
    return 0


def cmd_reject(args, reg, root) -> int:
    session = human_session(reg, "reject")
    seen = reg.get_risk(args.slug, args.id)
    print(show_risk(reg, args.slug, seen))
    _reject(reg, session, args.slug, seen)
    return 0


def cmd_merge(args, reg, root) -> int:
    session = human_session(reg, "merge")
    seen = reg.get_risk(args.slug, args.id)
    print(show_risk(reg, args.slug, seen))
    _merge(reg, session, args.slug, seen, args.into)
    return 0


def cmd_retire(args, reg, root) -> int:
    session = human_session(reg, "retire")
    seen = reg.get_risk(args.slug, args.id)
    print(show_risk(reg, args.slug, seen))
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
    db_only = argparse.ArgumentParser(add_help=False)  # c4 check reads only: no --trial
    db_only.add_argument("--db", metavar="PATH", help="use another database file")
    db_only.set_defaults(trial=False)

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

    sp = sub.add_parser("dfd", help="replaced by c4")
    sp.add_argument("rest", nargs=argparse.REMAINDER)
    sp.set_defaults(func=cmd_dfd_moved, human=False)

    c4p = sub.add_parser("c4", help="C4 model approvals").add_subparsers(dest="c4_command", required=True,
                                                                        metavar="subcommand")
    sp = c4p.add_parser("status", parents=[common])
    sp.set_defaults(func=cmd_c4_status, human=False)
    slug(sp)
    sp = c4p.add_parser("check", parents=[db_only], help="parse workspace.dsl and preview an approval")
    sp.set_defaults(func=cmd_c4_check, human=False)
    slug(sp)
    sp = c4p.add_parser("approve", parents=[common], help="human-only")
    sp.set_defaults(func=cmd_c4_approve, human=True, human_name="c4 approve")
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
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] == "dfd":  # any arguments: the parser would reject a leading option
        print(f"tmreg: {DFD_MOVED}", file=sys.stderr)
        return 2
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
    except sqlite3.OperationalError as e:  # locked by another tmreg, or the file cannot be opened
        print(f"tmreg: database is busy or unavailable: {e}", file=sys.stderr)
        return 1
    finally:
        if reg is not None:
            reg.close()
