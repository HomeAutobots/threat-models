from unittest import mock

import helpers
import pytest

from conftest import api_routes
from tmweb.app import create_app
from fastapi.testclient import TestClient

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def risk(reg):
    run = helpers.start(reg)
    return reg.add_risk("demo", helpers.ai_fields(), run_id=run)


@pytest.fixture
def dfd_risk(reg):
    """T-01 drafted against DFD-1, citing P2 and F2 (add needs a model approval now)."""
    helpers.seed_dfd_era(reg, "demo")
    return helpers.seed_dfd_risk(reg, "T-01", ["P2", "F2"])


def test_meta_values(client):
    meta = client.get("/api/meta").json()
    assert meta["note_min"] == 20
    assert meta["min_lengths"]["description"] == 80
    assert meta["stride"]["I"] == "Information disclosure"
    assert "retired" not in meta["statuses"]
    assert "stride-per-element" in meta["methods"]
    assert meta["origins"]
    for key in ("fields", "editable", "labels", "linddun", "treatments", "confidence",
                "human_required", "ai_required"):
        assert key in meta


def test_systems(client):
    body = client.get("/api/main/systems").json()
    assert body[0]["slug"] == "demo" and body[0]["name"] == "Demo"
    assert len(body) == 1


def test_no_database_file_is_created(tmp_path):
    root = helpers.make_project(tmp_path)
    app = create_app(root, port=8765, signin_token="T0KEN")
    with TestClient(app, base_url=BASE) as c:
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        c.headers.update({"X-CSRF-Token": r.headers["location"].split("#k=", 1)[1], "Origin": BASE})
        assert c.get("/api/main/systems").json() == []
        assert c.get("/api/trial/systems/demo/risks").status_code == 404
        assert c.get("/api/other/systems").status_code == 404
    assert not (root / "registry" / "registry.db").exists()
    assert not (root / "registry" / "trial.db").exists()


def test_risks_list(client, risk):
    rows = client.get("/api/main/systems/demo/risks", params={"state": "all"}).json()
    assert [r["id"] for r in rows] == ["T-01"]


def test_risk_detail_written_and_latest(client, reg, risk):
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    assert body["risk"]["id"] == "T-01"
    assert set(body["elements"]) == {"C2", "R2"}
    c2 = body["elements"]["C2"]
    assert c2["written"]["name"] == "C2 API" and c2["latest"] is None and c2["state"] == "same"
    assert body["elements"]["R2"]["written"]["source"] == "C1"
    assert body["model"] == {"state": "current", "latest_id": "MODEL-1",
                             "written_against": "MODEL-1", "moved_on": False, "changed": [],
                             "basis": "model"}
    assert body["duplicate"] is None
    assert isinstance(body["editors_since_approval"], list)


def test_risk_detail_when_the_model_moved_on(client, reg, risk):
    text = helpers.SAMPLE_WORKSPACE.replace(b'"Answers the web app."', b'"Answers the web app and more."')
    assert text != helpers.SAMPLE_WORKSPACE
    helpers.write_model(reg, "demo", text)
    helpers.approve_model(reg, "demo")
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    c2 = body["elements"]["C2"]
    assert c2["written"]["description"] == "Answers the web app."
    assert c2["latest"]["description"] == "Answers the web app and more."
    assert body["elements"]["C2"]["state"] == "changed"
    assert body["elements"]["R2"] == {"written": body["elements"]["R2"]["written"], "latest": None,
                                      "state": "same"}
    assert body["model"] == {"state": "current", "latest_id": "MODEL-2",
                             "written_against": "MODEL-1", "moved_on": True,
                             "changed": ["C2"], "basis": "model"}


def test_risk_detail_removed_element_has_null_latest(client, reg, risk):
    text = helpers.SAMPLE_WORKSPACE.replace(b'R2 = C1 -> C2 "R2 Calls"', b'R4 = C1 -> C2 "R4 Calls"')
    helpers.write_model(reg, "demo", text)
    helpers.approve_model(reg, "demo")
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    assert body["elements"]["R2"]["written"] is not None
    assert body["elements"]["R2"]["latest"] is None
    assert body["elements"]["R2"]["state"] == "removed"
    assert body["model"]["moved_on"] is True and "R2" in body["model"]["changed"]


def test_dfd_era_risk_detail(client, dfd_risk):
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    assert body["elements"] == {"P2": {"written": None, "latest": None, "state": "dfd"},
                                "F2": {"written": None, "latest": None, "state": "dfd"}}
    assert body["model"] == {"state": "current", "latest_id": "MODEL-1", "written_against": None,
                             "moved_on": False, "changed": [], "basis": "dfd"}


def test_registry_error_is_422(client, risk):
    r = client.get("/api/main/systems/demo/risks/T-99")
    assert r.status_code == 422
    assert r.json()["detail"] == "no risk T-99 in demo"


def test_history_and_verify(client, risk):
    hist = client.get("/api/main/systems/demo/risks/T-01/history").json()
    assert hist[0]["op"] == "add"
    assert client.get("/api/main/systems/demo/history").json()
    assert client.get("/api/main/systems/demo/verify").json() == {"problems": []}


C4 = "/api/main/systems/demo/c4"


def test_c4_endpoint_shape(client, reg, risk):
    body = client.get(C4).json()
    assert set(body) == {"status", "approvals", "preview", "error", "text", "counts",
                         "latest_record", "structurizr"}
    sha = reg.c4_status("demo").current_sha256
    assert body["status"]["state"] == "current"
    assert body["status"]["current_sha256"] == sha
    assert body["status"]["latest"]["id"] == "MODEL-1"
    assert [a["id"] for a in body["approvals"]] == ["MODEL-1"]
    assert "model" not in body["approvals"][0] and "source" not in body["approvals"][0]
    assert body["latest_record"]["items"]["C2"]["name"] == "C2 API"
    p = body["preview"]
    assert set(p) == {"sha256", "version", "ids", "record", "added", "removed", "changed",
                      "warnings", "next_ids", "reused", "problems", "diff", "adoption"}
    assert p["sha256"] == sha and p["version"] == "1.0" and p["ids"]["C"][:2] == ["C1", "C2"]
    assert p["added"] == [] and p["removed"] == [] and p["problems"] == []
    assert p["record"]["items"]["C2"]["name"] == "C2 API"
    assert body["error"] is None
    assert body["text"].startswith("workspace ")
    assert body["counts"] == {"C2": {"open": 0, "pending": 1}, "R2": {"open": 0, "pending": 1}}
    assert body["structurizr"] == {"state": "not-checked", "message": None, "base": None,
                                   "views": []}


def test_c4_endpoint_shows_a_change(client, reg):
    helpers.write_model(reg, "demo", helpers.SAMPLE_WORKSPACE.replace(
        b'"Answers the web app."', b'"Answers the web app and more."'))
    body = client.get(C4).json()
    assert body["status"]["state"] == "changed"
    assert body["preview"]["changed"] == {"C2": ["description"]}
    assert body["preview"]["diff"]


def test_c4_endpoint_invalid_file(client, project):
    (project / "systems" / "demo" / "workspace.dsl").write_bytes(b"garbage")
    r = client.get(C4)
    assert r.status_code == 200
    body = r.json()
    assert body["preview"] is None and body["error"].startswith("workspace.dsl")
    assert body["text"] == "garbage"
    assert body["latest_record"]["items"]


def test_c4_endpoint_no_file(client, project):
    (project / "systems" / "demo" / "workspace.dsl").unlink()
    body = client.get(C4).json()
    assert body["preview"] is None and "no workspace.dsl" in body["error"]
    assert body["text"] == "" and body["status"]["current_sha256"] is None


def test_c4_endpoint_sibling_unreadable_is_an_error_not_a_500(client):
    from tmreg.core import Registry, RegistryError
    with mock.patch.object(Registry, "c4_preview", side_effect=RegistryError("cannot read trial.db")):
        r = client.get(C4)
    assert r.status_code == 200
    body = r.json()
    assert body["preview"] is None and body["error"] == "cannot read trial.db"
    assert body["text"] == ""


def test_c4_endpoint_before_the_first_approval(client, tmp_path):
    reg = helpers.make_registry(tmp_path / "x", approve=False)
    app = create_app(reg.root, port=8765, signin_token="T0KEN")
    with TestClient(app, base_url=BASE) as c:
        r = c.get("/signin", params={"token": "T0KEN"}, follow_redirects=False)
        c.headers.update({"X-CSRF-Token": r.headers["location"].split("#k=", 1)[1], "Origin": BASE})
        body = c.get(C4).json()
    assert body["status"]["state"] == "none" and body["approvals"] == []
    assert body["latest_record"] is None
    assert body["preview"]["added"] and body["preview"]["adoption"] is None


def test_c4_routes_endpoint(client):
    r = client.get(C4 + "/routes", params={"from": "A1", "to": "C3"})
    assert r.status_code == 200, r.text
    chains = r.json()["chains"]
    assert chains and [h["path"] for h in chains[0]["hops"]] == ["R1", "R2", "R3"]


def test_c4_routes_bad_endpoint_is_422(client):
    r = client.get(C4 + "/routes", params={"from": "A1", "to": "C99"})
    assert r.status_code == 422 and "C99" in r.json()["detail"]
    assert client.get(C4 + "/routes", params={"from": "A1"}).status_code == 422


def test_c4_routes_exist_and_dfd_routes_are_gone(app):
    paths = {(m, r.path) for r in api_routes(app) for m in r.methods}
    base = "/api/{reg}/systems/{slug}"
    assert {("GET", base + "/c4"), ("GET", base + "/c4/routes"),
            ("POST", base + "/c4/approve")} <= paths
    assert not [p for _, p in paths if "dfd" in p]


def test_report_download(client, risk):
    r = client.get("/api/main/systems/demo/report",
                   params={"format": "csv", "download": "true"})
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="demo-register.csv"'
    r = client.get("/api/main/systems/demo/report")
    assert r.headers["content-type"].startswith("text/markdown")
    assert "content-disposition" not in r.headers
