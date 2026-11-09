import os
import re
from unittest import mock

from fastapi.routing import APIRoute

import tmreg.core
from tmweb.__main__ import main

PARAMS = {"reg": "main", "slug": "demo", "id": "T-01"}


def test_signin_token_works_once(anon):
    r = anon.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
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
    seen = 0
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api"):
            path = route.path.format(**PARAMS)
            for method in route.methods:
                seen += 1
                r = anon.request(method, path)
                assert r.status_code == 401, (method, route.path)
                assert r.json() == {"detail": "signed out"}
    assert seen >= 1


def test_unknown_host_refused(anon):
    for path in ("/signin?token=T0KEN", "/api/session"):
        r = anon.get(path, headers={"Host": "evil.example:8765"})
        assert r.status_code == 400
        assert r.json() == {"detail": "unknown host"}


def test_unsafe_methods_need_csrf_and_origin(client):
    token = client.headers["X-CSRF-Token"]
    no_csrf = {"X-CSRF-Token": ""}
    assert client.post("/api/session", headers=no_csrf).status_code == 403
    bad_origin = {"X-CSRF-Token": token, "Origin": "http://evil.example"}
    assert client.post("/api/session", headers=bad_origin).status_code == 403
    assert client.post("/api/session").status_code == 405


def test_session_shape(client):
    body = client.get("/api/session").json()
    assert body["reviewer"] == "Test Reviewer"
    assert body["trial"] is False
    assert isinstance(body["csrf"], str) and body["csrf"]
    assert set(body) == {"reviewer", "csrf", "trial"}


def test_spa_fallback(project, tmp_path):
    from fastapi.testclient import TestClient

    from tmweb.app import create_app

    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    app = create_app(project, port=8765, signin_token="T0KEN", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/main/demo/register").text == "<html>SPA</html>"
        c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        assert c.get("/api/nope").status_code == 404


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
