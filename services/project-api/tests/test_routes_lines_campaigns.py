"""Lightweight tests for the Line + Campaign sub-resources."""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

from fastapi.testclient import TestClient


def _project(client: TestClient, headers: dict) -> str:
    return client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]


# ─── Lines ─────────────────────────────────────────────────────


def test_create_line(client: TestClient, admin_headers: dict):
    pid = _project(client, admin_headers)
    resp = client.post(
        f"/api/v1/projects/{pid}/lines",
        json={"name": "L1", "edge_ids": ["edge_a", "edge_b"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "L1"
    assert body["edge_ids"] == ["edge_a", "edge_b"]
    assert body["project_id"] == pid


def test_list_lines(client: TestClient, admin_headers: dict):
    pid = _project(client, admin_headers)
    for n in ("L1", "L2"):
        client.post(f"/api/v1/projects/{pid}/lines", json={"name": n}, headers=admin_headers)
    resp = client.get(f"/api/v1/projects/{pid}/lines", headers=admin_headers)
    assert resp.status_code == 200
    assert {line["name"] for line in resp.json()} == {"L1", "L2"}


def test_line_under_unknown_project_returns_404(client: TestClient, admin_headers: dict):
    resp = client.post(
        "/api/v1/projects/proj_unknown/lines",
        json={"name": "L1"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_annotator_can_list_lines_but_not_create(
    client: TestClient, admin_headers: dict, annotator_headers: dict
):
    from conftest import make_headers

    # Same tenant as admin so the annotator can see the project.
    annotator_same_tenant = make_headers(roles=["annotator"], tenant=admin_headers["X-Tenant-Id"])
    pid = _project(client, admin_headers)
    client.post(f"/api/v1/projects/{pid}/lines", json={"name": "L1"}, headers=admin_headers)
    # Annotator can list (same tenant)
    assert (
        client.get(f"/api/v1/projects/{pid}/lines", headers=annotator_same_tenant).status_code
        == 200
    )
    # But not create
    resp = client.post(
        f"/api/v1/projects/{pid}/lines", json={"name": "L2"}, headers=annotator_headers
    )
    assert resp.status_code == 403


# ─── Campaigns ─────────────────────────────────────────────────


def test_create_campaign(client: TestClient, admin_headers: dict):
    pid = _project(client, admin_headers)
    resp = client.post(
        f"/api/v1/projects/{pid}/campaigns",
        json={"name": "Q3-pilot", "kind": "pilot", "description": "Lyon plant"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Q3-pilot"
    assert body["kind"] == "pilot"
    assert body["description"] == "Lyon plant"


def test_list_campaigns(client: TestClient, admin_headers: dict):
    pid = _project(client, admin_headers)
    for k in ("data_collection", "validation", "pilot", "ab"):
        client.post(
            f"/api/v1/projects/{pid}/campaigns",
            json={"name": f"camp-{k}", "kind": k},
            headers=admin_headers,
        )
    resp = client.get(f"/api/v1/projects/{pid}/campaigns", headers=admin_headers)
    assert resp.status_code == 200
    kinds = {c["kind"] for c in resp.json()}
    assert kinds == {"data_collection", "validation", "pilot", "ab"}
