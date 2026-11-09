import os
import re
from unittest import mock


import tmreg.core
from conftest import api_routes
from tmweb.__main__ import main

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
    assert len(visited) >= 17  # a broken route unwrap must fail loudly, not pass vacuously


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
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/main/demo/register").text == "<html>SPA</html>"
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        csrf = r.headers["location"].split("#k=", 1)[1]
        assert c.get("/api/nope", headers={"X-CSRF-Token": csrf}).status_code == 404


def test_main_refuses_without_terminal(tmp_path, capsys):
    with mock.patch.object(tmreg.core, "_has_tty", return_value=False), \
         mock.patch("uvicorn.run") as run:
        assert main([], root=tmp_path) == 1
    assert "needs an interactive terminal" in capsys.readouterr().err
    run.assert_not_called()


def test_main_refuses_under_claude_code(tmp_path, capsys, human):
    with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
         mock.patch("uvicorn.run") as run:
        assert main([], root=tmp_path) == 1
    assert "started by Claude Code" in capsys.readouterr().err
    run.assert_not_called()


def test_main_prints_one_time_link(project, capsys, human):
    with mock.patch("uvicorn.run") as run:
        assert main([], root=project) == 0
    out = capsys.readouterr().out
    assert re.search(r"http://127\.0\.0\.1:8765/signin\?token=\S{40,}", out)
    assert run.call_args.kwargs["host"] == "127.0.0.1"


def test_unhandled_error_is_500_no_store_without_leak(project):
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

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
