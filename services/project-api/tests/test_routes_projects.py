"""Integration tests for the project CRUD routes."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_project_returns_201(client: TestClient, admin_headers: dict):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "alpha", "phase": "POC", "tags": {"plant": "Lyon"}},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "alpha"
    assert body["phase"] == "POC"
    assert body["tags"] == {"plant": "Lyon"}
    assert body["id"].startswith("proj_") is False or len(body["id"]) > 4  # hex uuid, not prefixed
    assert body["deleted_at"] is None


def test_list_projects_empty(client: TestClient, admin_headers: dict):
    resp = client.get("/api/v1/projects", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_then_list_projects(client: TestClient, admin_headers: dict):
    for n in ("alpha", "beta", "gamma"):
        client.post("/api/v1/projects", json={"name": n}, headers=admin_headers)
    resp = client.get("/api/v1/projects", headers=admin_headers)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"alpha", "beta", "gamma"}


def test_get_project(client: TestClient, admin_headers: dict):
    create = client.post("/api/v1/projects", json={"name": "alpha"}, headers=admin_headers).json()
    resp = client.get(f"/api/v1/projects/{create['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == create["id"]


def test_get_unknown_project_returns_404(client: TestClient, admin_headers: dict):
    resp = client.get("/api/v1/projects/proj_doesnotexist", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_patch_project(client: TestClient, admin_headers: dict):
    create = client.post("/api/v1/projects", json={"name": "alpha"}, headers=admin_headers).json()
    resp = client.patch(
        f"/api/v1/projects/{create['id']}",
        json={"description": "new desc", "phase": "PILOT"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["description"] == "new desc"
    assert body["phase"] == "PILOT"
    # PATCH with only some fields shouldn't wipe others.
    assert body["name"] == "alpha"


def test_delete_project_is_soft(client: TestClient, admin_headers: dict):
    create = client.post("/api/v1/projects", json={"name": "alpha"}, headers=admin_headers).json()
    pid = create["id"]

    resp = client.delete(f"/api/v1/projects/{pid}", headers=admin_headers)
    assert resp.status_code == 204

    # Soft-deleted projects are hidden from list / get by default.
    resp = client.get(f"/api/v1/projects/{pid}", headers=admin_headers)
    assert resp.status_code == 404
    resp = client.get("/api/v1/projects", headers=admin_headers)
    assert resp.json() == []


# ─── Cross-tenant isolation ─────────────────────────────────────


def test_other_tenant_cannot_see_project(client: TestClient):
    from conftest import make_headers

    alice = make_headers(roles=["data-scientist"], tenant="tenant_alice")
    bob = make_headers(roles=["data-scientist"], tenant="tenant_bob")

    create = client.post("/api/v1/projects", json={"name": "alpha"}, headers=alice).json()
    pid = create["id"]

    # Bob can list — but his list is empty (tenant-scoped).
    assert client.get("/api/v1/projects", headers=bob).json() == []
    # Bob can't see Alice's project directly.
    assert client.get(f"/api/v1/projects/{pid}", headers=bob).status_code == 404


# ─── RBAC ───────────────────────────────────────────────────────


def test_annotator_cannot_create_project(client: TestClient, annotator_headers: dict):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "alpha"},
        headers=annotator_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_annotator_can_list_projects(client: TestClient, admin_headers: dict):
    # Annotator shares tenant with admin so they can see the project.
    from conftest import make_headers

    annotator_same_tenant = make_headers(roles=["annotator"], tenant=admin_headers["X-Tenant-Id"])
    client.post("/api/v1/projects", json={"name": "alpha"}, headers=admin_headers)
    resp = client.get("/api/v1/projects", headers=annotator_same_tenant)
    assert resp.status_code == 200
    assert [p["name"] for p in resp.json()] == ["alpha"]


def test_missing_auth_headers_returns_401(client: TestClient):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


# ─── Audit trail is written for every mutation ──────────────────


def test_audit_row_written_on_create(client: TestClient, admin_headers: dict, session_factory):
    from sqlalchemy import select
    from vulis_schemas import Base

    # Use a separate session to query audit_events (the request's session
    # has been closed by the time TestClient returns).
    create = client.post("/api/v1/projects", json={"name": "alpha"}, headers=admin_headers).json()

    with session_factory() as s:
        table = Base.metadata.tables["audit_events"]
        # Keep the Row objects (not .scalars() — we want the whole row).
        # Core-table Row objects support both _mapping["col_name"] and
        # _mapping attribute access.
        rows = list(s.execute(select(table)))
    actions = [r._mapping["action"] for r in rows]
    assert "project.create" in actions
    matching = [r for r in rows if r.action == "project.create"]
    assert matching[0].target_id == create["id"]
    assert matching[0].actor == admin_headers["X-Actor"]
