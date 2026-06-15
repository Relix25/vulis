"""Integration tests for the async import flow.

The tests use ``asyncio`` to wait for the worker to complete. We
register an asyncio Event per job via ``importers.import_done_event``
and wait on it from the test.
"""

# SPDX-FileCopyrightText: 2026 Vulis Project Contributors
# SPDX-License-Identifier: LicenseRef-Vulis-BSL-1.1

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _create_dataset_and_version(client: TestClient, headers: dict) -> dict:
    ds = client.post(
        "/api/v1/datasets",
        json={"project_id": "project_test", "name": "ds", "task_kind": "DETECTION"},
        headers=headers,
    ).json()
    v = client.post(
        f"/api/v1/datasets/{ds['id']}/versions",
        json={"created_by": "alice", "version": "0.0.1"},
        headers=headers,
    ).json()
    return {"dataset": ds, "version": v}


async def _wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> None:
    """Poll the job status endpoint until it reaches DONE/FAILED.

    This is simpler than a cross-loop event bridge: we hit a regular
    FastAPI endpoint from the test's event loop and wait until the
    worker has finished mutating the DB row. The polling cost is
    negligible at this scale.
    """
    slice_s = 0.05
    waited = 0.0
    admin = {"X-Tenant-Id": "tenant_test", "X-Actor": "admin", "X-Roles": "admin"}
    while waited < timeout:
        resp = client.get(f"/api/v1/import-jobs/{job_id}", headers=admin)
        if resp.status_code == 200:
            status = resp.json()["status"]
            if status in ("DONE", "FAILED"):
                return
        await asyncio.sleep(slice_s)
        waited += slice_s
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


def _run_async(coro):
    """Run an async coroutine to completion."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── LOCAL import happy path ──────────────────────────────────


def test_local_import_creates_samples(client: TestClient, admin_headers: dict, tmp_path: Path):
    # Create a temp directory with a few sample files.
    src = tmp_path / "raw"
    (src / "train").mkdir(parents=True)
    (src / "val").mkdir(parents=True)
    (src / "train" / "a.png").write_bytes(b"img-a-bytes")
    (src / "train" / "b.png").write_bytes(b"img-b-bytes")
    (src / "val" / "c.png").write_bytes(b"img-c-bytes")
    # A non-image file — should be skipped by the extension filter.
    (src / "train" / "README.txt").write_text("not an image")

    info = _create_dataset_and_version(client, admin_headers)
    ds = info["dataset"]
    v = info["version"]

    with TestClient(client.app) as sync_client:
        resp = sync_client.post(
            f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/import",
            json={
                "source_kind": "LOCAL",
                "source_descriptor": {"path": str(src)},
            },
            headers=admin_headers,
        )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    # The worker was scheduled by the request; wait for it to complete.
    _run_async(_wait_for_job(client, job_id))

    # Poll the job — it should be DONE with 3 samples.
    resp = client.get(f"/api/v1/import-jobs/{job_id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DONE", body
    assert body["total_samples"] == 3
    assert body["processed_samples"] == 3
    assert body["error_message"] is None

    # Verify samples exist + are content-addressed.
    from sqlalchemy import select

    from vulis_dataset.models import Sample

    with client.app.state.db_sessionmaker() as s:
        samples = list(s.execute(select(Sample).where(Sample.version_id == v["id"])).scalars())
    assert len(samples) == 3
    # Every sample's blob_key is content-addressed.
    for s in samples:
        assert s.blob_key.startswith("sha256/")
        assert s.blob_digest
    # The text file should have been filtered out.
    paths = {s.relative_path for s in samples}
    assert "train/README.txt" not in paths
    assert "train/a.png" in paths


# ─── ZIP import ───────────────────────────────────────────────


def test_zip_import_creates_samples(client: TestClient, admin_headers: dict, tmp_path: Path):
    # Build a ZIP in memory.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("train/x.png", b"x-bytes")
        zf.writestr("train/y.png", b"y-bytes")
        zf.writestr("README.txt", b"should-be-skipped")
    zip_bytes = buf.getvalue()

    # Pre-upload the ZIP to the storage backend.
    storage = client.app.state.storage
    zip_key = storage.put_blob(zip_bytes)

    info = _create_dataset_and_version(client, admin_headers)
    ds = info["dataset"]
    v = info["version"]

    with TestClient(client.app) as sync_client:
        resp = sync_client.post(
            f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/import",
            json={
                "source_kind": "ZIP",
                "source_descriptor": {"blob_key": zip_key},
            },
            headers=admin_headers,
        )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    _run_async(_wait_for_job(client, job_id))

    resp = client.get(f"/api/v1/import-jobs/{job_id}", headers=admin_headers)
    body = resp.json()
    assert body["status"] == "DONE", body
    assert body["total_samples"] == 2
    assert body["processed_samples"] == 2


# ─── Error cases ──────────────────────────────────────────────


def test_local_import_with_missing_path_422(client: TestClient, admin_headers: dict):
    info = _create_dataset_and_version(client, admin_headers)
    resp = client.post(
        f"/api/v1/datasets/{info['dataset']['id']}/versions/{info['version']['id']}/import",
        json={"source_kind": "LOCAL", "source_descriptor": {}},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_zip_import_without_blob_key_422(client: TestClient, admin_headers: dict):
    info = _create_dataset_and_version(client, admin_headers)
    resp = client.post(
        f"/api/v1/datasets/{info['dataset']['id']}/versions/{info['version']['id']}/import",
        json={"source_kind": "ZIP", "source_descriptor": {}},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_local_import_nonexistent_path_fails_job(
    client: TestClient, admin_headers: dict, tmp_path: Path
):
    info = _create_dataset_and_version(client, admin_headers)

    with TestClient(client.app) as sync_client:
        resp = sync_client.post(
            f"/api/v1/datasets/{info['dataset']['id']}/versions/{info['version']['id']}/import",
            json={
                "source_kind": "LOCAL",
                "source_descriptor": {"path": str(tmp_path / "does_not_exist")},
            },
            headers=admin_headers,
        )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _run_async(_wait_for_job(client, job_id))

    resp = client.get(f"/api/v1/import-jobs/{job_id}", headers=admin_headers)
    body = resp.json()
    assert body["status"] == "FAILED"
    assert "does not exist" in body["error_message"]


def test_import_into_published_version_422(client: TestClient, admin_headers: dict):
    from vulis_dataset.models import Sample

    info = _create_dataset_and_version(client, admin_headers)
    ds = info["dataset"]
    v = info["version"]
    # Add a sample + publish.
    with client.app.state.db_sessionmaker() as s:
        s.add(
            Sample(
                tenant_id=admin_headers["X-Tenant-Id"],
                version_id=v["id"],
                blob_key="sha256/x",
                relative_path="a.png",
                size_bytes=1,
                blob_digest="x",
            )
        )
        s.commit()
    client.post(f"/api/v1/datasets/{ds['id']}/versions/{v['id']}:publish", headers=admin_headers)
    resp = client.post(
        f"/api/v1/datasets/{ds['id']}/versions/{v['id']}/import",
        json={"source_kind": "LOCAL", "source_descriptor": {"path": "/tmp/anything"}},
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ─── Job visibility ────────────────────────────────────────────


def test_get_unknown_job_returns_404(client: TestClient, admin_headers: dict):
    resp = client.get("/api/v1/import-jobs/job_doesnotexist", headers=admin_headers)
    assert resp.status_code == 404


def test_other_tenant_cannot_see_job(client: TestClient, admin_headers: dict, tmp_path: Path):
    from conftest import make_headers

    info = _create_dataset_and_version(client, admin_headers)
    with TestClient(client.app) as sync_client:
        resp = sync_client.post(
            f"/api/v1/datasets/{info['dataset']['id']}/versions/{info['version']['id']}/import",
            json={
                "source_kind": "LOCAL",
                "source_descriptor": {"path": str(tmp_path)},
            },
            headers=admin_headers,
        )
    job_id = resp.json()["job_id"]
    _run_async(_wait_for_job(client, job_id))

    # Another tenant can't see this job.
    other = make_headers(roles=["admin"], tenant="tenant_bob")
    resp = client.get(f"/api/v1/import-jobs/{job_id}", headers=other)
    assert resp.status_code == 404
