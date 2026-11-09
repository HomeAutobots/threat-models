"""The diagrams: POST .../c4/export runs one Structurizr export, and /diagrams serves it behind the
lock. A fake runner stands in for Docker here; test_diagrams_docker.py runs the real one."""
import asyncio
import base64
import functools
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from unittest import mock

import helpers
import pytest
from fastapi.testclient import TestClient

from tmreg import c4
from tmreg.core import Registry
from tmweb import diagrams
from tmweb.app import CSP, create_app
from tmweb.security import COOKIE

BASE = "http://127.0.0.1:8765"
C4 = "/api/main/systems/demo/c4"
EXPORT = C4 + "/export"
SHA = hashlib.sha256(helpers.SAMPLE_WORKSPACE).hexdigest()
SITE = f"/diagrams/main/demo/{SHA}/"
VIEWS = ["context", "containers", "deployment-ENV1"]  # sample.dsl's views, in file order
INLINE = "\n    const greeting = '<b>hi</b>';\n"
INDEX = ('<!DOCTYPE html>\n<html><head><script type="text/javascript" src="./js/a.js"></script>'
         f'</head><body></body></html>\n<script>{INLINE}</script>\n')
NO_DOCKER = "Docker isn't running. Start Docker Desktop, then open the diagrams again."
TOO_SLOW = "Structurizr took too long to export the diagrams. Try again."
NOT_CHECKED = {"state": "not-checked", "message": None, "base": None, "views": []}
REAL_EXPORT = diagrams.export
MOUNT = ":/usr/local/structurizr"


def source(text: str) -> str:
    """The CSP source for an inline script with this text."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode() + "'"


def variant(i: int) -> bytes:
    """sample.dsl with one description changed: still checked, but another sha256."""
    data = helpers.SAMPLE_WORKSPACE.replace(b'"Answers the web app."',
                                            f'"Answers the web app, take {i}."'.encode())
    assert data != helpers.SAMPLE_WORKSPACE
    return data


class FakeDocker:
    """Stands in for subprocess.run: records each call and what the mounted folder held, then
    writes a small site the way Structurizr does (into site/ under the mount)."""

    def __init__(self, returncode=0, stderr="", raises=None, before=None):
        self.returncode, self.stderr, self.raises, self.before = returncode, stderr, raises, before
        self.calls: list = []
        self.mounted: list = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        if self.before is not None:
            self.before()
        if self.raises is not None:
            raise self.raises
        mount = args[args.index("-v") + 1]
        assert mount.endswith(MOUNT)
        in_dir = Path(mount[: -len(MOUNT)])
        self.mounted.append({p.name: p.read_bytes() for p in in_dir.iterdir()})
        if self.returncode == 0:
            site = in_dir / "site"
            (site / "js").mkdir(parents=True)
            (site / "index.html").write_text(INDEX)
            (site / "js" / "a.js").write_text("var a = 1;\n")
        return subprocess.CompletedProcess(args, self.returncode, "", self.stderr)


def fake_export(fake):
    """Patch the route's export so it runs `fake` instead of Docker."""
    return mock.patch.object(diagrams, "export", functools.partial(REAL_EXPORT, run=fake))


@pytest.fixture
def docker():
    fake = FakeDocker()
    with fake_export(fake):
        yield fake


def raw_get(app, path: str, cookie: str) -> int:
    """Call the ASGI app with a path exactly as given. The test client (like a browser) removes
    "../" before sending; a raw HTTP client would not."""
    sent = []
    received = []

    async def receive():
        if not received:
            received.append(True)
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # the client stays connected until the response is sent

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "http_version": "1.1", "method": "GET", "path": path,
             "raw_path": path.encode(), "query_string": b"", "scheme": "http",
             "headers": [(b"host", b"127.0.0.1:8765"), (b"cookie", f"{COOKIE}={cookie}".encode())],
             "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 50000), "root_path": ""}
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


def test_inline_script_hashes():
    html = ("<html><head><script type='text/javascript' src='./js/x.js'></script>"
            "<script>alert(1)</script></head>"
            "<body><SCRIPT>\nvar b = '</span>' + 1;\n</SCRIPT></body></html>")
    assert diagrams.inline_script_hashes(html) == [source("alert(1)"),
                                                  source("\nvar b = '</span>' + 1;\n")]
    # A browser hashes the text after its newline normalization, so CRLF and CR count as LF.
    assert diagrams.inline_script_hashes("<script>a\r\nb\rc</script>") == [source("a\nb\nc")]
    assert diagrams.inline_script_hashes("<p>no scripts</p>") == []


def test_view_url():
    base = f"/diagrams/main/demo/{SHA}/"
    # The viewer reads the view key from the hash (index.html: decodeURIComponent of the hash
    # without its "#"); test_diagrams_docker.py pins that against the real site.
    assert diagrams.view_url(base, "SEQ1") == base + "#SEQ1"
    assert diagrams.view_url(base, "deployment-ENV1") == base + "#deployment-ENV1"
    assert diagrams.view_url(base, "a b/#c") == base + "#a%20b%2F%23c"


def test_site_dir_takes_only_valid_names(tmp_path):
    assert diagrams.site_dir(tmp_path, "trial", "demo", SHA) == tmp_path / "diagrams" / "trial" / "demo" / SHA
    for reg, slug, sha in (("other", "demo", SHA), ("main", "Demo", SHA), ("main", "..", SHA),
                           ("main", "demo", SHA.upper()), ("main", "demo", SHA[:-1]),
                           ("main", "demo", "../" + SHA[3:])):
        with pytest.raises(ValueError):
            diagrams.site_dir(tmp_path, reg, slug, sha)


def test_export_runs_docker_exactly(client, project, docker):
    # The export writes the bytes c4_checked_bytes checked, even if the file changes afterwards.
    checked = Registry.c4_checked_bytes

    def checked_then_changed(self, slug):
        out = checked(self, slug)
        (project / "systems" / "demo" / "workspace.dsl").write_bytes(b"changed after the check")
        return out

    with mock.patch.object(Registry, "c4_checked_bytes", checked_then_changed):
        r = client.post(EXPORT)
    assert r.status_code == 200, r.text
    ((args, kwargs),) = docker.calls
    in_dir = Path(args[args.index("-v") + 1][: -len(MOUNT)])
    folder = project / "diagrams" / "main" / "demo"
    # It exports into a temp folder beside the target, then renames that into place.
    assert in_dir.name == "in" and in_dir.parent.parent == folder
    assert in_dir.parent.name.startswith(SHA + ".tmp-")
    assert args == [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only", "--tmpfs", "/tmp",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{in_dir}{MOUNT}", c4.STRUCTURIZR_IMAGE,
        "export", "-workspace", "workspace.dsl", "-format", "static", "-output", "site"]
    assert kwargs["timeout"] == 120 and kwargs["capture_output"] is True
    assert kwargs.get("shell") is not True
    assert docker.mounted == [{"workspace.dsl": helpers.SAMPLE_WORKSPACE}]
    assert [p.name for p in folder.iterdir()] == [SHA]  # the temp folder is gone
    target = folder / SHA
    assert sorted(p.name for p in target.iterdir()) == ["in", "result.json"]
    result = json.loads((target / "result.json").read_text())
    assert result == {"state": "accepted", "message": None, "hashes": [source(INLINE)],
                      "views": VIEWS}
    assert (target / "in" / "site" / "index.html").read_text() == INDEX
    assert r.json() == {"sha256": SHA, "state": "accepted", "message": None, "base": SITE,
                        "views": [{"key": k, "url": SITE + "#" + k} for k in VIEWS]}


def test_export_reuses_result_for_same_sha(client, project, docker):
    first = client.post(EXPORT)
    assert first.status_code == 200, first.text
    again = client.post(EXPORT)
    assert again.json() == first.json()
    assert len(docker.calls) == 1
    (project / "systems" / "demo" / "workspace.dsl").write_bytes(variant(1))
    other = client.post(EXPORT).json()
    assert other["sha256"] == hashlib.sha256(variant(1)).hexdigest() != SHA
    assert len(docker.calls) == 2


def test_two_exports_of_the_same_bytes_do_not_collide(tmp_path):
    data = helpers.SAMPLE_WORKSPACE
    # A second click's export finishes first, while this one is still running.
    racer = FakeDocker()
    slow = FakeDocker(before=lambda: REAL_EXPORT(tmp_path, "main", "demo", data, SHA, run=racer))
    result = REAL_EXPORT(tmp_path, "main", "demo", data, SHA, run=slow)
    assert len(racer.calls) == 1 and len(slow.calls) == 1
    target = diagrams.site_dir(tmp_path, "main", "demo", SHA)
    assert result == json.loads((target / "result.json").read_text())
    assert result["state"] == "accepted"
    assert [p.name for p in target.parent.iterdir()] == [SHA]  # the loser's temp folder is gone


def test_export_keeps_the_newest_five(tmp_path):
    folder = tmp_path / "diagrams" / "main" / "demo"
    shas = []
    for i in range(7):
        data = variant(i)
        sha = hashlib.sha256(data).hexdigest()
        shas.append(sha)
        REAL_EXPORT(tmp_path, "main", "demo", data, sha, run=FakeDocker())
        t = 1_700_000_000 + i * 60  # distinct mtimes, oldest first
        os.utime(folder / sha, (t, t))
    assert sorted(p.name for p in folder.iterdir()) == sorted(shas[2:])
    # By mtime, not by the order they were made: shas[2] now looks the newest of the old ones.
    t = time.time() + 3600
    os.utime(folder / shas[2], (t, t))
    stale = folder / f"{SHA}.tmp-0123456789abcdef"  # left by a crashed export, long ago
    stale.mkdir()
    os.utime(stale, (1, 1))
    fresh = folder / f"{SHA}.tmp-fedcba9876543210"  # an export still running
    fresh.mkdir()
    (folder / "notes.txt").write_text("not an export")
    REAL_EXPORT(tmp_path, "trial", "demo", variant(9), hashlib.sha256(variant(9)).hexdigest(),
                run=FakeDocker())  # another register: its own five
    assert len(list(folder.glob("[0-9a-f]" * 64))) == 5
    data = variant(7)
    sha = hashlib.sha256(data).hexdigest()
    REAL_EXPORT(tmp_path, "main", "demo", data, sha, run=FakeDocker())
    kept = sorted(p.name for p in folder.iterdir())
    assert kept == sorted([shas[2], *shas[4:7], sha, fresh.name, "notes.txt"])
    assert len(list((tmp_path / "diagrams" / "trial" / "demo").iterdir())) == 1


def test_export_refused(client, project, docker):
    docker.returncode = 1
    docker.stderr = "".join(f"line {i}\n" for i in range(1, 31))
    r = client.post(EXPORT)
    assert r.status_code == 200, r.text
    tail = "\n".join(f"line {i}" for i in range(11, 31))  # the last 20 lines of stderr
    refused = {"state": "refused", "message": tail, "base": None, "views": []}
    assert r.json() == {"sha256": SHA, **refused}
    result = json.loads((project / "diagrams" / "main" / "demo" / SHA / "result.json").read_text())
    assert result == {"state": "refused", "message": tail, "hashes": [], "views": []}
    assert client.get(C4).json()["structurizr"] == refused
    assert client.get(SITE).status_code == 404  # a refused export is never served
    assert client.post(EXPORT).json() == r.json()
    assert len(docker.calls) == 1  # the result is kept for this sha256


@pytest.mark.parametrize("returncode,stderr", [
    (125, "docker: Error response from daemon: Mounts denied: the path is not shared.\n"),
    (125, "Unable to find image locally\ndocker: Error response from daemon: pull failed.\n"),
    (137, ""),  # killed, for example when memory ran out
], ids=["mounts-denied", "no-image", "killed"])
def test_a_docker_failure_is_not_kept_as_a_verdict(client, project, returncode, stderr):
    fake = FakeDocker(returncode=returncode, stderr=stderr)
    with fake_export(fake):
        r = client.post(EXPORT)
        assert r.status_code == 200, r.text
        assert r.json() == {"sha256": SHA, "state": "refused", "message": stderr.rstrip("\n"),
                            "base": None, "views": []}
        # Structurizr never ran, so nothing is kept: the page still says "not checked", and
        # the next click (once Docker is fixed) runs the export again.
        assert list((project / "diagrams" / "main" / "demo").iterdir()) == []
        assert client.get(C4).json()["structurizr"] == NOT_CHECKED
        client.post(EXPORT)
    assert len(fake.calls) == 2


def test_export_with_no_index_html_is_refused(tmp_path):
    def no_site(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "", "")

    result = REAL_EXPORT(tmp_path, "main", "demo", helpers.SAMPLE_WORKSPACE, SHA, run=no_site)
    assert result["state"] == "refused" and "index.html" in result["message"]


@pytest.mark.parametrize("fake", [
    FakeDocker(raises=FileNotFoundError(2, "No such file or directory", "docker")),
    # Docker's CLI before 29, and with exit code 125.
    FakeDocker(returncode=125, stderr=(
        "docker: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
        "Is the docker daemon running?\nSee 'docker run --help'.\n")),
    # Docker's CLI 29 (seen on 2026-11-09 with the daemon unreachable): exit code 1.
    FakeDocker(returncode=1, stderr=(
        "failed to connect to the docker API at unix:///Users/x/.docker/run/docker.sock; check "
        "if the path is correct and if the daemon is running: dial unix "
        "/Users/x/.docker/run/docker.sock: connect: no such file or directory\n")),
], ids=["no-docker-command", "cannot-connect-125", "failed-to-connect"])
def test_export_without_docker(client, project, fake):
    with fake_export(fake):
        r = client.post(EXPORT)
    assert r.status_code == 503
    assert r.json() == {"detail": NO_DOCKER}
    assert len(fake.calls) == 1
    folder = project / "diagrams" / "main" / "demo"
    assert list(folder.iterdir()) == []  # nothing kept: the next click tries again
    assert client.get(C4).json()["structurizr"] == NOT_CHECKED


def test_export_timeout(client, project):
    fake = FakeDocker(raises=subprocess.TimeoutExpired(["docker"], 120))
    with fake_export(fake):
        r = client.post(EXPORT)
    assert r.status_code == 503
    assert r.json() == {"detail": TOO_SLOW}
    assert fake.calls[0][1]["timeout"] == 120
    assert list((project / "diagrams" / "main" / "demo").iterdir()) == []
    assert client.get(C4).json()["structurizr"] == NOT_CHECKED


@pytest.mark.parametrize("data", [
    b"workspace {",
    helpers.SAMPLE_WORKSPACE.replace(b'"tm.auth" "Session cookie"', b'"tm.auth" ""'),
], ids=["does-not-parse", "has-a-problem"])
def test_export_refuses_unchecked_file(client, project, docker, data):
    (project / "systems" / "demo" / "workspace.dsl").write_bytes(data)
    r = client.post(EXPORT)
    assert r.status_code == 422
    assert "workspace.dsl" in r.json()["detail"]
    assert docker.calls == []
    assert not (project / "diagrams").exists()


def test_export_refuses_bytes_that_are_not_the_sha(tmp_path):
    fake = FakeDocker()
    with pytest.raises(ValueError):
        REAL_EXPORT(tmp_path, "main", "demo", variant(1), SHA, run=fake)
    assert fake.calls == [] and not (tmp_path / "diagrams").exists()


def test_diagrams_lock(client, app, project, docker):
    assert client.post(EXPORT).status_code == 200
    session_id = client.cookies[COOKIE]

    ok = client.get(SITE)
    assert ok.status_code == 200 and ok.text == INDEX
    assert ok.headers["content-type"] == "text/html; charset=utf-8"
    assert ok.headers["content-security-policy"] == CSP.replace(
        "script-src 'self';", f"script-src 'self' {source(INLINE)};")
    assert ok.headers["cache-control"] == "no-store"
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert ok.headers["cross-origin-resource-policy"] == "same-origin"
    js = client.get(SITE + "js/a.js")
    assert js.status_code == 200 and js.text == "var a = 1;\n"
    assert js.headers["content-type"].startswith("text/javascript")
    assert client.get(SITE + "index.html").text == INDEX
    head = client.head(SITE)
    assert head.status_code == 200 and head.content == b""

    # The Host check comes first, as for every request.
    bad_host = client.get(SITE, headers={"Host": "evil.example:8765"})
    assert bad_host.status_code == 400
    assert bad_host.headers["x-content-type-options"] == "nosniff"

    # A valid session cookie is required; no CSRF header is needed (a navigation can't send one).
    with TestClient(app, base_url=BASE) as anon:
        r = anon.get(SITE)
        assert r.status_code == 401 and r.json() == {"detail": "signed out"}
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-security-policy"] == CSP
        assert anon.get(SITE + "js/a.js").status_code == 401
        assert anon.get(SITE, headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]}).status_code == 401
        assert anon.post(SITE).status_code == 401
        anon.cookies.set(COOKIE, session_id[:-1] + ("A" if session_id[-1] != "A" else "B"))
        assert anon.get(SITE).status_code == 401
        anon.cookies.set(COOKIE, session_id)
        assert anon.get(SITE).status_code == 200  # the cookie alone

    # Only GET and HEAD.
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        r = client.request(method, SITE)
        assert r.status_code == 405, method
        assert r.headers["allow"] == "GET, HEAD"
        assert r.headers["x-content-type-options"] == "nosniff"

    # Nothing outside the exported site: not result.json, not the input, not the repo.
    for path in ("%2e%2e/result.json", "..%2fresult.json", "%2E%2E/%2E%2E/result.json",
                 "%2e%2e/workspace.dsl", "%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/project.toml",
                 "/etc/passwd", "%2Fetc%2Fpasswd", "a%00b", "js", "js/", "nope.js", "%2e"):
        r = client.get(SITE + path)
        assert r.status_code == 404, path
        assert r.headers["content-security-policy"] == CSP, path
    for path in ("../result.json", "../../../../../../project.toml", "./../in/workspace.dsl",
                 ".", "js/.."):
        assert raw_get(app, SITE + path, session_id) == 404, path
    assert raw_get(app, SITE + "js/a.js", session_id) == 200

    # Only valid names, and only a folder that holds an accepted export.
    for url in (f"/diagrams/other/demo/{SHA}/", f"/diagrams/main/Demo/{SHA}/",
                f"/diagrams/main/demo/{SHA.upper()}/", f"/diagrams/main/demo/{SHA[:-1]}/",
                f"/diagrams/trial/demo/{SHA}/", f"/diagrams/main/demo/{'0' * 64}/",
                f"/diagrams/main/%2e%2e/{SHA}/"):
        assert client.get(url).status_code == 404, url


def test_diagrams_never_follow_a_link_out_of_the_site(client, project, docker):
    assert client.post(EXPORT).status_code == 200
    site = project / "diagrams" / "main" / "demo" / SHA / "in" / "site"
    (site / "leak.txt").symlink_to(project / "project.toml")
    (site / "inside.js").symlink_to(site / "js" / "a.js")
    assert client.get(SITE + "leak.txt").status_code == 404
    assert client.get(SITE + "inside.js").status_code == 200
    # The site folder itself must be the real one.
    elsewhere = project / "elsewhere"
    site.rename(elsewhere)
    site.symlink_to(elsewhere)
    assert client.get(SITE).status_code == 404


def test_verdict_states(tmp_path):
    assert diagrams.verdict(tmp_path, "main", "demo", None) == NOT_CHECKED
    assert diagrams.verdict(tmp_path, "main", "demo", SHA) == NOT_CHECKED
    assert diagrams.verdict(tmp_path, "main", "demo", "not a sha") == NOT_CHECKED
    REAL_EXPORT(tmp_path, "main", "demo", helpers.SAMPLE_WORKSPACE, SHA, run=FakeDocker())
    assert diagrams.verdict(tmp_path, "main", "demo", SHA) == {
        "state": "accepted", "message": None, "base": SITE,
        "views": [{"key": k, "url": SITE + "#" + k} for k in VIEWS]}
    assert diagrams.verdict(tmp_path, "trial", "demo", SHA) == NOT_CHECKED  # per register
    data = variant(1)
    sha = hashlib.sha256(data).hexdigest()
    REAL_EXPORT(tmp_path, "main", "demo", data, sha, run=FakeDocker(returncode=1, stderr="boom\n"))
    assert diagrams.verdict(tmp_path, "main", "demo", sha) == {
        "state": "refused", "message": "boom", "base": None, "views": []}
    # A damaged result.json counts as not checked, and is never served or trusted.
    result = diagrams.site_dir(tmp_path, "main", "demo", SHA) / "result.json"
    for damaged in ("{", '{"state": "accepted"}', json.dumps(
            {"state": "accepted", "message": None, "views": VIEWS,
             "hashes": ["'unsafe-inline'"]})):
        result.write_text(damaged)
        assert diagrams.verdict(tmp_path, "main", "demo", SHA) == NOT_CHECKED, damaged
    # The next export replaces it.
    fake = FakeDocker()
    assert REAL_EXPORT(tmp_path, "main", "demo", helpers.SAMPLE_WORKSPACE, SHA, run=fake)[
        "state"] == "accepted"
    assert len(fake.calls) == 1
    assert diagrams.verdict(tmp_path, "main", "demo", SHA)["state"] == "accepted"


def test_c4_shows_the_verdict_for_the_current_file(client, project, docker):
    assert client.get(C4).json()["structurizr"] == NOT_CHECKED
    assert client.post(EXPORT).status_code == 200
    shown = client.get(C4).json()["structurizr"]
    assert shown["state"] == "accepted" and shown["base"] == SITE
    assert [v["key"] for v in shown["views"]] == VIEWS
    (project / "systems" / "demo" / "workspace.dsl").write_bytes(variant(1))
    assert client.get(C4).json()["structurizr"] == NOT_CHECKED  # a new file: not checked yet
    (project / "systems" / "demo" / "workspace.dsl").write_bytes(b"garbage")
    assert client.get(C4).json()["structurizr"] == NOT_CHECKED


def test_outer_500_on_a_diagrams_path_keeps_the_headers(project):
    from starlette.requests import Request

    app = create_app(project, port=8765, signin_token="T0KEN")
    handler = app.exception_handlers[Exception]
    scope = {"type": "http", "method": "GET", "path": SITE, "headers": [], "query_string": b""}
    response = asyncio.run(handler(Request(scope), RuntimeError("secret-detail")))
    assert response.status_code == 500
    assert response.headers["content-security-policy"] == CSP
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert b"secret-detail" not in response.body
