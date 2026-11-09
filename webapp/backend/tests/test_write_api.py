from unittest import mock

import helpers
import pytest
from conftest import api_routes

from tmreg.core import Registry
from tmweb.app import create_app

NOTE = "Checked against the DFD and the evidence."
BASE = "/api/main/systems/demo/risks"


@pytest.fixture
def risk(reg):
    run = helpers.start(reg)
    return reg.add_risk("demo", helpers.ai_fields(), run_id=run)


def approve_body(client, id="T-01", note=NOTE):
    return {"note": note, "seen": client.get(f"{BASE}/{id}").json()["risk"]}


def test_approve_passes_seen_unmodified(client, human, risk):
    body = approve_body(client)
    with mock.patch.object(Registry, "approve", autospec=True, side_effect=Registry.approve) as m:
        r = client.post(f"{BASE}/T-01/approve", json=body)
    assert r.status_code == 200, r.text
    assert m.call_args.kwargs["seen"] == body["seen"]
    assert r.json()["risk"]["review_state"] == "approved"


def test_stale_approve_returns_409_and_writes_nothing(client, human, reg, risk):
    body = approve_body(client)
    run = helpers.start(reg)
    reg.edit_risk("demo", "T-01", {"notes": "AI changed this after the page loaded."}, run_id=run)
    before = len(reg.history("demo", "T-01"))
    r = client.post(f"{BASE}/T-01/approve", json=body)
    assert r.status_code == 409
    assert r.json()["current"]["notes"] == "AI changed this after the page loaded."
    assert r.json()["current"]["review_state"] == "pending"
    assert reg.get_risk("demo", "T-01")["review_state"] == "pending"
    assert len(reg.history("demo", "T-01")) == before


def test_second_approve_is_refused(client, human, risk):
    body = approve_body(client)
    assert client.post(f"{BASE}/T-01/approve", json=body).status_code == 200
    r = client.post(f"{BASE}/T-01/approve", json=approve_body(client))  # fresh seen
    assert r.status_code == 422
    assert "only a pending risk can be approved" in r.json()["detail"]


def test_short_note_is_422_with_core_message(client, human, risk):
    r = client.post(f"{BASE}/T-01/approve", json=approve_body(client, note="too short"))
    assert r.status_code == 422
    assert "20" in r.json()["detail"]


def test_owner_edit_of_approved_stays_approved(client, human, risk):
    assert client.post(f"{BASE}/T-01/approve", json=approve_body(client)).status_code == 200
    seen = client.get(f"{BASE}/T-01").json()["risk"]
    reason = "Owner confirmed in the November review."
    r = client.post(f"{BASE}/T-01/edit", json={"fields": {"owner": "A"}, "seen": seen,
                                              "reason": reason})
    assert r.status_code == 200, r.text
    assert r.json()["risk"]["review_state"] == "approved"
    assert r.json()["risk"]["owner"] == "A"
    hist = client.get(f"{BASE}/T-01/history").json()
    assert hist[-1]["note"] == reason


def test_add_lands_pending(client, human):
    r = client.post(BASE, json={"fields": helpers.ai_fields()})
    assert r.status_code == 200, r.text
    assert r.json()["risk"]["review_state"] == "pending"
    assert r.json()["risk"]["drafted_by"] == "human:Test Reviewer"


def test_reject_merge_retire(client, human, reg):
    run = helpers.start(reg)
    for _ in range(3):
        reg.add_risk("demo", helpers.ai_fields(title=f"Distinct title {_} for the risk"), run_id=run)
    ids = [r["id"] for r in reg.list_risks("demo", "all")]
    a, b, c = ids[:3]

    r = client.post(f"{BASE}/{a}/reject", json=approve_body(client, a))
    assert r.status_code == 200 and r.json()["risk"]["review_state"] == "rejected"

    assert client.post(f"{BASE}/{b}/approve", json=approve_body(client, b)).status_code == 200
    r = client.post(f"{BASE}/{c}/merge", json={**approve_body(client, c), "into": b})
    assert r.status_code == 200, r.text
    assert r.json()["risk"]["merged_into"] == b

    r = client.post(f"{BASE}/{b}/retire", json={"reason": NOTE,
                                                "seen": client.get(f"{BASE}/{b}").json()["risk"]})
    assert r.status_code == 200, r.text
    assert r.json()["risk"]["status"] == "retired"


def test_dfd_approve_and_stale_sha(client, human, project):
    path = project / "systems" / "demo" / "dfd.md"
    path.write_bytes(path.read_bytes() + b"\nA change.\n")
    sha = client.get("/api/main/systems/demo/dfd").json()["preview"]["sha256"]
    r = client.post("/api/main/systems/demo/dfd/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["id"] == "DFD-2"
    path.write_bytes(path.read_bytes() + b"\nAnother change.\n")
    r = client.post("/api/main/systems/demo/dfd/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 409
    now = client.get("/api/main/systems/demo/dfd").json()["status"]["current_sha256"]
    assert r.json()["current_sha256"] == now != sha


def test_human_ops_fail_closed_without_terminal(client, risk):
    body = approve_body(client)
    with mock.patch("tmreg.core._has_tty", return_value=False):
        r = client.post(f"{BASE}/T-01/approve", json=body)
    assert r.status_code == 422
    assert "needs an interactive terminal" in r.json()["detail"]


def test_write_routes_name_one_risk(app):
    posts = [r for r in api_routes(app) if "POST" in r.methods]
    assert len(posts) >= 7
    for route in posts:
        names = set(route.param_convertors)
        assert names <= {"reg", "slug", "id"}, route.path
        assert route.path.count("{id}") <= 1
