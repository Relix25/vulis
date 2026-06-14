"""Integration tests for the Task routes + state-machine transitions."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_project(client: TestClient, headers: dict, name: str = "p") -> str:
    resp = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_task(client: TestClient, headers: dict, pid: str, name: str = "t") -> str:
    resp = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"name": name, "kind": "DETECTION"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _transition(client: TestClient, headers: dict, tid: str, verb: str):
    return client.post(f"/api/v1/tasks/{tid}:transition", json={"verb": verb}, headers=headers)


# Full happy path: BACKLOG -> IN_PROGRESS -> IN_VALIDATION -> DEPLOYED
# -> MONITORING -> RETRAINING -> IN_PROGRESS.


def test_full_lifecycle(client: TestClient, admin_headers: dict):
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)

    assert _transition(client, admin_headers, tid, "start").json()["state"] == "IN_PROGRESS"
    assert _transition(client, admin_headers, tid, "submit").json()["state"] == "IN_VALIDATION"
    assert _transition(client, admin_headers, tid, "approve").json()["state"] == "DEPLOYED"
    assert _transition(client, admin_headers, tid, "deploy").json()["state"] == "MONITORING"
    assert _transition(client, admin_headers, tid, "retrain").json()["state"] == "RETRAINING"
    assert _transition(client, admin_headers, tid, "start").json()["state"] == "IN_PROGRESS"


def test_reject_from_in_validation(client: TestClient, admin_headers: dict):
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)
    _transition(client, admin_headers, tid, "start")
    _transition(client, admin_headers, tid, "submit")
    resp = _transition(client, admin_headers, tid, "reject")
    assert resp.status_code == 200
    assert resp.json()["state"] == "IN_PROGRESS"


# ─── Invalid transitions return 409 ────────────────────────────


def test_invalid_transition_returns_409(client: TestClient, admin_headers: dict):
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)
    # BACKLOG → submit is not allowed
    resp = _transition(client, admin_headers, tid, "submit")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "INVALID_TRANSITION"
    assert "BACKLOG" in body["error"]["message"]
    assert "submit" in body["error"]["message"]


def test_unknown_verb_returns_409(client: TestClient, admin_headers: dict):
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)
    resp = _transition(client, admin_headers, tid, "frobnicate")
    assert resp.status_code == 409
    assert "Unknown transition verb" in resp.json()["error"]["message"]


# ─── RBAC per verb ─────────────────────────────────────────────


def test_data_scientist_can_start_and_submit(client: TestClient, data_scientist_headers: dict):
    pid = _create_project(client, data_scientist_headers)
    tid = _create_task(client, data_scientist_headers, pid)
    assert _transition(client, data_scientist_headers, tid, "start").status_code == 200
    assert _transition(client, data_scientist_headers, tid, "submit").status_code == 200


def test_data_scientist_cannot_approve(client: TestClient, data_scientist_headers: dict):
    pid = _create_project(client, data_scientist_headers)
    tid = _create_task(client, data_scientist_headers, pid)
    _transition(client, data_scientist_headers, tid, "start")
    _transition(client, data_scientist_headers, tid, "submit")
    # Now in IN_VALIDATION. data-scientist can't approve.
    resp = _transition(client, data_scientist_headers, tid, "approve")
    assert resp.status_code == 403


def test_reviewer_can_approve_and_reject(
    client: TestClient, admin_headers: dict, reviewer_headers: dict
):
    from conftest import make_headers

    # Reviewer shares tenant with admin so they can see the task.
    reviewer_same_tenant = make_headers(roles=["reviewer"], tenant=admin_headers["X-Tenant-Id"])
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)
    _transition(client, admin_headers, tid, "start")
    _transition(client, admin_headers, tid, "submit")
    # Reviewer approves
    assert _transition(client, reviewer_same_tenant, tid, "approve").status_code == 200
    # Set up a second task to test reject
    tid2 = _create_task(client, admin_headers, pid, name="t2")
    _transition(client, admin_headers, tid2, "start")
    _transition(client, admin_headers, tid2, "submit")
    assert _transition(client, reviewer_same_tenant, tid2, "reject").status_code == 200


def test_operator_can_deploy_but_not_approve(
    client: TestClient, admin_headers: dict, operator_headers: dict
):
    from conftest import make_headers

    # Operator shares tenant with admin so they can see the task.
    operator_same_tenant = make_headers(roles=["operator"], tenant=admin_headers["X-Tenant-Id"])
    pid = _create_project(client, admin_headers)
    tid = _create_task(client, admin_headers, pid)
    # Get to DEPLOYED
    _transition(client, admin_headers, tid, "start")
    _transition(client, admin_headers, tid, "submit")
    _transition(client, admin_headers, tid, "approve")
    # Operator can deploy
    assert _transition(client, operator_same_tenant, tid, "deploy").status_code == 200
    # Set up a new task to test operator can't approve
    tid2 = _create_task(client, admin_headers, pid, name="t2")
    _transition(client, admin_headers, tid2, "start")
    _transition(client, admin_headers, tid2, "submit")
    assert _transition(client, operator_same_tenant, tid2, "approve").status_code == 403


# ─── Unknown task → 404 ────────────────────────────────────────


def test_unknown_task_returns_404(client: TestClient, admin_headers: dict):
    resp = _transition(client, admin_headers, "task_doesnotexist", "start")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
