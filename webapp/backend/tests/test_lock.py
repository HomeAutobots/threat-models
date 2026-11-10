import os
import re
import socket
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import tmreg.core
from tmreg import config
from conftest import DIAGRAMS_ROUTE, SPA_CATCH_ALL, all_routes, api_routes
from tmweb.__main__ import main
from tmweb.app import create_app

def free_port() -> int:
    """A port nothing listens on now. --port refuses 0, so tests ask the OS first."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


BASE = "http://127.0.0.1:8765"
PARAMS = {"reg": "main", "slug": "demo", "id": "T-01"}


def test_signin_token_works_once(anon):
    r = anon.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/#k=")
    cookie = r.headers["set-cookie"]
    assert "tmweb_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    r2 = anon.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
    assert r2.status_code == 403


def test_wrong_token_refused(anon):
    r = anon.get("/signin", params={"token": "nope"}, follow_redirects=False)
    assert r.status_code == 403
    assert "set-cookie" not in r.headers
    assert "has been used or is not valid" in r.text


def test_every_api_route_requires_session(app, anon):
    routes = api_routes(app)
    expected = {(m, r.path) for r in routes for m in r.methods}
    visited = set()
    for route in routes:
        path = route.path.format(**PARAMS)
        for method in route.methods:
            visited.add((method, route.path))
            r = anon.request(method, path)
            assert r.status_code == 401, (method, route.path)
            assert r.json() == {"detail": "signed out"}
    assert visited == expected
    # Count routes, not method/path pairs; a broken unwrap must fail loudly, not pass vacuously.
    assert len(routes) >= 17


def test_unknown_host_refused(anon):
    for path in ("/signin?token=T0KEN", "/api/session"):
        r = anon.get(path, headers={"Host": "evil.example:8765"})
        assert r.status_code == 400
        assert r.json() == {"detail": "unknown host"}


def test_unsafe_methods_need_csrf_and_origin(client):
    token = client.headers["X-CSRF-Token"]
    assert client.post("/api/session", headers={"X-CSRF-Token": ""}).status_code == 401
    bad_origin = {"X-CSRF-Token": token, "Origin": "http://evil.example"}
    assert client.post("/api/session", headers=bad_origin).status_code == 403
    assert client.post("/api/session").status_code == 405


def test_cookie_alone_is_refused(client, app):
    from fastapi.testclient import TestClient

    cookie_only = TestClient(app, base_url="http://127.0.0.1:8765")
    cookie_only.cookies.set("tmweb_session", client.cookies["tmweb_session"])
    r = cookie_only.get("/api/session")
    assert r.status_code == 401
    assert r.json() == {"detail": "signed out"}
    bad = cookie_only.get("/api/session", headers={"X-CSRF-Token": "wrong"})
    assert bad.status_code == 401
    forged = cookie_only.get(
        "/api/session",
        headers={"X-CSRF-Token": "wrong", "Origin": "http://127.0.0.1:8765"},
    )
    assert forged.status_code == 401
    assert client.get("/api/session").status_code == 200


def test_header_alone_is_refused(client, app):
    from fastapi.testclient import TestClient

    header_only = TestClient(app, base_url="http://127.0.0.1:8765")
    r = header_only.get("/api/session", headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]})
    assert r.status_code == 401


def test_api_responses_are_not_cached(client, anon):
    assert client.get("/api/session").headers["cache-control"] == "no-store"
    assert anon.get("/api/session").headers["cache-control"] == "no-store"
    bad_host = anon.get("/api/session", headers={"Host": "evil.example:8765"})
    assert bad_host.status_code == 400
    assert bad_host.headers["cache-control"] == "no-store"
    forbidden = client.post("/api/session", headers={"Origin": "http://evil.example"})
    assert forbidden.status_code == 403
    assert forbidden.headers["cache-control"] == "no-store"


def test_websocket_refused(project):
    import pytest
    from fastapi import WebSocket
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from tmweb.app import create_app

    app = create_app(project, port=8765, signin_token="T0KEN")

    @app.websocket("/api/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        await socket.send_text("open")

    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/api/ws") as sock:
                sock.receive_text()


def test_empty_signin_token_refused():
    import pytest

    from tmweb.security import SessionStore

    with pytest.raises(ValueError):
        SessionStore("")


def test_session_shape(client):
    assert client.get("/api/session").json() == {"reviewer": "Test Reviewer", "trial": False}


def test_spa_fallback(project, tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    # Registered last, so no real route (including every /api one) is shadowed by it.
    assert all_routes(app)[-1].path == SPA_CATCH_ALL
    assert [r.path for r in all_routes(app)].count(SPA_CATCH_ALL) == 1
    paths = [r.path for r in all_routes(app)]
    assert paths.count(DIAGRAMS_ROUTE) == 1
    assert paths.index(DIAGRAMS_ROUTE) < paths.index(SPA_CATCH_ALL)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/main/demo/register").text == "<html>SPA</html>"
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        csrf = r.headers["location"].split("#k=", 1)[1]
        assert c.get("/api/nope", headers={"X-CSRF-Token": csrf}).status_code == 404
        assert c.get("/api/session", headers={"X-CSRF-Token": csrf}).status_code == 200
        # Nothing under /diagrams falls through to the page, even a path the route doesn't match.
        for path in ("/diagrams", "/diagrams/main/demo/" + "0" * 64, "/diagrams/x"):
            r = c.get(path)
            assert r.status_code == 404, path
            assert "SPA" not in r.text, path


def test_main_refuses_without_terminal(tmp_path, capsys):
    with mock.patch.object(tmreg.core, "_has_tty", return_value=False), \
         mock.patch("uvicorn.Server.run") as run:
        assert main([], root=tmp_path) == 1
    captured = capsys.readouterr()
    assert "needs an interactive terminal" in captured.err
    assert "token=" not in captured.out
    run.assert_not_called()


def test_main_refuses_under_claude_code(tmp_path, capsys, human):
    with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
         mock.patch("uvicorn.Server.run") as run:
        assert main([], root=tmp_path) == 1
    captured = capsys.readouterr()
    assert "started by Claude Code" in captured.err
    assert "token=" not in captured.out
    run.assert_not_called()


def test_main_prints_one_time_link_after_binding(project, capsys, human):
    seen = {}

    def fake_run(server, sockets):
        # The link is already printed, and the server gets the socket main() bound.
        seen["out"] = capsys.readouterr().out
        (sock,) = sockets
        seen["addr"] = sock.getsockname()
        seen["reuse"] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        seen["reuseport"] = (
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) if hasattr(socket, "SO_REUSEPORT") else 0
        )

    # A port the OS just reported free, so the test never collides with a running app.
    with mock.patch("uvicorn.Server.run", autospec=True, side_effect=fake_run) as run:
        assert main(["--port", str(free_port())], root=project) == 0
    run.assert_called_once()
    host, port = seen["addr"]
    assert host == "127.0.0.1" and port != 0
    assert seen["reuse"] != 0  # SO_REUSEADDR: TIME_WAIT from a just-stopped app does not block
    assert seen["reuseport"] == 0  # never SO_REUSEPORT: that would let two apps share the port
    assert re.search(rf"http://127\.0\.0\.1:{port}/signin\?token=\S{{40,}}", seen["out"])


@pytest.mark.parametrize("holder_reuseaddr", [False, True], ids=["plain-listener", "reuseaddr-listener"])
def test_main_refuses_when_port_is_taken(project, capsys, human, holder_reuseaddr):
    # A socket still listening on the port, such as an app in another window (which sets
    # SO_REUSEADDR too), makes the bind fail even though main() sets SO_REUSEADDR.
    held = socket.socket()
    if holder_reuseaddr:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    held.bind(("127.0.0.1", 0))
    held.listen()
    port = held.getsockname()[1]
    try:
        with mock.patch("uvicorn.Server.run") as run:
            assert main(["--port", str(port)], root=project) == 1
    finally:
        held.close()
    captured = capsys.readouterr()
    assert captured.err == (
        f"tmweb: port {port} is in use. Is the app already running in another Terminal window?\n"
    )
    assert "token=" not in captured.out
    run.assert_not_called()


def test_main_starts_right_after_a_stopped_app(project, capsys, human):
    # An app that just stopped leaves its closed connections in TIME_WAIT on the port. Its socket
    # was created with SO_REUSEADDR, then closed; a later start must still bind.
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]
    cli = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()  # the server side closes first, as uvicorn does at shutdown
    assert cli.recv(1) == b""
    cli.close()
    srv.close()
    with mock.patch("uvicorn.Server.run") as run:
        assert main(["--port", str(port)], root=project) == 0
    run.assert_called_once()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert re.search(rf"http://127\.0\.0\.1:{port}/signin\?token=\S{{40,}}", captured.out)


def test_main_default_port_is_8765(project, capsys, human):
    with mock.patch.object(socket.socket, "bind", side_effect=OSError(48, "in use")) as bind, \
         mock.patch("uvicorn.Server.run") as run:
        assert main([], root=project) == 1
    assert bind.call_args.args == (("127.0.0.1", 8765),)
    assert "tmweb: port 8765 is in use." in capsys.readouterr().err
    run.assert_not_called()


def test_unhandled_error_is_500_no_store_without_leak(project, caplog):
    import logging

    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    # No static_dir on purpose: with one, the SPA catch-all is registered last and a route added
    # afterwards, like this one, would be shadowed by it.
    app = create_app(project, port=8765, signin_token="T0KEN")

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("secret-detail")

    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        csrf = r.headers["location"].split("#k=", 1)[1]
        r = c.get("/api/boom", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error"}
    assert r.headers["cache-control"] == "no-store"
    assert "secret-detail" not in r.text
    # The traceback goes to the Terminal through the tmweb logger, not to the browser.
    (record,) = [rec for rec in caplog.records if rec.name == "tmweb"]
    assert record.levelno == logging.ERROR
    assert record.exc_info and record.exc_info[0] is RuntimeError
    assert "GET /api/boom" in record.getMessage()
    assert "RuntimeError: secret-detail" in caplog.text


def test_unknown_scope_types_are_not_passed_to_the_app():
    import asyncio

    from tmweb.security import HttpAndLifespanOnly

    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["type"])

    wrapped = HttpAndLifespanOnly(inner)
    sent = []

    async def send(m):
        sent.append(m)

    async def run():
        for kind in ("http", "lifespan", "websocket", "mystery"):
            await wrapped({"type": kind}, None, send)

    asyncio.run(run())
    assert calls == ["http", "lifespan"]
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_csp_header_on_every_kind_of_response(project, client, anon, tmp_path):
    from fastapi.testclient import TestClient

    from tmweb.app import CSP, create_app

    assert client.get("/api/session").headers["content-security-policy"] == CSP
    assert anon.get("/api/session").headers["content-security-policy"] == CSP
    refused = anon.get("/signin", params={"token": "wrong"})
    assert refused.status_code == 403
    assert refused.headers["content-security-policy"] == CSP
    bad_host = anon.get("/api/session", headers={"Host": "evil.example:8765"})
    assert bad_host.status_code == 400
    assert bad_host.headers["content-security-policy"] == CSP

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "assets" / "a.js").write_text("1")
    (static / "index.html").write_text("<html>SPA</html>")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/").headers["content-security-policy"] == CSP
        assert c.get("/assets/a.js").headers["content-security-policy"] == CSP
    assert "script-src 'self';" in CSP and "img-src 'self' data: blob:;" in CSP


def test_missing_project_toml_is_422_on_meta_and_session(client, project):
    (project / "project.toml").unlink()
    with pytest.raises(config.ConfigError) as expected:
        config.load_project(project)
    message = str(expected.value)
    assert message
    for path in ("/api/meta", "/api/session"):
        r = client.get(path)
        assert r.status_code == 422, path
        assert r.json()["detail"] == message, path


def test_front_end_not_built_is_503_plain_text(project, tmp_path):
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    static = tmp_path / "dist"
    static.mkdir()
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    expected = (
        "The app's pages aren't built yet. Start it with webapp/start.command or make web."
    )
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        for path in ("/", "/main/demo/register"):
            r = c.get(path)
            assert r.status_code == 503, path
            assert r.text == expected
            assert r.headers["content-type"].startswith("text/plain")


def test_other_bind_errors_print_strerror(project, capsys, human):
    import errno

    err = OSError(errno.EACCES, "Permission denied")
    with mock.patch.object(socket.socket, "bind", side_effect=err), \
         mock.patch("uvicorn.Server.run") as run:
        assert main(["--port", "80"], root=project) == 1
    captured = capsys.readouterr()
    assert captured.err == "tmweb: cannot listen on 127.0.0.1:80: Permission denied\n"
    assert "token=" not in captured.out
    run.assert_not_called()


@pytest.mark.parametrize("port", ["0", "-1", "65536", "99999999999999999999", "abc"])
def test_bad_port_is_an_argparse_error(project, capsys, port):
    with pytest.raises(SystemExit) as exc:
        main(["--port", port], root=project)
    assert exc.value.code == 2
    assert "--port" in capsys.readouterr().err


def test_dev_uses_port_5199(project, capsys, human):
    from tmweb.security import DEV_ORIGIN, allowed_origins

    assert DEV_ORIGIN == "http://localhost:5199"
    assert DEV_ORIGIN in allowed_origins(8765, True)
    with mock.patch("uvicorn.Server.run"):
        assert main(["--port", str(free_port()), "--dev"], root=project) == 0
    assert re.search(r"Sign in: http://localhost:5199/signin\?token=\S{40,}", capsys.readouterr().out)


def test_outer_500_keeps_csp_and_no_store(project):
    from fastapi.testclient import TestClient

    from tmweb.app import CSP, create_app

    app = create_app(project, port=8765, signin_token="T0KEN")

    @app.get("/outside")
    def outside():
        raise RuntimeError("secret-detail")

    # The lock only catches errors inside /api; this one reaches ServerErrorMiddleware.
    with TestClient(app, base_url="http://127.0.0.1:8765", raise_server_exceptions=False) as c:
        r = c.get("/outside")
    assert r.status_code == 500
    assert r.headers["content-security-policy"] == CSP
    assert "secret-detail" not in r.text


def test_outer_500_on_api_path_is_no_store_with_csp(project):
    from fastapi.responses import Response
    from fastapi.testclient import TestClient

    from tmweb.app import CSP, create_app

    app = create_app(project, port=8765, signin_token="T0KEN")
    handler = app.exception_handlers[Exception]
    import asyncio

    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/api/x", "headers": [], "query_string": b""}
    response = asyncio.run(handler(Request(scope), RuntimeError("secret-detail")))
    assert isinstance(response, Response)
    assert response.status_code == 500
    assert response.headers["content-security-policy"] == CSP
    assert response.headers["cache-control"] == "no-store"
    assert b"secret-detail" not in response.body


def test_favicon_is_served_from_static_dir_only(project, tmp_path):
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    (static / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (static / "secret.txt").write_text("not served")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.get("/favicon.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].split(";")[0] == "image/svg+xml"
        assert "<svg" in r.text
        # No other root file is served: the catch-all still gives the SPA page.
        other = c.get("/secret.txt")
        assert "not served" not in other.text
        assert other.text == "<html>SPA</html>"


def test_missing_favicon_falls_back_to_not_found_not_the_page(project, tmp_path):
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/favicon.svg").status_code == 404


@pytest.mark.parametrize(
    "host",
    ["LOCALHOST:8765", "127.0.0.1:8765.", "localhost.:8765", "localhost:8765."],
    ids=["upper-case", "ip-trailing-dot", "name-dot-before-port", "name-trailing-dot"],
)
def test_odd_host_headers_are_refused(anon, host):
    r = anon.get("/api/session", headers={"Host": host})
    assert r.status_code == 400
    assert r.json() == {"detail": "unknown host"}


def test_missing_host_header_is_refused(app):
    # The test client always sends a Host, so call the ASGI app with a scope that has none.
    import asyncio

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "http_version": "1.1", "method": "GET", "path": "/api/session",
             "raw_path": b"/api/session", "query_string": b"", "headers": [], "scheme": "http",
             "server": ("127.0.0.1", 8765), "client": ("127.0.0.1", 50000), "root_path": ""}
    asyncio.run(app(scope, receive, send))
    start = sent[0]
    assert start["status"] == 400
    assert b"unknown host" in b"".join(m.get("body", b"") for m in sent[1:])


def test_write_without_origin_is_refused(client):
    del client.headers["Origin"]
    r = client.post("/api/session")  # a write: any method that is not GET or HEAD
    assert r.status_code == 403
    assert r.json() == {"detail": "forbidden"}


def test_dev_origin_is_allowed_only_with_dev(project):
    from tmweb.security import DEV_ORIGIN

    def post(dev):
        app = create_app(project, port=8765, signin_token="T0KEN", dev=dev)
        with TestClient(app, base_url=BASE) as c:
            r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
            csrf = r.headers["location"].split("#k=", 1)[1]
            # 405 means the lock let it through to the router; 403 means the lock stopped it.
            return c.post("/api/session", headers={"X-CSRF-Token": csrf, "Origin": DEV_ORIGIN})

    assert post(dev=False).status_code == 403
    assert post(dev=True).status_code == 405
