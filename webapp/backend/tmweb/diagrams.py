"""Structurizr's static viewer for a system's C4 model (spec section 8).

`export` runs one Docker export of bytes tmreg has already checked, and keeps the site by the
sha256 of those bytes:

    diagrams/<reg>/<slug>/<sha256>/
        result.json      what Structurizr said, the inline-script hashes, and the view keys
        in/workspace.dsl the checked bytes, and the only file Docker sees (mounted read-write)
        in/site/         what Structurizr wrote: the only folder /diagrams serves

A result is kept only when it is Structurizr's own verdict on the bytes, and an accepted one only
when the site's inline scripts are the reviewed ones (c4.EXPECTED_INLINE_HASHES). diagrams/ and the
folders in it must be real folders, never links. `verdict` reads result.json back for GET .../c4,
and `find` resolves a file for the /diagrams route. The route, its lock and its CSP live in app.py.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from tmreg import c4, db

REGS = ("main", "trial")
KEEP = 5  # exports kept per system and register
TAIL = 20  # lines of Structurizr's stderr shown when it refuses a file
STALE_TMP = 3600  # seconds before a temp folder left by a crash is removed
NO_DOCKER = ("Docker isn't running. Start Docker (Docker Desktop or OrbStack), then open the "
             "diagrams again.")
TOO_SLOW = "Structurizr took too long to export the diagrams. Try again."
NO_INDEX = "Structurizr exported no index.html."
STARTED = "Docker couldn't be started: "  # then the error
LINKED = ("The diagrams folder in the repo, and each folder in it, must be a real folder, not a "
          "link. Remove the link, then open the diagrams again.")
COLON = ("Docker can't mount the diagrams folder, because the repo's path has a colon in it. "
         "Move the repo to a path without one, then open the diagrams again.")
VIEWER_CHANGED = ("This Structurizr image's viewer isn't the one reviewed for the app's CSP: its "
                  "inline scripts changed. Review its JavaScript, then update "
                  "c4.EXPECTED_INLINE_HASHES.")
# Structurizr's export prints this on stdout once it runs. Without it, Docker never started
# Structurizr, so its stderr is Docker's, never the AI-written DSL that Structurizr echoes.
_RAN = "Exporting workspace from"
# What Docker's CLI prints when it can't reach the daemon: before version 29 ("docker: Cannot
# connect ...", exit code 125), and from 29 ("failed to connect to the docker API at ...").
_NO_DAEMON = ("Cannot connect to the Docker daemon", "failed to connect to the docker API")
# From 125 up, Docker or the OS stopped the run (125-127: Docker couldn't start it; 128+n: a
# signal, such as a kill when memory ran out). That is no verdict on the file, so it isn't kept.
_NOT_A_VERDICT = 125
_MOUNT = "/usr/local/structurizr"
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_TMP_RE = re.compile(r"[0-9a-f]{64}\.tmp-[0-9a-f]{16}")
HASH_RE = re.compile(r"'sha256-[A-Za-z0-9+/]{43}='")
_NOT_CHECKED = {"state": "not-checked", "message": None, "base": None, "views": []}
_TYPES = mimetypes.MimeTypes()  # Python's own table only, not the machine's mime.types files


class DiagramsUnavailable(Exception):
    """The export could not run; the message is shown to the owner as is."""


class LinkedFolder(ValueError):
    """diagrams/ or a folder in it is a link, or the target resolves outside the repo's diagrams/."""


def site_dir(root: Path, reg: str, slug: str, sha256: str) -> Path:
    if reg not in REGS:
        raise ValueError(f"unknown register {reg!r}")
    db.validate_slug(slug)
    if not isinstance(sha256, str) or not _SHA_RE.fullmatch(sha256):
        raise ValueError("sha256 must be 64 lowercase hex characters")
    target = Path(root) / "diagrams" / reg / slug / sha256
    _refuse_links(Path(root), target)
    return target


def _refuse_links(root: Path, target: Path) -> None:
    """Raise LinkedFolder if diagrams/, <reg>/, <slug>/ or <sha256>/ is a link (by lstat), or if
    the target resolves outside the repo's own diagrams/. A link above them, in the repo's own
    path, is resolved first and is fine."""
    folder = root / "diagrams"
    chain = [folder]
    for part in target.relative_to(folder).parts:
        folder = folder / part
        chain.append(folder)
    if any(p.is_symlink() for p in chain):
        raise LinkedFolder(LINKED)
    if not target.resolve().is_relative_to(root.resolve() / "diagrams"):
        raise LinkedFolder(LINKED)


def _check_links(root: Path, target: Path) -> None:
    """_refuse_links for the export, which shows the owner why."""
    try:
        _refuse_links(root, target)
    except LinkedFolder as e:
        raise DiagramsUnavailable(str(e)) from None


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inline: list[str] = []
        self._text: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._text = None if any(name == "src" for name, _ in attrs) else []

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            if self._text is not None:
                self.inline.append("".join(self._text))
            self._text = None


def inline_script_hashes(html: str) -> list[str]:
    """A CSP source, "'sha256-<base64>'", for each <script> without a src, in page order.

    Hashed the way a browser does: over the UTF-8 of the script's text, after the HTML parser's
    newline normalization (CRLF and CR become LF) and its NUL replacement."""
    html = html.replace("\r\n", "\n").replace("\r", "\n").replace("\0", "\ufffd")
    parser = _Scripts()
    parser.feed(html)
    parser.close()
    return ["'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest())
            .decode("ascii") + "'" for text in parser.inline]


def view_url(base: str, key: str) -> str:
    """The static site's link to one view: index.html reads the view key from the URL's hash
    (decodeURIComponent of the hash without its "#") and shows the view with that exact key."""
    return base + "#" + urllib.parse.quote(key, safe="")


def _command(in_dir: Path, name: str) -> list[str]:
    # --name lets a timed-out run be removed. --read-only needs the --tmpfs: the launcher unpacks
    # the app into /tmp. The image already runs as a non-root user; --user makes it the server's
    # own, so it can write into in_dir.
    return ["docker", "run", "--rm", "--name", name, "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--read-only", "--tmpfs", "/tmp",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{in_dir}:{_MOUNT}", c4.STRUCTURIZR_IMAGE,
            "export", "-workspace", "workspace.dsl", "-format", "static", "-output", "site"]


def _read_result(target: Path) -> dict | None:
    """result.json, or None if it is missing or not one this module wrote."""
    try:
        result = json.loads((target / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or set(result) != {"state", "message", "hashes", "views"}:
        return None
    state, message, hashes, views = (result[k] for k in ("state", "message", "hashes", "views"))
    if state == "accepted":
        # Only this image's reviewed scripts: an export from another viewer is exported again.
        ok = (message is None and hashes == list(c4.EXPECTED_INLINE_HASHES)
              and all(isinstance(h, str) and HASH_RE.fullmatch(h) for h in hashes)
              and isinstance(views, list) and all(isinstance(v, str) for v in views))
    else:
        ok = state == "refused" and isinstance(message, str) and hashes == [] and views == []
    return result if ok else None


def _touch(target: Path) -> None:
    """Mark an export as just used, so pruning keeps the one the owner has open."""
    try:
        os.utime(target)
    except OSError:
        pass


def _reuse(target: Path) -> dict | None:
    """The kept result for these bytes, or None to export them. Only a result.json that exists and
    fails the check marks the folder as damaged, and it is read again just before the folder is
    removed, in case another export of the same bytes has just put a good one in place."""
    done = _read_result(target)
    if done is None and (target / "result.json").exists():
        done = _read_result(target)
        if done is None:
            shutil.rmtree(target, ignore_errors=True)
    if done is not None:
        _touch(target)
    return done


def _remove(run, name: str) -> None:
    """Remove a timed-out run's container, so it doesn't keep running. Errors are ignored: it may
    never have started."""
    try:
        run(["docker", "rm", "-f", name], capture_output=True, text=True, errors="replace",
            stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def _run(run, in_dir: Path, name: str, timeout: int, views: list[str]) -> tuple[dict, bool]:
    """(the result, whether it is Structurizr's verdict on the bytes and so kept)."""
    try:
        proc = run(_command(in_dir, name), capture_output=True, text=True, errors="replace",
                   stdin=subprocess.DEVNULL, timeout=timeout)
    except FileNotFoundError:
        raise DiagramsUnavailable(NO_DOCKER) from None
    except OSError as e:  # found but not runnable, for example
        raise DiagramsUnavailable(STARTED + str(e)) from None
    except subprocess.TimeoutExpired:
        _remove(run, name)
        raise DiagramsUnavailable(TOO_SLOW) from None
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    if proc.returncode != 0:
        tail = "\n".join(stderr.splitlines()[-TAIL:])
        refused = {"state": "refused", "message": tail, "hashes": [], "views": []}
        if _RAN in stdout:  # Structurizr ran: its refusal, unless Docker or the OS stopped it
            return refused, 0 < proc.returncode < _NOT_A_VERDICT
        if any(s in stderr for s in _NO_DAEMON):
            raise DiagramsUnavailable(NO_DOCKER)
        return refused, False  # Docker's own error: shown, not kept
    try:
        html = (in_dir / "site" / "index.html").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"state": "refused", "message": NO_INDEX, "hashes": [], "views": []}, False
    hashes = inline_script_hashes(html)
    if hashes != list(c4.EXPECTED_INLINE_HASHES):
        return {"state": "refused", "message": VIEWER_CHANGED, "hashes": [], "views": []}, False
    return {"state": "accepted", "message": None, "hashes": hashes, "views": views}, True


def _prune(folder: Path, current: str) -> None:
    """Keep the newest KEEP exports (by mtime) in a system's folder, the current one included,
    and remove temp folders that a crashed export left long ago."""
    others = []
    now = time.time()
    for p in folder.iterdir():
        try:
            if p.is_symlink() or not p.is_dir():
                continue
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if p.name != current and _SHA_RE.fullmatch(p.name):
            others.append((mtime, p.name))
        elif _TMP_RE.fullmatch(p.name) and now - mtime > STALE_TMP:
            shutil.rmtree(p, ignore_errors=True)
    others.sort(reverse=True)
    for _, name in others[KEEP - 1:]:
        shutil.rmtree(folder / name, ignore_errors=True)


def export(root: Path, reg: str, slug: str, data: bytes, sha256: str, *, run=subprocess.run,
           timeout: int = 120) -> dict:
    """Export `data` (bytes tmreg checked) once per sha256; later calls reuse the result.

    Returns result.json: {"state": "accepted"|"refused", "message", "hashes", "views"}. Raises
    DiagramsUnavailable when Docker can't run the export, or diagrams/ holds a link; nothing is
    kept then. A refusal is kept only when Structurizr itself ran and refused the bytes; Docker's
    own errors, a run Docker or the OS stopped, and a viewer whose scripts aren't the reviewed
    ones are returned as refused but not kept."""
    root = Path(os.path.abspath(root))  # Docker's -v needs an absolute path
    try:
        target = site_dir(root, reg, slug, sha256)
    except LinkedFolder as e:
        raise DiagramsUnavailable(str(e)) from None
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("the bytes do not have that sha256")
    if ":" in str(target):  # -v splits on it
        raise DiagramsUnavailable(COLON)
    done = _reuse(target)
    if done is not None:
        return done
    views = list(c4.parse(data).views)  # the keys the links name, in the file's order
    target.parent.mkdir(parents=True, exist_ok=True)
    _check_links(root, target)  # again: nothing became a link while the folders were made
    # Export beside the target, then rename it into place, so two clicks can't collide.
    token = secrets.token_hex(8)
    tmp = target.with_name(f"{target.name}.tmp-{token}")
    in_dir = tmp / "in"
    try:
        in_dir.mkdir(parents=True)
        (in_dir / "workspace.dsl").write_bytes(data)
        result, keep = _run(run, in_dir, f"tm-c4-export-{sha256[:12]}-{token}", timeout, views)
        if not keep:
            return result
        (tmp / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        _check_links(root, target)
        try:
            os.replace(tmp, target)
        except OSError:
            done = _read_result(target)  # another export of the same bytes finished first
            if done is None:
                raise
            _touch(target)
            return done
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        _refuse_links(root, target)
    except LinkedFolder:
        return result  # the export is in place; never prune through a link
    _prune(target.parent, sha256)
    return result


def shown(reg: str, slug: str, sha256: str, result: dict) -> dict:
    """What the page shows for a result: the state and message, and for an accepted export the
    site's base and a link to each view."""
    if result["state"] != "accepted":
        return {"state": "refused", "message": result["message"], "base": None, "views": []}
    base = f"/diagrams/{reg}/{slug}/{sha256}/"
    return {"state": "accepted", "message": None, "base": base,
            "views": [{"key": k, "url": view_url(base, k)} for k in result["views"]]}


def verdict(root: Path, reg: str, slug: str, sha256: str | None) -> dict:
    """Structurizr's verdict on these exact bytes: "not-checked" until they are exported."""
    if sha256 is None:
        return dict(_NOT_CHECKED)
    try:
        target = site_dir(root, reg, slug, sha256)
    except ValueError:
        return dict(_NOT_CHECKED)
    result = _read_result(target)
    return dict(_NOT_CHECKED) if result is None else shown(reg, slug, sha256, result)


def find(root: Path, reg: str, slug: str, sha256: str, path: str) -> tuple[Path, list[str]] | None:
    """The file to serve for /diagrams/<reg>/<slug>/<sha256>/<path>, with the export's script
    hashes; None unless it is a regular file inside an accepted export's site folder."""
    try:
        target = site_dir(root, reg, slug, sha256)
        result = _read_result(target)
        if result is None or result["state"] != "accepted":
            return None
        real = target.resolve(strict=True)
        site = real / "in" / "site"
        if site.resolve(strict=True) != site:  # neither in/ nor site/ is a link
            return None
        file = (site / (path or "index.html")).resolve(strict=True)
    except (OSError, ValueError, RuntimeError):  # missing, a NUL byte, a symlink loop
        return None
    if not file.is_relative_to(site) or not file.is_file():
        return None
    return file, result["hashes"]


def media_type(file: Path) -> str:
    return _TYPES.guess_type(file.name)[0] or "application/octet-stream"
