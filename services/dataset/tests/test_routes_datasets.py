"""Integration tests for the Dataset CRUD routes."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_dataset(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "project_id": "project_test",
        "name": "alpha",
        "task_kind": "DETECTION",
        "description": "first dataset",
        "metadata": {"plant": "Lyon"},
    }
    body.update(overrides)
    resp = client.post("/api/v1/datasets", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── Happy path ────────────────────────────────────────────────


def test_create_dataset_returns_201(client: TestClient, admin_headers: dict):
    body = _create_dataset(client, admin_headers)
    assert body["name"] == "alpha"
    assert body["project_id"] == "project_test"
    assert body["task_kind"] == "DETECTION"
    assert body["description"] == "first dataset"
    assert body["metadata"] == {"plant": "Lyon"}
    assert body["deleted_at"] is None


def test_list_datasets_empty(client: TestClient, admin_headers: dict):
    resp = client.get("/api/v1/datasets", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_then_list(client: TestClient, admin_headers: dict):
    _create_dataset(client, admin_headers, name="a")
    _create_dataset(client, admin_headers, name="b")
    resp = client.get("/api/v1/datasets", headers=admin_headers)
    assert resp.status_code == 200
    assert {d["name"] for d in resp.json()} == {"a", "b"}


def test_get_dataset(client: TestClient, admin_headers: dict):
    created = _create_dataset(client, admin_headers)
    resp = client.get(f"/api/v1/datasets/{created['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_unknown_dataset_returns_404(client: TestClient, admin_headers: dict):
    resp = client.get("/api/v1/datasets/ds_doesnotexist", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_filter_datasets_by_project(client: TestClient, admin_headers: dict):
    _create_dataset(client, admin_headers, name="x")
    resp = client.get(
        "/api/v1/datasets",
        params={"project_id": "project_test"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_patch_dataset(client: TestClient, admin_headers: dict):
    created = _create_dataset(client, admin_headers)
    resp = client.patch(
        f"/api/v1/datasets/{created['id']}",
        json={"description": "new", "metadata": {"k": "v"}},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["description"] == "new"
    assert body["metadata"] == {"k": "v"}
    # Unchanged fields stay.
    assert body["name"] == "alpha"


def test_delete_dataset_is_soft(client: TestClient, admin_headers: dict):
    created = _create_dataset(client, admin_headers)
    did = created["id"]
    resp = client.delete(f"/api/v1/datasets/{did}", headers=admin_headers)
    assert resp.status_code == 204
    # Soft-deleted = hidden from list/get.
    assert client.get(f"/api/v1/datasets/{did}", headers=admin_headers).status_code == 404
    assert client.get("/api/v1/datasets", headers=admin_headers).json() == []


# ─── Missing project → 404 ────────────────────────────────────


def test_create_dataset_with_unknown_project_returns_404(client: TestClient, admin_headers: dict):
    resp = client.post(
        "/api/v1/datasets",
        json={
            "project_id": "proj_doesnotexist",
            "name": "x",
            "task_kind": "DETECTION",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ─── RBAC ──────────────────────────────────────────────────────


def test_annotator_cannot_create_dataset(client: TestClient, annotator_headers: dict):
    resp = client.post(
        "/api/v1/datasets",
        json={"project_id": "project_test", "name": "x", "task_kind": "DETECTION"},
        headers=annotator_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_annotator_can_list_datasets(
    client: TestClient, admin_headers: dict, annotator_headers: dict
):
    _create_dataset(client, admin_headers)
    resp = client.get("/api/v1/datasets", headers=annotator_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_missing_auth_headers_returns_401(client: TestClient):
    resp = client.get("/api/v1/datasets")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


# ─── Cross-tenant isolation ────────────────────────────────────


def test_other_tenant_cannot_see_dataset(client: TestClient):
    from conftest import make_headers

    alice = make_headers(roles=["data-scientist"], tenant="tenant_test")
    bob = make_headers(roles=["data-scientist"], tenant="tenant_bob")
    created = _create_dataset(client, alice)
    did = created["id"]
    # Bob's list is empty.
    assert client.get("/api/v1/datasets", headers=bob).json() == []
    # Bob can't see Alice's dataset directly.
    assert client.get(f"/api/v1/datasets/{did}", headers=bob).status_code == 404


# ─── Audit trail ───────────────────────────────────────────────


def test_audit_row_written_on_create(client: TestClient, admin_headers: dict, session_factory):
    from sqlalchemy import select
    from vulis_schemas import Base

    created = _create_dataset(client, admin_headers)
    with session_factory() as s:
        table = Base.metadata.tables["audit_events"]
        rows = list(s.execute(select(table)))
    actions = [r._mapping["action"] for r in rows]
    assert "dataset.create" in actions
    matching = [r for r in rows if r.action == "dataset.create"]
    assert matching[0].target_id == created["id"]
    assert matching[0].actor == admin_headers["X-Actor"]
