import helpers
import pytest

from tmweb.app import create_app
from fastapi.testclient import TestClient

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def risk(reg):
    run = helpers.start(reg)
    return reg.add_risk("demo", helpers.ai_fields(), run_id=run)


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


def test_risk_detail_element_details(client, risk):
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    assert body["risk"]["id"] == "T-01"
    assert body["elements"]["P2"] == {"name": "Gateway", "type": "Process", "description": ""}
    assert body["dfd"] == {"state": "current", "latest_id": "DFD-1",
                           "written_against": "DFD-1", "error": None}
    assert body["duplicate"] is None
    assert isinstance(body["editors_since_approval"], list)


def test_missing_ids_are_null(client, project, risk):
    path = project / "systems" / "demo" / "dfd.md"
    text = path.read_text()
    path.write_text("\n".join(l for l in text.splitlines() if not l.startswith("| F2 ")) + "\n")
    body = client.get("/api/main/systems/demo/risks/T-01").json()
    assert body["elements"]["F2"] is None
    assert body["elements"]["P2"] is not None
    assert body["dfd"]["state"] == "changed"


def test_invalid_dfd_still_shows_the_risk(client, project, risk):
    (project / "systems" / "demo" / "dfd.md").write_bytes(b"garbage")
    r = client.get("/api/main/systems/demo/risks/T-01")
    assert r.status_code == 200
    body = r.json()
    assert "DFD version" in body["dfd"]["error"]
    assert body["elements"] and all(v is None for v in body["elements"].values())


def test_registry_error_is_422(client, risk):
    r = client.get("/api/main/systems/demo/risks/T-99")
    assert r.status_code == 422
    assert r.json()["detail"] == "no risk T-99 in demo"


def test_history_and_verify(client, risk):
    hist = client.get("/api/main/systems/demo/risks/T-01/history").json()
    assert hist[0]["op"] == "add"
    assert client.get("/api/main/systems/demo/history").json()
    assert client.get("/api/main/systems/demo/verify").json() == {"problems": []}


def test_dfd_endpoint(client):
    body = client.get("/api/main/systems/demo/dfd").json()
    assert body["status"]["state"] == "current"
    assert body["approvals"][0]["id"] == "DFD-1"
    assert body["preview"]["added"] == []
    assert body["preview_error"] is None
    assert body["text"].startswith("| Field | Value |")


def test_dfd_endpoint_invalid_file(client, project):
    (project / "systems" / "demo" / "dfd.md").write_bytes(b"garbage")
    r = client.get("/api/main/systems/demo/dfd")
    assert r.status_code == 200
    body = r.json()
    assert body["preview"] is None and body["preview_error"]
    assert body["text"] == "garbage"


def test_report_download(client, risk):
    r = client.get("/api/main/systems/demo/report",
                   params={"format": "csv", "download": "true"})
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="demo-register.csv"'
    r = client.get("/api/main/systems/demo/report")
    assert r.headers["content-type"].startswith("text/markdown")
    assert "content-disposition" not in r.headers
