import re
import sys
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from starlette.routing import Mount
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "registry"))
sys.path.insert(0, str(REPO_ROOT / "registry" / "tests"))

import helpers  # noqa: E402

from tmweb.app import create_app  # noqa: E402

BASE = "http://127.0.0.1:8765"


SPA_CATCH_ALL = "/{full_path:path}"
NON_API_ROUTES = {"/signin", "/favicon.svg", SPA_CATCH_ALL}


def all_routes(app) -> list:
    """Every route, with included routers unwrapped (FastAPI 0.162 lists them as lazy wrappers in
    app.routes; recurse through original_router). Strict: anything that is not an APIRoute fails,
    except the /assets Mount, and an APIRoute outside /api fails unless it is /signin, the
    favicon, or the SPA catch-all. A new route kind or an unlocked path cannot slip past."""
    found = []

    def walk(routes):
        for r in routes:
            inner = getattr(r, "original_router", None)
            if inner is not None:
                walk(inner.routes)
            elif isinstance(r, APIRoute):
                assert r.path.startswith("/api") or r.path in NON_API_ROUTES, \
                    f"route outside /api: {r.path}"
                found.append(r)
            else:
                assert isinstance(r, Mount) and r.path == "/assets", f"unexpected route: {r!r}"
    walk(app.routes)
    return found


def api_routes(app) -> list:
    """Every APIRoute under /api (see all_routes for the checks)."""
    return [r for r in all_routes(app) if r.path.startswith("/api")]


@pytest.fixture
def reg(tmp_path):
    registry = helpers.make_registry(tmp_path)
    yield registry
    helpers.close_registries()


@pytest.fixture
def project(reg):
    return reg.root


@pytest.fixture
def app(project):
    return create_app(project, port=8765, signin_token="T0KEN")


@pytest.fixture
def anon(app):
    with TestClient(app, base_url=BASE) as c:
        yield c


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE) as c:
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        assert r.status_code == 303
        location = r.headers["location"]
        assert re.match(r"^/#k=[A-Za-z0-9_-]{40,}$", location)
        csrf = location.split("#k=", 1)[1]
        c.headers.update({"X-CSRF-Token": csrf, "Origin": BASE})
        yield c


@pytest.fixture
def human():
    with helpers.human_terminal():
        yield
