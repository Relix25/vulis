"""Integration tests for the ModelVersion routes.

Covers:
* Upload happy path (multipart ONNX file → ModelVersion + ONNX specs).
* Upload failure modes (non-ONNX bytes, missing file).
* Promote lifecycle (full DRAFT → ... → DEPLOYED walk).
* Promote RBAC per verb.
* Card + artifact GET.
* Cross-tenant isolation.
* Audit trail.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import onnx
from fastapi.testclient import TestClient


def _make_model(client: TestClient, headers: dict, name: str = "alpha") -> dict:
    resp = client.post(
        "/api/v1/models",
        json={"project_id": "project_test", "name": name, "task_kind": "DETECTION"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _minimal_onnx_bytes() -> bytes:
    """Build a minimal Add(a, b) -> y ONNX model and return its bytes."""
    a = onnx.helper.make_tensor_value_info("a", onnx.TensorProto.FLOAT, [1, 3])
    b = onnx.helper.make_tensor_value_info("b", onnx.TensorProto.FLOAT, [1, 3])
    y = onnx.helper.make_tensor_value_info("y", onnx.TensorProto.FLOAT, [1, 3])
    add_node = onnx.helper.make_node("Add", inputs=["a", "b"], outputs=["y"])
    graph = onnx.helper.make_graph(nodes=[add_node], name="add", inputs=[a, b], outputs=[y])
    opset = onnx.helper.make_opsetid("", 17)
    model = onnx.helper.make_model(graph, opset_imports=[opset])
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _upload_version(
    client: TestClient,
    headers: dict,
    model_id: str,
    *,
    file_bytes: bytes | None = None,
    filename: str = "model.onnx",
    version: str = "0.0.1",
    **form_fields,
) -> dict:
    if file_bytes is None:
        file_bytes = _minimal_onnx_bytes()
    return client.post(
        f"/api/v1/models/{model_id}/versions:upload",
        files={"file": (filename, file_bytes, "application/octet-stream")},
        data={"version": version, "created_by": "alice", **form_fields},
        headers=headers,
    )


# ─── Upload happy path ────────────────────────────────────────


def test_upload_version_returns_201(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    resp = _upload_version(client, admin_headers, m["id"])
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["major"] == 0 and body["minor"] == 0 and body["patch"] == 1
    assert body["status"] == "DRAFT"
    assert body["artifact_key"].startswith("sha256/")
    assert len(body["artifact_digest"]) == 64
    assert body["artifact_size_bytes"] > 0
    assert body["onnx_opset"] == 17
    assert body["model_card"] is not None
    # Card is auto-generated Markdown.
    assert "# " in body["model_card"]


def test_upload_creates_onnx_specs(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    # List the specs.
    resp = client.get(f"/api/v1/models/{m['id']}/versions/{v['id']}/specs", headers=admin_headers)
    assert resp.status_code == 200
    specs = resp.json()
    assert len(specs) == 3  # 2 inputs + 1 output
    directions = sorted(s["direction"] for s in specs)
    assert directions == ["input", "input", "output"]
    names = {s["name"] for s in specs}
    assert names == {"a", "b", "y"}


def test_upload_with_dataset_link_validates_dataset(
    client: TestClient, admin_headers: dict, session_factory
):
    from vulis_dataset.models import Dataset, DatasetVersion

    # Seed a DatasetVersion in the same tenant.
    with session_factory() as s:
        d = Dataset(
            tenant_id="tenant_test",
            project_id="project_test",
            name="ds",
            task_kind="DETECTION",
        )
        s.add(d)
        s.flush()
        dv = DatasetVersion(
            tenant_id="tenant_test",
            dataset_id=d.id,
            major=0,
            minor=0,
            patch=1,
            created_by="alice",
        )
        s.add(dv)
        s.commit()
        dvid = dv.id

    m = _make_model(client, admin_headers)
    resp = _upload_version(
        client,
        admin_headers,
        m["id"],
        trained_on_dataset_version_id=dvid,
    )
    assert resp.status_code == 201
    assert resp.json()["trained_on_dataset_version_id"] == dvid


def test_upload_with_unknown_dataset_returns_404(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    resp = _upload_version(
        client,
        admin_headers,
        m["id"],
        trained_on_dataset_version_id="dsv_doesnotexist",
    )
    assert resp.status_code == 404


# ─── Upload error cases ───────────────────────────────────────


def test_upload_non_onnx_returns_422(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    resp = _upload_version(
        client, admin_headers, m["id"], file_bytes=b"definitely not an ONNX file"
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION"


def test_upload_empty_file_returns_422(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    resp = _upload_version(client, admin_headers, m["id"], file_bytes=b"")
    assert resp.status_code == 422


def test_upload_duplicate_version_returns_409(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    _upload_version(client, admin_headers, m["id"], version="1.2.3")
    resp = _upload_version(client, admin_headers, m["id"], version="1.2.3")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ALREADY_EXISTS"


# ─── Get / list versions ──────────────────────────────────────


def test_list_versions(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    _upload_version(client, admin_headers, m["id"], version="0.0.1")
    _upload_version(client, admin_headers, m["id"], version="0.0.2")
    resp = client.get(f"/api/v1/models/{m['id']}/versions", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_version(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    resp = client.get(f"/api/v1/models/{m['id']}/versions/{v['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == v["id"]


# ─── Promote (state machine + RBAC) ───────────────────────────


def _promote(client: TestClient, headers: dict, m_id: str, v_id: str, verb: str):
    return client.post(
        f"/api/v1/models/{m_id}/versions/{v_id}:promote",
        json={"verb": verb},
        headers=headers,
    )


def test_full_lifecycle_to_deployed(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()

    assert (
        _promote(client, admin_headers, m["id"], v["id"], "submit_for_review").json()["status"]
        == "INTERNAL_REVIEW"
    )
    assert (
        _promote(client, admin_headers, m["id"], v["id"], "approve").json()["status"] == "STAGING"
    )
    assert (
        _promote(client, admin_headers, m["id"], v["id"], "approve").json()["status"] == "APPROVED"
    )
    assert (
        _promote(client, admin_headers, m["id"], v["id"], "deploy").json()["status"] == "DEPLOYED"
    )


def test_reject_in_internal_review(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    _promote(client, admin_headers, m["id"], v["id"], "submit_for_review")
    resp = _promote(client, admin_headers, m["id"], v["id"], "reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


def test_reject_in_staging_goes_back_to_draft(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    _promote(client, admin_headers, m["id"], v["id"], "submit_for_review")
    _promote(client, admin_headers, m["id"], v["id"], "approve")
    resp = _promote(client, admin_headers, m["id"], v["id"], "reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "DRAFT"


def test_invalid_transition_returns_409(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    # Can't deploy from DRAFT.
    resp = _promote(client, admin_headers, m["id"], v["id"], "deploy")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "INVALID_TRANSITION"


def test_unknown_verb_returns_422(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    resp = _promote(client, admin_headers, m["id"], v["id"], "frobnicate")
    assert resp.status_code == 422


def test_data_scientist_can_submit_and_review_cannot_deploy(
    client: TestClient,
    admin_headers: dict,
    data_scientist_headers: dict,
    reviewer_headers: dict,
    operator_headers: dict,
):
    from conftest import make_headers

    # Reviewer + operator must share the tenant.
    reviewer_same_tenant = make_headers(roles=["reviewer"], tenant=admin_headers["X-Tenant-Id"])
    operator_same_tenant = make_headers(roles=["operator"], tenant=admin_headers["X-Tenant-Id"])
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    # Data-scientist: submit_for_review OK.
    assert (
        _promote(client, data_scientist_headers, m["id"], v["id"], "submit_for_review").status_code
        == 200
    )
    # Data-scientist: approve → 403.
    assert _promote(client, data_scientist_headers, m["id"], v["id"], "approve").status_code == 403
    # Reviewer: approve (INTERNAL_REVIEW → STAGING).
    assert _promote(client, reviewer_same_tenant, m["id"], v["id"], "approve").status_code == 200
    # Reviewer: approve again (STAGING → APPROVED).
    assert _promote(client, reviewer_same_tenant, m["id"], v["id"], "approve").status_code == 200
    # Reviewer: deploy → 403 (operator only).
    assert _promote(client, reviewer_same_tenant, m["id"], v["id"], "deploy").status_code == 403
    # Operator: deploy OK (APPROVED → DEPLOYED).
    assert _promote(client, operator_same_tenant, m["id"], v["id"], "deploy").status_code == 200


def test_archive_requires_admin(
    client: TestClient, admin_headers: dict, data_scientist_headers: dict
):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    # Data-scientist: archive → 403.
    assert _promote(client, data_scientist_headers, m["id"], v["id"], "archive").status_code == 403
    # Admin: archive OK.
    assert _promote(client, admin_headers, m["id"], v["id"], "archive").status_code == 200


def test_promote_audit_written(client: TestClient, admin_headers: dict, session_factory):
    from sqlalchemy import select
    from vulis_schemas import Base

    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    _promote(client, admin_headers, m["id"], v["id"], "submit_for_review")

    with session_factory() as s:
        table = Base.metadata.tables["audit_events"]
        rows = list(s.execute(select(table).where(table.c.target_id == v["id"])))
    actions = [r._mapping["action"] for r in rows]
    assert "model_version.upload" in actions
    assert "model_version.promote" in actions


# ─── Card ──────────────────────────────────────────────────────


def test_get_card_returns_markdown(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    resp = client.get(f"/api/v1/models/{m['id']}/versions/{v['id']}/card", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    body = resp.text
    assert "# " in body
    assert v["id"] in body
    assert "Inputs" in body
    assert "Outputs" in body
    assert "DRAFT" in body


# ─── Artifact ──────────────────────────────────────────────────


def test_get_artifact_returns_onnx_bytes(client: TestClient, admin_headers: dict):
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    resp = client.get(
        f"/api/v1/models/{m['id']}/versions/{v['id']}/artifact", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    # Round-trip the bytes through onnx — they should still parse.
    parsed = onnx.load_from_string(resp.content)
    assert parsed.graph.node[0].op_type == "Add"
    # Digest header matches.
    assert resp.headers["x-content-sha256"] == v["artifact_digest"]


# ─── Cross-tenant isolation ────────────────────────────────────


def test_other_tenant_cannot_see_version(client: TestClient, admin_headers: dict):
    from conftest import make_headers

    bob = make_headers(roles=["data-scientist"], tenant="tenant_bob")
    m = _make_model(client, admin_headers)
    v = _upload_version(client, admin_headers, m["id"]).json()
    assert (
        client.get(f"/api/v1/models/{m['id']}/versions/{v['id']}", headers=bob).status_code == 404
    )
    # And Bob can't see the model itself.
    assert client.get(f"/api/v1/models/{m['id']}", headers=bob).status_code == 404
