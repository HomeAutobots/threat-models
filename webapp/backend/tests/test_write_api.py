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
    for n in range(3):
        reg.add_risk("demo", helpers.ai_fields(title=f"Distinct title {n} for the risk"), run_id=run)
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


C4 = "/api/main/systems/demo/c4"


def test_c4_approve_and_stale_sha(client, human, project, reg):
    path = project / "systems" / "demo" / "workspace.dsl"
    path.write_bytes(path.read_bytes().replace(b"Serves the pages.", b"Serves the pages, fast."))
    sha = client.get(C4).json()["preview"]["sha256"]
    r = client.post(C4 + "/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["id"] == "MODEL-2"
    assert r.json()["approval"]["approved_by"] == "Test Reviewer"
    assert "model" not in r.json()["approval"] and "source" not in r.json()["approval"]
    assert client.get(C4).json()["status"]["state"] == "current"
    path.write_bytes(path.read_bytes().replace(b"fast.", b"faster."))
    r = client.post(C4 + "/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 409
    assert [a["id"] for a in reg.model_approvals("demo")] == ["MODEL-1", "MODEL-2"]  # no new one
    now = client.get(C4).json()["status"]["current_sha256"]
    assert r.json()["current_sha256"] == now != sha
    assert "changed since" in r.json()["detail"]


def test_c4_approve_refusals_are_422(client, human, project, reg):
    path = project / "systems" / "demo" / "workspace.dsl"
    sha = client.get(C4).json()["preview"]["sha256"]
    r = client.post(C4 + "/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 422 and "already approved" in r.json()["detail"]
    path.write_bytes(path.read_bytes().replace(b"Serves the pages.", b"Serves the pages, fast."))
    sha = client.get(C4).json()["preview"]["sha256"]
    r = client.post(C4 + "/approve", json={"note": "short", "expected_sha256": sha})
    assert r.status_code == 422 and "20" in r.json()["detail"]
    path.write_bytes(b"garbage")
    sha = client.get(C4).json()["status"]["current_sha256"]
    r = client.post(C4 + "/approve", json={"note": NOTE, "expected_sha256": sha})
    assert r.status_code == 422 and "workspace.dsl" in r.json()["detail"]
    assert len(reg.model_approvals("demo")) == 1


WRITES = [
    ("add", "", lambda c: {"fields": helpers.ai_fields()}),
    ("edit", "/T-01/edit", lambda c: {"fields": {"owner": "A"}, "seen": approve_body(c)["seen"],
                                       "reason": "Owner confirmed in the November review."}),
    ("approve", "/T-01/approve", lambda c: approve_body(c)),
    ("reject", "/T-01/reject", lambda c: approve_body(c)),
    ("merge", "/T-01/merge", lambda c: {**approve_body(c), "into": "T-02"}),
    ("retire", "/T-01/retire", lambda c: {"reason": NOTE, "seen": approve_body(c)["seen"]}),
    ("c4-approve", "C4", lambda c: {"note": NOTE, "expected_sha256": "0" * 64}),
]


@pytest.mark.parametrize("name,suffix,body", WRITES, ids=[w[0] for w in WRITES])
def test_human_ops_fail_closed_without_terminal(client, reg, risk, name, suffix, body):
    url = (C4 + "/approve" if suffix == "C4" else BASE + suffix)
    payload = body(client)
    changes = len(reg.history("demo"))
    approvals = len(reg.model_approvals("demo"))
    with mock.patch("tmreg.core._has_tty", return_value=False):
        r = client.post(url, json=payload)
    assert r.status_code == 422, r.text
    # add and edit are also open to the modeling agent's runs, so they ask for a run instead.
    expected = ("must name a run" if name in ("add", "edit") else "needs an interactive terminal")
    assert expected in r.json()["detail"]
    assert len(reg.history("demo")) == changes
    assert len(reg.model_approvals("demo")) == approvals
    assert reg.get_risk("demo", "T-01")["review_state"] == "pending"


def test_same_seen_twice_is_409(client, human, risk):  # R12
    body = approve_body(client)
    assert client.post(f"{BASE}/T-01/approve", json=body).status_code == 200
    r = client.post(f"{BASE}/T-01/approve", json=body)
    assert r.status_code == 409
    assert r.json()["current"]["review_state"] == "approved"


def test_write_routes_name_one_risk(app):
    posts = [r for r in api_routes(app) if "POST" in r.methods]
    assert len(posts) >= 7
    assert any(r.path.endswith("/c4/approve") for r in posts)
    for route in posts:
        names = set(route.param_convertors)
        assert names <= {"reg", "slug", "id"}, route.path
        assert route.path.count("{id}") <= 1
