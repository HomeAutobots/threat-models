import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "registry"))
sys.path.insert(0, str(REPO_ROOT / "registry" / "tests"))

import helpers  # noqa: E402

from tmweb.app import create_app  # noqa: E402

BASE = "http://127.0.0.1:8765"


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
